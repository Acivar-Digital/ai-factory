from factory.infra.tools_const import *
'Tool confinement for the Orchestrator State Machine (build.md §4, §5c).\n\nEvery worker capability is a subprocess wrapper around an existing\n`factory/tools/*.py` CLI. Agents NEVER touch the filesystem directly — they\nreceive only the allow-listed, ACL-wrapped tools the orchestrator hands them.\n'
import contextvars
import functools
import inspect
import json
import logging
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel, model_validator
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai._run_context import AgentDepsT
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import FunctionToolset, WrapperToolset
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_core import SchemaValidator
from factory.common import OUTPUT_TYPE_REGISTRY, _run_tool, log_operator, resolve_model
from factory.infra.control import CODER_READ_FILE_BUDGET, CONTROL_SHEET, ORCH_ROOT, PKG_DIR, PYDANTIC_AI_INSTRUCTIONS, READ_BUDGET, REPO_ROOT, SKILL_MAP, SKILL_ROLES
from factory.infra.tools_memory import get_current_role, get_current_agent
from factory.infra.models import ApprovedTask, Strategy, TaskResult


def _auto_remember(note: str) -> None:
    try:
        from factory.infra import artefacts
        role = get_current_role()
        if role:
            artefacts.remember_note(role, note, agent_id=get_current_agent())
    except Exception:
        pass


def normalize_read_path(p: str) -> str:
    """Normalize a path to be relative to REPO_ROOT and strip staging/temp prefixes.

    Example:
      /abs/path/to/repo/factory/temp/src2/foo.py -> src2/foo.py
      factory/temp/src2/foo.py -> src2/foo.py
      src2/foo.py -> src2/foo.py
    """
    try:
        path_obj = Path(p)
        if path_obj.is_absolute():
            if path_obj.is_relative_to(REPO_ROOT):
                p = str(path_obj.relative_to(REPO_ROOT))
    except Exception:
        pass
    p = p.replace('\\', '/').strip('/')
    staging_prefixes = ['factory/temp/', 'factory/temp']
    for prefix in staging_prefixes:
        if p.startswith(prefix):
            p = p[len(prefix):].lstrip('/')
            break
    return p

def read_file(relative_path: str, start_line: int | None=None, end_line: int | None=None) -> str:
    """Read a file from the repo (optionally a 1-indexed line range). Returns JSON."""
    argv = [relative_path]
    if start_line is not None:
        argv += ['--start-line', str(start_line)]
    if end_line is not None:
        argv += ['--end-line', str(end_line)]
    result = _REMEMBER_NUDGE + _run_tool('read_file', argv) + _STEER
    _auto_remember(result)
    return result

def _parse_range(rng: str) -> tuple[int | None, int | None] | None:
    """Parse a 'start-end' or 'start' line-range string into 1-indexed ints.

    Returns None on a malformed range (e.g. a comma-joined multi-segment value
    like '400, 600-650, 760-800' that a model sometimes emits) so callers can
    surface a clean error instead of raising ValueError and killing the run.
    """
    if rng is None:
        return None
    rng = rng.strip()
    if not rng:
        return None
    if ',' in rng:
        return None
    if '-' in rng:
        a, b = rng.split('-', 1)
        try:
            return (int(a), int(b))
        except ValueError:
            return None
    try:
        return (int(rng), None)
    except ValueError:
        return None

def batch_read(paths: list[str], line_ranges: dict[str, str] | None=None) -> str:
    """Fetch MULTIPLE files in ONE call (declare-then-fetch).

    Replaces the old one-file-at-a-time read_file research loop. The agent
    declares the full set of files it needs up front; the harness fetches them
    once. `line_ranges` is MANDATORY per path (e.g. {"src2/foo.py": "10-100"})
    so each returned slice stays small. Returns a bundled, scoped report.

    Bounded by READ_BUDGET (attempts) — enforced by GuardToolset.
    """
    line_ranges = line_ranges or {}
    if not paths:
        return _BATCH_READ_NO_PATHS
    if len(paths) > MAX_BATCH_FILES:
        return f'batch_read: too many files ({len(paths)}). Max {MAX_BATCH_FILES} per call. Split into multiple batch_read calls with tighter line_ranges.'
    parts: list[str] = []
    missing_ranges: list[str] = []
    for p in paths:
        rng = line_ranges.get(p)
        if not rng:
            parsed = (1, _BATCH_READ_DEFAULT_HEAD)
            missing_ranges.append(p)
        else:
            parsed = _parse_range(rng)
            if parsed is None:
                return f"batch_read: malformed line_range {rng!r} for {p!r}. Use a single 'start-end' range (e.g. '400-500'), not comma-joined multi-segments. Re-call batch_read with a valid range."
        start, end = parsed
        argv = [p]
        if start is not None:
            argv += ['--start-line', str(start)]
        if end is not None:
            argv += ['--end-line', str(end)]
        res = _run_tool('read_file', argv)
        parts.append(res)
    steer = _BATCH_READ_STEER
    if missing_ranges:
        steer = f'\n---\nNote: no line_ranges given for {missing_ranges}; returned the first {_BATCH_READ_DEFAULT_HEAD} lines of each. Next time pass line_ranges={{path: "start-end"}} for a tighter slice.' + _BATCH_READ_STEER
    result = _REMEMBER_NUDGE + '\n\n'.join(parts) + steer
    _auto_remember(result)
    return result

def _src_ban_denied(norm_val: str) -> bool:
    """Return True if a normalized repo-relative path resolves inside src/ or src2/.

    Both src/ and src2/ are read-only for the harness — edits are confined to
    factory/. Catches traversal escapes via realpath resolution.
    """
    if not norm_val:
        return False
    if norm_val == 'src' or norm_val.startswith('src/'):
        return True
    if norm_val == 'src2' or norm_val.startswith('src2/'):
        return True
    candidate = REPO_ROOT / norm_val
    banned_roots = [(REPO_ROOT / 'src').resolve(), (REPO_ROOT / 'src2').resolve()]
    try:
        resolved = Path(os.path.realpath(candidate)).resolve()
    except (OSError, RuntimeError):
        return False
    for root in banned_roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False

def _src_write_guard(tool_name: str, *paths: str) -> str | None:
    """Deny a write/modify whose target path resolves inside src/ or src2/.

    Raises RuntimeError (Fail-Loudly) when a write targets a banned path, so the
    harness marks the task BLOCKED instead of returning a benign string the model
    treats as a successful write. Returns None when the path is allowed.
    """
    for p in paths:
        if not p or not p.strip():
            continue
        norm_val = os.path.normpath(p)
        if _src_ban_denied(norm_val):
            msg = '[OPERATOR][SECURITY] src/ write denied'
            print(msg, flush=True)
            _logger.warning(msg)
            raise RuntimeError(f'[HALT] {tool_name} blocked: {_SRC_BAN_MSG} (path={norm_val})')
    return None

def write_file(relative_path: str, content: str) -> str:
    """Write full content to a repo file. Returns JSON result.

    Fail-loud contract: the subprocess must actually create the file on disk.
    If the CLI reports success but the file is absent, we raise — the model must
    never be told a write happened when nothing landed on disk.
    """
    _src_write_guard('write_file', relative_path)
    target = (REPO_ROOT / relative_path).resolve()
    old_lines = target.read_text().splitlines(keepends=True) if target.exists() else []
    result = _run_tool('write_file', [relative_path, content])
    if not target.exists():
        raise RuntimeError(f'[HALT] write_file reported success but file is ABSENT on disk: {relative_path}')
    new_lines = content.splitlines(keepends=True)
    if old_lines != new_lines:
        import difflib
        diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=relative_path, tofile=relative_path, n=3))
        _auto_remember(f'[write_file] {relative_path}\n' + ''.join(diff))
    else:
        _auto_remember(f'[write_file] {relative_path} (no changes)')
    return result

def _check_edit_result(tool_name: str, out: str) -> str:
    try:
        import json
        obj = json.loads(out)
        if obj.get('status') == 'error':
            from pydantic_ai.exceptions import ModelRetry
            raise ModelRetry(f"{tool_name} failed: {obj.get('message', '')} {obj.get('error', '')}")
        data = obj.get('data', {})
        if obj.get('status') == 'success' and 'changed' in data and (not data['changed']):
            from pydantic_ai.exceptions import ModelRetry
            raise ModelRetry(f"{tool_name} failed: {obj.get('message', 'No changes made (target not found or already replaced).')}")
    except Exception as e:
        if type(e).__name__ == 'ModelRetry':
            raise
    return out

def delete_file(relative_path: str) -> str:
    """Delete a file/dir from the repo and clean its vector index. Returns JSON."""
    _g = _src_write_guard('delete_file', relative_path)
    if _g:
        return _g
    result = _check_edit_result('delete_file', _run_tool('delete_file', [relative_path]))
    _auto_remember(f'[delete_file] {relative_path}')
    return result

def rename_file(source_relative_path: str, destination_relative_path: str) -> str:
    """Rename/move a file and update the vector index. Returns JSON result."""
    _g = _src_write_guard('rename_file', source_relative_path, destination_relative_path)
    if _g:
        return _g
    result = _run_tool('rename_file', [source_relative_path, destination_relative_path])
    _auto_remember(f'[rename_file] {source_relative_path} → {destination_relative_path}')
    return result
