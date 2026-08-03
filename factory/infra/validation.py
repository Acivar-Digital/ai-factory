"""Plan invariants and gate validation helpers."""
from __future__ import annotations

from factory.infra.models import (
    ReviewFinding, AuditResult, AuditRisk, WorkGroup, CodePassed
)

# Roles whose turns are persisted in the reloadable exchange JSON.
EXCHANGE_ROLES = {"intern", "engineer", "senior"}

# Reviewer role -> pass/fail boolean field in its JSON output.
REVIEW_PASS_FIELD = {
    "intern": "passed",
    "engineer": "passed",
    "senior": "passed",
}

# Max review attempts per gated pair; the 3rd attempt is a FORCED pass.
MAX_RETRIES = 3

PLAN_INVARIANT_RETRIES = 5   # 01_fix: max intern/engineer retries before HALT


def check_plan_invariants(plan) -> list[str]:
    """Return violation strings (empty list = plan OK).

    Checks: (1) every task lists exactly 1 file; (2) file paths are disjoint
    across all tasks. Runs on output from both intern and engineer phases.
    """
    violations: list[str] = []
    seen: set[str] = set()

    # Try to find the workplan groups
    workplan = getattr(plan, "workplan", None)
    if not workplan:
        strategy = getattr(plan, "strategy", None)
        if strategy:
            workplan = getattr(strategy, "parallelisable_workplan", None)

    groups = getattr(workplan, "groups", []) if workplan else []

    if not workplan:
        violations.append("workplan or strategy.parallelisable_workplan is missing or null.")

    tasks = []
    for group in groups or []:
        tasks.extend(getattr(group, "tasks", []) or [])

    for task in tasks:
        fps = getattr(task, "file_paths", None) or []
        if len(fps) != 1:
            violations.append(f"task {getattr(task, 'id', '?')} lists {len(fps)} files (exactly 1 required)")
        for fp in fps:
            if fp in seen:
                violations.append(f"file collision: {fp} in multiple tasks")
            seen.add(fp)
    return violations


def _downstream_closure(failing: set[str], groups: list[WorkGroup]) -> set[str]:
    """Forward-reachable task set from `failing`: each failing task plus every
    task in any downstream (dependent) WorkGroup. Bounds re-execution so a bad
    upstream task re-runs its dependents, but untouched work is preserved."""
    task_group, by_id, dependents = _build_dependency_graph(groups)
    out = _traverse_downstream(failing, task_group, by_id, dependents)
    return out


def _build_dependency_graph(groups: list[WorkGroup]) -> tuple[dict[str, str], dict[str, WorkGroup], dict[str, list[str]]]:
    """Build lookup maps for task-to-group, group-by-id, and group dependents."""
    task_group: dict[str, str] = {}
    by_id = {g.id: g for g in groups}
    dependents: dict[str, list[str]] = {g.id: [] for g in groups}
    for g in groups:
        for t in g.tasks:
            task_group[t.id] = g.id
        for d in g.depends_on:
            if d in dependents:
                dependents[d].append(g.id)
    return task_group, by_id, dependents


def _traverse_downstream(
    failing: set[str],
    task_group: dict[str, str],
    by_id: dict[str, WorkGroup],
    dependents: dict[str, list[str]],
) -> set[str]:
    """Traverse downstream from failing tasks and collect all reachable task IDs."""
    out: set[str] = set(failing)
    stack = _initial_stack(failing, task_group)
    seen: set[str] = set()
    while stack:
        gid = stack.pop()
        if _already_seen(gid, seen):
            continue
        seen.add(gid)
        _process_group_deps(gid, dependents, by_id, out, stack)
    return out


def _initial_stack(failing: set[str], task_group: dict[str, str]) -> list[str]:
    """Build the initial traversal stack from failing task IDs."""
    return [task_group[t] for t in failing if t in task_group]


def _already_seen(gid: str, seen: set[str]) -> bool:
    """Return True if this group was already visited."""
    return gid in seen


def _process_group_deps(
    gid: str,
    dependents: dict[str, list[str]],
    by_id: dict[str, WorkGroup],
    out: set[str],
    stack: list[str],
) -> None:
    """Add all tasks from dependent groups and schedule them for traversal."""
    for dep in dependents[gid]:
        for t in by_id[dep].tasks:
            out.add(t.id)
        stack.append(dep)


def security_checks_passed(findings: list[dict], rubric_cells: list[dict]) -> bool:
    """Deterministic security audit go/no-go verdict — SINGLE SOURCE OF TRUTH.

    Used by both the inline reviewer check and the re-execution loop
    so the gating logic can never drift between the two code paths.

    Gate is driven SOLELY by:
      * `findings` (task-keyed, severity == "blocker") -> which tasks to recode,
      * an unresolvable global blocker in `rubric_cube` (a blocker cell with no
        matching `findings` entry) -> HARD FAIL.
    The LLM's free `green` boolean is NEVER trusted. This is exactly the
    contract documented in templates/senior.yaml + customised/senior.yaml.
    """
    failing = any(f.get("severity") == "blocker" for f in findings)
    has_audit_data = bool(findings) or bool(rubric_cells)
    unresolved_global = (
        any(c.get("severity") == "blocker" and not c.get("passed") for c in rubric_cells)
        and not failing
    )
    return has_audit_data and not (failing or unresolved_global)


def _feedback_from_review_findings(review: "CodePassed") -> dict[str, str]:
    """R1 (baziforecaster-nw9ov): render review findings + traceback_route
    into a task_id -> prior-feedback text map for the rerun coder brief."""
    out: dict[str, list[str]] = {}
    findings = getattr(review, "findings", None) or []
    for f in findings:
        if getattr(f, "severity", None) != "blocker":
            continue
        tid = getattr(f, "task_id", None)
        if not tid:
            continue
        parts = [
            f"- [{getattr(f, 'severity', 'blocker')}] {getattr(f, 'message', '')}",
        ]
        if getattr(f, "file", None):
            parts.append(f"  file: {f.file}")
        if getattr(f, "line", None) is not None:
            parts.append(f"  line: {f.line}")
        if getattr(f, "suggestion", None):
            parts.append(f"  fix: {f.suggestion}")
        out.setdefault(tid, []).append("\n".join(parts))
    traceback_route = getattr(review, "traceback_route", None)
    if traceback_route:
        for tid, lines in out.items():
            lines.append(f"  reviewer note: {traceback_route}")
    return {tid: "\n".join(blocks) for tid, blocks in out.items()}


def _feedback_from_audit(
    findings: list["ReviewFinding"],     audit: "AuditResult"
) -> dict[str, str]:
    """R1 (baziforecaster-nw9ov): render security audit findings + risks into a
    task_id -> prior-feedback text map for the rerun coder brief."""
    out: dict[str, list[str]] = {}
    for f in findings:
        if getattr(f, "severity", None) != "blocker":
            continue
        tid = getattr(f, "task_id", None)
        if not tid:
            continue
        parts = [f"- [SENIOR {getattr(f, 'severity', 'blocker')}] {getattr(f, 'message', '')}"]
        if getattr(f, "file", None):
            parts.append(f"  file: {f.file}")
        if getattr(f, "line", None) is not None:
            parts.append(f"  line: {f.line}")
        if getattr(f, "suggestion", None):
            parts.append(f"  fix: {f.suggestion}")
        out.setdefault(tid, []).append("\n".join(parts))
    # Also surface Critical/High risks that named a task (already promoted to
    # findings above, but include raw risk context for completeness).
    risks = getattr(audit, "risks", None) or []
    for r in risks:
        if getattr(r, "severity", None) not in ("Critical", "High"):
            continue
        tid = getattr(r, "task_id", None)
        if not tid or tid in out:
            continue
        block = (
            f"- [SENIOR {getattr(r, 'severity', 'risk')}] {getattr(r, 'description', '')}"
        )
        if getattr(r, "mitigation", None):
            block += f"\n  fix: {r.mitigation}"
        out.setdefault(tid, []).append(block)
    return {tid: "\n".join(blocks) for tid, blocks in out.items()}


def _blocker_findings_from_risks(
    findings: list[ReviewFinding],
    risks: list[AuditRisk],
    known_task_ids: set[str],
) -> tuple[list[ReviewFinding], list[str]]:
    """Anti-laziness guard for the self-graded security audit verdict.

    The security audit model emits BOTH `findings` (which route re-execution) and
    `risks` (which name offending tasks). A lazy model can emit Critical/High
    `risks` flagging real defects yet leave `findings` empty — which lets
    `security_checks_passed` return True and skip re-execution entirely, so the
    defects ship unreviewed.

    Any Critical/High `AuditRisk` that carries a `task_id` inside the approved
    plan but has NO matching blocker `ReviewFinding` is promoted to a blocker
    finding, so the offending task is actually re-coded. Risks that name a
    defect but carry no resolvable `task_id` are returned separately so the
    caller can HARD FAIL them as unresolvable (mirrors the rubric_cube
    global-blocker rule)."""
    have = {f.task_id for f in findings if f.severity == "blocker"}
    augmented = list(findings)
    unresolved_global: list[str] = []
    for r in risks:
        if r.severity not in ("Critical", "High"):
            continue
        if not r.task_id or r.task_id not in known_task_ids:
            unresolved_global.append(r.component or r.task_id or "<anonymous>")
            continue
        if r.task_id in have:
            continue
        augmented.append(
            ReviewFinding(
                task_id=r.task_id,
                severity="blocker",
                file=r.component,
                line=None,
                message=f"[auto-derived from {r.severity} risk] {r.description}",
                suggestion=r.mitigation,
            )
        )
        have.add(r.task_id)
    return augmented, unresolved_global
