"""Shared mutable runtime state for the orchestrator pipeline."""
from __future__ import annotations

_RECOVERY_COUNT: int = 0
_COMPACTION_COUNT: int = 0
PHASE_SUMMARIES: dict[str, str] = {}
SCOPE_CONTEXT: str = ""
RAW_OUTPUTS: dict[str, str] = {}
_SKIPPED_PHASES: list[str] = []

_PHASE_ORDER = ["planner", "supervisor_plan", "coder", "supervisor_review", "red_team"]
