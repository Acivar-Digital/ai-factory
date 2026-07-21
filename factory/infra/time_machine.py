"""Scoped git checkpoint / rollback for the Orchestrator.

This module owns ONLY local, scoped version control operations for a single
node (bd task):

  * checkpoint(...)      -> close the bd task (local commit via `./bd close`).
  * rollback_node(...)   -> revert ONLY the node's files (never `git reset --hard`,
                            never touch files outside `files_changed`).
  * signal_push_agent()  -> hand-off note that the git-push agent owns remote sync.

Hard rules enforced here:
  - NO `git reset --hard`.
  - NO `git push`.
  - NO edits to files outside `files_changed`.
  - Fail Loudly: subprocess failures are logged with context and re-raised.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
BD_SCRIPT = REPO_ROOT / "bd"


def _run(
    cmd: list[str],
    *,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command via subprocess. Logs + re-raises on failure (Fail Loudly).

    `cmd` should be the full argv list (e.g. ["./bd", "close", ...]). When the
    first token is an executable relative path it is resolved against REPO_ROOT.
    Git is run directly via subprocess (not `uv run`, which would just exec git);
    the bd CLI is run under `uv run` per contract.
    """
    argv = list(cmd)
    if argv and not Path(argv[0]).is_absolute() and (REPO_ROOT / argv[0]).exists():
        argv[0] = str(REPO_ROOT / argv[0])

    logger.info("running: %s", " ".join(argv))
    try:
        proc = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            capture_output=capture,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"command not found: {argv[0]}") from exc
    except OSError as exc:
        raise RuntimeError(f"failed to launch {argv[0]!r}: {exc}") from exc

    if check and proc.returncode != 0:
        raise RuntimeError(
            f"command failed (rc={proc.returncode}): {' '.join(argv)}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def checkpoint(bd_id: str, message: str) -> None:
    """Close the bd task, which commits the node's work locally.

    Runs `uv run ./bd close <bd_id> --reason "<message>"`. Raises a clear error
    if the bd CLI fails (Fail Loudly).
    """
    if not bd_id:
        raise ValueError("bd_id must be a non-empty string")
    if not message:
        raise ValueError("message (close reason) must be a non-empty string")

    try:
        _run(["uv", "run", str(BD_SCRIPT), "close", bd_id, "--reason", message])
    except RuntimeError as exc:
        logger.error("checkpoint failed for bd_id=%s: %s", bd_id, exc)
        raise RuntimeError(
            f"checkpoint() failed to close bd task '{bd_id}'. "
            f"The node's work was NOT committed. Fix the bd CLI failure and retry.\n"
            f"Underlying error: {exc}"
        ) from exc

    logger.info("checkpoint committed locally for bd_id=%s", bd_id)


def _tracked_files() -> set[str]:
    """Return the set of tracked files in the repo (relative paths)."""
    proc = _run(["git", "ls-files"])
    return {line for line in proc.stdout.splitlines() if line.strip()}


def rollback_node(files_changed: list[str]) -> None:
    """SCOPED rollback of ONLY the node's files.

    - Tracked files: `git restore -- <files>`.
    - New untracked files (not in `git ls-files`): removed via `git clean -fd -- <files>`.
    - Verify with `git status` and log the result.

    NEVER runs `git reset --hard`. NEVER touches files outside `files_changed`.
    """
    if not files_changed:
        logger.warning("rollback_node called with empty files_changed; nothing to do")
        return

    files = [f for f in files_changed if f]
    if not files:
        return

    tracked = _tracked_files()
    tracked_targets = [f for f in files if f in tracked]
    new_targets = [f for f in files if f not in tracked]

    # 1. Restore tracked files only.
    if tracked_targets:
        try:
            _run(["git", "restore", "--", *tracked_targets])
        except RuntimeError as exc:
            logger.error("rollback_node: git restore failed: %s", exc)
            raise RuntimeError(
                f"rollback_node() failed to restore tracked files: {tracked_targets}.\n"
                f"Underlying error: {exc}"
            ) from exc

    # 2. Remove NEW untracked files the coder created (scoped to files_changed).
    if new_targets:
        try:
            _run(["git", "clean", "-fd", "--", *new_targets])
        except RuntimeError as exc:
            logger.error("rollback_node: git clean failed: %s", exc)
            raise RuntimeError(
                f"rollback_node() failed to remove new files: {new_targets}.\n"
                f"Underlying error: {exc}"
            ) from exc

        # Fallback: `git clean -fd` cannot remove *gitignored* new files (e.g. a
        # file the coder created under an ignored tree). These are scoped,
        # coder-created files we KNOW are in `files_changed`, so remove any that
        # still exist on disk directly. This closes the scoped-rollback gap
        # without the blast radius of `git clean -fdx` (which would purge all
        # ignored build artifacts in the repo). Fail Loudly if unlink fails.
        for f in new_targets:
            p = Path(f) if Path(f).is_absolute() else REPO_ROOT / f
            if p.exists():
                try:
                    p.unlink()
                except OSError as exc:
                    raise RuntimeError(
                        f"rollback_node() failed to remove new file '{f}': {exc}"
                    ) from exc

    # 3. Verify via git status; confirm the listed files are clean/absent.
    status = _run(["git", "status", "--porcelain", "--", *files])
    remaining = [line for line in status.stdout.splitlines() if line.strip()]
    if remaining:
        logger.warning(
            "rollback_node: after rollback, unexpected working-tree changes for "
            "scope files:\n%s",
            "\n".join(remaining),
        )
    else:
        logger.info(
            "rollback_node: scope files clean after rollback (tracked=%d, new=%d).",
            len(tracked_targets),
            len(new_targets),
        )


def signal_push_agent() -> str:
    """Notify (do NOT perform) the remote sync hand-off.

    The git-push agent owns `git push` to remote. This module never pushes.
    Returns a clear hand-off message to be logged / surfaced to the operator.
    """
    message = (
        "CHECKPOINT COMPLETE. Handing off to the git-push agent: please sync the "
        "local commit to remote now. This module does NOT run `git push`."
    )
    logger.info(message)
    return message


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    print(signal_push_agent())
