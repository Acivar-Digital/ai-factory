"""Pipeline orchestration module containing all gate functions and the phase loop."""
from __future__ import annotations

import ast
import json
import os
import re
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
    load_skill, _load_role_messages, _recover_role_output, _intern_agent_id,
)
from factory.infra.control import (
    REPO_ROOT, TodoList, TodoItem,
)
from factory.infra.virtual_ast_buffer import (
    extract_file_skeleton_and_imports,
    extract_function_node_source,
)
from factory.infra.exchange import (
    update_status_board, save_exchange,
    format_exchange, append_exchange_turn,
    _render_history_md,
    ExchangeTurn,
)
from factory.infra.models import (
    ApprovedPlan, ApprovedTask, AuditResult, CodePassed,
    DraftPlan, ExecutablePlan, TaskBatch, WorkGroup, ParallelisableWorkplan,
)
from factory.infra.output_sanitizer import (
    clean_role_output, extract_model_json, extract_tool_call_payload,
)
from factory.infra.state import save_state, record_phase
from factory.infra.context import compact_context_if_needed
from factory.infra.tools import wrap_injected_context
from factory.infra.tools_shell import verify_edit
from factory.infra.validation import EXCHANGE_ROLES

RESUME_RE = re.compile(r"^Resume:\s*(true|false)\s*$", re.IGNORECASE)
MAX_ATTEMPTS = 1


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


def _extract_condition_vars(node: ast.AST) -> list[str]:
    """Collect variable names referenced in an AST condition node."""
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.append(child.id)
    return names


def generate_ast_decomposition_hint(file_path: str, function_name: str) -> str:
    """Parse file_path, find function_name, and return a decomposition hint.

    If the function's cyclomatic complexity exceeds 8, scans inner ``if``
    statements, loops, and nested call nodes to suggest specific helper
    function extractions (e.g. ``_helper_<name>()``).

    Returns a formatted hint string, or an empty string if CC <= 8.
    """
    path = Path(file_path)
    if not path.exists():
        return ""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            cc = _compute_cc(node)
            if cc <= 8:
                return ""
            suggestions: list[str] = []
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.If):
                    cond_vars = _extract_condition_vars(child.test)
                    if cond_vars:
                        suggestions.append(
                            f"Extract condition '{cond_vars[0]}' into _helper_{function_name}_guard()"
                        )
                elif isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
                    suggestions.append(
                        f"Extract loop body into _helper_{function_name}_loop()"
                    )
                elif isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    callee = child.func.id
                    if callee != function_name and not callee.startswith("_helper_"):
                        suggestions.append(
                            f"Extract call to '{callee}' into _helper_{function_name}_{callee}()"
                        )
            unique = []
            seen = set()
            for s in suggestions:
                if s not in seen:
                    seen.add(s)
                    unique.append(s)
            if not unique:
                return f"Function `{function_name}` has CC={cc}. Consider splitting into smaller helpers."
            hint_lines = [f"Function `{function_name}` has CC={cc} (above 8). Suggested decompositions:"]
            for s in unique:
                hint_lines.append(f"  - {s}")
            return "\n".join(hint_lines)
    return ""


def auto_discover_high_cc_functions(staged_paths: list[str], max_cc: int = 5) -> list[tuple[str, str]]:
    """Scan staged_paths for functions with cyclomatic complexity exceeding max_cc.

    Returns a list of ``(staged_file_path, function_name)`` tuples for every
    ``FunctionDef`` / ``AsyncFunctionDef`` where CC > max_cc, sorted in
    ascending order of their initial CC score so lower-CC functions are
    refactored before high-CC functions.
    """
    results: list[tuple[str, str, int]] = []
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
                    results.append((staged_path, node.name, cc))
    results.sort(key=lambda item: item[2])
    return [(path, name) for path, name, _ in results]


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
                if parsed.get("function_name") == fn_name:
                    cc = parsed.get("cc", 0)
                    ok = parsed.get("ok", False)
                    passed = ok and cc <= 5
                    items.append(
                        TodoItem(
                            file_path=staged_file_path,
                            function_name=fn_name,
                            target_cc=5,
                            current_cc=cc,
                            passed=passed,
                        )
                    )
                    continue
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
    """Run one role, seed the first intern pass, append to history + exchange."""
    brief = state_dict["brief"]
    seeded = state_dict["seeded"]
    run_brief = brief
    if role == "intern" and prior and not seeded:
        run_brief = brief + "\n\n" + wrap_injected_context(
            format_exchange(prior), label="resumed_exchange"
        )
        state_dict["seeded"] = True

    update_status_board(history, role, bd)
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


async def record_intern(
    brief: str,
    bd: str,
    history: list[tuple[str, str]],
    prior: list[ExchangeTurn],
    state_dict: dict[str, Any],
    task_id: str | None = None
) -> str:
    """Run the intern and record it in `history` (so the status board shows it)."""
    seeded = state_dict["seeded"]
    run_brief = brief
    if prior and not seeded:
        run_brief = brief + "\n\n" + wrap_injected_context(
            format_exchange(prior), label="resumed_exchange"
        )
        state_dict["seeded"] = True
    update_status_board(history, "intern", bd)
    try:
        out = await load_skill("intern", run_brief, bd, task_id=task_id)
    except UnexpectedModelBehavior as e:
        out = _recover_from_unexpected_behavior("intern", e, agent_id=_intern_agent_id(task_id))
    out_md = PHASE_SUMMARIES.get("intern", out)
    history.append(("intern", out_md))
    PHASE_SUMMARIES["intern"] = out_md
    update_status_board(history, "intern", bd)
    return out


def _run_verify_edit(author: str, bd: str, state_dict: dict[str, Any], target_fn: str | None = None) -> str | None:
    """Run verify_edit on the author's scoped staged files after a tier edit.

    If target_fn is provided, only verifies that function in the staged paths.
    If target_fn is None, verifies all target_functions in staged paths.

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

    functions_to_verify = [target_fn] if target_fn is not None else target_functions

    todo_list = build_todo_checklist(staged_paths, functions_to_verify)
    state_dict["todo_list"] = todo_list

    for staged_file_path in staged_paths:
        diagnostic: str | None = None
        try:
            if functions_to_verify:
                for fn_name in functions_to_verify:
                    full_path = REPO_ROOT / staged_file_path
                    orig_path = full_path.with_suffix(full_path.suffix + ".orig")
                    fn_exists = False
                    for check_path in [full_path, orig_path]:
                        if check_path.exists():
                            try:
                                tree = ast.parse(check_path.read_text(encoding="utf-8"))
                                if any(
                                    isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                                    and n.name == fn_name
                                    for n in ast.walk(tree)
                                ):
                                    fn_exists = True
                                    break
                            except SyntaxError:
                                pass
                    if not fn_exists:
                        continue
                    result = verify_edit(staged_file_path, fn_name)
                    parsed = json.loads(result) if result else {}
                    if parsed.get("function_name") == fn_name:
                        cc = parsed.get("cc", 0)
                        ok = parsed.get("ok", False)
                        if ok is False or cc > 5:
                            diagnostic = (
                                f"[verify_edit] {author}: FAIL — {staged_file_path} — "
                                f"function '{fn_name}' has CC={cc} (target CC <= 5)"
                                if cc > 5
                                else f"[verify_edit] {author}: FAIL — {staged_file_path} — "
                                f"function '{fn_name}' did not pass verification"
                            )
                            break
                        continue
                    if parsed.get("ok") is False:
                        diagnostic = (
                            f"[verify_edit] {author}: FAIL — {staged_file_path} — "
                            f"{parsed.get('error', 'validation error')}"
                        )
                        break
                    funcs = parsed.get("functions", [])
                    target_fn_match = next((f for f in funcs if f.get("function") == fn_name), None)
                    if target_fn_match is None:
                        diagnostic = (
                            f"[verify_edit] {author}: FAIL — {staged_file_path} — "
                            f"function '{fn_name}' not found or did not pass verification"
                        )
                        break
                    if not target_fn_match.get("passed", False):
                        diagnostic = (
                            f"[verify_edit] {author}: FAIL — {staged_file_path} — "
                            f"function '{fn_name}': {target_fn_match.get('message', 'validation failed')}"
                        )
                        break
                    cc = target_fn_match.get("cc", 0)
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


def _build_isolated_ast_block(target_fn: str | None = None) -> str:
    """Construct a Surgical Context Sandwich for target function(s).

    If target_fn is provided, generates the sandwich for ONLY that function.
    If target_fn is None, generates for all target_functions.

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
    functions_to_process = [target_fn] if target_fn is not None else target_functions
    for staged_path in staged_paths:
        for fn_name in functions_to_process:
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
            try:
                hint = generate_ast_decomposition_hint(staged_path, fn_name)
                if hint:
                    lines.append("")
                    lines.append("#### Decomposition Hint")
                    lines.append(hint)
            except Exception:
                pass
            lines.append("")
    return "\n".join(lines)


def _persist_checkpoint(staged_path: str, fn_name: str, locked_functions: set[str]) -> None:
    """Atomically persist locked_functions and state to checkpoint_state.json."""
    reports_dir = REPO_ROOT / "factory" / "orch" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = reports_dir / "checkpoint_state.json"
    state = {
        "locked_functions": sorted(locked_functions),
        "staged_path": staged_path,
        "function_name": fn_name,
    }
    tmp = checkpoint_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, checkpoint_path)


def _extract_failure_summary(tier: str, attempt: int, verify_result: str, fn_name: str) -> str:
    """Extract a concise 2-line failure summary from a verify_edit diagnostic.

    Returns a string like:
    "Attempt 1 [intern]: Function '_affected_tests' failed CC check: CC=8 (target <= 5)."
    """
    reason = verify_result
    for prefix in (
        "[verify_edit] intern: FAIL — ",
        "[verify_edit] engineer: FAIL — ",
        "[verify_edit] senior: FAIL — ",
    ):
        if prefix in reason:
            reason = reason.split(prefix, 1)[1]
            break
    else:
        for prefix in (
            "[verify_edit] intern: ",
            "[verify_edit] engineer: ",
            "[verify_edit] senior: ",
        ):
            if prefix in reason:
                reason = reason.split(prefix, 1)[1]
                break

    fn_part = fn_name if fn_name else "unknown"
    return f"Attempt {attempt} [{tier}]: Function '{fn_part}' {reason}."


def _render_cumulative_failure_ledger(failure_history: list[str]) -> str:
    """Render a [CUMULATIVE FAILURE LEDGER] block from all recorded entries."""
    lines = [
        "[CUMULATIVE FAILURE LEDGER — DO NOT REPEAT THESE FAILURE PATHS]",
    ]
    for entry in failure_history:
        lines.append(f"• {entry}")
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

    A cumulative failure ledger is maintained in state_dict["failure_history"]
    and rendered into the brief for subsequent attempts and tiers.

    Before each tier attempt, compact_context_if_needed is called to
    keep the brief within token budget.

    The 15 write failure halt rule enforces that if a target function
    reaches 15 write/replace verification failures across attempts,
    a RuntimeError is raised to signal a harness/prompt instruction mismatch.

    Returns the role output string.
    """
    brief = state_dict["brief"]
    run_brief = brief

    state_dict.setdefault("failure_history", [])
    state_dict.setdefault("write_failure_count", {})

    target_functions = _read_target_functions()
    staged_paths = _read_staged_paths()

    if not target_functions:
        target_functions = [
            fn_name for _, fn_name in auto_discover_high_cc_functions(staged_paths)
        ]

    def _get_cc_for_fn(fn_name: str) -> int:
        for staged_path in staged_paths:
            try:
                source = Path(staged_path).read_text(encoding="utf-8")
                tree = ast.parse(source, filename=staged_path)
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
                    return _compute_cc(node)
        return 0

    target_functions.sort(key=_get_cc_for_fn)

    locked_functions: set[str] = set()

    for fn_name in target_functions:
        if fn_name in locked_functions:
            continue

        # FAIL-LOUDLY FIX: Do NOT auto-lock functions based on stale staged file CC.
        # The ONLY acceptable pre-check is whether the function was ALREADY
        # locked in via checkpoint_state.json in a prior completed job.
        # If the agent did not explicitly edit the function in THIS run,
        # verify_edit must confirm the current state -- not a stale file.

        ast_block = _build_isolated_ast_block(target_fn=fn_name)
        if ast_block:
            state_dict["brief"] = brief + "\n\n" + ast_block
            run_brief = state_dict["brief"]

        fn_write_failures = state_dict["write_failure_count"].setdefault(fn_name, 0)

        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"\n=== [conductor -> {tier}] (attempt {attempt}) ===", flush=True)
            run_brief = await compact_context_if_needed(run_brief)
            state_dict["brief"] = run_brief
            out = await do_role(tier, task, bd, history, exchange, pass_counter, prior, state_dict)

            # FAIL-LOUDLY GATE: if the agent returned a blocked/failed status, HALT immediately.
            # The agent output must be a valid JSON dict with status == "done".
            # If status is "blocked" or any other non-"done" value, the agent did not complete
            # its task -- do NOT proceed to verification or escalate to the next tier.
            import json as _json
            try:
                _agent_result = _json.loads(out)
                if isinstance(_agent_result, dict) and _agent_result.get("status") != "done":
                    _agent_notes = _agent_result.get("notes", _agent_result.get("error", ""))
                    raise RuntimeError(
                        f"[HALT] {tier} tier: agent returned status "
                        f"{repr(_agent_result.get('status'))} (expected 'done'). "
                        f"Notes: {_agent_notes}. "
                        f"HALTING -- do not escalate to next tier or proceed with verification."
                    )
            except (ValueError, TypeError):
                pass  # not JSON output -- acceptable for free-form agent output
            if record_exchange and tier in EXCHANGE_ROLES:
                append_exchange_turn(exchange, pass_counter, tier, out, bd)

            _verify_result = _run_verify_edit(tier, bd, state_dict, target_fn=fn_name)
            if _verify_result is not None:
                print(f"[verify_edit] {tier}: {_verify_result}", flush=True)

            todo_list = state_dict.get("todo_list")
            if todo_list is not None:
                todo_md = todo_list.render_markdown()
                state_dict["brief"] = state_dict["brief"] + "\n\n" + todo_md

            if _verify_result is not None and "FAIL" in _verify_result:
                fn_write_failures += 1
                state_dict["write_failure_count"][fn_name] = fn_write_failures
                if fn_write_failures >= 15:
                    raise RuntimeError(
                        "[HALT] Target function exceeded 15 write retries — Harness/AST verification failure. Intervene on harness instructions."
                    )
                failure_summary = _extract_failure_summary(tier, attempt, _verify_result, fn_name)
                state_dict["failure_history"].append(failure_summary)
                ledger_block = _render_cumulative_failure_ledger(state_dict["failure_history"])
                diagnostic = (
                    f"\n\n[DIAGNOSTIC FEEDBACK — {tier} attempt {attempt}]\n"
                    f"Verification failed: {_verify_result}\n"
                    f"Please address the following issues in your next attempt:\n"
                    f"1. Fix any AST violations reported above.\n"
                    f"2. Fix any complexity (CC) errors reported above.\n"
                    f"3. Fix any ruff linting failures reported above.\n"
                    f"4. Ensure the output passes all verification gates.\n"
                )
                run_brief = brief + "\n\n" + ledger_block + "\n\n" + diagnostic
                state_dict["brief"] = brief + "\n\n" + ledger_block + "\n\n" + diagnostic
                if attempt == MAX_ATTEMPTS:
                    raise RuntimeError(
                        f"[HALT] {tier} tier attempt {attempt} failed verification: {_verify_result}"
                    )
                continue

            for staged_path in staged_paths:
                result = verify_edit(staged_path, fn_name)
                parsed = json.loads(result) if result else {}
                cc = parsed.get("cc", 0)
                if parsed.get("ok") is False or cc > 5:
                    continue
                locked_functions.add(fn_name)
                _persist_checkpoint(staged_path, fn_name, locked_functions)
                print(
                    f"[conductor -> {tier}] Locked in function {fn_name} (CC <= 5)",
                    flush=True,
                )
                break

            if fn_name in locked_functions:
                break

        if fn_name not in locked_functions:
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
    """The intern MUST NOT run on a missing / malformed / failing approved plan."""
    approved = RAW_OUTPUTS.get("engineer_plan") or next(
        (v for r, v in reversed(history) if r == "engineer_plan"), None
    )
    if not approved:
        raise RuntimeError(
            "[PLAN-GATE] HALT: no engineer_plan output — intern/engineer "
            "chain produced no ApprovedPlan. Intern will NOT run."
        )
    try:
        plan_eval = clean_role_output(approved, ApprovedPlan)
    except Exception as exc:
        raise RuntimeError(
            f"[PLAN-GATE] HALT: engineer_plan output was unparseable as "
            f"ApprovedPlan ({exc!r}). Intern will NOT run."
        ) from exc
    if plan_eval is None:
        raise RuntimeError(
            "[PLAN-GATE] HALT: ApprovedPlan parsed to None. Intern will NOT run."
        )
    draft_json = RAW_OUTPUTS.get("intern") or next(
        (v for r, v in reversed(history) if r == "intern"), None
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
            "[PLAN-GATE] HALT: engineer_plan approved=False. Intern will NOT run."
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
        plan_file = artefacts_dir() / "workplan" / "intern" / "intern.json"
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        from factory.tools.normalize_json_escapes import remap
        text = json.dumps(draft_dict, indent=2, ensure_ascii=False)
        normalized_text = remap(text)
        plan_file.write_text(normalized_text, encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Failed to write merged intern.json: {e}", flush=True)

    RAW_OUTPUTS["intern"] = json.dumps(draft_dict)

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
            f"Every ApprovedTask.id MUST be 'intern01', 'intern02', … unique. "
            f"Intern will NOT run."
        ) from exc

    print("[PLAN-GATE] OK: engineer_plan approved with 0 failed blockers.", flush=True)
    return exe_plan


def _sync_state(st: Any) -> None:
    """Capture validated RAW_OUTPUTS into the durable OrchestratorState."""
    draft_json = RAW_OUTPUTS.get("intern")
    if draft_json:
        st.draft = DraftPlan.model_validate_json(draft_json)
    approved_json = RAW_OUTPUTS.get("engineer_plan")
    if approved_json:
        st.approved = ApprovedPlan.model_validate_json(approved_json)
    batch_json = RAW_OUTPUTS.get("intern")
    if batch_json:
        try:
            st.batch = TaskBatch.model_validate_json(batch_json)
        except Exception:
            pass
    code_passed_json = RAW_OUTPUTS.get("senior_review")
    if code_passed_json:
        try:
            st.code_passed = CodePassed.model_validate_json(code_passed_json)
        except Exception:
            pass
    audit_json = RAW_OUTPUTS.get("senior")
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


def revert_state(checkpoint_file: Path | str | None = None) -> dict[str, Any]:
    """Restore orchestrator state from the last crash-resume checkpoint.

    Mirrors ``_persist_checkpoint``: reads ``factory/orch/reports/checkpoint_state.json``
    (atomically written via ``os.replace``) and returns the persisted dict containing
    ``locked_functions``, ``staged_path`` and ``function_name``.

    Contract (consistent with ``load_checkpoint``):
      - Missing file -> ``{}`` (no checkpoint has been persisted yet).
      - Stale file (older than ``CHECKPOINT_TTL_SECONDS``) -> ``{}``.
      - Corrupt JSON -> raises ``json.JSONDecodeError`` (fail loudly; never silently swallowed).
    """
    if checkpoint_file is None:
        checkpoint_file = REPO_ROOT / "factory" / "orch" / "reports" / "checkpoint_state.json"
    path = Path(checkpoint_file)
    if not path.exists():
        return {}
    mtime = path.stat().st_mtime
    if time.time() - mtime > CHECKPOINT_TTL_SECONDS:
        return {}
    raw = path.read_text(encoding="utf-8")
    state = json.loads(raw)
    if not isinstance(state, dict):
        raise ValueError(f"[checkpoint] {path} did not contain a JSON object")
    return state

