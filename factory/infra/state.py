"""Crash-resume durable state for the orchestrator (build.md §8.3, README Crash-Resume).

State lives in ``orch/reports/run_<ts>_<bd_id>/state.json``. The single source of
truth is the ``OrchestratorState`` Pydantic model (models.py); this module only
persists + reloads it.

Three invariants (verified by tests/test_state.py):

* **Atomic write** — ``save_state`` writes to ``state.json.tmp`` then ``os.replace``,
  so a kill mid-write never leaves a torn ``state.json``.
* **Resume** — ``load_state`` picks the NEWEST ``run_*_<bd_id>`` dir, so restarting
  with the same ``--bd`` continues the latest run.
* **Exactly-once re-execution** — ``reset_stale_in_progress`` flips any ``in_progress``
  task back to ``pending`` BEFORE spawn, so a killed run re-executes the precise
  failed unit, not the whole pipeline.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from factory.common.registry import resolve_run_dir
from factory.infra.control import REPORTS_DIR
from factory.infra.models import OrchestratorState, TaskState


def _reports_dir(reports_dir: Path | None = None) -> Path:
    return reports_dir or REPORTS_DIR


def _run_dir(bd_id: str, ts: str, reports_dir: Path | None = None) -> Path:
    return _reports_dir(reports_dir) / f"run_{ts}_{bd_id}"


def fresh_state(
    bd_id: str,
    global_alignment: str = "",
    reports_dir: Path | None = None,
    timestamp: str | None = None,
) -> OrchestratorState:
    """Create a brand-new run dir + empty ``OrchestratorState``.

    Pass an explicit ``timestamp`` only in tests to keep dir names deterministic.
    """
    ts = timestamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    run_dir = _run_dir(bd_id, ts, reports_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return OrchestratorState(
        bd_id=bd_id,
        run_dir=str(run_dir),
        timestamp=ts,
        global_alignment=global_alignment,
    )


def save_state(state: OrchestratorState) -> Path:
    """Atomically persist ``state`` to ``<run_dir>/state.json`` (os.replace)."""
    run_dir = Path(state.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    tmp = run_dir / "state.json.tmp"
    final = run_dir / "state.json"
    tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, final)  # atomic: never a torn state.json
    return final


def load_state(bd_id: str, reports_dir: Path | None = None) -> OrchestratorState | None:
    """Return the newest persisted ``OrchestratorState`` for ``bd_id``, else None.

    Delegates run-dir resolution to ``common.resolve_run_dir`` (newest
    ``run_*_<bd_id>`` with a ``state.json``, then TEMP fallback), then reads
    the state JSON.
    """
    run_dir = resolve_run_dir(bd_id, reports_dir=reports_dir)
    if run_dir is None:
        return None
    state_json = run_dir / "state.json"
    if not state_json.exists():
        return None
    return OrchestratorState.model_validate_json(state_json.read_text(encoding="utf-8"))


def reset_stale_in_progress(state: OrchestratorState) -> OrchestratorState:
    """Flip any ``in_progress`` task back to ``pending`` (exactly-once resume).

    Call this on the freshly loaded state, BEFORE spawning workers, so a run
    killed mid-task re-executes the precise unit rather than the whole pipeline.
    """
    for t in state.tasks.values():
        if t.status == "in_progress":
            t.status = "pending"
    return state


def record_phase(state: OrchestratorState, phase: str) -> OrchestratorState:
    """Advance ``current_phase`` and bump its attempt counter (append semantics)."""
    state.current_phase = phase
    state.phase_attempts[phase] = state.phase_attempts.get(phase, 0) + 1
    return state


def upsert_task(state: OrchestratorState, task: TaskState) -> OrchestratorState:
    """Append or replace a task's ``TaskState`` keyed by ``task_id``."""
    state.tasks[task.task_id] = task
    return state
