"""Subprocess wrapper — single source of truth.

Generic ``_run_proc`` is the SSoT for EVERY harness subprocess call (argv-based,
with stdout/tuple/completed return contracts). ``_run_tool`` is a thin wrapper
that builds the `uv run python factory/tools/<tool>.py` argv.
Moved from infra/tools.py so workers and ledger.py share ONE implementation.
On timeout we kill the child and FAIL LOUDLY (RuntimeError) — never swallow.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from factory.infra.control import (
    PKG_DIR,
    REPO_ROOT,
    TOOL_SUBPROCESS_TIMEOUT,
)


def _run_proc(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = TOOL_SUBPROCESS_TIMEOUT,
    raise_on_error: bool = False,
    return_format: str = "stdout",
) -> str | subprocess.CompletedProcess[str] | tuple[int, str, str]:
    """Generic argv runner — single SSoT for every harness subprocess call.

    * ``return_format="stdout"``  -> returns stripped stdout, or
      ``"ERROR(<rc>): <stderr>"`` on non-zero (never raises).
    * ``return_format="tuple"``  -> returns ``(returncode, stdout, stderr)``
      (never raises; mirrors the old gatekeeper contract).
    * ``return_format="completed"`` -> returns the ``subprocess.CompletedProcess``
      (re-raises RuntimeError on non-zero when ``raise_on_error``).
    On ``TimeoutExpired`` we kill the child and raise RuntimeError (Fail Loudly).
    """
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd or REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        proc = getattr(e, "process", None)
        if proc is not None:
            proc.kill()
        raise RuntimeError(
            f"[HALT] command exceeded timeout={timeout}s: {' '.join(argv)}"
        ) from e
    if return_format == "completed":
        if raise_on_error and proc.returncode != 0:
            raise RuntimeError(
                f"command failed (rc={proc.returncode}): {' '.join(argv)}\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )
        return proc
    if return_format == "tuple":
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    if proc.returncode != 0:
        return f"ERROR({proc.returncode}): {proc.stderr.strip()}"
    return proc.stdout.strip() or "0 matches"


def _run_tool(tool: str, argv: list[str]) -> str:
    """Run `uv run python factory/tools/<tool>.py <argv>` and return stdout.

    A non-zero CLI returncode (e.g. a blocked/denied write) raises RuntimeError
    so the harness fails loud instead of swallowing the error as a benign tool
    result string. A hung CLI is killed and fails loudly (RuntimeError) on timeout.
    """
    proc = _run_proc(
        ["uv", "run", "--no-sync", "python", str(PKG_DIR / "tools" / f"{tool}.py"), *argv],
        cwd=REPO_ROOT,
        return_format="completed",
        raise_on_error=True,
    )
    return proc.stdout.strip() or "0 matches"
