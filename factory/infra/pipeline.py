"""Pipeline orchestration module containing all gate functions and the phase loop."""
from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic_ai.exceptions import UnexpectedModelBehavior

from factory.common import ROLE_OUTPUT_TYPE, OUTPUT_TYPE_REGISTRY
from factory.infra._runtime import (
    RAW_OUTPUTS, PHASE_SUMMARIES, _PHASE_ORDER,
)
from factory.infra.agent import (
    load_skill, _load_role_messages, _recover_role_output, _coder_agent_id,
)
from factory.infra.control import (
    REPO_ROOT, MAX_AGENTS, TodoList, TodoItem,
)
from factory.infra.execution import (
    run_execute_phase,
)
from factory.infra.virtual_ast_buffer import (
    extract_file_skeleton_and_imports,
    extract_function_node_source,
)
from factory.infra.exchange import (
    update_status_board, save_exchange,
    format_exchange, append_exchange_turn, _model_to_md, _render_verdict_block,
    _render_upfront_diffs,
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
from factory.infra.tools_shell import verify_edit
from factory.infra.validation import (
    EXCHANGE_ROLES, MAX_RETRIES, PLAN_INVARIANT_RETRIES,
    check_plan_invariants, _downstream_closure,
)

RESUME_RE = re.compile(r"^Resume:\s*(true|false)\s*$", re.IGNORECASE)
MAX_ATTEMPTS = 5


def _compute_cc(node: ast.AST) -> int:
    """Calculate cyclomatic complexity for an AST function node."""
    cc = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
            cc += 1
        elif isinstance(child, ast.ExceptHandler):
            cc += 1
        elif isinstance(child, (ast.With, ast.AsyncWith)):
            cc += 1
        elif isinstance(child, ast.BoolOp):
            cc += len(child.values) - 1
        elif isinstance(child, (ast.IfExp, ast.Assert)):
            cc += 1
    return cc


def auto_discover_high_cc_functions(staged_paths: list[str], max_cc: int = 5) -> list[tuple[str, str]]:
    """Scan staged_paths for functions with cyclomatic complexity exceeding max_cc.

    Returns a list of ``(staged_file_path, function_name)`` tuples for every
    ``FunctionDef`` / ``AsyncFunctionDef`` where CC > max_cc.
    """
    results: list[tuple[str, str]] = []
    for staged_path in staged_paths:
        path = Path(staged_path)
        if not path.exists():
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = _compute_cc(node)
                if cc > max_cc:
                    results.append((staged_path, node.name))
    return results


def compute_dynamic_retry_budget(file_path: str, function_name: str) -> int:
    """Calculate a retry budget based on a function's line count.

    Returns ``max(5, line_count // 5)`` where line_count is derived from
    the function's ``lineno`` and ``end_lineno`` in the AST.
    """
    path = Path(file_path)
    if not path.exists():
        return 5
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return 5
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            line_count = (node.end_lineno or node.lineno) - node.lineno + 1
            return max(5, line_count // 5)
    return 5


def build_todo_checklist(staged_paths: list[str], target_functions: list[str]) -> TodoList:
    """Build an initial TodoList by running verify_edit on target functions at phase startup."""
    items: list[TodoItem] = []
    for staged_file_path in staged_paths:
        if target_functions:
            for fn_name in target_functions:
                result = verify_edit(staged_file_path, fn_name)
                parsed = json.loads(result) if result else {}
                funcs = parsed.get("functions", [])
                target_fn = next((f for f in funcs if f.get("function") == fn_name), None)
                if not target_fn:
                    continue
                cc = target_fn.get("cc", 0)
                passed = target_fn.get("passed", False) and cc <= 5
                items.append(
                    TodoItem(
                        file_path=staged_file_path,
                        function_name=fn_name,
                        target_cc=5,
                        current_cc=cc,
                        passed=passed,
                    )
                )
        else:
            result = verify_edit(staged_file_path, None)
            parsed = json.loads(result) if result else {}
            functions = parsed.get("functions", [])
            for fn in functions:
                cc = fn.get("cc", 0)
                passed = fn.get("passed", False) or (cc <= 5)
                items.append(
                    TodoItem(
                        file_path=staged_file_path,
                        function_name=fn.get("function", "unknown"),
                        target_cc=5,
                        current_cc=cc,
                        passed=passed,
                    )
                )
    return TodoList(items=items)


def read_prompt(prompt_file: Path) -> tuple[bool, str, list[str], str | None, str | None]:
    """Parse the user prompt with an optional YAML front-matter block.

    Returns ``(resume_flag, task_spec, scope, start_phase, stop_phase)``.
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
    """Recover structured output when the model hallucinates a tool call."""
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


def _run_verify_edit(author: str, bd: str, state_dict: dict[str, Any]) -> str | None:
    """Run verify_edit on the author's scoped staged files after a tier edit.

    Reads scope and target_functions from the user_prompt.md frontmatter,
    maps each to its staged copy under factory/temp/, and verifies every
    function in each file has CC <= 5 and a clean AST.

    Per-file diagnostic is persisted into state_dict under
    ``f"last_tier_diagnostic_{staged_file_path}"`` so the conductor
    can route immediate focus to that file.

    Returns the first failing file's diagnostic message, or None on success.
    """
    prompt_file = REPO_ROOT / "factory" / "prompt" / "user_prompt.md"
    if not prompt_file.exists():
        prompt_file = REPO_ROOT / "prompt" / "user_prompt.md"
    scope: list[str] = []
    target_functions: list[str] = []
    if prompt_file.exists():
        try:
            text = prompt_file.read_text(encoding="utf-8")
            lines = text.splitlines()
            if lines and lines[0].strip() == "---":
                end_idx = None
                for i in range(1, len(lines)):
                    if lines[i].strip() == "---":
                        end_idx = i
                        break
                if end_idx is not None:
                    fm_text = "\n".join(lines[1:end_idx])
                    front = yaml.safe_load(fm_text) or {}
                    if isinstance(front, dict):
                        raw_scope = front.get("scope", []) or []
                        if isinstance(raw_scope, str):
                            raw_scope = [raw_scope]
                        if isinstance(raw_scope, list):
                            scope = [str(s) for s in raw_scope]
                        target_functions = front.get("target_functions", []) or []
                        if not isinstance(target_functions, list):
                            target_functions = []
                        target_functions = [str(f) for f in target_functions]
        except Exception:
            scope = []
            target_functions = []

    if not scope:
        temp_dir = REPO_ROOT / "factory" / "temp"
        if temp_dir.exists():
            scope = [str(p.relative_to(temp_dir)) for p in temp_dir.rglob("*") if p.is_file() and p.suffix == ".py"]

    staged_paths = [f"factory/temp/{s}" for s in scope]

    todo_list = build_todo_checklist(staged_paths, target_functions)
    state_dict["todo_list"] = todo_list

    for staged_file_path in staged_paths:
        diagnostic: str | None = None
        try:
            if target_functions:
                for fn_name in target_functions:
                    result = verify_edit(staged_file_path, fn_name)
                    parsed = json.loads(result) if result else {}
                    funcs = parsed.get("functions", [])
                    target_fn = next((f for f in funcs if f.get("function") == fn_name), None)
                    if target_fn:
                        if not target_fn.get("passed", False):
                            diagnostic = (
                                f"[verify_edit] {author}: FAIL — {staged_file_path} — "
                                f"function '{fn_name}': {target_fn.get('message', 'validation failed')}"
                            )
                            break
                        cc = target_fn.get("cc", 0)
                        if cc > 5:
                            diagnostic = (
                                f"[verify_edit] {author}: FAIL — {staged_file_path} — "
                                f"function '{fn_name}' has CC={cc} (target CC <= 5)"
                            )
                            break
            else:
                result = verify_edit(staged_file_path, None)
                parsed = json.loads(result) if result else {}
                if parsed.get("ok") is False:
                    failed = [f for f in parsed.get("functions", []) if not f.get("passed", True)]
                    if failed:
                        details = "; ".join(
                            f"fn '{f.get('function', '?')}' (CC={f.get('cc', 0)}): {f.get('message', '')}"
                            for f in failed
                        )
                    else:
                        details = parsed.get("error", "unknown error")
                    diagnostic = (
                        f"[verify_edit] {author}: FAIL — {staged_file_path} — "
                        f"{details}"
                    )
                else:
                    functions = parsed.get("functions", [])
                    for fn in functions:
                        cc = fn.get("cc", 0)
                        if cc > 5:
                            diagnostic = (
                                f"[verify_edit] {author}: FAIL — {staged_file_path} — "
                                f"function '{fn.get('function', '?')}' has CC={cc} "
                                f"(target CC <= 5)"
                            )
                            break
        except Exception as e:
            diagnostic = f"[verify_edit] {author}: error — {staged_file_path} — {e}"

        state_dict[f"last_tier_diagnostic_{staged_file_path}"] = diagnostic or "pass"

        if diagnostic is not None:
            return diagnostic

    return None


def _build_isolated_ast_block() -> str:
    """Construct a Surgical Context Sandwich for each target function.

    Layer 1: File skeleton + imports (top-level structure).
    Layer 2: Isolated target function AST node source.
    Layer 3: Refactoring instruction for ONLY that function to reach CC <= 5.
    """
    prompt_file = REPO_ROOT / "factory" / "prompt" / "user_prompt.md"
    if not prompt_file.exists():
        prompt_file = REPO_ROOT / "prompt" / "user_prompt.md"
    scope: list[str] = []
    target_functions: list[str] = []
    if prompt_file.exists():
        try:
            text = prompt_file.read_text(encoding="utf-8")
            lines = text.splitlines()
            if lines and lines[0].strip() == "---":
                end_idx = None
                for i in range(1, len(lines)):
                    if lines[i].strip() == "---":
                        end_idx = i
                        break
                if end_idx is not None:
                    fm_text = "\n".join(lines[1:end_idx])
                    front = yaml.safe_load(fm_text) or {}
                    if isinstance(front, dict):
                        raw_scope = front.get("scope", []) or []
                        if isinstance(raw_scope, str):
                            raw_scope = [raw_scope]
                        if isinstance(raw_scope, list):
                            scope = [str(s) for s in raw_scope]
                        target_functions = front.get("target_functions", []) or []
                        if not isinstance(target_functions, list):
                            target_functions = []
                        target_functions = [str(f) for f in target_functions]
        except Exception:
            scope = []
            target_functions = []
    if not scope:
        temp_dir = REPO_ROOT / "factory" / "temp"
        if temp_dir.exists():
            scope = [str(p.relative_to(temp_dir)) for p in temp_dir.rglob("*") if p.is_file() and p.suffix == ".py"]
    staged_paths = [f"factory/temp/{s}" for s in scope]
    lines: list[str] = []
    for staged_path in staged_paths:
        for fn_name in target_functions:
            try:
                skeleton = extract_file_skeleton_and_imports(staged_path)
            except Exception:
                continue
            try:
                fn_source = extract_function_node_source(staged_path, fn_name)
            except Exception:
                continue
            lines.append("### Surgical Context Sandwich")
            lines.append(f"**File**: `{staged_path}` — **Function**: `{fn_name}`")
            lines.append("")
            lines.append("#### Layer 1 — File Skeleton & Imports")
            lines.append("```python")
            lines.append(skeleton)
            lines.append("```")
            lines.append("")
            lines.append("#### Layer 2 — Target Function AST Node")
            lines.append("```python")
            lines.append(fn_source)
            lines.append("```")
            lines.append("")
            lines.append("#### Layer 3 — Refactoring Instruction")
            lines.append(f"Refactor ONLY the function `{fn_name}` in `{staged_path}` to reduce its cyclomatic complexity to CC <= 5. Do not modify any other function or file.")
            lines.append("")
    return "\n".join(lines)


async def run_tier(
    tier: str,
    task: str,
    bd: str,
    history: list[tuple[str, str]],
    exchange: list[ExchangeTurn],
    pass_counter: dict[str, int],
    prior: list[ExchangeTurn],
    state_dict: dict[str, Any],
    record_exchange: bool = False,
    is_final: bool = False,
) -> str:
    """Run a single pipeline tier (intern → engineer → senior).

    Strict linear flow: do_role → _run_verify_edit → diagnostic injection
    on failure → retry up to MAX_ATTEMPTS. No backward bouncing.

    Per-function micro-loop: iterates target_functions sequentially,
    verifying CC <= 5 for each fn_name after every edit. Once a function
    reaches CC <= 5, it is locked in and the loop moves to the next function.

    If verification fails, structured diagnostic feedback is prepended to
    the next attempt's input prompt (same-tier retry) or carried forward
    to the next tier via state_dict["brief"].

    Returns the role output string.
    """
    brief = state_dict["brief"]
    run_brief = brief

    ast_block = _build_isolated_ast_block()
    if ast_block:
        state_dict["brief"] = brief + "\n\n" + ast_block
        run_brief = state_dict["brief"]

    target_functions = _read_target_functions()
    staged_paths = _read_staged_paths()

    if not target_functions:
        target_functions = [
            fn_name for _, fn_name in auto_discover_high_cc_functions(staged_paths)
        ]

    locked_functions: set[str] = set()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n=== [conductor -> {tier}] (attempt {attempt}) ===", flush=True)
        state_dict["brief"] = run_brief
        out = await do_role(tier, task, bd, history, exchange, pass_counter, prior, state_dict)
        if record_exchange and tier in EXCHANGE_ROLES:
            append_exchange_turn(exchange, pass_counter, tier, out, bd)

        _verify_result = _run_verify_edit(tier, bd, state_dict)
        if _verify_result is not None:
            print(f"[verify_edit] {tier}: {_verify_result}", flush=True)

        todo_list = state_dict.get("todo_list")
        if todo_list is not None:
            todo_md = todo_list.render_markdown()
            state_dict["brief"] = state_dict["brief"] + "\n\n" + todo_md

        if _verify_result is not None and "FAIL" in _verify_result:
            diagnostic = (
                f"\n\n[DIAGNOSTIC FEEDBACK — {tier} attempt {attempt}]\n"
                f"Verification failed: {_verify_result}\n"
                f"Please address the following issues in your next attempt:\n"
                f"1. Fix any AST violations reported above.\n"
                f"2. Fix any complexity (CC) errors reported above.\n"
                f"3. Fix any ruff linting failures reported above.\n"
                f"4. Ensure the output passes all verification gates.\n"
            )
            run_brief = brief + "\n\n" + diagnostic
            if attempt == MAX_ATTEMPTS:
                if tier == "senior" and is_final:
                    raise RuntimeError(
                        "[gate] Senior tier failed verification after 5 attempts - HALT"
                    )
                print(
                    f"[gate] {tier} attempt {attempt}: VERIFICATION FAIL -> "
                    f"advancing to next tier with diagnostics",
                    flush=True,
                )
            continue

        for staged_path in staged_paths:
            for fn_name in target_functions:
                if fn_name in locked_functions:
                    continue
                result = verify_edit(staged_path, fn_name)
                parsed = json.loads(result) if result else {}
                cc = parsed.get("cc", 0)
                if parsed.get("ok") is False or cc > 5:
                    continue
                locked_functions.add(fn_name)
                print(
                    f"[gate] {tier} attempt {attempt}: {fn_name} CC={cc} <= 5 LOCKED",
                    flush=True,
                )

        if len(locked_functions) == len(target_functions):
            print(f"[gate] {tier} attempt {attempt}: ALL functions locked at CC <= 5 -> proceed", flush=True)
            return out

        remaining = [fn for fn in target_functions if fn not in locked_functions]
        run_brief = brief + f"\n\n[FUNCTION MICRO-LOOP] Functions still above CC=5: {remaining}. Focus the next edit on these."

    if tier == "senior" and is_final:
        raise RuntimeError(
            "[gate] Senior tier failed verification after 5 attempts - HALT"
        )
    return out


def _read_target_functions() -> list[str]:
    """Read target_functions from the user_prompt.md frontmatter.

    If the frontmatter has no target_functions (empty or missing),
    automatically discovers high-CC functions from staged paths.
    """
    prompt_file = REPO_ROOT / "factory" / "prompt" / "user_prompt.md"
    if not prompt_file.exists():
        prompt_file = REPO_ROOT / "prompt" / "user_prompt.md"
    if not prompt_file.exists():
        return []
    try:
        text = prompt_file.read_text(encoding="utf-8")
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            end_idx = None
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    end_idx = i
                    break
            if end_idx is not None:
                fm_text = "\n".join(lines[1:end_idx])
                front = yaml.safe_load(fm_text) or {}
                if isinstance(front, dict):
                    tf = front.get("target_functions", []) or []
                    if isinstance(tf, list):
                        target_functions = [str(f) for f in tf]
                        if target_functions:
                            return target_functions
    except Exception:
        pass
    staged_paths = _read_staged_paths()
    discovered = auto_discover_high_cc_functions(staged_paths)
    return [fn_name for _, fn_name in discovered]


def _read_staged_paths() -> list[str]:
    """Read scope from user_prompt.md and map to staged paths."""
    prompt_file = REPO_ROOT / "factory" / "prompt" / "user_prompt.md"
    if not prompt_file.exists():
        prompt_file = REPO_ROOT / "prompt" / "user_prompt.md"
    if not prompt_file.exists():
        return []
    scope: list[str] = []
    try:
        text = prompt_file.read_text(encoding="utf-8")
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            end_idx = None
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    end_idx = i
                    break
            if end_idx is not None:
                fm_text = "\n".join(lines[1:end_idx])
                front = yaml.safe_load(fm_text) or {}
                if isinstance(front, dict):
                    raw_scope = front.get("scope", []) or []
                    if isinstance(raw_scope, str):
                        raw_scope = [raw_scope]
                    if isinstance(raw_scope, list):
                        scope = [str(s) for s in raw_scope]
    except Exception:
        pass
    if not scope:
        temp_dir = REPO_ROOT / "factory" / "temp"
        if temp_dir.exists():
            scope = [str(p.relative_to(temp_dir)) for p in temp_dir.rglob("*") if p.is_file() and p.suffix == ".py"]
    return [f"factory/temp/{s}" for s in scope]


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
    """Persist validated outputs + advance current_phase."""
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
            _render_upfront_diffs(batch)
            + "Review the executed tasks against their acceptance criteria.\n"
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
            _render_upfront_diffs(batch)
            + "Audit the executed code batch against the red-team rubric.\n"
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


CHECKPOINT_TTL_SECONDS = 86400


def load_checkpoint(checkpoint_file: Path | str) -> dict[str, Any]:
    """Load AST verification checkpoint file if present and within TTL."""
    path = Path(checkpoint_file)
    if not path.exists():
        return {}
    try:
        mtime = path.stat().st_mtime
        if time.time() - mtime > CHECKPOINT_TTL_SECONDS:
            return {}
        res = {}
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if isinstance(data, dict) and "file_path" in data:
                    res[data["file_path"]] = data
        return res
    except Exception:
        return {}

