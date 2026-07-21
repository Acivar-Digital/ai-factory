"""Test the coder_fn/reviewer_fn adapter closures and PHASE_SUMMARIES coder guard.

Bug 2 (runner.py): record_coder and do_role have 6/8 required params but call
site coder_fn(brief, task_id=t.id) supplies only 2. The fix wraps them in
closure adapters inside runner.main().

Bug 3 (agent.py): PHASE_SUMMARIES[role] write inside load_skill races when
multiple coders run concurrently. The fix guards writes for role != "coder".
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart

from factory.infra import agent
from factory.infra import _runtime
from factory.infra.pipeline import record_coder, _recover_from_unexpected_behavior
from factory.infra.exchange import ExchangeTurn


# ── helpers ────────────────────────────────────────────────────────────────


class _MockResult:
    """Minimal stand-in for an agent RunResult."""

    def __init__(self, output: object, messages: list | None = None) -> None:
        self.output = output
        self._messages = messages or []

    def all_messages(self) -> list:
        return self._messages

    def usage(self) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(input_tokens=0, output_tokens=0, requests=0)


# ── coder_fn adapter contract ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_coder_fn_adapter_contract(monkeypatch) -> None:
    """Verify a callable that matches coder_fn(brief, task_id) -> str can
    bridge to record_coder's full signature via closure."""
    calls: list[dict[str, object]] = []

    async def fake_load_skill(
        role: str, brief: str, bd: str, task_id: str | None = None
    ) -> str:
        calls.append({"role": role, "brief": brief, "bd": bd, "task_id": task_id})
        return json.dumps({"status": "done", "task_id": task_id or "coder00", "files_changed": [], "diff_summary": "", "notes": ""})

    monkeypatch.setattr("factory.infra.pipeline.load_skill", fake_load_skill)
    monkeypatch.setattr("factory.infra.pipeline.update_status_board", lambda *a, **kw: None)

    bd = "test-bd"
    history: list[tuple[str, str]] = []
    prior: list = []
    state = {"brief": "test task", "seeded": False}

    # Simulate the adapter closure from runner.py
    async def _coder_fn(brief: str, task_id: str | None = None) -> str:
        return await record_coder(brief, bd, history, prior, state, task_id=task_id)

    # ── invoke like execution.py does ──────────────────────────────────
    out = await _coder_fn("write the code", task_id="coder01")
    parsed = json.loads(out)
    assert parsed["task_id"] == "coder01"
    assert parsed["status"] == "done"
    assert len(calls) == 1
    assert calls[0]["role"] == "coder"
    assert calls[0]["bd"] == "test-bd"
    assert calls[0]["task_id"] == "coder01"
    assert "write the code" in calls[0]["brief"]


@pytest.mark.asyncio
async def test_coder_fn_replay_respects_seeded(monkeypatch) -> None:
    """Second call with same state sees seeded=True, skips prior prepend."""
    call_count: int = 0

    async def fake_load_skill(role: str, brief: str, bd: str, task_id: str | None = None) -> str:
        nonlocal call_count
        call_count += 1
        return json.dumps({"status": "done", "task_id": task_id or "coder00", "files_changed": [], "diff_summary": "", "notes": ""})

    monkeypatch.setattr("factory.infra.pipeline.load_skill", fake_load_skill)
    monkeypatch.setattr("factory.infra.pipeline.update_status_board", lambda *a, **kw: None)

    bd = "test-bd"
    history: list[tuple[str, str]] = []
    prior = [ExchangeTurn(role="planner", pass_no=1, content="plan")]
    state = {"brief": "test task", "seeded": False}

    async def _coder_fn(brief: str, task_id: str | None = None) -> str:
        return await record_coder(brief, bd, history, prior, state, task_id=task_id)

    # First call — prior is truthy and seeded=False => prior_injected
    # In this test we can't easily assert the injection happened, but we
    # verify seeded flips to True and second call completes without error.
    out1 = await _coder_fn("first task", task_id="coder01")
    assert json.loads(out1)["task_id"] == "coder01"
    assert call_count == 1
    assert state["seeded"] is True, "state.seeded must flip after first call"

    # Second call — seeded=True, prior prepend skipped
    out2 = await _coder_fn("second task", task_id="coder02")
    assert json.loads(out2)["task_id"] == "coder02"
    assert call_count == 2


# ── reviewer_fn adapter contract ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_reviewer_fn_adapter_contract(monkeypatch) -> None:
    """Verify reviewer_fn(brief) -> str bridges to load_skill(role, brief, bd)."""
    load_skill_calls: list[dict[str, str]] = []

    async def fake_load_skill(role: str, brief: str, bd: str, task_id: str | None = None) -> str:
        load_skill_calls.append({"role": role, "brief": brief, "bd": bd})
        return json.dumps({"evaluations": [{"item_id": "coder01", "approved": "Yes", "comments": "ok"}]})

    monkeypatch.setattr("factory.infra.pipeline.load_skill", fake_load_skill)
    monkeypatch.setattr("factory.infra.agent.load_skill", fake_load_skill)
    monkeypatch.setattr("factory.infra.pipeline.update_status_board", lambda *a, **kw: None)

    bd = "test-bd"

    async def _run_supervisor_review(brief: str) -> str:
        return await agent.load_skill("supervisor_review", brief, bd)

    out = await _run_supervisor_review("review this batch")
    parsed = json.loads(out)
    assert "evaluations" in parsed
    assert len(load_skill_calls) == 1
    assert load_skill_calls[0]["role"] == "supervisor_review"


# ── PHASE_SUMMARIES coder guard ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_skill_does_not_write_phase_summaries_for_coder(monkeypatch) -> None:
    """load_skill with role='coder' must NOT write to PHASE_SUMMARIES
    to avoid concurrent-write races (Bug 3)."""
    monkeypatch.setattr("factory.infra.agent.build_role_agent", lambda role: (None, None))
    monkeypatch.setattr("factory.infra.agent.build_md_bridge", lambda role, agent_id=None: None)
    monkeypatch.setattr("factory.infra.agent.log_response_raw", lambda **kw: None)
    monkeypatch.setattr("factory.infra.agent.append_eval_log", lambda **kw: None)
    monkeypatch.setattr("factory.infra.agent.persist_role", lambda role, result, agent_id=None: None)
    monkeypatch.setattr("factory.infra.agent.set_current_role", lambda role: None)
    monkeypatch.setattr("factory.infra.agent.set_current_agent", lambda agent_id: None)
    monkeypatch.setattr("factory.infra.agent._coder_agent_id", lambda task_id: task_id)
    monkeypatch.setattr("factory.infra.agent._model_to_md", lambda output: str(output))

    async def fake_run_agent(*args, **kwargs):
        return _MockResult("coder output", messages=[ModelRequest(parts=[UserPromptPart(content="hi")])])

    monkeypatch.setattr("factory.infra.agent._run_agent_retry", fake_run_agent)

    _runtime.PHASE_SUMMARIES.clear()
    _runtime.PHASE_SUMMARIES["planner"] = "existing plan summary"

    validated_json = await agent.load_skill("coder", "write code", bd="test-bd", task_id="coder01")
    assert "coder" not in _runtime.PHASE_SUMMARIES, (
        "PHASE_SUMMARIES must NOT contain 'coder' entry to avoid concurrent-write race"
    )
    # Other role entries must remain untouched
    assert _runtime.PHASE_SUMMARIES["planner"] == "existing plan summary"


@pytest.mark.asyncio
async def test_load_skill_writes_phase_summaries_for_planner(monkeypatch) -> None:
    """Non-coder roles MUST still write to PHASE_SUMMARIES."""
    monkeypatch.setattr("factory.infra.agent.build_role_agent", lambda role: (None, None))
    monkeypatch.setattr("factory.infra.agent.build_md_bridge", lambda role, agent_id=None: None)
    monkeypatch.setattr("factory.infra.agent.log_response_raw", lambda **kw: None)
    monkeypatch.setattr("factory.infra.agent.append_eval_log", lambda **kw: None)
    monkeypatch.setattr("factory.infra.agent.persist_role", lambda role, result, agent_id=None: None)
    monkeypatch.setattr("factory.infra.agent.set_current_role", lambda role: None)
    monkeypatch.setattr("factory.infra.agent.set_current_agent", lambda agent_id: None)
    monkeypatch.setattr("factory.infra.agent._coder_agent_id", lambda task_id: task_id)
    monkeypatch.setattr("factory.infra.agent._model_to_md", lambda output: str(output))

    async def fake_run_agent(*args, **kwargs):
        return _MockResult("planner output", messages=[ModelRequest(parts=[UserPromptPart(content="hi")])])

    monkeypatch.setattr("factory.infra.agent._run_agent_retry", fake_run_agent)

    _runtime.PHASE_SUMMARIES.clear()

    validated_json = await agent.load_skill("planner", "make a plan", bd="test-bd")
    assert "planner" in _runtime.PHASE_SUMMARIES
    assert _runtime.PHASE_SUMMARIES["planner"] == "planner output"
