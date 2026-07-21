"""Regression tests for baziforecaster-uqj06: spawn-all coders + halt-on-block.

No LLM keys required: coder_fn is stubbed and the ApprovedPlan is built in-process.

Validates end-to-end through `run_execute_phase`:

  * SPAWN-ALL — when a prerequisite group's only task returns `blocked`, the
    dependent group's unrelated tasks STILL spawn and execute (the old code
    short-circuited the whole dependent group with "produced 0 usable tasks").
  * HALT-ON-BLOCK — after ALL groups finish, if ANY task is `blocked`/`failed`
    (or produced no result), the run is hard-halted with
    `RuntimeError("[HALT] EXECUTE phase incomplete: <ids>")`, listing every
    incomplete task id. This guarantees incomplete work never reaches review.

These guard the fix from `baziforecaster-uqj06`. If a future change re-adds the
skip-short-circuit, tasks 2-6 silently vanish again — this test fails loudly.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import asyncio
import json
import subprocess

_orig_run = subprocess.run
def _mock_run(args, *args_, **kwargs):
    if args and isinstance(args, list) and len(args) > 0 and "./bd" in str(args[0]):
        class DummyCP:
            returncode = 0
            stdout = ""
            stderr = ""
        return DummyCP()
    return _orig_run(args, *args_, **kwargs)
subprocess.run = _mock_run

import factory.infra.runner as m
m._write_harness_patches = lambda task_id, files, bd="": ([], 1)

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
    """g1=[coder_1]; g2=[coder_2..coder_6] depends_on g1 (mirrors baziforecaster-hbh1)."""
    epic = Epic(title="e", deliverables=["d"], must_be_pydantic=True)
    g1 = WorkGroup(
        id="g1",
        tasks=[ApprovedTask(id="coder01", title="t1", file_paths=["src2/a.py"],
                            instruction="implement coder_1", acceptance="coder_1 ok",
                            tool_preference="CLI-wrapper")],
        concurrent=True,
    )
    g2 = WorkGroup(
        id="g2",
        depends_on=["g1"],
        tasks=[ApprovedTask(id=f"coder{i:02d}", title=f"t{i}", file_paths=[f"src2/{i}.py"],
                            instruction=f"implement coder_{i}", acceptance=f"coder_{i} ok",
                            tool_preference="CLI-wrapper") for i in range(2, 7)],
        concurrent=True,
    )
    strat = Strategy(
        how_to_fix="x",
        tool_preference={f"coder{i:02d}": "CLI-wrapper" for i in range(1, 7)},
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
        approved=True
    )


def _coder_block_first(blocked_ids: set[str], spawned: dict[str, str] | None = None):
    """Coder stub: returns `blocked` for ids in blocked_ids, else `done`.

    Records every spawned task into `spawned` so the test can assert all
    dependent-group coders still ran despite a prerequisite block.
    """
    def _make(blocked: set[str]):
        async def coder_fn(brief: str, task_id: str | None = None) -> str:
            tid = task_id or brief.split("TASK ID:")[1].split()[0]
            if spawned is not None:
                spawned[tid] = brief
            status = "blocked" if tid in blocked else "done"
            return json.dumps({"status": status, "rc": 0, "stdout": "ok", "stderr": "",
                                "task_id": tid, "files_changed": [], "diff_summary": "",
                                "notes": "blocked on read budget" if status == "blocked" else ""})
        return coder_fn
    return _make(blocked_ids)


def _coder_record_spawn(spawned: dict[str, str]):
    async def coder_fn(brief: str, task_id: str | None = None) -> str:
        tid = task_id or brief.split("TASK ID:")[1].split()[0]
        spawned[tid] = brief
        return json.dumps({"status": "done", "rc": 0, "stdout": "ok", "stderr": "",
                            "task_id": tid, "files_changed": [], "diff_summary": "",
                            "notes": ""})
    return coder_fn


def test_spawn_all_when_prerequisite_blocked():
    """SPAWN-ALL: task_1 blocks but tasks 2-6 MUST still spawn and execute."""
    plan = _plan()
    spawned: dict[str, str] = {}
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(run_execute_phase(
            plan, TEMP_DIR / "spawn_all", asyncio.Semaphore(20),
            _coder_block_first({"coder01"}, spawned),
        ))
    # All six coders spawned despite the prerequisite block.
    assert set(spawned) == {f"coder{i:02d}" for i in range(1, 7)}
    # The halt names only the incomplete task(s).
    assert "[HALT] EXECUTE phase incomplete: coder01" in str(exc.value)


def test_halt_lists_all_incomplete_tasks():
    """HALT-ON-BLOCK: multiple blocked tasks are all reported, not just one."""
    plan = _plan()
    spawned: dict[str, str] = {}
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(run_execute_phase(
            plan, TEMP_DIR / "spawn_all_multi", asyncio.Semaphore(20),
            _coder_block_first({"coder01", "coder04", "coder06"}, spawned),
        ))
    assert set(spawned) == {f"coder{i:02d}" for i in range(1, 7)}
    msg = str(exc.value)
    assert "[HALT] EXECUTE phase incomplete:" in msg
    for tid in ("coder01", "coder04", "coder06"):
        assert tid in msg


def test_no_halt_when_all_done():
    """No regression: a fully-successful run proceeds without raising."""
    plan = _plan()
    spawned: dict[str, str] = {}
    results = asyncio.run(run_execute_phase(
        plan, TEMP_DIR / "spawn_all_ok", asyncio.Semaphore(20),
        _coder_record_spawn(spawned),
    ))
    assert set(spawned) == {f"coder{i:02d}" for i in range(1, 7)}
    assert all(r.status == "done" for r in results.values())


def test_halt_on_exception_mapping():
    """Verify that if coder_fn raises an exception, the runner wraps it into a TaskResult(status="blocked") instead of crashing."""
    plan = _plan()
    
    async def throwing_coder_fn(brief: str, task_id: str | None = None) -> str:
        tid = task_id or brief.split("TASK ID:")[1].split()[0]
        if tid == "coder01":
            raise RuntimeError("Simulation of a tool/subprocess failure")
        return json.dumps({"status": "done", "rc": 0, "stdout": "ok", "stderr": "",
                            "task_id": tid, "files_changed": [], "diff_summary": "",
                            "notes": ""})

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(run_execute_phase(
            plan, TEMP_DIR / "spawn_all_exception", asyncio.Semaphore(20),
            throwing_coder_fn,
        ))
    msg = str(exc.value)
    assert "[HALT] EXECUTE phase incomplete: coder01" in msg
