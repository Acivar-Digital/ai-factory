"""Tests for string output resilience in the orchestrator runner."""
from __future__ import annotations

import sys
from pathlib import Path
import pytest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from factory.infra import runner


class MockOutput:
    """Mock output object with no model_dump_json method."""
    def __init__(self, value: str):
        self.value = value

    def __str__(self):
        return self.value


class MockResult:
    """Mock RunResult with an output and usage."""
    def __init__(self, output: any):
        self.output = output
        self._messages = []

    def all_messages(self) -> list:
        return self._messages

    def usage(self) -> SimpleNamespace:
        return SimpleNamespace(input_tokens=0, output_tokens=0, requests=0)


@pytest.mark.asyncio
async def test_load_skill_string_output(monkeypatch) -> None:
    """Verify load_skill handles non-Pydantic string outputs and serializes cleanly."""
    # Mock build_role_agent to avoid setting up real agent models
    monkeypatch.setattr(runner, "build_role_agent", lambda role: (None, None))
    
    # Mock build_md_bridge to return no prior history
    monkeypatch.setattr(runner, "build_md_bridge", lambda role, agent_id=None: None)
    
    # Mock log_response_raw, append_eval_log, and persist_role to avoid side effects
    monkeypatch.setattr(runner, "persist_role", lambda role, result, agent_id=None: None)
    
    # Mock _run_agent_retry to return a MockResult carrying a string output (as an async function)
    mock_result = MockResult("This is a raw markdown or string plan output")
    async def fake_run_agent(*args, **kwargs):
        return mock_result
        
    monkeypatch.setattr(runner, "_run_agent_retry", fake_run_agent)
    
    # Run load_skill for a role (e.g. planner) and ensure it doesn't raise AttributeError
    validated_json = await runner.load_skill(role="planner", brief="Verify me", bd="dummy-bd")
    
    # Assert that the serialized JSON is the string representation of the output
    assert validated_json == "This is a raw markdown or string plan output"
    assert runner.RAW_OUTPUTS["planner"] == "This is a raw markdown or string plan output"
