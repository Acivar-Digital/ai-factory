"""Regression tests for 01_fix.md: red-team gate vocabulary crash (baziforecaster-61y93).

Root cause: red_team evaluated by planner's `US-*` user-story ids, but the gate
could not map `US-3` -> `coder03` (the planner's `coder_idents` were empty), so
it raised HARD FAIL on attempt 1 — aborting the whole run even though the engine
shims it cited were fine.

Fix: the gate resolves a rejected item to a coder via authoritative FILE
OWNERSHIP (file_paths -> coder_N), with rubric coder_idents + comment filenames
as backstops. A vocabulary slip (US-*) that stays unresolvable is FORCE-PASSED
(propose-only, unpushed) on the final attempt instead of aborting.

No LLM keys required: coder_fn + reviewer_fn are stubbed in-process.
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
    EvaluationItem,
    ExecutablePlan,
    ParallelisableWorkplan,
    RubricCell,
    RubricCube,
    Strategy,
    TaskResult,
    WorkGroup,
)
from factory.infra.exchange import ExchangeTurn
from factory.infra.pipeline import run_red_team_gate
from factory.infra.validation import MAX_RETRIES


def _plan() -> ExecutablePlan:
    """g1=[coder01->src2/a.py]; g2=[coder02->src2/b.py] depends on g1."""
    g1 = WorkGroup(
        id="g1",
        tasks=[ApprovedTask(id="coder01", title="coder01", file_paths=["src2/a.py"],
                            instruction="i", acceptance="a",
                            tool_preference="CLI-wrapper")],
    )
    g2 = WorkGroup(
        id="g2",
        depends_on=["g1"],
        tasks=[ApprovedTask(id="coder02", title="coder02", file_paths=["src2/b.py"],
                            instruction="i", acceptance="a",
                            tool_preference="CLI-wrapper")],
    )
    strat = Strategy(
        how_to_fix="x",
        tool_preference={"coder01": "CLI-wrapper", "coder02": "CLI-wrapper"},
        parallelisable_workplan=ParallelisableWorkplan(groups=[g1, g2]),
    )
    return ExecutablePlan(
        epic=Epic(title="e", deliverables=["d"], must_be_pydantic=True),
        definition_of_done=["d"],
        acceptance_criteria=["a"],
        rubric_cube=RubricCube(cells=[RubricCell(dimension="security", criterion="engine_cleanout",
                                                  severity="blocker", passed=True)]),
        summary="s",
        tasks=[g1.tasks[0], g2.tasks[0]],
        alignment="align",
        workplan=ParallelisableWorkplan(groups=[g1, g2]),
        strategy=strat,
        approved=True,
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


def _reviewer_always_failing_US_vocab():
    """The crash repro: red_team rejects `US-3` (planner's vocab), not `coder_N`.
    The comment names a real file path so the gate's file-ownership resolver can
    still map US-3 -> coder02 and list it in the forced-pass marker."""
    async def _rev(brief: str) -> str:
        evals = [
            EvaluationItem(item_id="US-3", approved="No",
                           comments="dict shim in src2/b.py looks unsafe"),
        ]
        return AuditResult(evaluations=evals).model_dump_json()
    return _rev


def _patch_layer_passing(monkeypatch):
    """Isolate the gate test from the unrelated harness patch-generation layer:
    a coder that genuinely edited a file passes (real_changes > 0)."""
    def _fake_patches(tid, files, bd):
        return (files, 1)

    monkeypatch.setattr("factory.infra.context._write_harness_patches", _fake_patches)


def test_us_vocab_rejection_does_not_hard_fail(monkeypatch):
    """Run 01_fix.md crash repro: US-3 rejection must NOT raise HARD FAIL.
    The gate resolves US-3 -> coder02 via the filename in the comment, and on
    final attempt force-passes propose-only (unpushed)."""
    _patch_layer_passing(monkeypatch)
    plan = _plan()
    log: dict[str, int] = {}
    exchanged: list[ExchangeTurn] = []
    pass_counter: dict[str, int] = {}
    batch = asyncio.run(run_red_team_gate(
        plan, TEMP_DIR / "rt_vocab", _coder_factory(log),
        _reviewer_always_failing_US_vocab(),
        prior_batch=_prior_batch(plan),
        exchange=exchanged,  # type: ignore[arg-type]
        pass_counter=pass_counter,
    ))
    from factory.infra.models import TaskBatch
    assert isinstance(batch, TaskBatch)
    # 3 loop attempts (1,2,3) + the coerced-audit re-record on the final attempt.
    assert pass_counter["red_team"] >= MAX_RETRIES


def test_forced_pass_marker_names_review_files(monkeypatch):
    """On final attempt, the forced-pass evaluation carries a [FORCED PASS ...]
    marker listing exactly the files to review manually."""
    _patch_layer_passing(monkeypatch)
    plan = _plan()
    log: dict[str, int] = {}
    exchanged: list[ExchangeTurn] = []
    pass_counter: dict[str, int] = {}
    asyncio.run(run_red_team_gate(
        plan, TEMP_DIR / "rt_vocab_marker", _coder_factory(log),
        _reviewer_always_failing_US_vocab(),
        prior_batch=_prior_batch(plan),
        exchange=exchanged,  # type: ignore[arg-type]
        pass_counter=pass_counter,
    ))
    # The exchange JSONL captures the final (attempt == MAX_RETRIES) red_team audit.
    last_red = [t for t in exchanged if t.role == "red_team"]
    assert last_red, "red_team turns recorded in exchange"
    # The last red_team content should carry the forced-pass marker + resolved file.
    assert "[FORCED PASS attempt" in last_red[-1].content
    assert "src2/b.py" in last_red[-1].content


def test_plan_intent_block_present_in_planner_template():
    """Fix A: planner.yaml must state ONE FILE = ONE CODER + intent/scope/count."""
    import yaml

    PKG = Path(__file__).resolve().parents[1] / "factory"
    text = yaml.safe_load((PKG / "infra" / "agents" / "planner.yaml").read_text())
    instr = text.get("instructions", "")
    if isinstance(instr, dict):
        instr = " ".join(str(v) for v in instr.values() if isinstance(v, str))
    low = (instr or "").lower()
    assert "one file = one" in low
    assert "intent" in low
    assert "scope" in low


def test_reviewer_prompts_require_coder_n_item_id():
    """Fix D: red_team.yaml + supervisor_review.yaml must forbid US-* vocab."""
    import yaml

    PKG = Path(__file__).resolve().parents[1] / "factory"
    for name in ("red_team.yaml", "supervisor_review.yaml"):
        text = yaml.safe_load((PKG / "infra" / "agents" / name).read_text())
        instr = text.get("instructions", "")
        if isinstance(instr, dict):
            instr = " ".join(str(v) for v in instr.values() if isinstance(v, str))
        low = (instr or "").lower()
        assert "coder_" in low, f"{name} must require coder_N item_id"
        assert "us-*" in low, f"{name} must forbid US-* vocab"
