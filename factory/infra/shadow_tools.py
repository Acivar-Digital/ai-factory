"""Anti-rogue tool wrapper layer for the Orchestrator State Machine.

This module is the defensive perimeter that sits BETWEEN an LLM sub-agent and
the shadow CLI tools in ``factory/tools/*.py``. Every worker tool below:

1. Is budget-gated (``enforce_budget``) so a runaway/rogue agent cannot spin
   forever — the budget yields *gracefully* (returns a sentinel string) rather
   than hard-killing the run.
2. Routes ALL filesystem I/O through ``factory/tools/*.py`` via ``uv run`` —
   NEVER ``open()`` directly.
3. Is ACL-wrapped (``wrap_tools_with_acl``) so any path that escapes the repo
   boundary is denied and logged.

Budget vs. UsageLimits precedence (explicit):
  * ``enforce_budget`` is a SOFT, graceful trip. When ``tools_used > tool_budget``
    it returns a fixed string and lets the model emit its final result. It does
    NOT raise and does NOT abort the process.
  * pydantic-ai's ``UsageLimits`` is the FINAL HARD-KILL (token/request caps).
    It is intentionally NOT reimplemented here — it remains the orchestrator's
    last-resort backstop. Soft budget first, hard UsageLimits last.
"""

from __future__ import annotations

import functools
import os
from collections.abc import Callable
from typing import Any

from pydantic_ai import RunContext

from factory.common import _run_tool
from factory.infra import models, tools

# ── Reuse the hardened ACL containment check from tools.py (S2 hardened) ─────
# These are the canonical ACL helpers exported by tools.py.
_acl_within_repo = tools._within_repo
_acl_log = tools._log_acl_denied

# Path-arg parameter names the ACL wrapper will police. Mirrors tools.py so a
# path passed as ``filepath`` / ``relative_path`` / ``path`` etc. is caught.
_PATH_PARAMS = {
    "relative_path",
    "path",
    "filepath",
    "source_relative_path",
    "destination_relative_path",
    "source_path",
    "dest_path",
    "filename",
    "directory",
}

_FATAL_BUDGET = "FATAL: Tool budget exhausted. You MUST output your final result now."
_TOO_LARGE = "ERROR: File too large, use AST extraction tool."
_MAX_READ_LINES = 500


# ── 1. Budget gate ──────────────────────────────────────────────────────────
def enforce_budget(ctx: RunContext[models.AgentDependencies]) -> str | None:
    """Soft budget gate. Increments ``deps.tools_used``; if it EXCEEDS
    ``deps.tool_budget`` (trips at ``>``, NOT ``>=``) returns the exact FATAL
    sentinel telling the model to emit its final result. Otherwise returns None.

    Precedence: this is a graceful yield, NOT a hard kill. pydantic-ai
    ``UsageLimits`` remains the final hard-stop and is NOT implemented here.
    """
    deps = ctx.deps
    deps.tools_used = (deps.tools_used or 0) + 1
    if deps.tools_used > deps.tool_budget:
        return _FATAL_BUDGET
    return None


# ── 2. Safe (wrapped) read_file ─────────────────────────────────────────────
def _run_read_cli(filepath: str, start: int | None = None, end: int | None = None) -> str:
    """Run ``factory/tools/read_file.py`` via ``uv run`` and return raw stdout.

    Routes ALL file reads through the shadow CLI. Raises ``RuntimeError`` on a
    non-zero exit or subprocess failure so the caller can degrade gracefully.
    """
    argv = [filepath]
    if start is not None:
        argv += ["--start-line", str(start)]
    if end is not None:
        argv += ["--end-line", str(end)]
    result = _run_tool("read_file", argv)
    if result.startswith("ERROR("):
        raise RuntimeError(result)
    return result


def _line_count_of(raw: str) -> int:
    """Best-effort line count: prefers a JSON ``content`` field, else raw text."""
    try:
        import json

        data = json.loads(raw)
        if isinstance(data, dict):
            content = data.get("content")
            if isinstance(content, str):
                return len(content.splitlines())
            # Some CLIs return a list of line dicts / total_lines key.
            if isinstance(data.get("lines"), list):
                return len(data["lines"])
            if isinstance(data.get("total_lines"), int):
                return data["total_lines"]
    except Exception:
        pass
    return len(raw.splitlines())


def safe_read_file(ctx: RunContext[models.AgentDependencies], filepath: str) -> str:
    """Read a file through the shadow CLI. NEVER use raw ``open()``.

    Graceful on any error (returns ``"ERROR Reading File: <msg>"``). If the file
    exceeds ``_MAX_READ_LINES`` (500) lines, returns the too-large sentinel so
    the agent is forced onto an AST extraction tool instead.
    """
    try:
        raw = _run_read_cli(filepath)
    except Exception as e:  # noqa: BLE001 — fail gracefully, never raise to model
        return f"ERROR Reading File: {e}"

    if _line_count_of(raw) > _MAX_READ_LINES:
        return _TOO_LARGE

    return raw


# ── 3. Yield / escape hatch ─────────────────────────────────────────────────
def yield_to_orchestrator(ctx: RunContext[models.AgentDependencies], reason: str) -> str:
    """Escape hatch: force budget exhaustion (sentinel 999) and hand control
    back to the orchestrator with a reason.

    Setting ``tools_used = 999`` is the SENTINEL meaning "this worker has given
    up its turn" — the next ``enforce_budget`` call returns the FATAL string,
    so the agent stops tooling and emits its final result. It is NOT a blind
    999 misuse: it is the documented mechanism for a voluntary yield.
    """
    ctx.deps.tools_used = 999
    return f"YIELDING TO ORCHESTRATOR. Reason: {reason}"


# ── 4. ACL-wrapping helper ──────────────────────────────────────────────────
def wrap_tools_with_acl(
    tool_funcs: list[Callable[..., Any]],
    allowed_paths: list[str] | None = None,
) -> list[Callable[..., Any]]:
    """Wrap a list of tool callables with a repo-boundary (containment) check.

    For every string argument that looks like a path (param name in
    ``_PATH_PARAMS`` or ending in ``_path``), the wrapper calls ``_acl_within_repo``
    (imported from ``tools.py``; re-implemented minimally as fallback). A denial
    returns ``"ACL DENIED: ..."`` to the agent AND is logged via ``_acl_log``.

    ``allowed_paths`` is accepted for API parity with ``tools.wrap_with_acl`` but
    the hard containment check (repo boundary) always applies regardless.
    """
    wrapped: list[Callable[..., Any]] = []
    for func in tool_funcs:
        import inspect

        sig = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, _func: Callable[..., Any] = func, _sig: inspect.Signature = sig, **kwargs: Any) -> Any:
            try:
                bound = _sig.bind(*args, **kwargs)
            except TypeError as e:
                return f"ACL DENIED: invalid tool call to {_func.__name__}: {e}"
            bound.apply_defaults()
            for pname, pval in bound.arguments.items():
                if not isinstance(pval, str):
                    continue
                if pname in _PATH_PARAMS or pname.endswith("_path"):
                    norm_val = os.path.normpath(pval) if pval else ""
                    if not _acl_within_repo(norm_val):
                        _acl_log(
                            f"repo-boundary blocked '{pval}' in tool "
                            f"'{_func.__name__}' (exits REPO_ROOT)"
                        )
                        return (
                            "ACL DENIED: path escapes the repository boundary "
                            f"({pval}) and is forbidden."
                        )
            return _func(*args, **kwargs)

        setattr(wrapper, "__signature__", sig)  # preserve signature for pydantic-ai
        wrapped.append(wrapper)
    return wrapped
