"""runner — deterministic conductor (NO LLM orchestrator), bare_v12 skill tooling."""

import argparse
import asyncio
import re
import sys
from pathlib import Path

from factory.infra.control import TEMP_DIR, RUNTIME_DIR, USER_PROMPT_PATH, REPO_ROOT  # noqa: F401
from factory.infra.ledger import inject_repo_map
from factory.infra.exchange import (
    TeeLogger, update_status_board, load_exchange, save_exchange,
    ExchangeTurn
)
from factory.infra.state import fresh_state, load_state, reset_stale_in_progress
import factory.infra._runtime as runtime

# These will be created in subsequent prompts
from factory.infra.pipeline import (
    do_role, record_coder, run_gated, _assert_plan_gate_ok,
    run_code_review_gate, run_red_team_gate, _recover_from_unexpected_behavior,
)
from pydantic_ai.exceptions import UnexpectedModelBehavior
from factory.infra.agent import (
    _configure_logfire, load_skill,
)
from factory.infra.models import TaskBatch

# Re-exports for backward compatibility with test imports
from factory.common.operator import log_operator  # noqa: F401
from factory.common.md_bridge import build_md_bridge  # noqa: F401
from factory.infra.context import (  # noqa: F401
    stage_path, staged_zero_diff, _write_harness_patches,
    TASK_TOKEN_THRESHOLD, _real_source_paths,
)
from factory.infra.validation import (  # noqa: F401
    red_team_passed, check_plan_invariants, MAX_RETRIES,
    _feedback_from_review_findings, _blocker_findings_from_risks,
    _feedback_from_audit,
)
from factory.infra.execution import (  # noqa: F401
    run_execute_phase, CODER_VALIDATION_PASSES, DAG_DEADLOCK_TIMEOUT,
)
from factory.infra.agent import (  # noqa: F401
    build_role_agent, _run_agent_retry, load_skill, _coder_agent_id,
)
from factory.infra.artefacts import persist_role  # noqa: F401
from factory.infra._runtime import RAW_OUTPUTS, SCOPE_CONTEXT, _PHASE_ORDER  # noqa: F401
import subprocess  # noqa: F401

RESUME_RE = re.compile(r"^Resume:\s*(true|false)\s*$", re.IGNORECASE)


def read_prompt(prompt_file: Path) -> tuple[bool, str, list[str], str | None, str | None]:
    """Parse the user prompt with an optional YAML front-matter block."""
    if not prompt_file.exists():
        return False, "Create a python script that prints 'This Harness is Working'", [], None, None

    text = prompt_file.read_text()
    lines = text.splitlines()
    scope: list[str] = []
    task_body = text.strip()
    start_phase: str | None = None
    stop_phase: str | None = None

    if lines and lines[0].strip() == "---":
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break
        if end_idx is None:
            raise SystemExit(f"[HALT] {prompt_file} has an opening '---' front-matter fence but no closing '---'.")
        try:
            import yaml
            fm_text = "\n".join(lines[1:end_idx])
            front = yaml.safe_load(fm_text) or {}
        except Exception as e:
            raise SystemExit(f"[HALT] {prompt_file} front-matter YAML parse failed: {e}")
        if not isinstance(front, dict):
            raise SystemExit(f"[HALT] {prompt_file} front-matter must be a YAML mapping.")
        resume_raw = str(front.get("Resume", "false")).strip().lower()
        if resume_raw not in ("true", "false"):
            raise SystemExit(f"[HALT] {prompt_file} Resume: must be 'true' or 'false' (got: {front.get('Resume')!r}).")
        resume = resume_raw == "true"
        raw_scope = front.get("scope", []) or []
        if isinstance(raw_scope, str):
            raw_scope = [raw_scope]
        if not isinstance(raw_scope, list):
            raise SystemExit(f"[HALT] {prompt_file} scope: must be a YAML list of paths.")
        scope = [str(s) for s in raw_scope]

        raw_start = front.get("start_phase")
        if raw_start is not None:
            start_phase = str(raw_start).strip()
            if start_phase not in runtime._PHASE_ORDER:
                raise SystemExit(f"[HALT] {prompt_file} start_phase must be one of {runtime._PHASE_ORDER} (got: {start_phase!r}).")
        raw_stop = front.get("stop_phase")
        if raw_stop is not None:
            stop_phase = str(raw_stop).strip()
            if stop_phase not in runtime._PHASE_ORDER:
                raise SystemExit(f"[HALT] {prompt_file} stop_phase must be one of {runtime._PHASE_ORDER} (got: {stop_phase!r}).")

        task_body = "\n".join(lines[end_idx + 1 :]).strip()
    else:
        m = RESUME_RE.match(lines[0]) if lines else None
        if not m:
            raise SystemExit(f"[HALT] {prompt_file} first line must be a YAML '---' front-matter block or a strict 'Resume: True|False' line.")
        resume = m.group(1).lower() == "true"
        task_body = "\n".join(ln for ln in lines[1:] if not re.match(r"^bd:[ \t]*[A-Za-z0-9_-]+", ln)).strip()

    if not task_body:
        raise SystemExit(f"[HALT] {prompt_file} has no task spec body.")
    return resume, task_body, scope, start_phase, stop_phase


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bd", default="default", help="bd ticket id (keys the exchange file)")
    ap.add_argument("--prompt-file", default=str(USER_PROMPT_PATH))
    ap.add_argument("--from", dest="from_", choices=runtime._PHASE_ORDER, default=None)
    ap.add_argument("--stop-after", dest="stop_after", choices=runtime._PHASE_ORDER, default=None)
    ap.add_argument("--resume", dest="resume_flag", action="store_true", default=False)
    args = ap.parse_args()

    resume, task, scope, start_phase, stop_phase = read_prompt(Path(args.prompt_file))
    bd = args.bd

    _cli_from = args.from_
    _cli_resume = args.resume_flag

    if start_phase is not None:
        args.from_ = start_phase
    if stop_phase is not None:
        args.stop_after = stop_phase

    if args.from_:
        runtime._SKIPPED_PHASES = runtime._PHASE_ORDER[: runtime._PHASE_ORDER.index(args.from_)]

    if scope:
        runtime.SCOPE_CONTEXT = inject_repo_map(scope)
    else:
        runtime.SCOPE_CONTEXT = ""

    from factory.infra.tools import wrap_untrusted_task
    task = wrap_untrusted_task(task)

    _configure_logfire()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    sys.stdout = TeeLogger(RUNTIME_DIR / "run.log")

    _start_role = args.from_ if args.from_ else "planner"
    update_status_board([], _start_role, bd)

    print("=== ORCHESTRATOR RUN (deterministic conductor, no LLM orchestrator) ===")
    print(f"[resume] {resume}  [bd] {bd}")

    prior = load_exchange(bd) if (resume or args.from_ == "coder") else []
    history: list[tuple[str, str]] = []
    exchange: list[ExchangeTurn] = []
    pass_counter: dict[str, int] = {}
    batch: TaskBatch | None = None

    _continuation = bool(_cli_from or _cli_resume)
    if _continuation:
        st = load_state(bd)
        if st is None:
            raise RuntimeError("[HALT] no prior state for continuation.")
        st = reset_stale_in_progress(st)
        if st.draft:
            history.append(("planner", st.draft.model_dump_json()))
        if st.approved:
            history.append(("supervisor_plan", st.approved.model_dump_json()))
            runtime.RAW_OUTPUTS["supervisor_plan"] = st.approved.model_dump_json()
            runtime.PHASE_SUMMARIES["supervisor_plan"] = st.approved.model_dump_json()
        if st.batch:
            history.append(("coder", st.batch.model_dump_json()))
        if st.code_passed:
            history.append(("supervisor_review", st.code_passed.model_dump_json()))
        if st.audit:
            history.append(("red_team", st.audit.model_dump_json()))
    else:
        st = fresh_state(bd, global_alignment="")

    # Planning gate
    _coder_idx = runtime._PHASE_ORDER.index("coder")
    _from_idx = runtime._PHASE_ORDER.index(args.from_) if args.from_ else 0

    if args.from_ and _from_idx >= _coder_idx:
        print(f"\n=== [conductor] --from {args.from_}: SKIPPING planner/supervisor_plan ===", flush=True)
        plan = None
        batch = None
    else:
        is_forced_pass = await run_gated("planner", "supervisor_plan", task, bd, history, exchange, pass_counter, prior, {"brief": task, "seeded": False})
        plan = _assert_plan_gate_ok(history, bd, st=st, is_forced_pass=is_forced_pass)
        if plan is None:
            return  # Checkpoint stop

    approved_json = runtime.RAW_OUTPUTS.get("supervisor_plan") or next((v for r, v in reversed(history) if r == "supervisor_plan"), None)
    if args.from_ and _from_idx >= _coder_idx and not approved_json:
        raise RuntimeError("[HALT] --from but no persisted ApprovedPlan found.")

    # Build closure wrappers so coder_fn matches execute_task's contract:
    #   coder_fn(brief: str, task_id: str | None = None) -> str
    # and reviewer_fn matches run_code_review_gate/run_red_team_gate's contract:
    #   reviewer_fn(brief: str) -> str
    coder_state = {"brief": task, "seeded": False}

    async def _coder_fn(brief: str, task_id: str | None = None) -> str:
        return await record_coder(brief, bd, history, prior, coder_state, task_id=task_id)

    async def _run_supervisor_review(brief: str) -> str:
        try:
            return await load_skill("supervisor_review", brief, bd)
        except UnexpectedModelBehavior as e:
            return _recover_from_unexpected_behavior("supervisor_review", e)

    async def _run_red_team_audit(brief: str) -> str:
        try:
            return await load_skill("red_team", brief, bd)
        except UnexpectedModelBehavior as e:
            return _recover_from_unexpected_behavior("red_team", e)

    # Code-review gate
    if plan is not None and plan.workplan and plan.workplan.groups:
        run_dir = TEMP_DIR / bd
        run_dir.mkdir(parents=True, exist_ok=True)
        batch = await run_code_review_gate(plan, run_dir, _coder_fn, _run_supervisor_review, exchange=exchange, pass_counter=pass_counter, bd=bd, history=history)
        history.append(("supervisor_review", batch.model_dump_json()))
    else:
        await run_gated("coder", "supervisor_review", task, bd, history, exchange, pass_counter, prior, {"brief": task, "seeded": False}, record_exchange=(args.from_ == "coder"))

    # Red-team gate
    if plan is not None and plan.workplan and plan.workplan.groups:
        run_dir = TEMP_DIR / bd
        batch = await run_red_team_gate(plan, run_dir, _coder_fn, _run_red_team_audit, {t.task_id: t for t in batch.results} if batch else {}, exchange=exchange, pass_counter=pass_counter, bd=bd, history=history)
        history.append(("red_team", batch.model_dump_json()))
    else:
        await run_gated("coder", "red_team", task, bd, history, exchange, pass_counter, prior, {"brief": task, "seeded": False}, hard=True, record_exchange=(args.from_ == "coder"))

    save_exchange(bd, exchange)

    if batch is not None and batch.results:
        all_done = all(r.status == "done" for r in batch.results)
        verdict = "PASS" if all_done else "CHECK"
    else:
        last_coder = next((v for r, v in reversed(history) if r == "coder"), "")
        verdict = "PASS" if "This Harness is Working" in last_coder else "CHECK"
    update_status_board(history, None, bd)
    print("\n=== PIPELINE COMPLETE (propose-only) ===")
    print("\nVERDICT:", verdict)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        import traceback as _tb
        _tb.print_exc()
        try:
            RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            _exc = _tb.format_exc()
            (RUNTIME_DIR / "fail_main.log").write_text(_exc, encoding="utf-8")
            with (RUNTIME_DIR / "run.log").open("a", encoding="utf-8") as _fh:
                _fh.write("\n=== [FATAL] unhandled exception ===\n")
                _fh.write(_exc)
        except Exception:
            pass
        raise
