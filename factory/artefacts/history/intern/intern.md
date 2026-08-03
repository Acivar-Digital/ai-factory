<!-- msg 0 | 2026-08-03-02:53:07 | user-prompt -->

## User

# EPIC
Reduce Cyclomatic Complexity (CC) to <= 5 for all listed target functions across factory/infra/ modules:

## CONTEXT
The CC scanner identified high-complexity violation:
1. red_team_passed (CC=6)

Refactor using guard clauses, early returns, helper extraction, and single-responsibility decomposition. Do NOT alter public function signatures or break existing contracts.

## REFACTORING PATTERN TO FOLLOW
1. Guard clauses first: validate inputs and return early.
2. Extract private helpers: pull out nested loops/branches into private helper functions with CC<=5.
3. Keep pure logic clean.
4. Preserve full signatures & type annotations: zero changes to public function signatures or parameters.

## DELIVERABLES
1. Refactor target function from CC > 5 to <= 5.
2. Code must pass uv run ruff check with 0 errors.
3. Code must pass find_cc_nested.py verification (CC <= 5).

### Surgical Context Sandwich
**File**: `factory/temp/factory/infra/pipeline.py` — **Function**: `_run_verify_edit`

#### Layer 1 — File Skeleton & Imports
```python
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
from factory.infra._runtime import RAW_OUTPUTS, PHASE_SUMMARIES, _PHASE_ORDER
from factory.infra.agent import load_skill, _load_role_messages, _recover_role_output, _coder_agent_id
from factory.infra.control import REPO_ROOT, TodoList, TodoItem
from factory.infra.virtual_ast_buffer import extract_file_skeleton_and_imports, extract_function_node_source
from factory.infra.exchange import update_status_board, save_exchange, format_exchange, append_exchange_turn, _render_history_md, ExchangeTurn
from factory.infra.models import ApprovedPlan, ApprovedTask, AuditResult, CodePassed, DraftPlan, ExecutablePlan, TaskBatch, WorkGroup, ParallelisableWorkplan
from factory.infra.output_sanitizer import clean_role_output, extract_model_json, extract_tool_call_payload
from factory.infra.state import save_state, record_phase
from factory.infra.context import compact_context_if_needed
from factory.infra.tools import wrap_injected_context
from factory.infra.tools_shell import verify_edit
from factory.infra.validation import EXCHANGE_ROLES
def _compute_cc(node: ast.AST) -> int:...
def _extract_condition_vars(node: ast.AST) -> list[str]:...
def generate_ast_decomposition_hint(file_path: str, function_name: str) -> str:...
def auto_discover_high_cc_functions(staged_paths: list[str], max_cc: int=5) -> list[tuple[str, str]]:...
def compute_dynamic_retry_budget(file_path: str, function_name: str) -> int:...
def build_todo_checklist(staged_paths: list[str], target_functions: list[str]) -> TodoList:...
def read_prompt(prompt_file: Path) -> tuple[bool, str, list[str], str | None, str | None]:...
def _recover_from_unexpected_behavior(role: str, e: UnexpectedModelBehavior, agent_id: str | None=None) -> str:...
async def do_role(role: str, task: str, bd: str, history: list[tuple[str, str]], exchange: list[ExchangeTurn], pass_counter: dict[str, int], prior: list[ExchangeTurn], state_dict: dict[str, Any]) -> str:...
async def record_coder(brief: str, bd: str, history: list[tuple[str, str]], prior: list[ExchangeTurn], state_dict: dict[str, Any], task_id: str | None=None) -> str:...
def _run_verify_edit(author: str, bd: str, state_dict: dict[str, Any], target_fn: str | None=None) -> str | None:...
def _build_isolated_ast_block(target_fn: str | None=None) -> str:...
def _persist_checkpoint(staged_path: str, fn_name: str, locked_functions: set[str]) -> None:...
def _extract_failure_summary(tier: str, attempt: int, verify_result: str, fn_name: str) -> str:...
def _render_cumulative_failure_ledger(failure_history: list[str]) -> str:...
async def run_tier(tier: str, task: str, bd: str, history: list[tuple[str, str]], exchange: list[ExchangeTurn], pass_counter: dict[str, int], prior: list[ExchangeTurn], state_dict: dict[str, Any], record_exchange: bool=False, is_final: bool=False) -> str:...
def _read_target_functions() -> list[str]:...
def _read_staged_paths() -> list[str]:...
def _assert_plan_gate_ok(history: list, bd: str, st: Any, is_forced_pass: bool=False) -> ExecutablePlan:...
def _sync_state(st: Any) -> None:...
def _checkpoint(phase: str, st: Any, stop_after: str | None, bd: str, exchange: list, history: list) -> bool:...
def load_checkpoint(checkpoint_file: Path | str) -> dict[str, Any]:...
```

#### Layer 2 — Target Function AST Node
```python
def _run_verify_edit(author: str, bd: str, state_dict: dict[str, Any], target_fn: str | None=None) -> str | None:
    """Run verify_edit on the author's scoped staged files after a tier edit.

    If target_fn is provided, only verifies that function in the staged paths.
    If target_fn is None, verifies all target_functions in staged paths.

    Per-file diagnostic is persisted into state_dict under
    ``f"last_tier_diagnostic_{staged_file_path}"`` so the conductor
    can route immediate focus to that file.

    Returns the first failing file's diagnostic message, or None on success.
    """
    prompt_file = REPO_ROOT / 'factory' / 'prompt' / 'user_prompt.md'
    if not prompt_file.exists():
        prompt_file = REPO_ROOT / 'prompt' / 'user_prompt.md'
    scope: list[str] = []
    target_functions: list[str] = []
    if prompt_file.exists():
        try:
            text = prompt_file.read_text(encoding='utf-8')
            lines = text.splitlines()
            if lines and lines[0].strip() == '---':
                end_idx = None
                for i in range(1, len(lines)):
                    if lines[i].strip() == '---':
                        end_idx = i
                        break
                if end_idx is not None:
                    fm_text = '\n'.join(lines[1:end_idx])
                    front = yaml.safe_load(fm_text) or {}
                    if isinstance(front, dict):
                        raw_scope = front.get('scope', []) or []
                        if isinstance(raw_scope, str):
                            raw_scope = [raw_scope]
                        if isinstance(raw_scope, list):
                            scope = [str(s) for s in raw_scope]
                        target_functions = front.get('target_functions', []) or []
                        if not isinstance(target_functions, list):
                            target_functions = []
                        target_functions = [str(f) for f in target_functions]
        except Exception:
            scope = []
            target_functions = []
    if not scope:
        temp_dir = REPO_ROOT / 'factory' / 'temp'
        if temp_dir.exists():
            scope = [str(p.relative_to(temp_dir)) for p in temp_dir.rglob('*') if p.is_file() and p.suffix == '.py']
    staged_paths = [f'factory/temp/{s}' for s in scope]
    functions_to_verify = [target_fn] if target_fn is not None else target_functions
    todo_list = build_todo_checklist(staged_paths, functions_to_verify)
    state_dict['todo_list'] = todo_list
    for staged_file_path in staged_paths:
        diagnostic: str | None = None
        try:
            if functions_to_verify:
                for fn_name in functions_to_verify:
                    full_path = REPO_ROOT / staged_file_path
                    orig_path = full_path.with_suffix(full_path.suffix + '.orig')
                    fn_exists = False
                    for check_path in [full_path, orig_path]:
                        if check_path.exists():
                            try:
                                tree = ast.parse(check_path.read_text(encoding='utf-8'))
                                if any((isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn_name for n in ast.walk(tree))):
                                    fn_exists = True
                                    break
                            except SyntaxError:
                                pass
                    if not fn_exists:
                        continue
                    result = verify_edit(staged_file_path, fn_name)
                    parsed = json.loads(result) if result else {}
                    if parsed.get('function_name') == fn_name:
                        cc = parsed.get('cc', 0)
                        ok = parsed.get('ok', False)
                        if ok is False or cc > 5:
                            diagnostic = f"[verify_edit] {author}: FAIL — {staged_file_path} — function '{fn_name}' has CC={cc} (target CC <= 5)" if cc > 5 else f"[verify_edit] {author}: FAIL — {staged_file_path} — function '{fn_name}' did not pass verification"
                            break
                        continue
                    if parsed.get('ok') is False:
                        diagnostic = f"[verify_edit] {author}: FAIL — {staged_file_path} — {parsed.get('error', 'validation error')}"
                        break
                    funcs = parsed.get('functions', [])
                    target_fn_match = next((f for f in funcs if f.get('function') == fn_name), None)
                    if target_fn_match is None:
                        diagnostic = f"[verify_edit] {author}: FAIL — {staged_file_path} — function '{fn_name}' not found or did not pass verification"
                        break
                    if not target_fn_match.get('passed', False):
                        diagnostic = f"[verify_edit] {author}: FAIL — {staged_file_path} — function '{fn_name}': {target_fn_match.get('message', 'validation failed')}"
                        break
                    cc = target_fn_match.get('cc', 0)
                    if cc > 5:
                        diagnostic = f"[verify_edit] {author}: FAIL — {staged_file_path} — function '{fn_name}' has CC={cc} (target CC <= 5)"
                        break
            else:
                result = verify_edit(staged_file_path, None)
                parsed = json.loads(result) if result else {}
                if parsed.get('ok') is False:
                    failed = [f for f in parsed.get('functions', []) if not f.get('passed', True)]
                    if failed:
                        details = '; '.join((f"fn '{f.get('function', '?')}' (CC={f.get('cc', 0)}): {f.get('message', '')}" for f in failed))
                    else:
                        details = parsed.get('error', 'unknown error')
                    diagnostic = f'[verify_edit] {author}: FAIL — {staged_file_path} — {details}'
                else:
                    functions = parsed.get('functions', [])
                    for fn in functions:
                        cc = fn.get('cc', 0)
                        if cc > 5:
                            diagnostic = f"[verify_edit] {author}: FAIL — {staged_file_path} — function '{fn.get('function', '?')}' has CC={cc} (target CC <= 5)"
                            break
        except Exception as e:
            diagnostic = f'[verify_edit] {author}: error — {staged_file_path} — {e}'
        state_dict[f'last_tier_diagnostic_{staged_file_path}'] = diagnostic or 'pass'
        if diagnostic is not None:
            return diagnostic
    return None
```

#### Layer 3 — Refactoring Instruction
Refactor ONLY the function `_run_verify_edit` in `factory/temp/factory/infra/pipeline.py` to reduce its cyclomatic complexity to CC <= 5. Do not modify any other function or file.

#### Decomposition Hint
Function `_run_verify_edit` has CC=46 (above 8). Suggested decompositions:
  - Extract condition 'prompt_file' into _helper__run_verify_edit_guard()
  - Extract condition 'scope' into _helper__run_verify_edit_guard()
  - Extract loop body into _helper__run_verify_edit_loop()


---

<!-- msg 1 | 2026-08-03-02:53:51 | text+tool-call -->

I'll start by recording my plan (mandatory Turn 1), then read the target file and the `verify_edit` contract to inform the decomposition.

### Tool call: `remember`

- **note**: PLAN: Refactor _run_verify_edit in factory/temp/factory/infra/pipeline.py from CC=46 to <=5.
Steps:
1. Read factory/temp/factory/infra/pipeline.py (target function context + verify_edit import).
2. Read factory/infra/tools_shell.py to learn verify_edit signature + JSON output contract (fields: ok, cc, function_name, functions[], error, passed, message) so parsing stays correct.
3. Design decomposition into private _-prefixed helpers, each CC<=5:
   - _run_verify_edit : thin orchestrator (parse metadata -> build staged_paths -> build todo -> loop verify -> return first diagnostic/None)
   - _parse_prompt_metadata(prompt_file) -> (scope, target_functions)
   - _compute_staged_paths(scope) -> list[str]
   - _verify_file_diagnostics(author, staged_file_path, functions_to_verify) -> str|None
   - _verify_named_function_result(author, staged_file_path, parsed) -> str|None  (handles function_name==fn_name shape)
   - _verify_function_entry_result(author, staged_file_path, parsed, fn_name) -> str|None (handles ok/functions shape)
   - _verify_all_functions(author, staged_file_path) -> str|None  (verify_edit(None) branch)
4. Apply via replace_function (target _run_verify_edit + insert helpers) on staged copy only.
5. Run ruff check + verify_edit to confirm CC<=5 and 0 ruff errors.

---

<!-- msg 2 | 2026-08-03-02:53:51 | tool-return -->

### Tool result: `remember`

remember: note recorded to role 'intern' history (persists across turns).

[TOOL CALL 1/15]

---

<!-- msg 3 | 2026-08-03-02:53:55 | tool-call -->

### Tool call: `read_file`

- **relative_path**: `factory/temp/factory/infra/pipeline.py`
- **start_line**: 1
- **end_line**: 80

### Tool call: `read_file`

- **relative_path**: `factory/infra/tools_shell.py`
- **start_line**: 1
- **end_line**: 60

---

<!-- msg 4 | 2026-08-03-02:53:55 | tool-return -->

### Tool result: `read_file`

[scrubbed for context hygiene: 3614 bytes from read_file]

### Tool result: `read_file`

[scrubbed for context hygiene: 3565 bytes from read_file]

---

<!-- msg 5 | 2026-08-03-02:54:01 | text+tool-call -->

Let me read the `verify_edit` function definition and locate the exact line range of `_run_verify_edit` in the staged file.

### Tool call: `batch_read`

- **paths**: - **factory/infra/tools_shell.py**: 60-241
- **factory/temp/factory/infra/pipeline.py**: 980-1185
- **line_ranges**: - **factory/infra/tools_shell.py**: 60-241
- **factory/temp/factory/infra/pipeline.py**: 1080-1185

---

<!-- msg 6 | 2026-08-03-02:54:01 | retry-prompt -->

### retry-prompt

{
  "content": [
    {
      "type": "list_type",
      "loc": [
        "paths"
      ],
      "msg": "Input should be a valid array",
      "input": {
        "factory/infra/tools_shell.py": "60-241",
        "factory/temp/factory/infra/pipeline.py": "980-1185"
      }
    }
  ],
  "tool_name": "batch_read",
  "tool_call_id": "chatcmpl-tool-314a3ac643824bce9abab76f7bd8a3d3",
  "timestamp": "2026-08-03T02:54:01.368792Z",
  "part_kind": "retry-prompt"
}

---

<!-- msg 7 | 2026-08-03-02:54:04 | tool-call -->

### Tool call: `batch_read`

- **paths**: - `factory/infra/tools_shell.py`
- `factory/temp/factory/infra/pipeline.py`
- **line_ranges**: - **factory/infra/tools_shell.py**: 60-241
- **factory/temp/factory/infra/pipeline.py**: 1080-1185

---

<!-- msg 8 | 2026-08-03-02:54:04 | tool-return -->

### Tool result: `batch_read`

[scrubbed for context hygiene: 14074 bytes from batch_read]

---

<!-- msg 9 | 2026-08-03-02:54:11 | text+tool-call -->

I found the `verify_edit` contract. Now let me find the exact line range of `_run_verify_edit` in the staged file.

### Tool call: `batch_read`

- **paths**: - `factory/temp/factory/infra/pipeline.py`
- `factory/infra/pipeline.py`
- **line_ranges**: - **factory/temp/factory/infra/pipeline.py**: 1-1
- **factory/infra/pipeline.py**: 1-1

### Tool call: `shell`

- **cmd**: `grep -n "def _run_verify_edit" factory/temp/factory/infra/pipeline.py`
- **description**: Find _run_verify_edit line number in staged file

---

<!-- msg 10 | 2026-08-03-02:54:11 | retry-prompt+tool-return -->

### Tool result: `batch_read`

[scrubbed for context hygiene: 819 bytes from batch_read]

### retry-prompt

{
  "content": "Unknown tool name: 'shell'. Available tools: 'add_constant', 'add_import', 'batch_read', 'delete_file', 'final_result', 'move_symbol', 'read_file', 'remember', 'rename_file', 'replace_function', 'replace_text', 'verify_edit', 'write_file'",
  "tool_name": "shell",
  "tool_call_id": "chatcmpl-tool-2b7f6f53651d40bdade1dc52040ee0de",
  "timestamp": "2026-08-03T02:54:11.004108Z",
  "part_kind": "retry-prompt"
}

---

<!-- msg 11 | 2026-08-03-02:54:19 | text+tool-call -->

I have the `verify_edit` contract. Now let me locate `_run_verify_edit` lines in the staged file by reading a range.

### Tool call: `read_file`

- **relative_path**: `factory/temp/factory/infra/pipeline.py`
- **start_line**: 500
- **end_line**: 620

---

<!-- msg 12 | 2026-08-03-02:54:19 | tool-return -->

### Tool result: `read_file`

[scrubbed for context hygiene: 7184 bytes from read_file]

---

<!-- msg 13 | 2026-08-03-02:54:27 | text+tool-call -->

I have lines 500-585. Let me read backward to find the function's `def` line and the prompt-file parsing block above it.

### Tool call: `read_file`

- **end_line**: 499
- **relative_path**: `factory/temp/factory/infra/pipeline.py`
- **start_line**: 420

---

<!-- msg 14 | 2026-08-03-02:54:27 | tool-return -->

### Tool result: `read_file`

[scrubbed for context hygiene: 4777 bytes from read_file]

---

<!-- msg 15 | 2026-08-03-02:54:30 | tool-call -->

### Tool call: `read_file`

- **end_line**: 620
- **relative_path**: `factory/temp/factory/infra/pipeline.py`
- **start_line**: 499

---

<!-- msg 16 | 2026-08-03-02:54:30 | tool-return -->

### Tool result: `read_file`

[scrubbed for context hygiene: 7247 bytes from read_file]

---

<!-- msg 17 | 2026-08-03-02:54:34 | text+tool-call -->

Let me find the exact `def _run_verify_edit` line and read its full body.

### Tool call: `read_file`

- **end_line**: 498
- **relative_path**: `factory/temp/factory/infra/pipeline.py`
- **start_line**: 440

---

<!-- msg 18 | 2026-08-03-02:54:34 | tool-return -->

### Tool result: `read_file`

[scrubbed for context hygiene: 3695 bytes from read_file]

---

<!-- msg 19 | 2026-08-03-02:54:37 | tool-call -->

### Tool call: `read_file`

- **end_line**: 590
- **relative_path**: `factory/temp/factory/infra/pipeline.py`
- **start_line**: 560

---

<!-- msg 20 | 2026-08-03-02:54:37 | tool-return -->

### Tool result: `read_file`

File read: factory/temp/factory/infra/pipeline.py

---

<!-- msg 21 | 2026-08-03-02:54:50 | text+tool-call -->

I have the full function body (ends at line 585, next function at 588). Let me capture the exact `def` line and the prompt-metadata parsing block (lines 440-446).

### Tool call: `read_file`

- **end_line**: 446
- **relative_path**: `factory/temp/factory/infra/pipeline.py`
- **start_line**: 439

---

<!-- msg 22 | 2026-08-03-02:54:51 | tool-return -->

### Tool result: `read_file`


---
Since you are stateless across turns, you may call `remember("<note>")` to record anything you need to execute correctly on your next turn (e.g. a focused slice, an edit decision, or a collision to avoid). Use `remember`, not `bd`.=== File read: factory/temp/factory/infra/pipeline.py (lines 439-446 of 1185) ===
439:     Returns the first failing file's diagnostic message, or None on success.
440:     """
441:     prompt_file = REPO_ROOT / "factory" / "prompt" / "user_prompt.md"
442:     if not prompt_file.exists():
443:         prompt_file = REPO_ROOT / "prompt" / "user_prompt.md"
444:     scope: list[str] = []
445:     target_functions: list[str] = []
446:     if prompt_file.exists():
---
Tip: Use batch_read for broad discovery; read_file is for targeted line reads only.
batch_read format: line_ranges is ONE contiguous 'start-end' range per file (e.g. {"src/foo.py": "400-500"}). NEVER use comma-joined multi-segments like '400, 600-650, 760-800' — that is a malformed range and the call fails. For non-contiguous slices, make separate batch_read calls (one range each).

[TOOL CALL 11/15]