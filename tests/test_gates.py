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

import json


from factory.infra.models import (
    ApprovedTask,
    AuditResult,
    Epic,
    ExecutablePlan,
    EvaluationItem,
    ParallelisableWorkplan,
    RubricCell,
    RubricCube,
    Strategy,
    TaskResult,
    UserStory,
    WorkGroup,
)


def _plan() -> ExecutablePlan:
    """g1=[coder_1]; g2=[coder_2,coder_3] depends on g1."""
    epic = Epic(title="e", deliverables=["d"], must_be_pydantic=True)
    g1 = WorkGroup(
        id="g1",
        tasks=[ApprovedTask(id="coder01", title="coder01", file_paths=["src2/a.py"],
                            instruction="i", acceptance="a",
                            tool_preference="CLI-wrapper")],
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

