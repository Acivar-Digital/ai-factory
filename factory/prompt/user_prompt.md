---
Resume: false
bd: factory-self-refactor-cc-reduce-epic
write_mode: staged
language: python
lint_command: uv run ruff check
start_phase: intern
stop_phase: senior
target_repo: /home/yapilwsl/arthityap/ai-factory
target_functions:
  - check_plan_invariants
  - _feedback_from_audit
  - _py_tree
scope:
  - factory/infra/validation.py
  - factory/infra/ledger.py
---

# EPIC
Reduce Cyclomatic Complexity (CC) to ≤ 5 for all target functions in factory/infra/.

## CONTEXT
The CC scanner identified high-complexity violations in factory/infra/:
1. validation.py: `check_plan_invariants` (CC=13)
2. validation.py: `_feedback_from_audit` (CC=13)
3. ledger.py: `_py_tree` (CC=11)

Refactor using guard clauses, early returns, helper extraction, and single-responsibility decomposition. Do NOT alter public function signatures or break existing contracts.

## REFACTORING PATTERN TO FOLLOW
1. Guard clauses first: validate inputs and return early.
2. Extract private helpers: pull out nested loops/branches into private helper functions with CC≤5.
3. Keep pure logic clean.
4. Preserve full signatures & type annotations: zero changes to public function signatures or parameters.

## DELIVERABLES
1. Refactor all target functions from CC > 10 to ≤ 5.
2. Code must pass `uv run ruff check` with 0 errors.
3. Code must pass `find_cc_nested.py` verification (CC ≤ 5).

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
1. `find_cc_nested.py` reports CC ≤ 5 for all target functions.
2. `uv run ruff check` passes cleanly.
3. All existing unit tests pass (`PYTHONPATH=. uv run pytest tests/`).
