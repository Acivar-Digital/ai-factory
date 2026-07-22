"""Shared stdlib helpers for the shadow CLI codebase tools.

Replaces the legacy external ``infra/codebase/mcp_codebase.py`` dependency so the
admin/tools CLI wrappers are fully self-contained within the repo (no libcst, no
out-of-repo imports). Keeps the ``{success, message, data}`` JSON envelope that the
orchestrator harness (factory/infra/tools.py ``_run_tool``) consumes as a
raw stdout string, and that the test suite asserts against.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EXCLUDE_DIRS = {"__pycache__", ".git", ".venv", "node_modules", ".agent", ".gemini"}
INCLUDE_EXTENSIONS = {".py", ".md", ".json", ".txt", ".yaml", ".yml", ".toml", ".sql", ".sh"}


def _resolve_target_root() -> Path:
    """Return TARGET_REPO if set (for reads), else PROJECT_ROOT (backward compat)."""
    tr = os.environ.get("TARGET_REPO")
    return Path(tr).resolve() if tr else PROJECT_ROOT.resolve()


def _safe_relative(path: Path) -> str:
    root = _resolve_target_root()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _normalize_content(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def resolve_secure_path(relative_path: str) -> Path:
    """Resolve a path against TARGET_REPO if set, else PROJECT_ROOT (for reads).

    When TARGET_REPO env var is set, all paths resolve against the target repo.
    Factory files (.env, runner.py, etc.) become invisible — the agent has no
    business reading them. Falls back to PROJECT_ROOT for backward compat.
    """
    root = _resolve_target_root()
    if relative_path.startswith(f"{root.name}/"):
        relative_path = relative_path[len(f"{root.name}/") :]
    elif relative_path == root.name:
        relative_path = ""
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Path escape detected: {relative_path}")
    return target


def resolve_repo_path(relative_path: str) -> Path:
    """Resolve a path against PROJECT_ROOT (factory repo) for write tools.

    Always uses the factory repo root, so write tools write to factory/temp/
    regardless of TARGET_REPO. Sandboxed against path escape, same as
    resolve_secure_path.
    """
    root = PROJECT_ROOT.resolve()
    if relative_path.startswith(f"{root.name}/"):
        relative_path = relative_path[len(f"{root.name}/") :]
    elif relative_path == root.name:
        relative_path = ""
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Path escape detected: {relative_path}")
    return target


def ok(message: str, data: dict) -> dict:
    return {"success": True, "message": message, "data": data}


def fail(message: str) -> dict:
    return {"success": False, "message": message}
