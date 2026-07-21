"""Regression tests for the coder rerun feedback injection (R1) + frozen
behaviour appendix (R5).

No LLM keys required: coder_fn / reviewer_fn are stubbed and the ApprovedPlan
is built in-process. Validates, end-to-end through `run_red_team_gate`:

  * R1 — when a task is reopened for re-execution, its coder brief carries a
    `=== PRIOR FEEDBACK ===` block containing the prior red-team finding
    (message + file + suggestion), while NON-rerun tasks do NOT get the block.
  * R5 — every coder brief (fresh or rerun) carries the frozen
    `=== EXPECTED CODER BEHAVIOUR` appendix with the task's acceptance line.

These guard the fixes from `baziforecaster-nw9ov` (R1) and `baziforecaster-6gizg`
(R5). If a future change drops the injection, the rerun coder goes blind again
— this test fails loudly.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import asyncio
import json

from factory.infra.control import TEMP_DIR
from factory.infra.models import (
    ApprovedTask,
    AuditResult,
    Epic,
    ExecutablePlan,
    EvaluationItem,
    ParallelisableWorkplan,
    ReviewFinding,
    RubricCell,
    RubricCube,
    Strategy,
    TaskResult,
    UserStory,
    WorkGroup,
)
from factory.infra.pipeline import run_red_team_gate


def _plan() -> ExecutablePlan:
    """g1=[coder_1]; g2=[coder_2] depends on g1."""
    epic = Epic(title="e", deliverables=["d"], must_be_pydantic=True)
    g1 = WorkGroup(
        id="g1",
        tasks=[ApprovedTask(id="coder01", title="coder_1 task", file_paths=["src2/a.py"],
                             instruction="implement coder_1", acceptance="coder_1 must pass lint",
                             tool_preference="CLI-wrapper")],
        concurrent=True,
    )
    g2 = WorkGroup(
        id="g2",
        depends_on=["g1"],
        tasks=[ApprovedTask(id="coder02", title="coder_2 task", file_paths=["src2/b.py"],
                            instruction="implement coder_2", acceptance="coder_2 must pass lint",
                            tool_preference="CLI-wrapper")],
        concurrent=True,
    )
    strat = Strategy(
        how_to_fix="x",
        tool_preference={"coder01": "CLI-wrapper", "coder02": "CLI-wrapper"},
        parallelisable_workplan=ParallelisableWorkplan(groups=[g1, g2]),
    )
    return ExecutablePlan(
        epic=epic,
        user_stories=[UserStory(id="s1", story="s", acceptance_criteria=["a"],
                                 definition_of_done=["d"])],
        definition_of_done=["d"],
        acceptance_criteria=["a"],
        rubric_cube=RubricCube(cells=[RubricCell(dimension="x", criterion="c",
                                                   severity="blocker", passed=True)]),
        summary="s",
        tasks=[g1.tasks[0], g2.tasks[0]],
        alignment="align",
        workplan=ParallelisableWorkplan(groups=[g1, g2]),
        strategy=strat,
        approved=True
    )


def _coder_capture(briefs: dict[str, str]):
    async def coder_fn(brief: str, task_id: str | None = None) -> str:
        tid = task_id or brief.split("TASK ID:")[1].split()[0]
        briefs[tid] = brief
        return json.dumps({"status": "done", "rc": 0, "stdout": "ok", "stderr": "",
                            "task_id": tid, "files_changed": [], "diff_summary": "",
                            "notes": ""})
    return coder_fn


def _prior_batch(plan: ExecutablePlan) -> dict[str, TaskResult]:
    return {t.id: TaskResult(task_id=t.id, status="done",
                             files_changed=[], diff_summary="", notes="")
            for t in plan.tasks}


def _audit_json(cells_ok: bool, findings: list | None = None) -> str:
    evals = []
    if findings:
        for f in findings:
            comments = f.get("message", "recode")
            if f.get("file"):
                comments += f"\n  file: {f.get('file')}"
            if f.get("suggestion"):
                comments += f"\n  fix: {f.get('suggestion')}"
            evals.append(EvaluationItem(item_id=f.get("task_id", "coder01"), approved="No", comments=comments))
    if not evals and not cells_ok:
        evals.append(EvaluationItem(item_id="rubric_global", approved="No", comments="failed rubric"))
    if not evals:
        evals.append(EvaluationItem(item_id="coder01", approved="Yes", comments="all ok"))
    return AuditResult(evaluations=evals).model_dump_json()


def _reviewer_always(cells_ok: bool):
    async def _rev(brief: str) -> str:
        return _audit_json(cells_ok)
    return _rev


def test_r5_frozen_behaviour_appendix_in_every_brief():
    """R5: every coder brief carries the frozen behaviour appendix + acceptance."""
    plan = _plan()
    briefs: dict[str, str] = {}
    # No prior_batch -> the initial DAG dispatch executes the coder for every
    # task, so we capture each brief and assert the frozen appendix is present.
    asyncio.run(run_red_team_gate(
        plan, TEMP_DIR / "rt_r5", _coder_capture(briefs),
        _reviewer_always(cells_ok=True),
        prior_batch={},
    ))
    assert set(briefs) == {"coder01", "coder02"}
    for tid, brief in briefs.items():
        assert "=== EXPECTED CODER BEHAVIOUR (frozen contract) ===" in brief
        assert "ACCEPTANCE (verbatim):" in brief


def test_r1_rerun_brief_carries_prior_feedback_for_failing_task():
    """R1: the reopened task's rerun brief gets the PRIOR FEEDBACK block; the
    untouched task does NOT."""
    plan = _plan()
    briefs: dict[str, str] = {}
    calls = {"n": 0}

    async def reviewer(brief: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            # Real recode-targeting audit: rubric cells PASS, but a task-keyed
            # blocker finding on A routes A (+downstream) to re-execution.
            return _audit_json(cells_ok=True, findings=[
                ReviewFinding(task_id="coder01", severity="blocker",
                              file="src2/a.py", message="coder_1 violates import order",
                              suggestion="sort imports").model_dump(),
            ])
        return _audit_json(cells_ok=True)

    asyncio.run(run_red_team_gate(
        plan, TEMP_DIR / "rt_r1", _coder_capture(briefs),
        reviewer, prior_batch={},
    ))

    # A was reopened -> its rerun brief must contain the prior finding.
    assert "coder01" in briefs
    a_brief = briefs["coder01"]
    assert "=== PRIOR FEEDBACK (why this task was reopened) ===" in a_brief
    assert "coder_1 violates import order" in a_brief
    assert "sort imports" in a_brief
    assert "src2/a.py" in a_brief

    # B is a downstream rerun target (g2 depends_on g1) but has NO structured
    # findings of its own -> it gets the generic reopened note, NOT A's finding.
    assert "coder02" in briefs
    b_brief = briefs["coder02"]
    assert "=== PRIOR FEEDBACK" in b_brief
    assert "coder_1 violates import order" not in b_brief


def test_r1_fallback_note_when_rerun_without_feedback(monkeypatch):
    """R1 fallback: a reopened task with no structured findings in the feedback
    map still gets a generic 'reopened, re-read your memory' note (not blind).

    Driven directly through `run_execute_phase` with rerun_ids set and an empty
    feedback map — this isolates the fallback branch without the red-team gate's
    (correct) HARD FAIL on an unresolvable global blocker.
    """
    from factory.infra.runner import run_execute_phase
    monkeypatch.setattr("factory.infra.execution._write_harness_patches", lambda task_id, files_changed, bd="": (["fake.diff"], 1))

    plan = _plan()
    briefs: dict[str, str] = {}

    async def coder_fn(brief: str, task_id: str | None = None) -> str:
        tid = task_id or brief.split("TASK ID:")[1].split()[0]
        briefs[tid] = brief
        return json.dumps({"status": "done", "rc": 0, "stdout": "ok", "stderr": "",
                            "task_id": tid, "files_changed": [], "diff_summary": "",
                            "notes": ""})

    asyncio.run(run_execute_phase(
        plan, TEMP_DIR / "rt_r1b", asyncio.Semaphore(20), coder_fn,
        prior={t.id: TaskResult(task_id=t.id, status="done", files_changed=[],
                                 diff_summary="", notes="") for t in plan.tasks},
        rerun_ids={"coder01"},
        feedback={},  # no structured findings captured for coder_1
    ))
    assert "coder01" in briefs
    assert "=== PRIOR FEEDBACK ===" in briefs["coder01"]
    assert "reopened" in briefs["coder01"].lower()
