---
Resume: false
bd: factory-self-refactor-cc-reduce-check-plan-invariants
write_mode: staged
language: python
lint_command: uv run ruff check
start_phase: senior
stop_phase: senior
target_repo: /home/yapilwsl/arthityap/ai-factory
target_functions:
  - _unwrap_tool_output
scope:
  - factory/infra/ledger.py
---

# EPIC
Reduce CC (Cyclomatic Complexity) to ≤10 for target function _unwrap_tool_output in factory/infra/ledger.py.

## CONTEXT
The CC scanner (find_cc_nested.py, min-cc=11) identified a high-complexity violation:
- ledger.py: `_unwrap_tool_output` (CC=13)

This function exceeds the project maximum of CC=10. Refactor using guard clauses, early returns, helper extraction, and single-responsibility decomposition. Do NOT alter public function signatures or break existing contracts.

## REFACTORING PATTERN TO FOLLOW
1. **Guard clauses first**: validate inputs and return early.
2. **Extract private helpers**: pull out nested loops/branches into private helper functions with CC≤3.
3. **Keep pure logic clean**: separate path processing from dependency traversal.
4. **Preserve full signature & type annotations**: zero changes to public function signatures or parameters.

## DELIVERABLES
1. Refactor `_unwrap_tool_output` (factory/infra/ledger.py) from CC=13 to ≤10.
2. The function must pass `uv run ruff check` with 0 errors.
3. The function must pass `find_cc_nested.py` verification (CC ≤ 10).

## REQUIREMENTS & CONSTRAINTS
- Strict Pydantic v2 syntax; no raw dicts for business logic.
- AST-preserving edits (preserve existing docstrings and high-value comments).
- Surgical diffs; zero unrequested refactoring.
- Fail loudly on errors; no silent exception swallowing (`except: pass`).

## ANTI-PATTERNS (CRITICAL)
- Do NOT use `except: pass`.
- Do NOT modify files outside the declared `scope`.
- Do NOT alter function signatures or return types.

## ACCEPTANCE
1. `find_cc_nested.py` reports CC ≤ 10 for `_unwrap_tool_output` in `factory/infra/ledger.py`.
2. `uv run ruff check factory/infra/ledger.py` passes.
3. All existing unit tests pass (`PYTHONPATH=. uv run pytest tests/`).
