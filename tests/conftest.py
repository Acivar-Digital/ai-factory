"""Shared fixtures for the orchestrator GOLD test suite (BIFR adoption).

Bootstraps the import path and gives every gold test a hermetic runtime dir so
Boundary/Freeze artifacts (io_*.log, fail_*.json, freeze_*.json) never touch the
real repo. See infra/testing_framework.md §GOLD TEST SUITE.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from factory.infra import _loopguard as loopguard_mod  # noqa: E402
from factory.infra import control as ctrl  # noqa: E402
from factory.infra import runner as runner_mod  # noqa: E402
from factory.infra import tools as tools_mod  # noqa: E402


@pytest.fixture
def orch_runtime(tmp_path, monkeypatch):
    """Redirect the harness runtime root to a temp dir (hermetic gold tests)."""
    rt = tmp_path / "orch"
    monkeypatch.setattr(ctrl, "ORCH_ROOT", rt)
    if hasattr(runner_mod, "ORCH_ROOT"):
        monkeypatch.setattr(runner_mod, "ORCH_ROOT", rt)
    monkeypatch.setattr(loopguard_mod, "ORCH_ROOT", rt)
    if hasattr(tools_mod, "ORCH_ROOT"):
        monkeypatch.setattr(tools_mod, "ORCH_ROOT", rt)
    (rt / "logs" / "runtime").mkdir(parents=True, exist_ok=True)
    return rt


@pytest.fixture
def freeze_dir(tmp_path) -> Path:
    d = tmp_path / "freeze"
    d.mkdir(parents=True, exist_ok=True)
    return d
