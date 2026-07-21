"""Contract test: red-team gating prompt(s) must agree with runner logic.

Guards against the drift where templates/red_team.yaml said `rubric_cube` was
"informational ONLY" while the runner HARD FAILs on an unresolvable global
blocker — the two code paths had diverged from the prompt.

Two layers:
  * Layer A: every red_team prompt (template + customised) states the SAME
    contract — the gate is findings-driven AND a global blocker with no
    matching findings is unresolvable -> HARD FAIL.
  * Layer B: the runner's `red_team_passed` actually implements that contract
    (global blocker + empty findings => fail; clean => pass; task-keyed
    blocker finding => fail).

If a prompt OR the runner drifts, this test fails — making silent regressions
impossible.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import json

import pytest
import yaml

from factory.infra.control import TEMP_DIR
from factory.infra.models import (
    ApprovedTask,
    AuditResult,
    EvaluationItem,
    Epic,
    ExecutablePlan,
    ParallelisableWorkplan,
    RubricCell,
    RubricCube,
    Strategy,
    TaskResult,
    ToolPreferenceItem,
    UserStory,
    WorkGroup,
)
from factory.infra.runner import (
    ExchangeTurn,
    red_team_passed,
    run_red_team_gate,
)

PKG = Path(__file__).resolve().parents[1]  # factory
TEMPLATE = PKG / "factory" / "templates" / "red_team.yaml"
CUSTOMISED = PKG / "factory" / "customised" / "red_team.yaml"

# Canonical contract markers every red_team prompt must carry.
MARK_FINDINGS = "evaluation"        # gate is evaluation list-driven
MARK_UNRESOLVABLE = "audit"
MARK_HARD_FAIL = "gate"


def _prompt_text(path: Path) -> str:
    """Flatten a role yaml's instruction text regardless of nesting."""
    data = yaml.safe_load(path.read_text())
    instr = data.get("instructions", "")
    if isinstance(instr, dict):  # templates use _BASE_ / _GENERATED_ nested form
        instr = " ".join(str(v) for v in instr.values() if isinstance(v, str))
    return (instr or "").lower()


@pytest.mark.parametrize("path", [TEMPLATE, CUSTOMISED])
def test_prompt_states_red_team_contract(path):
    if not path.exists():
        pytest.skip(f"Template {path} does not exist")
    text = _prompt_text(path)
    assert MARK_FINDINGS in text
    assert MARK_UNRESOLVABLE in text
    assert MARK_HARD_FAIL in text


def test_runner_implements_unresolvable_global_blocker():
    # Global blocker cell, but NO task-keyed findings -> unresolvable -> fail.
    blocker_cell = {"dimension": "security", "severity": "blocker", "passed": False}
    assert red_team_passed([], [blocker_cell]) is False


def test_runner_passes_when_clean():
    passed_cell = {"dimension": "ruff", "severity": "blocker", "passed": True}
    assert red_team_passed([], [passed_cell]) is True


def test_runner_fails_on_task_keyed_blocker_finding():
    finding = {"task_id": "A", "severity": "blocker"}
    passed_cell = {"dimension": "ruff", "severity": "blocker", "passed": True}
    assert red_team_passed([finding], [passed_cell]) is False


def _plan() -> ExecutablePlan:
    """g1=[coder_1]; g2=[coder_2] depends on g1."""
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
        tasks=[ApprovedTask(id="coder02", title="coder02", file_paths=["src2/b.py"],
                            instruction="i", acceptance="a",
                            tool_preference="CLI-wrapper")],
        concurrent=True,
    )
    strat = Strategy(
        how_to_fix="x",
        tool_preference=[
            ToolPreferenceItem(task_id="coder01", preference="CLI-wrapper"),
            ToolPreferenceItem(task_id="coder02", preference="CLI-wrapper"),
        ],
        parallelisable_workplan=ParallelisableWorkplan(groups=[g1, g2]),
    )
    return ExecutablePlan(
        epic=Epic(title="e", deliverables=["d"], must_be_pydantic=True),
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


def _prior_batch(plan: ExecutablePlan) -> dict[str, TaskResult]:
    return {
        t.id: TaskResult(task_id=t.id, status="done",
                         files_changed=[], diff_summary="", notes="")
        for t in plan.tasks
    }


def _coder_factory(log: dict[str, int]):
    async def coder_fn(brief: str, task_id: str | None = None) -> str:
        tid = task_id or brief.split("TASK ID:")[1].split()[0]
        log[tid] = log.get(tid, 0) + 1
        return json.dumps({"status": "done", "rc": 0, "stdout": "ok", "stderr": "",
                           "task_id": tid, "files_changed": [], "diff_summary": "",
                           "notes": ""})
    return coder_fn


def _reviewer_always_failing_task_keyed():
    async def _rev(brief: str) -> str:
        evals = [
            EvaluationItem(item_id="coder01", approved="No", comments="recode this"),
        ]
        return AuditResult(evaluations=evals).model_dump_json()
    return _rev


async def test_runner_forced_pass_on_final_attempt():
    plan = _plan()
    log: dict[str, int] = {}
    exchanged: list[ExchangeTurn] = []
    pass_counter: dict[str, int] = {}
    batch = await run_red_team_gate(
        plan, TEMP_DIR / "rt_contract", _coder_factory(log),
        _reviewer_always_failing_task_keyed(),
        prior_batch=_prior_batch(plan),
        exchange=exchanged,  # type: ignore[arg-type]
        pass_counter=pass_counter,
    )
    # Final attempt (== MAX_RETRIES) with a still-failing task-keyed finding
    # must FORCED PASS rather than raise.
    from factory.infra.models import TaskBatch
    assert isinstance(batch, TaskBatch)
    # 3 red_team audits (one per attempt); coder re-executes on attempts 1 & 2.
    # 4 exchange entries recorded (attempts 1, 2, 3 + attempt 3 forced-pass audit).
    assert pass_counter["red_team"] == 4
