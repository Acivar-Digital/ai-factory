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
  - red_team_passed
scope:
  - factory/infra/validation.py
---

# EPIC
Reduce Cyclomatic Complexity (CC) to <= 5 for red_team_passed in factory/infra/validation.py.

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
