---
Resume: false
bd: factory-self-refactor-cc-reduce
write_mode: staged
language: python
lint_command: uv run ruff check
start_phase: intern
stop_phase: senior
target_repo: /home/yapilwsl/arthityap/ai-factory
target_functions:
  - _affected_tests
scope:
  - factory/infra/gatekeeper.py
---

# EPIC
Reduce CC (Cyclomatic Complexity) to ≤5 for target function _affected_tests in factory/infra/gatekeeper.py.

## CONTEXT
The CC scanner (find_cc_nested.py, min-cc=6) identified a high-complexity violation:
- gatekeeper.py: `_affected_tests` (CC=12)

This function exceeds the project maximum of CC=5. Refactor using guard clauses, early returns, helper extraction, and single-responsibility decomposition. Do NOT alter public function signatures or break existing contracts.

## REFACTORING PATTERN TO FOLLOW
1. **Guard clauses first**: validate inputs and return early.
2. **Extract private helpers**: pull out nested loops/branches into private helper functions with CC≤3.
3. **Keep pure logic clean**: separate path processing from filesystem traversal.
4. **Preserve full signature & type annotations**: zero changes to public function signatures or parameters.

## DELIVERABLES
1. Refactor `_affected_tests` (factory/infra/gatekeeper.py) from CC=12 to ≤5.
2. The function must pass `uv run ruff check` with 0 errors.
3. The function must pass `find_cc_nested.py` verification (CC ≤ 5).

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
1. `find_cc_nested.py` reports CC ≤ 5 for `_affected_tests` in `factory/infra/gatekeeper.py`.
2. `uv run ruff check factory/infra/gatekeeper.py` passes.
3. All existing unit tests pass (`PYTHONPATH=. uv run pytest tests/`).
