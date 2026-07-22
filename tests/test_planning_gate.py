"""Regression tests for the Mandatory Planning Hard Gate (docs/FIX.md).

Every agent is strictly forbidden from executing any tool except `remember`,
`final_result`, or `keep_memory` until it has called `remember` to record its
step-by-step plan. GuardToolset.call_tool enforces this:

  * Non-exempt tools return a nudge string (block) before planning.
  * After 3 blocked attempts, RuntimeError is raised (fail loudly).
  * `remember` sets _has_planned = True, unblocking all tools.

If a future change removes or weakens this gate, these tests fail loudly.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from factory.infra.tools import GuardToolset


class _FakeTool:
    """Minimal ToolsetTool stand-in (only identity matters for the guard)."""


class _FakeWrapped:
    """Records executed calls so tests can prove a tool did/didn't execute."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, tool_args: dict, ctx, tool) -> str:
        self.calls.append((name, dict(tool_args)))
        return f"CONTENT:{name}"


def _make_guard(budget: int = 100) -> GuardToolset:
    wrapped = _FakeWrapped()
    gt = GuardToolset(
        wrapped=wrapped,  # type: ignore[arg-type]
        budget=budget,
        read_budget=5,
        read_file_budget=10,
    )
    gt._known_tools = {
        "remember": _FakeTool(),
        "keep_memory": _FakeTool(),
        "batch_read": _FakeTool(),
        "read_file": _FakeTool(),
        "write_file": _FakeTool(),
    }  # type: ignore[index]
    return gt


async def test_non_exempt_tool_blocked_before_planning() -> None:
    gt = _make_guard()
    res = await gt.call_tool(
        "batch_read", {"paths": ["a.py"]}, None, _FakeTool()
    )
    assert "SYSTEM ERROR" in res
    assert "remember" in res
    assert gt._plan_nudges == 1
    assert gt._has_planned is False
    assert len(gt.wrapped.calls) == 0  # tool NOT executed


async def test_remember_sets_has_planned() -> None:
    gt = _make_guard()
    assert gt._has_planned is False
    await gt.call_tool("remember", {"note": "my plan"}, None, _FakeTool())
    assert gt._has_planned is True


async def test_exempt_tools_not_blocked_before_planning() -> None:
    gt = _make_guard()
    for name in ("remember", "final_result", "keep_memory"):
        res = await gt.call_tool(name, {"note": "plan"}, None, _FakeTool())
        assert "SYSTEM ERROR" not in res
        assert gt._plan_nudges == 0


async def test_non_exempt_tool_allowed_after_planning() -> None:
    gt = _make_guard()
    await gt.call_tool("remember", {"note": "my plan"}, None, _FakeTool())
    assert gt._has_planned is True
    res = await gt.call_tool(
        "batch_read", {"paths": ["a.py"]}, None, _FakeTool()
    )
    assert "SYSTEM ERROR" not in res
    assert ("batch_read", {"paths": ["a.py"]}) in gt.wrapped.calls  # tool WAS executed


async def test_three_strikes_raises_runtime_error() -> None:
    gt = _make_guard()
    for i in range(2):
        res = await gt.call_tool(
            "batch_read", {"paths": ["a.py"]}, None, _FakeTool()
        )
        assert "SYSTEM ERROR" in res
        assert gt._plan_nudges == i + 1
    try:
        await gt.call_tool("batch_read", {"paths": ["a.py"]}, None, _FakeTool())
        assert False, "Expected RuntimeError after 3 strikes"
    except RuntimeError as exc:
        assert "HALT" in str(exc)
        assert "3 times" in str(exc)


async def test_plan_nudges_resets_after_remember() -> None:
    gt = _make_guard()
    await gt.call_tool("batch_read", {"paths": ["a.py"]}, None, _FakeTool())
    assert gt._plan_nudges == 1
    await gt.call_tool("remember", {"note": "my plan"}, None, _FakeTool())
    assert gt._has_planned is True
    res = await gt.call_tool(
        "batch_read", {"paths": ["a.py"]}, None, _FakeTool()
    )
    assert "SYSTEM ERROR" not in res
    assert ("batch_read", {"paths": ["a.py"]}) in gt.wrapped.calls


async def test_final_result_exempt_does_not_increment_nudges() -> None:
    gt = _make_guard()
    await gt.call_tool("final_result", {"output": "done"}, None, _FakeTool())
    assert gt._plan_nudges == 0
    assert gt._has_planned is False


async def test_keep_memory_exempt_does_not_increment_nudges() -> None:
    gt = _make_guard()
    await gt.call_tool("keep_memory", {"note": "plan"}, None, _FakeTool())
    assert gt._plan_nudges == 0
    assert gt._has_planned is False


async def test_write_file_blocked_before_planning() -> None:
    gt = _make_guard()
    res = await gt.call_tool(
        "write_file", {"relative_path": "x.py", "content": "..."}, None, _FakeTool()
    )
    assert "SYSTEM ERROR" in res
    assert len(gt.wrapped.calls) == 0


async def test_read_file_blocked_before_planning() -> None:
    gt = _make_guard()
    res = await gt.call_tool(
        "read_file", {"relative_path": "x.py"}, None, _FakeTool()
    )
    assert "SYSTEM ERROR" in res
    assert len(gt.wrapped.calls) == 0


async def test_replace_text_blocked_before_planning() -> None:
    gt = _make_guard()
    res = await gt.call_tool(
        "replace_text", {"relative_path": "x.py", "old": "a", "new": "b"},
        None, _FakeTool(),
    )
    assert "SYSTEM ERROR" in res
    assert len(gt.wrapped.calls) == 0


async def test_nudge_message_mentions_remember() -> None:
    gt = _make_guard()
    res = await gt.call_tool(
        "batch_read", {"paths": ["a.py"]}, None, _FakeTool()
    )
    assert "remember" in res.lower()
    assert "step-by-step" in res.lower()


async def test_has_planned_and_plan_nudges_initialized_in_post_init() -> None:
    gt = _make_guard()
    assert hasattr(gt, "_has_planned")
    assert hasattr(gt, "_plan_nudges")
    assert gt._has_planned is False
    assert gt._plan_nudges == 0


if __name__ == "__main__":
    asyncio.run(test_non_exempt_tool_blocked_before_planning())
    asyncio.run(test_remember_sets_has_planned())
    asyncio.run(test_exempt_tools_not_blocked_before_planning())
    asyncio.run(test_non_exempt_tool_allowed_after_planning())
    asyncio.run(test_three_strikes_raises_runtime_error())
    asyncio.run(test_plan_nudges_resets_after_remember())
    asyncio.run(test_final_result_exempt_does_not_increment_nudges())
    asyncio.run(test_keep_memory_exempt_does_not_increment_nudges())
    asyncio.run(test_write_file_blocked_before_planning())
    asyncio.run(test_read_file_blocked_before_planning())
    asyncio.run(test_replace_text_blocked_before_planning())
    asyncio.run(test_nudge_message_mentions_remember())
    asyncio.run(test_has_planned_and_plan_nudges_initialized_in_post_init())
    print("OK")
