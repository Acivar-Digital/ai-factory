"""BaziRAG client for the orchestrator.

Enforces the repo rule that BaziRAG queries use TECHNICAL CHINESE KEYWORDS
only (no prose questions to the LLM), then routes the validated query through
`uv run python infrastructure/bazirag.py` via subprocess.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

VALIDATION_ERROR = (
    "BAZIRAG: use technical Chinese keywords only (e.g. 食神, 偏財, 沖, 三會). "
    "No prose questions."
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_PROSE_RE = re.compile(r"[A-Za-z]")
_LATIN_QUESTION_RE = re.compile(r"\?")
_PROSE_PHRASES = ("what is", "what are", "how do", "how to", "how can", "why is", "tell me")


def validate_query(query: str) -> tuple[bool, str]:
    """Validate that a query looks like technical Chinese Bazi keywords.

    Returns ``(True, query)`` when valid, otherwise ``(False, error)``.
    """
    if not query or not query.strip():
        return False, VALIDATION_ERROR

    has_cjk = bool(_CJK_RE.search(query))
    if not has_cjk:
        return False, VALIDATION_ERROR

    latin_chars = _LATIN_PROSE_RE.findall(query)
    latin_ratio = len(latin_chars) / max(len(query.strip()), 1)
    if latin_ratio > 0.2:
        return False, VALIDATION_ERROR

    if _LATIN_QUESTION_RE.search(query):
        return False, VALIDATION_ERROR

    lowered = query.lower()
    if any(phrase in lowered for phrase in _PROSE_PHRASES):
        return False, VALIDATION_ERROR

    return True, query


def query_bazirag(query: str) -> str:
    """Run a validated BaziRAG query via `uv run`.

    Returns the subprocess output on success, or the validation error string
    if the query fails validation.
    """
    ok, payload = validate_query(query)
    if not ok:
        return payload

    try:
        result = subprocess.run(
            ["uv", "run", "python", "infrastructure/bazirag.py", payload],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "BAZIRAG: query timed out."
    except FileNotFoundError:
        return "BAZIRAG: `uv` executable not found."

    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown error"
        return f"BAZIRAG: subprocess failed ({result.returncode}): {stderr}"

    return result.stdout.strip()
