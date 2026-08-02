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
  - _feedback_from_audit
  - check_plan_invariants
  - _downstream_closure
  - _affected_tests
  - _py_tree
scope:
  - factory/infra/validation.py
  - factory/infra/gatekeeper.py
  - factory/infra/ledger.py
---

# EPIC
Reduce CC (Cyclomatic Complexity) to ≤5 for 5 functions across 3 files in factory/infra/.

## CONTEXT
The CC scanner (find_cc_nested.py, min-cc=6) identified 5 high-complexity violations across 3 core infrastructure files:
- validation.py: `_feedback_from_audit` (CC=14), `check_plan_invariants` (CC=13), `_downstream_closure` (CC=13)
- gatekeeper.py: `_affected_tests` (CC=12)
- ledger.py: `_py_tree` (CC=12)

These functions exceed the project maximum of CC=5. Refactor using guard clauses, early returns, helper extraction, and single-responsibility decomposition. Do NOT alter public function signatures or break existing contracts.

## NEGATIVE EXAMPLES (CC>5 — DO NOT EMIT)

### validation.py :: `_feedback_from_audit` (CC=14) — TOO MANY NESTED LOOPS AND CONDITIONALS
```python
def _feedback_from_audit(findings: list[ReviewFinding], audit: AuditResult) -> dict[str, str]:
    out: dict[str, list[str]] = {}
    for f in findings:
        if getattr(f, "severity", None) != "blocker":
            continue
        tid = getattr(f, "task_id", None)
        if not tid:
            continue
        # nested formatting ...
    risks = getattr(audit, "risks", None) or []
    for r in risks:
        if getattr(r, "severity", None) not in ("Critical", "High"):
            continue
        # nested formatting ...
    return {tid: "\n".join(blocks) for tid, blocks in out.items()}
```
Problem: Dual loops with multi-level nested attribute guards and string formatting logic. Accumulates CC=14.

### gatekeeper.py :: `_affected_tests` (CC=12) — MULTIPLE BRANCHES AND DEEP NESTING
```python
def _affected_tests(changed_files: list[str]) -> list[str]:
    if not changed_files:
        return []
    # multiple nested loops for stems and walk ...
```
Problem: Deep nested loops over file paths, package paths, and os.walk file trees. Accumulates CC=12.

## POSITIVE EXAMPLES (CC≤5 — TARGET SHAPE)

### preflight.py :: `_is_invalid_webhook_url` (CC=2) — GUARD CLAUSES
```python
def _is_invalid_webhook_url(url: str | None) -> bool:
    if not url:
        return True
    if not url.startswith("https://"):
        return True
    return False
```
Pattern: Guard clauses return early. Each condition is a single CC point. No nesting.

## REFACTORING PATTERN TO FOLLOW

For each violating function:
1. **Guard clauses first**: validate inputs and return early.
2. **Extract private helpers**: pull out nested loops/branches into private helper functions with CC≤3.
3. **Keep pure logic clean**: separate data extraction from string rendering.
4. **Preserve full signature & type annotations**: zero changes to public function signatures or parameters.

## DELIVERABLES
1. Refactor `_feedback_from_audit` (factory/infra/validation.py) from CC=14 to ≤5.
2. Refactor `check_plan_invariants` (factory/infra/validation.py) from CC=13 to ≤5.
3. Refactor `_downstream_closure` (factory/infra/validation.py) from CC=13 to ≤5.
4. Refactor `_affected_tests` (factory/infra/gatekeeper.py) from CC=12 to ≤5.
5. Refactor `_py_tree` (factory/infra/ledger.py) from CC=12 to ≤5.
6. All functions must pass `uv run ruff check` with 0 errors.
7. All functions must pass `find_cc_nested.py` verification (CC ≤ 5).

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
1. `find_cc_nested.py` reports 0 violations (CC ≤ 5) across the 3 scoped files.
2. `uv run ruff check` passes on all 3 files.
3. All existing unit tests pass (`PYTHONPATH=. uv run pytest tests/`).
