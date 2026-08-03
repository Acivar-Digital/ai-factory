<!-- msg 0 | 2026-08-03-00:26:14 | user-prompt -->

## User

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

### Surgical Context Sandwich
**File**: `factory/temp/factory/infra/validation.py` — **Function**: `red_team_passed`

#### Layer 1 — File Skeleton & Imports
```python
from __future__ import annotations
from factory.infra.models import ReviewFinding, AuditResult, AuditRisk, WorkGroup, CodePassed
def check_plan_invariants(plan) -> list[str]:...
def _downstream_closure(failing: set[str], groups: list[WorkGroup]) -> set[str]:...
def _build_dependency_graph(groups: list[WorkGroup]) -> tuple[dict[str, str], dict[str, WorkGroup], dict[str, list[str]]]:...
def _traverse_downstream(failing: set[str], task_group: dict[str, str], by_id: dict[str, WorkGroup], dependents: dict[str, list[str]]) -> set[str]:...
def _initial_stack(failing: set[str], task_group: dict[str, str]) -> list[str]:...
def _already_seen(gid: str, seen: set[str]) -> bool:...
def _process_group_deps(gid: str, dependents: dict[str, list[str]], by_id: dict[str, WorkGroup], out: set[str], stack: list[str]) -> None:...
def red_team_passed(findings: list[dict], rubric_cells: list[dict]) -> bool:...
def _feedback_from_review_findings(review: 'CodePassed') -> dict[str, str]:...
def _feedback_from_audit(findings: list['ReviewFinding'], audit: 'AuditResult') -> dict[str, str]:...
def _blocker_findings_from_risks(findings: list[ReviewFinding], risks: list[AuditRisk], known_task_ids: set[str]) -> tuple[list[ReviewFinding], list[str]]:...
```

#### Layer 2 — Target Function AST Node
```python
def red_team_passed(findings: list[dict], rubric_cells: list[dict]) -> bool:
    """Deterministic red-team go/no-go verdict — SINGLE SOURCE OF TRUTH.

    Used by BOTH `run_red_team_gate` and the inline `passed()` reviewer check
    so the gating logic can never drift between the two code paths (and never
    contradict red_team.yaml).

    Gate is driven SOLELY by:
      * `findings` (task-keyed, severity == "blocker") -> which tasks to recode,
      * an unresolvable global blocker in `rubric_cube` (a blocker cell with no
        matching `findings` entry) -> HARD FAIL.
    The LLM's free `green` boolean is NEVER trusted. This is exactly the
    contract documented in templates/red_team.yaml + customised/red_team.yaml.
    """
    failing = any((f.get('severity') == 'blocker' for f in findings))
    has_audit_data = bool(findings) or bool(rubric_cells)
    unresolved_global = any((c.get('severity') == 'blocker' and (not c.get('passed')) for c in rubric_cells)) and (not failing)
    return has_audit_data and (not (failing or unresolved_global))
```

#### Layer 3 — Refactoring Instruction
Refactor ONLY the function `red_team_passed` in `factory/temp/factory/infra/validation.py` to reduce its cyclomatic complexity to CC <= 5. Do not modify any other function or file.
