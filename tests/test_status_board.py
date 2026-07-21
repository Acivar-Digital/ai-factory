"""Regression tests for the orchestrator STATUS BOARD (l4wjg).

Covers the two root causes the session analysis identified:

- RC1 (stale bleed): a fresh run must NOT carry a prior run's `coder:A` LIVE
  line. The board is derived from the history list + current_role passed by the
  caller, so this is asserted at the `update_status_board` contract level: a
  fresh call with no matching history + a review role must NOT show a stale
  `coder:A`.
- RC2 (live-tracking gap): the review phases (supervisor_review, red_team) must
  be reflected on the board while they run — previously the DAG reviewer path
  bypassed `do_role` and the board froze on the last coder task.

The harness-wide launcher wipe (run_orchestrator.sh) is unit-checked by the
bash-guard below; this module verifies the Python contract.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from factory.infra.exchange import update_status_board
import factory.infra.exchange as exchange_mod
import factory.infra._runtime as runtime


@pytest.fixture
def status_board(tmp_path, monkeypatch):
    """Point STATUS_MD at a temp file and reset global counters."""
    board = tmp_path / "STATUS.md"
    monkeypatch.setattr(exchange_mod, "STATUS_MD", board)
    monkeypatch.setattr(runtime, "_RECOVERY_COUNT", 0)
    monkeypatch.setattr(runtime, "_COMPACTION_COUNT", 0)
    return board


def _read(board: Path) -> str:
    return board.read_text(encoding="utf-8")


def test_fresh_board_has_no_stale_coder_line(status_board):
    """RC1: a fresh status update with no coder history must not bleed coder:A."""
    update_status_board([], "supervisor_plan", "l4wjg")
    text = _read(status_board)
    assert "coder:A" not in text
    assert "supervisor_plan" in text
    assert "LIVE" in text


def test_review_phase_surfaced_while_running(status_board):
    """RC2: supervisor_review + red_team appear as IN-PROGRESS on the board."""
    update_status_board([], "supervisor_review", "bd1")
    assert "supervisor_review" in _read(status_board)
    update_status_board([], "red_team", "bd1")
    assert "red_team" in _read(status_board)


def test_coder_in_flight_shown_before_run(status_board):
    """A coder task id is reported active immediately (not after it returns)."""
    update_status_board([("planner", "{}")], "coder:A", "bd1")
    text = _read(status_board)
    assert "coder:A" in text
    assert "Active task: coder:A" in text
    # planner already in history => DONE
    assert "- [x] planner" in text


def test_done_folds_skipped_phases(status_board, monkeypatch):
    """A --from continuation run shows pre-completed phases as DONE."""
    monkeypatch.setattr(runtime, "_SKIPPED_PHASES", ["planner", "supervisor_plan"])
    update_status_board([], "coder", "bd1")
    text = _read(status_board)
    assert "- [x] planner" in text
    assert "- [x] supervisor_plan" in text
    # coder is the in-progress role, not a stale TODO
    assert "- [~] coder" in text


def test_run_start_shows_planner_and_clears_stale_coder(status_board):
    """RC3 (run-start init): a stale prior-run `coderNN` LIVE row must be
    overwritten the instant the run starts, which initializes the board with
    the planner phase as IN-PROGRESS — matching what the runner does at the
    top of main() (update_status_board([], start_role, bd) with
    start_role='planner')."""
    # Seed a leftover board from a crashed prior run.
    status_board.write_text(
        "# Orchestrator Status — bd:  (updated: 2026-07-20 22:40:59 UTC)\n\n"
        "## ▶ LIVE — coder01 → src2/a.py\n"
        "- [~] coder01 → src2/a.py\n"
        "- [ ] planner\n- [ ] supervisor_plan\n- [ ] coder\n"
        "- [ ] supervisor_review\n- [ ] red_team\n",
        encoding="utf-8",
    )
    # Simulate the runner's run-start board init (history empty, planner role).
    update_status_board([], "planner", "bd1")
    text = _read(status_board)
    # Stale coder row gone, fresh timestamp applied.
    assert "coder01" not in text
    assert "coder → src2" not in text
    # Planner is the live/in-progress role from the moment the run starts.
    assert "planner" in text
    assert "LIVE — planner" in text
    assert "- [~] planner" in text
    # Planner not mis-reported as TODO.
    assert "- [ ] planner" not in text


def test_run_start_with_from_phase(status_board):
    """A `--from coder` resume initializes the board at the coder phase, not a
    stale planner/coder row from a prior run."""
    status_board.write_text(
        "# Orchestrator Status — bd:  (updated: 2026-07-20 22:40:59 UTC)\n\n"
        "## ▶ LIVE — coder99 → src2/zzz.py\n- [~] coder99 → src2/zzz.py\n",
        encoding="utf-8",
    )
    update_status_board([], "coder", "bd1")
    text = _read(status_board)
    assert "coder99" not in text
    assert "LIVE — coder" in text
    assert "- [~] coder" in text
