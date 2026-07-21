"""Bazi-domain policy enforcement for the orchestrator gatekeeper.

Detects hand-rolled reimplementations of heavenly-stem / earthly-branch /
hidden-stem / four-pillar math that `lunar-python` already provides. Such
reimplementations are policy violations: the engine MUST use `lunar-python`.
"""

from __future__ import annotations

import subprocess

# Heuristic markers of a hand-rolled Bazi math reimplementation.
_BAZI_MATH_MARKERS: tuple[str, ...] = (
    "HeavenlyStem",
    "EarthlyBranch",
    "get_hidden_stem",
    "hidden_stem",
    "four_pillars",
    "FourPillar",
    "class Stem",
    "class Branch",
)

# Suspiciously large literal maps of stem/branch indices to values, which are a
# classic signature of reimplemented Gan-Zhi tables.
_BAZI_DICT_KEYWORDS: tuple[str, ...] = (
    "heavenly_stems",
    "earthly_branches",
    "stem_map",
    "branch_map",
    "GAN",
    "ZHI",
)


def _read_diffs(changed_files: list[str]) -> str:
    """Return the git diff text for the given files, routed via `uv run`.

    Falls back to reading current file contents if there is no diff (e.g. the
    file is untracked but staged, or the repo has no committed baseline).
    """
    if not changed_files:
        return ""

    try:
        result = subprocess.run(
            ["uv", "run", "git", "diff", "--", *changed_files],
            capture_output=True,
            text=True,
            check=False,
        )
        diff = result.stdout
        if diff.strip():
            return diff
    except (FileNotFoundError, OSError):
        pass

    # Fallback: read current contents of the changed files directly.
    contents: list[str] = []
    for path in changed_files:
        try:
            with open(path, encoding="utf-8") as fh:
                contents.append(fh.read())
        except (FileNotFoundError, OSError, UnicodeDecodeError):
            continue
    return "\n".join(contents)


def check_bazi_math_discipline(changed_files: list[str]) -> tuple[bool, str]:
    """Check changed files for reimplemented Bazi stem/branch math.

    Returns `(True, "ok")` when no reimplementation is suspected, otherwise
    `(False, "BAZI MATH POLICY: use lunar-python; do not reimplement stems/branches.")`.
    """
    text = _read_diffs(changed_files)
    if not text:
        return True, "ok"

    lowered = text.lower()
    for marker in _BAZI_MATH_MARKERS:
        if marker.lower() in lowered:
            return (
                False,
                "BAZI MATH POLICY: use lunar-python; do not reimplement stems/branches.",
            )

    # Heuristic for large index->value dicts of stems/branches (>=10 entries).
    for keyword in _BAZI_DICT_KEYWORDS:
        idx = lowered.find(keyword.lower())
        if idx != -1:
            window = text[idx : idx + 400]
            if window.count(":") >= 10 and ("{" in window or "=" in window):
                return (
                    False,
                    "BAZI MATH POLICY: use lunar-python; do not reimplement stems/branches.",
                )

    return True, "ok"
