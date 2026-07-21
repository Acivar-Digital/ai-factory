"""Pre-LLM gate for the Orchestrator.

The conductor (A8) calls :func:`run_gate` BEFORE LLM supervisors ever see a
coder's output. It enforces two cheap, deterministic quality gates:

1. ``ruff check --fix`` on every changed file (style/lint hygiene).
2. ``pytest`` on the test files that actually exercise the touched modules —
   but ONLY when such tests exist. When a module has no tests, the gate
   degrades to ``ruff``-only instead of failing on ``pytest``'s absence.

Nothing here raises to the caller on subprocess failure: every failure is
captured and turned into a report string. All external commands are routed
through ``uv run`` per repo policy (never bare ``ruff`` / ``pytest``).
"""

from __future__ import annotations

import os
import subprocess

TESTS_DIR = os.path.join(os.path.dirname(__file__), "..", "tests")
_RUFF_FIX = ("ruff", "check", "--fix")
_RUFF_PLAIN = ("ruff", "check")
_PYTEST = ("pytest", "-q")


def _run(cmd: tuple[str, ...], paths: list[str]) -> tuple[int, str, str]:
    """Run a ``uv run`` command over ``paths``; never raise on failure.

    Returns ``(returncode, stdout, stderr)``. A non-zero return code from
    ``uv`` itself (e.g. missing tool) is recorded in ``stderr`` but the
    gate logic decides severity from the command's purpose, never by
    letting the exception escape.
    """
    full = ["uv", "run", *cmd, *paths]
    try:
        proc = subprocess.run(
            full,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError as exc:
        return 127, "", f"uv not found on PATH: {exc}"
    except subprocess.TimeoutExpired as exc:
        return 124, "", f"command timed out: {' '.join(full)} ({exc})\n"
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _affected_tests(changed_files: list[str]) -> list[str]:
    """Find test files that target the touched modules.

    Strategy: for every changed ``<pkg>/<module>.py`` (ignoring ``__init__``),
    look for ``test_<module>.py`` anywhere under the tests tree. We match on
    stem name, which is the repo's naming convention (``gatekeeper`` ↔
    ``test_gatekeeper.py``). Returns the real path list; empty => ruff-only.
    """
    if not changed_files:
        return []
    tests_root = os.path.normpath(TESTS_DIR)
    if not os.path.isdir(tests_root):
        return []

    stems: set[str] = set()
    for f in changed_files:
        base = os.path.basename(f)
        if base == "__init__.py":
            # package-wide init change: exercise its sibling tests only
            pkg = os.path.basename(os.path.dirname(f))
            stems.add(pkg)
            continue
        stem, ext = os.path.splitext(base)
        if ext == ".py":
            stems.add(stem)

    if not stems:
        return []

    matched: list[str] = []
    for root, _dirs, files in os.walk(tests_root):
        for name in files:
            stem, ext = os.path.splitext(name)
            if ext != ".py":
                continue
            if stem.startswith("test_") and stem[5:] in stems:
                matched.append(os.path.join(root, name))
    return sorted(set(matched))


def _run_ruff(changed_files: list[str]) -> tuple[bool, str]:
    """Run ``ruff check --fix``; fall back to plain ``ruff check`` if --fix
    is unsupported. Returns ``(passed, output)``."""
    rc, out, err = _run(_RUFF_FIX, changed_files)
    if rc == 2 and ("--fix" in err or "No such option" in err or "unrecognized" in err):
        # --fix not supported in this ruff version; retry without it
        rc, out, err = _run(_RUFF_PLAIN, changed_files)
    lines = [f"$ uv run ruff check --fix {' '.join(changed_files)}", out, err]
    passed = rc == 0
    if not passed:
        lines.append(f"[ruff exit {rc}]")
    return passed, "\n".join(s for s in lines if s).rstrip()


def _run_pytest(test_paths: list[str]) -> tuple[bool, str]:
    """Run ``pytest`` over affected test paths. Returns ``(passed, output)``."""
    rc, out, err = _run(_PYTEST, test_paths)
    lines = [f"$ uv run pytest -q {' '.join(test_paths)}", out, err]
    passed = rc == 0
    if not passed:
        lines.append(f"[pytest exit {rc}]")
    return passed, "\n".join(s for s in lines if s).rstrip()


def run_gate(changed_files: list[str]) -> tuple[bool, str]:
    """Run the orchestrator gate over ``changed_files``.

    Always runs ``ruff``. Runs ``pytest`` ONLY if matching test files exist;
    otherwise it notes ``"NO TESTS — ruff-only"`` instead of failing.

    Returns ``(passed, report)``. ``passed`` is False if ruff failed (its
    stderr is embedded in the report). pytest absence is never a failure.
    """
    changed_files = list(changed_files or [])
    if not changed_files:
        return False, "run_gate: no changed files supplied — nothing to gate."

    ruff_ok, ruff_report = _run_ruff(changed_files)

    affected = _affected_tests(changed_files)
    if affected:
        pytest_ok, pytest_report = _run_pytest(affected)
        report = f"{ruff_report}\n\n--- PYTEST (affected) ---\n{pytest_report}"
        passed = ruff_ok and pytest_ok
    else:
        report = f"{ruff_report}\n\n--- PYTEST ---\nNO TESTS — ruff-only"
        passed = ruff_ok

    if not passed:
        report += "\n\nGATE: FAILED"
    else:
        report += "\n\nGATE: PASSED"
    return passed, report


def feedback_to_coder(report: str) -> str:
    """Format a failing gate report for the conductor to feed back to coder."""
    return f"Your code failed the gate. Fix it:\n{report}"


if __name__ == "__main__":
    import sys

    files = sys.argv[1:]
    ok, rep = run_gate(files)
    print(rep)
    raise SystemExit(0 if ok else 1)
