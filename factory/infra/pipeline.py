"""Pipeline orchestration module containing all gate functions and the phase loop."""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml
from pydantic_ai.exceptions import UnexpectedModelBehavior

from factory.common import ROLE_OUTPUT_TYPE, OUTPUT_TYPE_REGISTRY
from factory.common.operator import log_operator
from factory.infra._runtime import (
    RAW_OUTPUTS, PHASE_SUMMARIES, _PHASE_ORDER,
)
from factory.infra.agent import (
    load_skill, _load_role_messages, _recover_role_output, _coder_agent_id,
)
from factory.infra.context import (
    stage_workspace_from_draft,
)
from factory.infra.control import (
    REPO_ROOT, MAX_AGENTS,
)
from factory.infra.execution import (
    run_execute_phase,
)
from factory.infra.exchange import (
    update_status_board, save_exchange,
    format_exchange, append_exchange_turn, _model_to_md, _render_verdict_block,
    _render_history_md,
    ExchangeTurn,
)
from factory.infra.models import (
    ApprovedPlan, ApprovedTask, AuditResult, CodePassed,
    DraftPlan, ExecutablePlan, GitResult, ReviewResult, TaskBatch, TaskResult, WorkGroup, ParallelisableWorkplan,
)
from factory.infra.output_sanitizer import (
    clean_role_output, extract_model_json, extract_tool_call_payload,
)
from factory.infra.state import save_state, record_phase
from factory.infra.tools import wrap_injected_context
from factory.infra.validation import (
    EXCHANGE_ROLES, REVIEW_PASS_FIELD, MAX_RETRIES, PLAN_INVARIANT_RETRIES,
    check_plan_invariants, _downstream_closure,
)

RESUME_RE = re.compile(r"^Resume:\s*(true|false)\s*$", re.IGNORECASE)


def read_prompt(prompt_file: Path) -> tuple[bool, str, list[str], str | None, str | None]:
    """Parse the user prompt with an optional YAML front-matter block.

    Returns ``(resume_flag, task_spec, scope, start_phase, stop_phase)``.

    Format::

        ---
        Resume: false
        bd: baziforecaster-hbh1
        start_phase: planner
        stop_phase: supervisor_plan
        scope:
          - src2/core/schemas/unified.py
          - src2/engine/
        ---
        # EPIC
        ...freeform markdown body...

    The front-matter is delimited by leading ``---`` / closing ``---``. If no
    front-matter is present the first line MUST be a strict ``Resume:
    True|False`` (legacy format) — fail loudly otherwise. ``scope`` is a
    context hint only (never wired to an ACL); defaults to ``[]`` when absent.
    ``start_phase`` / ``stop_phase`` control which pipeline segment runs:
    if set, they override CLI ``--from`` / ``--stop-after``.
    """
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
            raise SystemExit(
                f"[HALT] {prompt_file} has an opening '---' front-matter fence "
                f"but no closing '---'."
            )
        try:
            fm_text = "\n".join(lines[1:end_idx])
            front = yaml.safe_load(fm_text) or {}
        except Exception as e:
            raise SystemExit(f"[HALT] {prompt_file} front-matter YAML parse failed: {e}")
        if not isinstance(front, dict):
            raise SystemExit(
                f"[HALT] {prompt_file} front-matter must be a YAML mapping."
            )
        resume_raw = str(front.get("Resume", "false")).strip().lower()
        if resume_raw not in ("true", "false"):
            raise SystemExit(
                f"[HALT] {prompt_file} Resume: must be 'true' or 'false' "
                f"(got: {front.get('Resume')!r})."
            )
        resume = resume_raw == "true"
        raw_scope = front.get("scope", []) or []
        if isinstance(raw_scope, str):
            raw_scope = [raw_scope]
        if not isinstance(raw_scope, list):
            raise SystemExit(
                f"[HALT] {prompt_file} scope: must be a YAML list of paths."
            )
        scope = [str(s) for s in raw_scope]

        raw_start = front.get("start_phase")
        if raw_start is not None:
            start_phase = str(raw_start).strip()
            if start_phase not in _PHASE_ORDER:
                raise SystemExit(
                    f"[HALT] {prompt_file} start_phase must be one of "
                    f"{_PHASE_ORDER} (got: {start_phase!r})."
                )
        raw_stop = front.get("stop_phase")
        if raw_stop is not None:
            stop_phase = str(raw_stop).strip()
            if stop_phase not in _PHASE_ORDER:
                raise SystemExit(
                    f"[HALT] {prompt_file} stop_phase must be one of "
                    f"{_PHASE_ORDER} (got: {stop_phase!r})."
                )

        raw_target = front.get("target_repo")
        if raw_target is not None:
            os.environ["TARGET_REPO"] = str(raw_target).strip()

        task_body = "\n".join(lines[end_idx + 1:]).strip()
    else:
        m = RESUME_RE.match(lines[0]) if lines else None
        if not m:
            raise SystemExit(
                f"[HALT] {prompt_file} first line must be a YAML '---' front-matter "
                f"block (with Resume:/bd:/scope:) or a strict 'Resume: True|False' "
                f"line (got: {lines[0] if lines else '<empty>'})."
            )
        resume = m.group(1).lower() == "true"
        task_body = "\n".join(
            ln for ln in lines[1:] if not re.match(r"^bd:[ \t]*[A-Za-z0-9_-]+", ln)
        ).strip()

    if not task_body:
        raise SystemExit(f"[HALT] {prompt_file} has no task spec body.")
    return resume, task_body, scope, start_phase, stop_phase


def _recover_from_unexpected_behavior(
    role: str,
    e: UnexpectedModelBehavior,
    agent_id: str | None = None,
) -> str:
    """Recover structured output when the model hallucinates a tool call.

    Both `do_role` and `record_coder` share this path. Raises on unrecoverable.
    """
    real_messages = _load_role_messages(role, agent_id=agent_id)
    raw = extract_model_json(real_messages)
    if not raw:
        raw = extract_tool_call_payload(e) or ""
    if not raw:
        raise RuntimeError(
            f"[HALT] role {role!r} emitted no final_result call"
        ) from e
    recovered = _recover_role_output(raw, OUTPUT_TYPE_REGISTRY[ROLE_OUTPUT_TYPE[role]], role, None)
    if recovered is not None:
        if hasattr(recovered.output, "model_dump_json"):
            return recovered.output.model_dump_json()
        return str(recovered.output)
    raise RuntimeError(
        f"[{role}] role {role!r} hallucinated an unregistered tool "
        f"(pydantic_ai exhausted retries). Check {role}'s tool_allow_list "
        f"vs its prompt — do NOT instruct it to run commands it has no tool for."
    ) from e


async def do_role(
    role: str,
    task: str,
    bd: str,
    history: list[tuple[str, str]],
    exchange: list[ExchangeTurn],
    pass_counter: dict[str, int],
    prior: list[ExchangeTurn],
    state_dict: dict[str, Any]
) -> str:
    """Run one role, seed the first coder pass, append to history + exchange."""
    brief = state_dict["brief"]
    seeded = state_dict["seeded"]
    run_brief = brief
    if role == "coder" and prior and not seeded:
        run_brief = brief + "\n\n" + wrap_injected_context(
            format_exchange(prior), label="resumed_exchange"
        )
        state_dict["seeded"] = True

    update_status_board(history, role, bd)
    if role in ("planner", "supervisor_plan"):
        brief_to_use = run_brief
        for attempt in range(1, PLAN_INVARIANT_RETRIES + 1):
            try:
                out = await load_skill(role, brief_to_use, bd)
                violations = []
                if role == "planner":
                    draft = clean_role_output(out, DraftPlan)
                    violations = check_plan_invariants(draft) if draft else ["Plan is empty or malformed"]
                else:
                    plan_eval = clean_role_output(out, ApprovedPlan)
                    draft_json = RAW_OUTPUTS.get("planner")
                    draft = clean_role_output(draft_json, DraftPlan) if draft_json else None
                    if plan_eval and draft:
                        eval_map = {item.item_id: item for item in plan_eval.evaluations}
                        merged_tasks = []
                        for t in draft.subtasks:
                            eval_item = eval_map.get(t.id)
                            app_val = (eval_item.approved == "Yes") if eval_item else True
                            notes_val = eval_item.comments if eval_item else ""
                            merged_tasks.append(
                                ApprovedTask(
                                    id=t.id,
                                    title=t.title,
                                    file_paths=t.file_paths,
                                    instruction=t.instruction,
                                    acceptance=t.acceptance,
                                    tool_preference=t.tool_preference,
                                    evidence=t.evidence,
                                    approved=app_val,
                                    notes=notes_val,
                                )
                            )

                        groups_merged = []
                        for g in draft.strategy.parallelisable_workplan.groups:
                            group_tasks = []
                            for gt in g.tasks:
                                eval_item = eval_map.get(gt.id)
                                app_val = (eval_item.approved == "Yes") if eval_item else True
                                notes_val = eval_item.comments if eval_item else ""
                                group_tasks.append(
                                    ApprovedTask(
                                        id=gt.id,
                                        title=gt.title,
                                        file_paths=gt.file_paths,
                                        instruction=gt.instruction,
                                        acceptance=gt.acceptance,
                                        tool_preference=gt.tool_preference,
                                        evidence=gt.evidence,
                                        approved=app_val,
                                        notes=notes_val,
                                    )
                                )
                            groups_merged.append(
                                WorkGroup(
                                    id=g.id,
                                    depends_on=g.depends_on,
                                    tasks=group_tasks,
                                )
                            )
                        temp_plan = ExecutablePlan(
                            epic=draft.epic,
                            definition_of_done=draft.definition_of_done,
                            acceptance_criteria=draft.acceptance_criteria,
                            rubric_cube=draft.rubric_cube,
                            summary=draft.summary,
                            tasks=merged_tasks,
                            alignment=draft.summary,
                            workplan=ParallelisableWorkplan(groups=groups_merged),
                            rejected_subtasks=[],
                            strategy=draft.strategy,
                            approved=True,
                        )
                        violations = check_plan_invariants(temp_plan)
                    else:
                        violations = ["No plan evaluation or DraftPlan found to check invariants."]

                if violations:
                    raise RuntimeError(f"Plan invariant violations: {violations}")
                break
            except Exception as e:
                if attempt == PLAN_INVARIANT_RETRIES:
                    raise
                print(f"[gate] {role} attempt {attempt} failed: {e!r} -> replan", flush=True)
                brief_to_use = run_brief + f"\n\n[INVARIANT VIOLATION] Your previous plan was rejected: {e!r}. Please ensure every task lists exactly 1 file, and file paths are disjoint across all tasks."
                continue
    else:
        try:
            out = await load_skill(role, run_brief, bd)
        except UnexpectedModelBehavior as e:
            out = _recover_from_unexpected_behavior(role, e)

    out_md = PHASE_SUMMARIES.get(role, out)
    history.append((role, out_md))
    PHASE_SUMMARIES[role] = out_md
    print(f"\n--- {role} ---\n{out_md}", flush=True)
    update_status_board(history, role, bd)

    summaries_block = (
        "\n\n".join(f"## {r} summary (L3):\n{s}" for r, s in PHASE_SUMMARIES.items())
    ) if PHASE_SUMMARIES else ""
    state_dict["brief"] = task + "\n\n" + wrap_injected_context(
        "\n\n".join(
            f"## {r} output:\n{_render_history_md(r, v)}"
            for r, v in history
        ),
        label="prior_role_outputs",
    )
    if summaries_block:
        state_dict["brief"] += "\n\n" + wrap_injected_context(summaries_block, label="phase_summaries")
    return out


async def record_coder(
    brief: str,
    bd: str,
    history: list[tuple[str, str]],
    prior: list[ExchangeTurn],
    state_dict: dict[str, Any],
    task_id: str | None = None
) -> str:
    """Run the coder and record it in `history` (so the status board shows it)."""
    seeded = state_dict["seeded"]
    run_brief = brief
    if prior and not seeded:
        run_brief = brief + "\n\n" + wrap_injected_context(
            format_exchange(prior), label="resumed_exchange"
        )
        state_dict["seeded"] = True
    update_status_board(history, "coder", bd)
    try:
        out = await load_skill("coder", run_brief, bd, task_id=task_id)
    except UnexpectedModelBehavior as e:
        out = _recover_from_unexpected_behavior("coder", e, agent_id=_coder_agent_id(task_id))
    out_md = PHASE_SUMMARIES.get("coder", out)
    history.append(("coder", out_md))
    PHASE_SUMMARIES["coder"] = out_md
    update_status_board(history, "coder", bd)
    return out


def passed(reviewer: str, out: str) -> bool:
    """Read the reviewer's pass/fail from its JSON output."""
    try:
        obj = json.loads(out)
    except Exception as e:
        log_operator(
            f"reviewer '{reviewer}' output was not valid JSON; treating as FAIL. "
            f"error={e!r}",
            level="WARNING",
        )
        return False
    if reviewer in ("supervisor_plan", "supervisor_review", "red_team"):
        evals = obj.get("evaluations")
        if not evals:
            return False
        for ev in evals:
            app = ev.get("approved")
            if isinstance(app, str):
                app_lower = app.lower()
                if app_lower.startswith("no") or app_lower.startswith("block"):
                    return False
            elif isinstance(app, bool):
                if not app:
                    return False
            else:
                if not app:
                    return False
        return True
    field = REVIEW_PASS_FIELD.get(reviewer)
    return bool(obj.get(field, False)) if field else False


async def run_gated(
    author: str,
    reviewer: str,
    task: str,
    bd: str,
    history: list[tuple[str, str]],
    exchange: list[ExchangeTurn],
    pass_counter: dict[str, int],
    prior: list[ExchangeTurn],
    state_dict: dict[str, Any],
    hard: bool = False,
    record_exchange: bool = False,
) -> bool:
    """Author produces work; reviewer gates. Up to MAX_RETRIES."""
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n=== [conductor -> {author}] (attempt {attempt}) ===", flush=True)
        author_out = await do_role(author, task, bd, history, exchange, pass_counter, prior, state_dict)
        if record_exchange and author in EXCHANGE_ROLES:
            append_exchange_turn(exchange, pass_counter, author, author_out, bd)

        if author == "planner" and reviewer == "supervisor_plan":
            draft_json = RAW_OUTPUTS.get("planner")
            if draft_json:
                try:
                    draft = clean_role_output(draft_json, DraftPlan)
                    if draft:
                        stage_workspace_from_draft(draft, bd)
                except Exception as e:
                    print(f"[WARN] Pre-stage workspace failed: {e}", flush=True)

        print(f"=== [conductor -> {reviewer}] (attempt {attempt}) ===", flush=True)
        reviewer_out = await do_role(reviewer, task, bd, history, exchange, pass_counter, prior, state_dict)
        if record_exchange and reviewer in EXCHANGE_ROLES:
            append_exchange_turn(exchange, pass_counter, reviewer, reviewer_out, bd)

        if attempt == MAX_RETRIES:
            if hard and not passed(reviewer, reviewer_out):
                raise RuntimeError(
                    f"[gate] HARD FAIL: {reviewer} still failing after "
                    f"{MAX_RETRIES} attempts — aborting (no forced pass)."
                )
            print(f"[gate] {reviewer} attempt {attempt}: FORCED PASS -> proceed")
            return True
        if passed(reviewer, reviewer_out):
            print(f"[gate] {reviewer} attempt {attempt}: PASS -> proceed")
            return True
        print(f"[gate] {reviewer} attempt {attempt}: FAIL -> {author} revises")
    return False


def _assert_plan_gate_ok(history: list, bd: str, st: Any, is_forced_pass: bool = False) -> ExecutablePlan:
    """The coder MUST NOT run on a missing / malformed / failing approved plan."""
    approved = RAW_OUTPUTS.get("supervisor_plan") or next(
        (v for r, v in reversed(history) if r == "supervisor_plan"), None
    )
    if not approved:
        raise RuntimeError(
            "[PLAN-GATE] HALT: no supervisor_plan output — planner/supervisor "
            "chain produced no ApprovedPlan. Coder will NOT run."
        )
    try:
        plan_eval = clean_role_output(approved, ApprovedPlan)
    except Exception as exc:
        raise RuntimeError(
            f"[PLAN-GATE] HALT: supervisor_plan output was unparseable as "
            f"ApprovedPlan ({exc!r}). Coder will NOT run."
        ) from exc
    if plan_eval is None:
        raise RuntimeError(
            "[PLAN-GATE] HALT: ApprovedPlan parsed to None. Coder will NOT run."
        )
    draft_json = RAW_OUTPUTS.get("planner") or next(
        (v for r, v in reversed(history) if r == "planner"), None
    )
    if not draft_json:
        raise RuntimeError("[PLAN-GATE] HALT: no DraftPlan found in history to merge.")
    draft = clean_role_output(draft_json, DraftPlan)
    if not draft:
        raise RuntimeError("[PLAN-GATE] HALT: DraftPlan is malformed.")

    is_plan_approved = True
    eval_map = {item.item_id: item for item in plan_eval.evaluations}
    for item in plan_eval.evaluations:
        if item.approved == "No":
            if is_forced_pass:
                print(
                    f"[WARN] [PLAN-GATE] Overriding evaluation {item.item_id} "
                    f"from 'No' to 'Yes' due to FORCED PASS.",
                    flush=True,
                )
                item.approved = "Yes"
            else:
                is_plan_approved = False

    if not is_plan_approved:
        raise RuntimeError(
            "[PLAN-GATE] HALT: supervisor_plan approved=False. Coder will NOT run."
        )

    draft_dict = json.loads(draft_json)
    for task in draft_dict.get("subtasks", []):
        tid = task.get("id")
        ev = eval_map.get(tid)
        task["Approved"] = ev.approved if ev else "Yes"
        task["Comments"] = ev.comments if ev else ""

    strategy = draft_dict.get("strategy", {})
    workplan = strategy.get("parallelisable_workplan", {})
    for gp in workplan.get("groups", []):
        for task in gp.get("tasks", []):
            tid = task.get("id")
            ev = eval_map.get(tid)
            task["Approved"] = ev.approved if ev else "Yes"
            task["Comments"] = ev.comments if ev else ""

    try:
        from factory.infra.artefacts import artefacts_dir
        plan_file = artefacts_dir() / "workplan" / "planner" / "planner.json"
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        # Normalize JSON escapes/domain terms before persisting
        from factory.tools.normalize_json_escapes import remap
        text = json.dumps(draft_dict, indent=2, ensure_ascii=False)
        normalized_text = remap(text)
        plan_file.write_text(normalized_text, encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Failed to write merged planner.json: {e}", flush=True)

    RAW_OUTPUTS["planner"] = json.dumps(draft_dict)

    merged_tasks = []
    for t in draft.subtasks:
        eval_item = eval_map.get(t.id)
        app_val = (eval_item.approved == "Yes") if eval_item else True
        notes_val = eval_item.comments if eval_item else ""
        merged_tasks.append(
            ApprovedTask(
                id=t.id,
                title=t.title,
                file_paths=t.file_paths,
                instruction=t.instruction,
                acceptance=t.acceptance,
                tool_preference=t.tool_preference,
                evidence=t.evidence,
                approved=app_val,
                notes=notes_val,
            )
        )

    groups_merged = []
    for g in draft.strategy.parallelisable_workplan.groups:
        group_tasks = []
        for gt in g.tasks:
            eval_item = eval_map.get(gt.id)
            app_val = (eval_item.approved == "Yes") if eval_item else True
            notes_val = eval_item.comments if eval_item else ""
            group_tasks.append(
                ApprovedTask(
                    id=gt.id,
                    title=gt.title,
                    file_paths=gt.file_paths,
                    instruction=gt.instruction,
                    acceptance=gt.acceptance,
                    tool_preference=gt.tool_preference,
                    evidence=gt.evidence,
                    approved=app_val,
                    notes=notes_val,
                )
            )
        groups_merged.append(
            WorkGroup(
                id=g.id,
                depends_on=g.depends_on,
                tasks=group_tasks,
            )
        )

    exe_plan = ExecutablePlan(
        epic=draft.epic,
        definition_of_done=draft.definition_of_done,
        acceptance_criteria=draft.acceptance_criteria,
        rubric_cube=draft.rubric_cube,
        summary=draft.summary,
        tasks=merged_tasks,
        alignment=st.global_alignment or draft.summary,
        workplan=ParallelisableWorkplan(groups=groups_merged),
        rejected_subtasks=[],
        strategy=draft.strategy,
        approved=is_plan_approved,
    )

    try:
        exe_plan = ExecutablePlan.model_validate(exe_plan.model_dump())
    except Exception as exc:
        raise RuntimeError(
            f"[PLAN-GATE] HALT: ExecutablePlan validation failed ({exc!r}). "
            f"Every ApprovedTask.id MUST be 'coder01', 'coder02', … unique. "
            f"Coder will NOT run."
        ) from exc

    print("[PLAN-GATE] OK: supervisor_plan approved with 0 failed blockers.", flush=True)
    return exe_plan


def _sync_state(st: Any) -> None:
    """Capture validated RAW_OUTPUTS into the durable OrchestratorState."""
    draft_json = RAW_OUTPUTS.get("planner")
    if draft_json:
        st.draft = DraftPlan.model_validate_json(draft_json)
    approved_json = RAW_OUTPUTS.get("supervisor_plan")
    if approved_json:
        st.approved = ApprovedPlan.model_validate_json(approved_json)
    batch_json = RAW_OUTPUTS.get("coder")
    if batch_json:
        try:
            st.batch = TaskBatch.model_validate_json(batch_json)
        except Exception:
            pass
    code_passed_json = RAW_OUTPUTS.get("supervisor_review")
    if code_passed_json:
        try:
            st.code_passed = CodePassed.model_validate_json(code_passed_json)
        except Exception:
            pass
    audit_json = RAW_OUTPUTS.get("red_team")
    if audit_json:
        try:
            st.audit = AuditResult.model_validate_json(audit_json)
        except Exception:
            pass


def _checkpoint(phase: str, st: Any, stop_after: str | None, bd: str, exchange: list, history: list) -> bool:
    """Persist validated outputs + advance current_phase.

    Returns True when --stop-after <phase> was requested (caller must STOP).
    """
    _sync_state(st)
    record_phase(st, phase)
    save_state(st)
    if stop_after == phase:
        save_exchange(bd, exchange)
        print(
            f"[STOP] halted after {phase}; set start_phase in "
            f"prompt frontmatter to resume from next phase",
            flush=True,
        )
        update_status_board(history, None, bd)
        return True
    return False


async def run_code_review_gate(
    plan: ApprovedPlan,
    run_dir: Path,
    coder_fn,
    reviewer_fn,
    exchange: list[ExchangeTurn] | None = None,
    pass_counter: dict[str, int] | None = None,
    bd: str = "",
    history: list[tuple[str, str]] | None = None,
) -> TaskBatch:
    """Execute the DAG, have supervisor_review mark failures, then re-execute
    only the failing tasks + their downstream dependents (bounded by the DAG),
    up to MAX_RETRIES. Returns the final TaskBatch."""
    sem = asyncio.Semaphore(MAX_AGENTS)
    print(f"\n=== [conductor -> coder] (DAG initial dispatch: {len(plan.workplan.groups)} groups) ===", flush=True)
    results = await run_execute_phase(plan, run_dir, sem, coder_fn, exchange=exchange, pass_counter=pass_counter, bd=bd, history=history, strict=False)
    batch = TaskBatch(results=list(results.values()))
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n=== [conductor -> supervisor_review] (attempt {attempt}) ===", flush=True)
        update_status_board(history if history is not None else [], "supervisor_review", bd)
        review_brief = (
            "Review the executed tasks against their acceptance criteria.\n"
            "Emit CodePassed with `findings` keyed by `task_id` "
            "(severity 'blocker' = must recode).\n\n"
            "PROPOSE-ONLY: the coder staged proposed edits under "
            "factory/temp/ (mirroring repo paths, e.g. "
            "temp/src2/core/schemas/unified.py). Read the staged files there to "
            "verify against the live src2/ originals — the live tree was NOT "
            "modified.\n\n"
            + wrap_injected_context(
                f"GLOBAL ALIGNMENT:\n{plan.alignment}\n\n"
                f"TASK BATCH RESULTS:\n{_model_to_md(batch)}",
                label="review_context",
            )
            + "\n"
            + _render_verdict_block(batch)
            + "\n"
        )
        rev_out = await reviewer_fn(review_brief)
        append_exchange_turn(exchange, pass_counter, "supervisor_review", rev_out, bd)
        try:
            review = clean_role_output(rev_out, ReviewResult)
        except RuntimeError as e:
            raise RuntimeError(
                f"[HALT] supervisor_review output unparseable after sanitize: {e}"
            ) from e
        passed_ = True
        failing = set()
        review_feedback = {}
        for ev in review.evaluations:
            app = ev.approved
            if app == "No":
                passed_ = False
                failing.add(ev.item_id)
                review_feedback[ev.item_id] = f"- [Review Feedback] {ev.comments}"
        if passed_:
            print(f"[gate] supervisor_review attempt {attempt}: PASS -> proceed")
            return batch
        if attempt == MAX_RETRIES:
            print(f"[WARN] [gate] supervisor_review attempt {attempt}: FORCED PASS -> overriding evaluations and proceeding", flush=True)
            for ev in review.evaluations:
                if ev.approved == "No":
                    ev.approved = "Yes"
            return batch
        rerun = _downstream_closure(failing, plan.workplan.groups)
        print(f"[gate] supervisor_review attempt {attempt}: FAIL on {sorted(failing)} -> rerun {sorted(rerun)}")
        results = await run_execute_phase(
            plan,
            run_dir,
            sem,
            coder_fn,
            prior=results,
            rerun_ids=rerun,
            feedback=review_feedback,
            exchange=exchange,
            pass_counter=pass_counter,
            bd=bd,
            history=history,
            strict=False,
        )
        batch = TaskBatch(results=list(results.values()))
    return batch


async def run_red_team_gate(
    plan: ApprovedPlan,
    run_dir: Path,
    coder_fn,
    reviewer_fn,
    prior_batch: dict[str, TaskResult],
    exchange: list[ExchangeTurn] | None = None,
    pass_counter: dict[str, int] | None = None,
    bd: str = "",
    history: list[tuple[str, str]] | None = None,
) -> TaskBatch:
    """Red-team audit of the executed batch, then re-execute only the failing
    tasks + their downstream dependents (bounded by the DAG), up to MAX_RETRIES."""
    sem = asyncio.Semaphore(MAX_AGENTS)
    print(f"\n=== [conductor -> coder] (red-team DAG dispatch: {len(plan.workplan.groups)} groups) ===", flush=True)
    results = await run_execute_phase(
        plan,
        run_dir,
        sem,
        coder_fn,
        prior=prior_batch,
        exchange=exchange,
        pass_counter=pass_counter,
        bd=bd,
        history=history,
        strict=False,
    )
    batch = TaskBatch(results=list(results.values()))
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n=== [conductor -> red_team] (attempt {attempt}) ===", flush=True)
        update_status_board(history if history is not None else [], "red_team", bd)
        review_brief = (
            "Audit the executed code batch against the red-team rubric.\n"
            "Emit AuditResult with `rubric_cube` (any blocker cell not passed = FAIL) "
            "and `findings` keyed by `task_id` (severity 'blocker' = must recode).\n\n"
            "PROPOSE-ONLY: the coder staged proposed edits under "
            "factory/temp/ (mirroring repo paths, e.g. "
            "temp/src2/core/schemas/unified.py). Read the staged files there to "
            "verify against the live src2/ originals — the live tree was NOT "
            "modified.\n\n"
            + wrap_injected_context(
                f"GLOBAL ALIGNMENT:\n{plan.alignment}\n\n"
                f"TASK BATCH RESULTS:\n{_model_to_md(batch)}",
                label="audit_context",
            )
            + "\n"
            + _render_verdict_block(batch)
            + "\n"
        )
        rev_out = await reviewer_fn(review_brief)
        append_exchange_turn(exchange, pass_counter, "red_team", rev_out, bd)
        try:
            audit = clean_role_output(rev_out, AuditResult)
        except RuntimeError as e:
            raise RuntimeError(
                f"[HALT] red_team output unparseable after sanitize: {e}"
            ) from e
        known_task_ids = {t.id for g in plan.workplan.groups for t in g.tasks}
        passed_ = True
        failing = set()
        global_failures = []
        red_feedback = {}

        file_to_coder: dict[str, str] = {}
        for g in plan.workplan.groups:
            for t in g.tasks:
                for fp in t.file_paths:
                    file_to_coder[fp] = t.id
        rubric_coder: dict[str, list[str]] = {}
        for cell in plan.rubric_cube.cells:
            if cell.coder_idents:
                rubric_coder.setdefault(cell.dimension, cell.coder_idents)
                rubric_coder.setdefault(cell.criterion, cell.coder_idents)

        def resolve_item(item_id: str, comment: str) -> list[str]:
            if item_id in known_task_ids:
                return [item_id]
            blob = f"{item_id} {comment}"
            hits = {file_to_coder[fp] for fp in file_to_coder if fp in blob}
            if hits:
                return sorted(hits)
            base = os.path.basename(item_id)
            hits = {c for fp, c in file_to_coder.items() if os.path.basename(fp) == base}
            if hits:
                return sorted(hits)
            if item_id in rubric_coder:
                return rubric_coder[item_id]
            return []

        for ev in audit.evaluations:
            app = ev.approved
            if app == "No":
                passed_ = False
                matched_tasks = resolve_item(ev.item_id, ev.comments or "")

                if matched_tasks:
                    for tid in matched_tasks:
                        failing.add(tid)
                        red_feedback[tid] = f"- [RED-TEAM Feedback] (item {ev.item_id}) {ev.comments}"
                else:
                    global_failures.append(ev.item_id)
        if global_failures and not failing:
            if attempt == MAX_RETRIES:
                print(
                    f"[WARN] [gate] red_team attempt {attempt}: UNRESOLVABLE items force-passed: "
                    + ", ".join(global_failures)
                    + " (propose-only, unpushed)",
                    flush=True,
                )
            else:
                print(
                    f"[WARN] [gate] red_team attempt {attempt}: UNRESOLVABLE items "
                    + ", ".join(global_failures)
                    + " — will force-pass on final attempt.",
                    flush=True,
                )
                continue
        if passed_:
            print(f"[gate] red_team attempt {attempt}: PASS -> proceed to ops")
            return batch
        # When red_team FAILS, status board must show loop-back to coder.
        update_status_board(history if history is not None else [], "red_team", bd)
        if attempt == MAX_RETRIES:
            print(f"[WARN] [gate] red_team attempt {attempt}: FORCED PASS -> overriding evaluations and proceeding (propose-only, unpushed)", flush=True)
            for ev in audit.evaluations:
                if ev.approved == "No":
                    tids = resolve_item(ev.item_id, ev.comments or "")
                    files = sorted(
                        {fp for g in plan.workplan.groups
                         for t in g.tasks if t.id in tids
                         for fp in t.file_paths}
                    )
                    marker = f"[FORCED PASS attempt {attempt} — UNVERIFIED, review files: {files}]"
                    ev.comments = (marker + " " + (ev.comments or "")).strip()
                    ev.approved = "Yes"
            # Update the last exchange entry in-place with the modified audit
            # instead of appending a duplicate, to avoid corrupting the exchange
            # history (the review's double-append bug fix).
            if exchange and exchange[-1].role == "red_team":
                exchange[-1].content = audit.model_dump_json()
            return batch
        if failing:
            rerun = _downstream_closure(failing, plan.workplan.groups)
            print(f"[gate] red_team attempt {attempt}: FAIL on {sorted(failing)} -> rerun {sorted(rerun)}")
            results = await run_execute_phase(
                plan,
                run_dir,
                sem,
                coder_fn,
                prior=results,
                rerun_ids=rerun,
                feedback=red_feedback,
                exchange=exchange,
                pass_counter=pass_counter,
                bd=bd,
                history=history,
                strict=False,
            )
            batch = TaskBatch(results=list(results.values()))
            continue
        else:
            raise RuntimeError(
                "[gate] HARD FAIL: red_team flagged a global blocker with no task-keyed evaluations to recode — unresolvable; aborting (no forced pass)."
            )
    return batch


async def _run_subprocess_with_timeout(
    cmd: list[str], cwd: str, timeout: float = 120.0, stderr_target: int = asyncio.subprocess.PIPE
) -> tuple[int, str]:
    """Run an async subprocess with a hard timeout. Kills the process on timeout."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=stderr_target
    )
    try:
        stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        raise RuntimeError(
            f"[ops] subprocess {cmd[0]!r} timed out after {timeout}s — killed"
        )
    stdout_text = stdout_data.decode("utf-8", "replace") if stdout_data else ""
    stderr_text = stderr_data.decode("utf-8", "replace") if stderr_data else ""
    merged = stdout_text + ("\n" + stderr_text if stderr_text else "")
    return proc.returncode or 0, merged


async def run_ops_phase(
    bd: str,
    *,
    history: list[tuple[str, str]],
    repo_root: Path = REPO_ROOT,
) -> GitResult:
    """Review the work: run hygiene scanners + show diff, NO auto-push."""
    update_status_board(history, "ops", bd)

    hook = repo_root / ".git" / "hooks" / "pre-push"
    if hook.exists():
        rc, stderr_text = await _run_subprocess_with_timeout(
            [str(hook)], str(repo_root), timeout=120.0
        )
        if rc != 0:
            raise RuntimeError(
                "[ops] pre-push hygiene scanners FAILED — HALTING, not pushing\n"
                + stderr_text
            )

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30.0,
    ).stdout.strip()

    result = GitResult(
        pushed=False,
        commit_sha=sha,
        bd_closed=False,
        message="changes ready for human review. Run factory/tools/git-push.sh to push.",
    )
    history.append(("ops", result.model_dump_json()))
    update_status_board(history, "ops", bd)
    return result
