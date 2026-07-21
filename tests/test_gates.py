"""Control-flow tests for the DAG execution gates (code-review + red-team).

No LLM keys required: coder_fn / reviewer_fn are stubbed, and the ApprovedPlan
is built in-process. Validates:
  * run_red_team_gate re-derives the verdict from rubric_cube (ignore `green`);
  * a blocker finding re-executes only the failing task + downstream closure;
  * the HARD wall raises after MAX_RETRIES (no forced pass);
  * per-task coder turns + reviewer turns are appended to the resume exchange.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import asyncio
import json

import pytest

from factory.infra.control import TEMP_DIR
from factory.infra.models import (
    ApprovedTask,
    AuditResult,
    Epic,
    ExecutablePlan,
    EvaluationItem,
    ParallelisableWorkplan,
    ReviewResult,
    RubricCell,
    RubricCube,
    Strategy,
    TaskResult,
    UserStory,
    WorkGroup,
)
from factory.infra.runner import (
    ExchangeTurn,
    run_code_review_gate,
    run_red_team_gate,
)


def _plan() -> ExecutablePlan:
    """g1=[coder_1]; g2=[coder_2,coder_3] depends on g1."""
    epic = Epic(title="e", deliverables=["d"], must_be_pydantic=True)
    g1 = WorkGroup(
        id="g1",
        tasks=[ApprovedTask(id="coder01", title="coder01", file_paths=["src2/a.py"],
                            instruction="i", acceptance="a",
                            tool_preference="CLI-wrapper")],
        concurrent=True,
    )
    g2 = WorkGroup(
        id="g2",
        depends_on=["g1"],
        tasks=[
            ApprovedTask(id="coder02", title="coder02", file_paths=["src2/b.py"],
                         instruction="i", acceptance="a",
                         tool_preference="CLI-wrapper"),
            ApprovedTask(id="coder03", title="coder03", file_paths=["src2/c.py"],
                         instruction="i", acceptance="a",
                         tool_preference="CLI-wrapper"),
        ],
        concurrent=True,
    )
    strat = Strategy(
        how_to_fix="x",
        tool_preference={"coder01": "CLI-wrapper", "coder02": "CLI-wrapper", "coder03": "CLI-wrapper"},
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
        tasks=[g1.tasks[0], *g2.tasks],
        alignment="align",
        workplan=ParallelisableWorkplan(groups=[g1, g2]),
        strategy=strat,
        approved=True
    )


def _coder_factory(log: dict[str, int]):
    async def coder_fn(brief: str, task_id: str | None = None) -> str:
        tid = task_id or brief.split("TASK ID:")[1].split()[0]
        log[tid] = log.get(tid, 0) + 1
        return json.dumps({"status": "done", "rc": 0, "stdout": "ok", "stderr": "", "task_id": tid, "files_changed": [], "diff_summary": "", "notes": ""})
    return coder_fn


def _prior_batch(plan: ExecutablePlan) -> dict[str, TaskResult]:
    """Simulate the code-review gate having already executed every task."""
    return {
        t.id: TaskResult(task_id=t.id, status="done",
                         files_changed=[], diff_summary="", notes="")
        for t in plan.tasks
    }


def _audit_json(passed: bool, failed_tasks: list[str] | None = None) -> str:
    evals = []
    if failed_tasks:
        for tid in failed_tasks:
            evals.append(EvaluationItem(item_id=tid, approved="No", comments="recode this"))
    if not evals and not passed:
        evals.append(EvaluationItem(item_id="rubric_global", approved="No", comments="failed rubric"))
    if evals:
        return AuditResult(evaluations=evals).model_dump_json()
    return AuditResult(evaluations=[EvaluationItem(item_id="coder01", approved="Yes", comments="all good")]).model_dump_json()


def _reviewer_always(passed: bool):
    async def _rev(brief: str) -> str:
        return _audit_json(passed)
    return _rev


def test_red_team_passes_first_try():
    plan = _plan()
    log: dict[str, int] = {}
    exchanged: list[ExchangeTurn] = []
    pass_counter: dict[str, int] = {}
    batch = asyncio.run(run_red_team_gate(
        plan, TEMP_DIR / "rt_test", _coder_factory(log),
        _reviewer_always(passed=True),
        prior_batch=_prior_batch(plan),
        exchange=exchanged,  # type: ignore[arg-type]
        pass_counter=pass_counter,
    ))
    # pass on attempt 1 -> no re-exec, so no coder turns appended; only the
    # red_team turn lands in the exchange.
    assert log == {}
    assert {r.task_id for r in batch.results} == {"coder01", "coder02", "coder03"}
    assert pass_counter == {"red_team": 1}
    assert [e.role for e in exchanged] == ["red_team"]


def test_red_team_rexec_failing_plus_downstream():
    plan = _plan()
    calls = {"n": 0}
    log: dict[str, int] = {}

    async def reviewer(brief: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return _audit_json(passed=False, failed_tasks=["coder01"])
        return _audit_json(passed=True)

    asyncio.run(run_red_team_gate(
        plan, TEMP_DIR / "rt_test", _coder_factory(log),
        reviewer, prior_batch=_prior_batch(plan),
    ))
    # only the failing task + its downstream are re-executed (issues-only)
    assert log == {"coder01": 1, "coder02": 1, "coder03": 1}
    assert calls["n"] == 2


def test_red_team_hard_wall_raises():
    plan = _plan()
    log: dict[str, int] = {}
    with pytest.raises(RuntimeError, match="HARD FAIL"):
        asyncio.run(run_red_team_gate(
            plan, TEMP_DIR / "rt_test", _coder_factory(log),
            _reviewer_always(passed=False),
            prior_batch=_prior_batch(plan),
        ))


def test_red_team_forced_pass_overrides_evaluations():
    plan = _plan()
    log: dict[str, int] = {}
    exchanged: list[ExchangeTurn] = []
    pass_counter: dict[str, int] = {}
    
    async def reviewer(brief: str) -> str:
        return _audit_json(passed=False, failed_tasks=["coder01"])
        
    batch = asyncio.run(run_red_team_gate(
        plan, TEMP_DIR / "rt_forced_test", _coder_factory(log),
        reviewer,
        prior_batch=_prior_batch(plan),
        exchange=exchanged,  # type: ignore[arg-type]
        pass_counter=pass_counter,
    ))
    
    assert {r.task_id for r in batch.results} == {"coder01", "coder02", "coder03"}
    assert pass_counter.get("red_team") == 3


def test_code_review_forced_pass_overrides_evaluations():
    plan = _plan()
    log: dict[str, int] = {}
    exchanged: list[ExchangeTurn] = []
    pass_counter: dict[str, int] = {}
    
    async def reviewer(brief: str) -> str:
        evals = [EvaluationItem(item_id="coder01", approved="No", comments="fix it")]
        return ReviewResult(evaluations=evals).model_dump_json()
        
    batch = asyncio.run(run_code_review_gate(
        plan, TEMP_DIR / "cr_forced_test", _coder_factory(log),
        reviewer,
        exchange=exchanged,  # type: ignore[arg-type]
        pass_counter=pass_counter,
    ))
    
    assert {r.task_id for r in batch.results} == {"coder01", "coder02", "coder03"}
    assert pass_counter.get("supervisor_review") == 3


def test_red_team_maps_user_story_to_coder():
    plan = _plan()
    # Map story 's1' to coder_1
    plan.user_stories[0].coder_idents = ["coder01"]
    log: dict[str, int] = {}
    calls = {"n": 0}

    async def reviewer(brief: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            # Reject the user story
            return AuditResult(evaluations=[
                EvaluationItem(item_id="s1", approved="No", comments="story failed")
            ]).model_dump_json()
        return _audit_json(passed=True)

    asyncio.run(run_red_team_gate(
        plan, TEMP_DIR / "rt_test_story", _coder_factory(log),
        reviewer, prior_batch=_prior_batch(plan),
    ))
    # s1 maps to coder_1, and coder_1 triggers downstream coder_2 and coder_3
    assert log == {"coder01": 1, "coder02": 1, "coder03": 1}
    assert calls["n"] == 2


def test_red_team_maps_rubric_dimension_to_coder():
    plan = _plan()
    # Add a rubric cell mapping dimension 'dim_test' to coder_2
    plan.rubric_cube.cells.append(
        RubricCell(dimension="dim_test", criterion="crit_test", severity="blocker", passed=True, coder_idents=["coder02"])
    )
    log: dict[str, int] = {}
    calls = {"n": 0}

    async def reviewer(brief: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            # Reject by dimension name
            return AuditResult(evaluations=[
                EvaluationItem(item_id="dim_test", approved="No", comments="rubric failed")
            ]).model_dump_json()
        return _audit_json(passed=True)

    asyncio.run(run_red_team_gate(
        plan, TEMP_DIR / "rt_test_rubric", _coder_factory(log),
        reviewer, prior_batch=_prior_batch(plan),
    ))
    # dim_test maps to coder_2, which executes coder_2. But since we use prior_batch containing coder_3, coder_3 is not rerun here because it wasn't marked failing itself, or it was blocked.
    assert log == {"coder02": 1}
    assert "coder01" not in log
    assert calls["n"] == 2

