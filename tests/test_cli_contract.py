"""CLI contract regression suite (factory/test/tools/test_cli_contract.py).

Protects the harness-level contracts the orchestrator silently depends on:

- coder tool-budget dynamic scaling + clamping (``tools._coder_budget_for``)
- staging/temp path normalization (``tools.normalize_read_path``)
- the local JSONL fact store used by the agent memory CLIs
  (``factory/tools/{remember,recall,list}_fact.py``)

If any of these regress, the coder/planner tool ACL and agent memory break
WITHOUT a loud error -- exactly the class of silent failure this suite exists
to catch before go-live.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from factory.infra.tools import _coder_budget_for, normalize_read_path


def test_coder_budget_dynamic_scales_and_clamps():
    """Budget scales with file count but is clamped to [MIN, MAX]."""
    assert _coder_budget_for(0) == 16   # effective files floored to 1 -> MIN
    assert _coder_budget_for(1) == 16
    assert _coder_budget_for(3) == 24
    assert _coder_budget_for(10) == 30  # clamps at MAX for big refactors
    assert _coder_budget_for(100) == 30
    # monotonic non-decreasing in file count
    assert _coder_budget_for(1) <= _coder_budget_for(2) <= _coder_budget_for(5)


def test_path_normalization_deduplication():
    """normalize_read_path strips staging/temp prefixes and dedups variants."""
    # absolute + staging prefix -> repo-relative
    assert normalize_read_path(
        "/home/yapilwsl/arthityap/baziforecaster/factory/temp/src2/foo.py"
    ) == "src2/foo.py"
    # staging-prefixed relative -> repo-relative
    assert normalize_read_path("factory/temp/src2/foo.py") == "src2/foo.py"
    # already repo-relative passes through unchanged
    assert normalize_read_path("src2/foo.py") == "src2/foo.py"
    # idempotent: re-normalizing a normalized path is a no-op
    p = "factory/temp/src2/foo.py"
    assert normalize_read_path(normalize_read_path(p)) == normalize_read_path(p)
    # windows separators normalized
    assert normalize_read_path("admin\\orchestrator\\temp\\src2\\foo.py") == "src2/foo.py"



