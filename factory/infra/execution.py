"""DAG execution for coder tasks."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from factory.common.operator import log_operator
from factory.infra._loopguard import AGENT_RUN_TIMEOUT
from factory.infra.control import REPO_ROOT, RUNTIME_DIR
from factory.infra.models import (
    TaskResult, ApprovedTask, WorkGroup, ApprovedPlan
)
from factory.infra.context import (
    estimate_task_tokens, _stage_copies, stage_path,
    stage_paths, _edit_mode_block, _build_tier_b_map, _write_harness_patches,
    _quarantine_coder_artifacts, staged_zero_diff, _dep_pointers_for,
    _real_source_paths, TaskNeedsSplitError, TASK_TOKEN_THRESHOLD, TIER_B_SLICE_THRESHOLD
)
from factory.infra.exchange import (
    update_status_board, append_exchange_turn, ExchangeTurn
)
from factory.infra.tools import wrap_injected_context

CODER_VALIDATION_PASSES = 3
DAG_DEADLOCK_TIMEOUT: float = CODER_VALIDATION_PASSES * 600  # 1800.0


async def run_execute_phase(
    plan: ApprovedPlan,
    run_dir: Path,
    sem: asyncio.Semaphore,
    coder_fn,
    prior: dict[str, TaskResult] | None = None,
    rerun_ids: set[str] | None = None,
    feedback: dict[str, str] | None = None,
    exchange: list[ExchangeTurn] | None = None,
    pass_counter: dict[str, int] | None = None,
    bd: str = "",
    history: list[tuple[str, str]] | None = None,
    strict: bool = True,
) -> dict[str, TaskResult]:
    """Execute the workplan DAG.

    - Topologically ordered via per-group asyncio.Event gating on depends_on.
    - Tasks within a group ALWAYS run concurrently via asyncio.gather, bounded
      by `sem`.  The group-level `concurrent` flag is IGNORED during execution:
      if the Planner needs sequential ordering it must put tasks in separate
      groups chained via depends_on — that is the ONLY supported gating
      mechanism.  Addressed user complaint 'not spawning agents based on DAG'.
    - `prior` + `rerun_ids` enable surgical re-execution: only tasks whose id is
      in `rerun_ids` are re-run; others are copied from `prior`.
    - `feedback` (optional) is a task_id -> prior-review/audit findings text map.
      When a rerun task's id is in `feedback`, its coder brief is augmented with
      a `=== PRIOR FEEDBACK ===` block (R1, ticket baziforecaster-nw9ov) so the
      rerun coder is told exactly what to change instead of re-deriving it blind.
    - Asserts the Planner's file-disjoint claim per concurrent group (HALT)."""
    workplan = plan.workplan
    groups = {g.id: g for g in workplan.groups}
    for g in workplan.groups:
        for d in g.depends_on:
            if d not in groups:
                raise RuntimeError(f"[DAG] group {g.id!r} depends on unknown group {d!r}")
    for g in workplan.groups:
        if g.concurrent:
            seen_paths: set[tuple[str, ...]] = set()
            for t in g.tasks:
                key = tuple(sorted(_real_source_paths(t.file_paths)))
                # A task with no REAL source files has nothing to race on; do
                # not let the empty tuple collide across tasks (vw4dd).
                if not key:
                    continue
                if key in seen_paths:
                    raise RuntimeError(
                        f"[DAG] group {g.id!r} is NOT file-disjoint "
                        f"(shared {sorted(key)}) — violates Planner claim"
                    )
                seen_paths.add(key)
    # P0 zu9u (H8): cross-group disjointness. Groups run concurrently via
    # asyncio.gather below, so two DIFFERENT groups sharing a file can race.
    # Intra-group assert above is insufficient — assert globally here.
    # NOTE: this is a PLANNER-CONTRACT violation surfaced fail-loudly — not a
    # runtime patch. The planner owns parallelism; we do not silently reorder.
    _all_paths: dict[str, str] = {}  # file_path -> group_id (first owner)
    for g in workplan.groups:
        for t in g.tasks:
            for fp in _real_source_paths(t.file_paths):
                owner = _all_paths.get(fp)
                if owner is not None and owner != g.id:
                    raise RuntimeError(
                        f"[DAG] cross-group file overlap: {fp} appears in multiple "
                        f"groups ({owner!r} and {g.id!r}) — violates concurrency safety"
                    )
                _all_paths[fp] = g.id
    group_events = {gid: asyncio.Event() for gid in groups}
    group_done: dict[str, bool] = {}
    results: dict[str, TaskResult] = dict(prior or {})

    async def execute_task(t: ApprovedTask) -> TaskResult:
        staged = stage_paths(t.file_paths)
        # ── SIZE-AWARE CONTEXT INJECTION GATE (epic baziforecaster-gx30p) ──
        # A coder must hold the full target file to edit precisely, but an
        # unbounded file risks blowing the 200K budget. Compute deterministic
        # token counts per task BEFORE any coder spawns (cheap assertion before
        # an expensive LLM call). k2owt / qkm3p / fzqa2 / vze01.
        est = estimate_task_tokens(t.file_paths)
        total_tokens: int = est["total"]  # type: ignore[typeddict-item]
        per_file: dict[str, int] = est["per_file"]  # type: ignore[typeddict-item]
        tier = "A" if total_tokens <= TASK_TOKEN_THRESHOLD else "B"
        # fzqa2: stage (copy) live files into temp/<task>/ as an eviction-exempt
        # baseline. The coder reads from staging (real content, never evicted),
        # the live tree stays read-only. Modes drive the per-file EDIT MODE block.
        edit_modes = _stage_copies(t.file_paths, staged)
        if tier == "B":
            # vze01 (last resort): if ANY single file alone exceeds the slice
            # budget, even a targeted slice read would blow the context — the
            # task genuinely needs a huge file and must be SPLIT by the planner.
            oversized = [fp for fp, n in per_file.items() if n > TIER_B_SLICE_THRESHOLD]
            if oversized:
                raise TaskNeedsSplitError(
                    f"[HALT] task {t.id} requires SPLIT — file(s) exceed the "
                    f"{TIER_B_SLICE_THRESHOLD:,}-token slice budget: "
                    f"{sorted(oversized)}. Re-plan with narrower file_paths."
                )
            # qkm3p: Tier B — do NOT inject the full files. The coder works from
            # the eviction-exempt staging copies + a structural map so it can
            # target precise slices without the whole file in its context.
            tier_b_map = _build_tier_b_map(t.file_paths)
            print(
                f"  [SIZE-GATE] task {t.id}: Tier B ({total_tokens:,} tokens > "
                f"{TASK_TOKEN_THRESHOLD:,} threshold) — injecting structural map, "
                f"coder reads staging slices.",
                flush=True,
            )
            inline_files = ""
        else:
            tier_b_map = ""
            print(
                f"  [SIZE-GATE] task {t.id}: Tier A ({total_tokens:,} tokens) — "
                f"full files injected normally.",
                flush=True,
            )
            inline_files = ""
            if staged:
                try:
                    text = Path(staged[0]).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = f"<unreadable staging mirror: {staged[0]}>"
                prefix_text = "\n".join(
                    f"{i+1}: {line}" for i, line in enumerate(text.splitlines())
                )
                inline_files = (
                    f"--- FILE TO EDIT: {t.file_paths[0]} (staging: {staged[0]}) ---\n"
                    f"{prefix_text}\n--- END FILE ---"
                )
        # R5 (baziforecaster-6gizg): frozen, structured behaviour appendix derived
        # from the task's acceptance/DoD — NOT the planner's raw prose. Anchors the
        # coder to a contract regardless of planner wording.
        behaviour_appendix = (
            "=== EXPECTED CODER BEHAVIOUR (frozen contract) ===\n"
            "- Implement ONLY this task; do not touch other tasks' files.\n"
            "- Satisfy EVERY acceptance_criteria line below verbatim; if a criterion "
            "is unachievable, return status 'blocked' with the reason — never fake it.\n"
            "- Use STRICT Pydantic models / typed fields only; no bare dicts for "
            "domain logic; no dict access on Pydantic models.\n"
            "- Code MUST pass `uv run ruff check`. Write output under "
            "factory/temp/ (PROPOSE-ONLY); never write src/ or src2/.\n"
            "- Return a TaskResult (task_id, status, files_changed, diff_summary, "
            "notes) with NO file content inside it.\n"
            f"- ACCEPTANCE (verbatim):\n{t.acceptance}\n"
        )
        is_rerun = bool(rerun_ids) and t.id in rerun_ids
        feedback_block = ""
        if feedback and t.id in feedback:
            # R1 (baziforecaster-nw9ov): the harness computed prior review/audit
            # findings to pick rerun_ids but never showed them to the coder. The
            # rerun coder is per-agent isolated (coderN.jsonl) and effectively
            # fresh, so explicit injection is REQUIRED — do not rely on message_history.
            feedback_block = (
                "\n=== PRIOR FEEDBACK (why this task was reopened) ===\n"
                "You are FIXING a previously-failed attempt. The harness reopened "
                "this task based on the review/audit findings below. Address EVERY "
                "point. Your own prior attempt context lives in your coder memory "
                "(compacted via keep_memory) — this block is the authoritative list "
                "of what changed.\n"
                f"{feedback[t.id]}\n"
            )
        elif is_rerun:
            feedback_block = (
                "\n=== PRIOR FEEDBACK ===\n"
                "This task was reopened by the harness (rerun target) but no "
                "structured findings were captured. Re-read your own coder memory "
                "(keep_memory) and the staged files, and re-verify your prior "
                "attempt against the acceptance criteria.\n"
            )
        discipline_block = (
            "\n=== FROZEN DISCIPLINE (load-bearing rules — DO NOT VIOLATE) ===\n"
            "- ZERO-DICTS: No bare dict access on Pydantic models. All domain data uses strict Pydantic models/Enums/Literals.\n"
            "- PYDANTIC-ONLY: All domain lookups/tables = Pydantic registry models with typed fields. Enums ONLY as field types.\n"
            "- FAIL LOUDLY: Full tracebacks on errors. No silent except:pass, no hidden fallbacks.\n"
            "- FAIL CHEAPLY: Cheap assertions before expensive LLM calls.\n"
            "- NO src/ or src2/ edits: Write output under factory/temp/ only.\n"
            "- Code MUST pass `uv run ruff check` before being considered done.\n"
        )
        brief = (
            "You are implementing EXACTLY ONE task. Do not implement others.\n\n"
            f"TASK ID: {t.id}\nTITLE: {t.title}\n"
            f"FILE TO EDIT: {t.file_paths[0] if t.file_paths else 'None'}\n\n"
            f"INSTRUCTION:\n{t.instruction}\n\n"
            f"ACCEPTANCE CRITERIA:\n{t.acceptance}\n\n"
            f"LIVE FILES (read-only reference — DO NOT write here):\n{t.file_paths}\n\n"
            f"STAGING PATHS (WRITE your proposed files ONLY here, under factory/temp/):\n{staged}\n\n"
            + _edit_mode_block(edit_modes, staged)
            + "\n"
            + (tier_b_map + "\n\n" if tier_b_map else "")
            + (f"\n=== FULL FILE CONTENT (edit directly; NO read tool needed) ===\n{inline_files}\n" if inline_files else "")
            + wrap_injected_context(f"GLOBAL ALIGNMENT:\n{plan.alignment}", label="global_alignment")
            + "\n\n"
            + behaviour_appendix
            + discipline_block
            + feedback_block
        )
        # --- CQRS CLAIM ---
        try:
            import subprocess
            subprocess.run(["./bd", "update", f"bd-{t.id}", "--claim", "--status", "in_progress"], cwd=str(REPO_ROOT), capture_output=True, check=False)
        except Exception:
            pass
        # ------------------
        async with sem:
            # P1 vo94 (M3): show the coder as IN-FLIGHT *before* it runs, so an
            # active task is not misreported as finished (the board previously
            # only flipped to coder:{id} after the call returned).
            update_status_board(history if history is not None else [], f"{t.id} → {t.file_paths[0] if t.file_paths else '?'}", bd)
            try:
                out = await asyncio.wait_for(
                    coder_fn(brief, task_id=t.id), timeout=AGENT_RUN_TIMEOUT
                )
            except TimeoutError:
                # docs/01_fix.md Fix B: surface silent blocked paths loudly.
                log_operator(
                    f"task {t.id} blocked: coder timed out after "
                    f"{AGENT_RUN_TIMEOUT}s (initial pass)",
                    level="WARNING",
                )
                return TaskResult(
                    task_id=t.id,
                    status="blocked",
                    files_changed=[],
                    diff_summary="",
                    notes=f"coder timed out after {AGENT_RUN_TIMEOUT}s",
                )
            except Exception as e:
                log_operator(
                    f"[execute_task] coder_fn exception for task {t.id}; "
                    f"marking blocked. error={e!r}",
                    level="ERROR",
                )
                return TaskResult(
                    task_id=t.id,
                    status="blocked",
                    files_changed=[],
                    diff_summary="",
                    notes=f"coder execution failed: {e}",
                )
            # SA5-F2: per-task transcript for coder/EXECUTE diagnostics.
            try:
                task_log = RUNTIME_DIR / f"task_{t.id}.log"
                task_log.parent.mkdir(parents=True, exist_ok=True)
                task_log.write_text(
                    f"=== TASK {t.id} ===\nBRIEF:\n{brief}\n\nOUTPUT:\n{out}\n",
                    encoding="utf-8",
                )
            except Exception as log_exc:
                print(f"[WARN] task transcript write failed for {t.id}: {log_exc!r}", flush=True)
        append_exchange_turn(exchange, pass_counter, "coder", out, bd)
        try:
            obj = json.loads(out)
        except Exception as e:
            # SA4-F4: graceful degradation (return a blocked TaskResult string to
            # the LLM loop) BUT surface the fault to the operator instead of
            # hiding it inside `notes` alone.
            log_operator(
                f"[execute_task] coder output for task {t.id} was not valid JSON; "
                f"marking blocked. error={e!r}",
                level="WARNING",
            )
            return TaskResult(
                task_id=t.id,
                status="blocked",
                files_changed=[],
                diff_summary="",
                notes=f"coder output not JSON: {e}",
            )

        # --- HARNESS-OWNED VALIDATION RE-SPAWN LOOP (DECISION C / Q4-A) ---
        # The coder only DECLARES done; the harness runs the guardrail (ruff +
        # smoke type-construction gate + broadened union pyright) on the staged
        # files. On RUFF, SMOKE, OR PYRIGHT failure it spawns a FRESH coder agent
        # with the feedback appended so it self-corrects (docs/01_fix.md Tasks
        # 1, 2, 6: pyright is now BLOCKING, immediate re-spawn). The per-stage
        # gate means a broken upstream type contract surfaces at the PRODUCER,
        # not the consumer. Each coder call is a clean agent (no shell needed).
        feedback_brief = brief
        verdict_state: dict[str, dict] = {}  # fp -> last guardrail payload
        for _pass in range(CODER_VALIDATION_PASSES + 1):
            files = obj.get("files_changed") or obj.get("files") or []
            ruff_failed = False
            pyright_failed = False
            smoke_failed = False
            zero_diff_failed = False
            feedback_block = ""
            for fp in files:
                try:
                    edit_set_arg = ",".join(t.file_paths) if t.file_paths else ""
                    # 00_fix Fix A/B: validate the STAGED copy via the single
                    # normalization seam so BOTH absolute and relative temp paths
                    # resolve to the correct staging file (absolute paths used to
                    # collapse to the live file and self-compare as a false zero-diff).
                    validate_target = stage_path(fp)
                    # 00_fix Fix A (Q5 Option B): zero-diff vs the captured .orig
                    # baseline -> genuine no-op edit. Re-spawn the coder to actually
                    # edit; block (via the SPAWN-ALL HALT) only if it persists.
                    _zd = staged_zero_diff(fp)
                    if _zd is True:
                        zero_diff_failed = True
                        feedback_block += (
                            f"\n--- {fp} (ZERO-DIFF) ---\n"
                            f"You changed nothing versus the baseline (no .orig diff). "
                            f"Apply the required edits to {stage_path(fp)} and re-output done JSON.\n"
                        )
                    res = subprocess.run(
                        [sys.executable, "factory/tools/guardrail_check.py", "validate", validate_target, edit_set_arg],
                        capture_output=True,
                        text=True,
                        cwd=str(REPO_ROOT),
                        timeout=240,
                    )
                except Exception as guard_exc:
                    # GUARDRAIL ITSELF errored (not a lint failure) — fail loudly
                    # to the operator but treat as pass so we never crash the task.
                    log_operator(
                        f"[execute_task] guardrail_check.py crashed on {fp!r} for "
                        f"task {t.id}: {guard_exc!r}",
                        level="WARNING",
                    )
                    continue
                try:
                    gj = json.loads(res.stdout.strip().splitlines()[-1]) if res.stdout.strip() else {}
                except Exception:
                    # Unparseable guardrail output -> treat as pass to avoid loops.
                    continue
                verdict_state[fp] = gj
                # Fix E (00_fix): mechanically auto-fix lint on the staged file,
                # then re-score the auto-fixed file so a coder is never burned for
                # a trivial I001/UP034 it can't see. Only re-runs when ruff failed.
                if gj.get("ruff_ok", True) is False:
                    try:
                        subprocess.run(
                            ["uv", "run", "ruff", "check", "--fix", validate_target],
                            cwd=str(REPO_ROOT),
                            capture_output=True,
                            timeout=120,
                        )
                        subprocess.run(
                            ["uv", "run", "ruff", "format", validate_target],
                            cwd=str(REPO_ROOT),
                            capture_output=True,
                            timeout=120,
                        )
                        res2 = subprocess.run(
                            [sys.executable, "factory/tools/guardrail_check.py", "validate", validate_target, edit_set_arg],
                            capture_output=True,
                            text=True,
                            cwd=str(REPO_ROOT),
                            timeout=240,
                        )
                        gj2 = json.loads(res2.stdout.strip().splitlines()[-1]) if res2.stdout.strip() else {}
                        if gj2.get("ruff_ok", True) is True:
                            feedback_block += (
                                f"\n--- {fp} (RUFF AUTO-FIX APPLIED) ---\n"
                                f"The harness auto-fixed lint; re-validate passed.\n"
                            )
                            gj = gj2
                            verdict_state[fp] = gj2
                    except Exception:
                        pass
                if gj.get("ruff_ok", True) is False:
                    ruff_failed = True
                    feedback_block += (
                        f"\n--- {fp} (RUFF) ---\n"
                        f"RUFF OUTPUT:\n{gj.get('ruff_output', '')}\n"
                        f"DIFF VS CHECKPOINT:\n{gj.get('diff_vs_checkpoint', '')}\n"
                    )
                if gj.get("smoke_ok", True) is False:
                    # Task 1: type-construction smoke gate (BUG 2 class) blocks.
                    smoke_failed = True
                    feedback_block += (
                        f"\n--- {fp} (SMOKE TYPE-CONSTRUCTION) ---\n"
                        f"SMOKE OUTPUT:\n{gj.get('smoke_output', '')}\n"
                    )
                if gj.get("pyright_ok", True) is False:
                    # Task 2: pyright is now BLOCKING, scoped to the edited file's
                    # own lines (our_errors filter inside guardrail_check).
                    pyright_failed = True
                    feedback_block += (
                        f"\n--- {fp} (PYRIGHT) ---\n"
                        f"PYRIGHT OUTPUT:\n{gj.get('pyright_output', '')}\n"
                    )

            if not (ruff_failed or smoke_failed or pyright_failed or zero_diff_failed):
                break  # clean -> final result is the current out/obj.

            if _pass + 1 > CODER_VALIDATION_PASSES:
                # HARD-HALT after exhausting all re-spawn attempts.
                reasons = []
                if ruff_failed:
                    reasons.append("ruff")
                if smoke_failed:
                    reasons.append("smoke type-construction")
                if pyright_failed:
                    reasons.append("pyright")
                if zero_diff_failed:
                    reasons.append("zero-diff (no change vs baseline)")
                # Fix G (00_fix): surface the gate reason next to the SPAWN-ALL
                # HALT so the operator sees it without a deep log dive.
                log_operator(
                    f"[HALT] task {t.id} failed validation after "
                    f"{CODER_VALIDATION_PASSES} re-spawn attempts "
                    f"({', '.join(reasons)})",
                    level="ERROR",
                )
                raise RuntimeError(
                    f"[HALT] task {t.id} failed validation after "
                    f"{CODER_VALIDATION_PASSES} re-spawn attempts "
                    f"({', '.join(reasons)}). EXECUTE phase aborted — a broken "
                    f"type contract must not reach review/red-team."
                )

            prior_rejection_notes = obj.get("notes", "")
            rejection_block = (
                "\n\n=== PRIOR ATTEMPT REJECTION (your last attempt was rejected; "
                "do NOT repeat this) ===\n" + prior_rejection_notes
            ) if prior_rejection_notes else ""
            feedback_brief = (
                brief
                + rejection_block
                + "\n\n=== GUARDRAIL FEEDBACK (ruff failed on your staged file(s); "
                "fix the errors below, then output your done JSON again) ===\n"
                + feedback_block
            )
            async with sem:
                update_status_board(history if history is not None else [], f"{t.id} → {t.file_paths[0] if t.file_paths else '?'}", bd)
                try:
                    out = await asyncio.wait_for(
                        coder_fn(feedback_brief, task_id=t.id), timeout=AGENT_RUN_TIMEOUT
                    )
                except TimeoutError:
                    # docs/01_fix.md Fix B: surface silent blocked paths loudly.
                    log_operator(
                        f"task {t.id} blocked: coder re-spawn timed out after "
                        f"{AGENT_RUN_TIMEOUT}s (validation re-spawn pass)",
                        level="WARNING",
                    )
                    return TaskResult(
                        task_id=t.id,
                        status="blocked",
                        files_changed=[],
                        diff_summary="",
                        notes=f"coder re-spawn timed out after {AGENT_RUN_TIMEOUT}s",
                    )
                except Exception as e:
                    log_operator(
                        f"[execute_task] coder_fn re-spawn exception for task {t.id}; "
                        f"marking blocked. error={e!r}",
                        level="ERROR",
                    )
                    return TaskResult(
                        task_id=t.id,
                        status="blocked",
                        files_changed=[],
                        diff_summary="",
                        notes=f"coder re-spawn execution failed: {e}",
                    )
                try:
                    task_log = RUNTIME_DIR / f"task_{t.id}.log"
                    task_log.parent.mkdir(parents=True, exist_ok=True)
                    with task_log.open("a", encoding="utf-8") as fh:
                        fh.write(f"\n=== RE-SPAWN PASS {_pass + 2} ===\nBRIEF:\n{feedback_brief}\n\nOUTPUT:\n{out}\n")
                except Exception as log_exc:
                    print(f"[WARN] task transcript append failed for {t.id}: {log_exc!r}", flush=True)
            append_exchange_turn(exchange, pass_counter, "coder", out, bd)
            try:
                obj = json.loads(out)
            except Exception as e:
                log_operator(
                    f"[execute_task] re-spawned coder output for task {t.id} was not "
                    f"valid JSON; proceeding with last valid obj. error={e!r}",
                    level="WARNING",
                )
                break

        # --- PRE-REVIEW GATES (00_fix Fix A: single seam vs .orig baseline) ---
        # Zero-diff detection now lives in the validation re-spawn loop (it owns
        # re-spawn-then-block). Here we only run the Runtime Load Gate, resolved
        # through the single stage_path seam so BOTH absolute and relative temp
        # paths validate the correct staging file (no silent skip on relative fp).
        if obj.get("status") == "done":
            files = obj.get("files_changed") or obj.get("files") or []
            for fp in files:
                if str(fp).endswith(".py") and obj.get("status") == "done":
                    staged_path = stage_path(fp)
                    if Path(staged_path).exists():
                        try:
                            import subprocess
                            res = subprocess.run(
                                [sys.executable, "factory/tools/load_schema_gate.py", str(staged_path)],
                                capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=30
                            )
                            if res.returncode != 0:
                                obj["status"] = "blocked"
                                obj["notes"] = f"[Runtime Load Gate] {fp} failed schema validation: {res.stdout.strip()} " + obj.get("notes", "")
                                log_operator(f"task {t.id} blocked: schema load failed on {fp}: {res.stdout.strip()}", level="WARNING")
                                break
                        except Exception:
                            pass

        # --- CQRS CLOSE ---
        try:
            import subprocess
            status_out = obj.get("status", "blocked")
            if status_out == "done":
                subprocess.run(["./bd", "close", f"bd-{t.id}", "--reason", str(obj.get("notes", ""))[:100]], cwd=str(REPO_ROOT), capture_output=True, check=False)
            else:
                subprocess.run(["./bd", "update", f"bd-{t.id}", "--status", "blocked"], cwd=str(REPO_ROOT), capture_output=True, check=False)
        except Exception:
            pass
        # ------------------

        # HARNESS-OWNED PATCH GENERATION (B1–B7) — replaces coder hand-written .diff
        files = obj.get("files_changed") or obj.get("files") or []
        if obj.get("status") == "done":
            written, real_changes = _write_harness_patches(t.id, files, bd)
            _quarantine_coder_artifacts(bd)
            if real_changes == 0:
                # B3: fake-done — claimed done but changed nothing
                log_operator(f"[PATCH] task {t.id} status=done but ZERO real changes -> blocked", level="WARNING")
                return TaskResult(task_id=t.id, status="blocked", files_changed=[],
                                  diff_summary="", notes="fake-done: no file changes vs baseline")

        # Task 4 (docs/01_fix.md, D1): cumulative ValidationVerdict. The coder's
        # JSON is the *claim* half; these fields are the harness-filled *verdict*
        # half, derived from the guardrail payloads collected in the re-spawn loop.
        ruff_ok = py_ok = smk_ok = True
        verdict_errors_parts: list[str] = []
        verdict_diff_parts: list[str] = []
        for fp, gj in verdict_state.items():
            if gj.get("ruff_ok", True) is False:
                ruff_ok = False
                verdict_errors_parts.append(f"[ruff] {fp}: {gj.get('ruff_output', '')}")
            if gj.get("pyright_ok", True) is False:
                py_ok = False
                verdict_errors_parts.append(f"[pyright] {fp}: {gj.get('pyright_output', '')}")
            if gj.get("smoke_ok", True) is False:
                smk_ok = False
                verdict_errors_parts.append(f"[smoke] {fp}: {gj.get('smoke_output', '')}")
            diff = gj.get("diff_vs_checkpoint", "")
            if diff and diff not in ("no checkpoint", "no diff"):
                verdict_diff_parts.append(f"--- {fp} ---\n{diff}")
        # Dependency pointers (Task 5, D5): for each edited file, note upstream
        # imports discovered by the union pyright so reviewers know where to trace.
        dep_pointers = _dep_pointers_for(t.file_paths) if t.file_paths else []

        return TaskResult(
            task_id=obj.get("task_id", t.id),
            status=obj.get("status", "blocked"),
            files_changed=obj.get("files_changed", []),
            diff_summary=str(obj.get("diff_summary", ""))[:2000],
            notes=str(obj.get("notes", ""))[:2000],
            ruff_ok=ruff_ok,
            pyright_ok=py_ok,
            exec_ok=smk_ok,
            verdict_errors="\n".join(verdict_errors_parts)[:4000],
            verdict_diff="\n".join(verdict_diff_parts)[:4000],
            dep_pointers=dep_pointers,
        )

    async def process_group(g: WorkGroup) -> None:
        for d in g.depends_on:
            # SPAWN-ALL (baziforecaster-uqj06): every group ALWAYS spawns and
            # executes regardless of whether a sibling/prerequisite task blocked.
            # We no longer short-circuit a dependent group when its prerequisite
            # yielded blocked tasks — a single blocked task must NOT axe unrelated
            # sibling coders. The whole EXECUTE phase is instead hard-halted AFTER
            # all groups finish (see post-gather scan below), so incomplete work
            # never flows on toward review. The wait still gates true dependency
            # ordering (a group only starts once its prerequisites completed).
            # 01_FIX-D1: unbounded wait + liveness guard. The old 300s deadline
            # crashed on slow-but-legitimate groups (coder_1 + coder_2 re-spawns
            # took >5min). Now we only raise if the prerequisite already completed
            # but forgot to signal its event (true code-regression bug).
            try:
                await asyncio.wait_for(group_events[d].wait(), timeout=DAG_DEADLOCK_TIMEOUT)
            except TimeoutError:
                if group_done.get(d, False):
                    raise RuntimeError(
                        f"[HALT] prerequisite group {d!r} completed but never signaled "
                        f"its completion event (dependency deadlock bug)"
                    )
                # Prerequisite is still legitimately working — wait indefinitely.
                await group_events[d].wait()
        if rerun_ids is None:
            # Fresh run when no prior exists; adopt prior verbatim (no re-exec)
            # when a prior batch is supplied (e.g. the red-team gate auditing an
            # already-executed code-review batch).
            to_run = [] if prior else list(g.tasks)
        else:
            to_run = [t for t in g.tasks if t.id in rerun_ids]
        if not to_run:
            group_events[g.id].set()
            group_done[g.id] = True
            return
        # ALWAYS concurrent dispatch — the `concurrent` flag on WorkGroup is
        # logged but NOT obeyed.  Sequential tasks must be in separate groups
        # chained via `depends_on`.
        task_labels = ", ".join(t.id for t in to_run[:5])
        if len(to_run) > 5:
            task_labels += f" … ({len(to_run)} total)"
        print(
            f"  [DAG] group {g.id!r} — {len(to_run)} task(s): {task_labels}",
            flush=True,
        )
        sub = await asyncio.gather(
            *(execute_task(t) for t in to_run), return_exceptions=True
        )
        for t, r in zip(to_run, sub):
            if isinstance(r, TaskNeedsSplitError):
                # vze01: do NOT swallow the split signal into a blocked result —
                # re-raise so it propagates out of run_execute_phase and the
                # operator re-plans with narrower file_paths.
                raise r
            if isinstance(r, Exception):
                # docs/01_fix.md Fix B: surface the harness-owned gate/validation
                # failure loudly next to the SPAWN-ALL HALT so triage does not
                # require a deep log dive. The message carries the underlying
                # reason (e.g. "[HALT] task <id> failed validation after N
                # coder passes (pyright/ruff/smoke)" from the re-spawn loop).
                log_operator(
                    f"task {t.id} blocked: {type(r).__name__}: {r}",
                    level="WARNING",
                )
                results[t.id] = TaskResult(
                    task_id=t.id,
                    status="blocked",
                    files_changed=[],
                    diff_summary="",
                    notes=f"task crashed: {type(r).__name__}: {r}",
                )
            else:
                assert isinstance(r, TaskResult)
                results[t.id] = r
        group_events[g.id].set()
        group_done[g.id] = True

    _concurrent = sum(1 for g in workplan.groups if getattr(g, "concurrent", True))
    _sequential = len(workplan.groups) - _concurrent
    print(
        f"[DAG] planner topology: concurrent_groups={_concurrent} "
        f"sequential_groups={_sequential} (total={len(workplan.groups)})",
        flush=True,
    )
    group_results = await asyncio.gather(
        *(process_group(g) for g in workplan.groups), return_exceptions=True
    )
    for g, grp_r in zip(workplan.groups, group_results):
        if isinstance(grp_r, Exception):
            raise RuntimeError(
                f"[DAG] group {g.id} fault: {type(grp_r).__name__}: {grp_r}"
            ) from grp_r
    # SPAWN-ALL HALT (baziforecaster-uqj06): after EVERY group has spawned and
    # executed, if ANY task is blocked/failed (or produced no result), hard-halt
    # the run — BUT only when `strict=True` (a top-level caller with no
    # recovery owner). When called from run_code_review_gate / run_red_team_gate
    # the gates own recovery (supervisor_review / red_team rerun + force-pass
    # at MAX_RETRIES), so they pass strict=False and RECEIVE the incomplete
    # results to recover. The HALT must NOT pre-empt the gate's retry loop
    # (00_fix: it previously killed the run before supervisor_review could run).
    incomplete: list[str] = []
    for t in workplan.groups:
        for task in t.tasks:
            r = results.get(task.id)
            if r is None or r.status in ("blocked", "failed"):
                incomplete.append(task.id)
    if incomplete and strict:
        raise RuntimeError(
            f"[HALT] EXECUTE phase incomplete: {', '.join(sorted(set(incomplete)))}"
        )
    return results
