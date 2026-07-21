"""Dedicated 'stupid' timeout test.

The whole point of this file: prove the harness ACTUALLY trips its timeouts
instead of hanging forever. We set the timeout constants to tiny values (1
second) via monkeypatch -- test-only, the live constants stay 600/1800 -- and
assert the run HALTS rather than stalls.

No LLM keys required: coder_fn is stubbed and the ApprovedPlan is built in-process.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import asyncio
import json

import pytest

from factory.infra.control import TEMP_DIR
from factory.infra.models import (
    ApprovedTask,
    Epic,
    ExecutablePlan,
    ParallelisableWorkplan,
    RubricCell,
    RubricCube,
    Strategy,
    UserStory,
    WorkGroup,
)
from factory.infra.runner import run_execute_phase


def _plan() -> ExecutablePlan:
    epic = Epic(title="e", deliverables=["d"], must_be_pydantic=True)
    g1 = WorkGroup(
        id="g1",
        tasks=[ApprovedTask(id="coder01", title="t1", file_paths=["src2/a.py"],
                            instruction="implement coder01", acceptance="coder01 ok",
                            tool_preference="CLI-wrapper")],
        concurrent=True,
    )
    g2 = WorkGroup(
        id="g2",
        depends_on=["g1"],
        tasks=[ApprovedTask(id=f"coder{i:02d}", title=f"t{i}", file_paths=[f"src2/{i}.py"],
                            instruction=f"implement coder{i:02d}", acceptance=f"coder{i:02d} ok",
                            tool_preference="CLI-wrapper") for i in range(2, 5)],
        concurrent=True,
    )
    strat = Strategy(
        how_to_fix="x",
        tool_preference={f"coder{i:02d}": "CLI-wrapper" for i in range(1, 5)},
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
        tasks=list(g1.tasks) + list(g2.tasks),
        alignment="align",
        workplan=ParallelisableWorkplan(groups=[g1, g2]),
        strategy=strat,
        approved=True,
    )


def test_per_task_timeout_fires_at_one_second(monkeypatch):
    """AGENT_RUN_TIMEOUT=1 must trip and block the hung coder (no infinite stall)."""
    import factory.infra.runner as m
    monkeypatch.setattr(m, "AGENT_RUN_TIMEOUT", 1.0)
    monkeypatch.setattr(m, "DAG_DEADLOCK_TIMEOUT", 30.0)

    async def hang_coder_fn(brief: str, task_id: str | None = None) -> str:
        tid = task_id or brief.split("TASK ID:")[1].split()[0]
        if tid == "coder01":
            await asyncio.sleep(2.0)
        return json.dumps({"status": "done", "task_id": tid, "files_changed": [],
                           "diff_summary": "", "notes": ""})

    with pytest.raises(RuntimeError, match="EXECUTE phase incomplete.*coder01"):
        asyncio.run(run_execute_phase(
            _plan(), TEMP_DIR / "timeout_fire_task", asyncio.Semaphore(20), hang_coder_fn,
        ))


def test_dependent_group_timeout_fires_at_one_second(monkeypatch):
    """A hung coder in a DEPENDENT group (g2 waits on g1) must still trip the
    per-task timeout and halt the whole EXECUTE phase -- not hang on the DAG wait.

    Note: the DAG liveness guard is intentionally unbounded (slow-but-legit work
    must be allowed to finish), so the real fail-loud trip is AGENT_RUN_TIMEOUT,
    which wraps every coder_fn including those in downstream groups.
    """
    import factory.infra.runner as m
    monkeypatch.setattr(m, "AGENT_RUN_TIMEOUT", 1.0)
    monkeypatch.setattr(m, "DAG_DEADLOCK_TIMEOUT", 60.0)

    async def hang_coder_fn(brief: str, task_id: str | None = None) -> str:
        tid = task_id or brief.split("TASK ID:")[1].split()[0]
        if tid == "coder02":  # lives in the dependent group g2
            await asyncio.sleep(2.0)
        return json.dumps({"status": "done", "task_id": tid, "files_changed": [],
                           "diff_summary": "", "notes": ""})

    with pytest.raises(RuntimeError, match="EXECUTE phase incomplete.*coder02"):
        asyncio.run(run_execute_phase(
            _plan(), TEMP_DIR / "timeout_fire_dep", asyncio.Semaphore(20), hang_coder_fn,
        ))
