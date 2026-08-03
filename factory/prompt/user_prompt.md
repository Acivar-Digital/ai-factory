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
  - _run_ruff
  - run_gate
  - _is_dir
  - _py_tree
  - _compute_cc
  - generate_ast_decomposition_hint
  - auto_discover_high_cc_functions
  - compute_dynamic_retry_budget
  - build_todo_checklist
  - read_prompt
  - _recover_from_unexpected_behavior
  - do_role
  - _run_verify_edit
  - _build_isolated_ast_block
  - _extract_failure_summary
  - run_tier
  - _get_cc_for_fn
  - _read_target_functions
  - _read_staged_paths
  - _assert_plan_gate_ok
  - _sync_state
  - load_checkpoint
scope:
  - factory/infra/validation.py
---

# EPIC
Reduce Cyclomatic Complexity (CC) to <= 5 for all listed target functions across factory/infra/ modules:
- gatekeeper.py: _run_ruff (CC=7), run_gate (CC=6)
- ledger.py: _is_dir (CC=7), _py_tree (CC=11)
- pipeline.py: _compute_cc (CC=7), generate_ast_decomposition_hint (CC=19), auto_discover_high_cc_functions (CC=7), compute_dynamic_retry_budget (CC=7), build_todo_checklist (CC=13), read_prompt (CC=24), _recover_from_unexpected_behavior (CC=6), do_role (CC=7), _run_verify_edit (CC=49), _build_isolated_ast_block (CC=27), _extract_failure_summary (CC=6), run_tier (CC=36), _get_cc_for_fn (CC=6), _read_target_functions (CC=14), _read_staged_paths (CC=18), _assert_plan_gate_ok (CC=31), _sync_state (CC=9), load_checkpoint (CC=9)

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
