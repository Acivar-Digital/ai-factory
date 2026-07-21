"""MD-twin per-turn re-injection bridge (ticket baziforecaster-mb1k5).

Reverse of an LLM-reverted design: the `.md` twin (rendered from the evicted
`.jsonl` by ``converter.convert_file``) is the PER-TURN continuity re-injection
source fed as ``message_history`` to ALL agents EVERY spawn — NOT the raw
``.jsonl``. This is token-saving (~67% lighter than the jsonl per converter
notes) and gives the visibility assurance: the on-screen `.md` IS exactly what
the agent received. The jsonl stays internal-only (pydantic-ai owns the real
accumulated message_history during ``agent.run``); only the INJECTION point
changes (jsonl -> md).

Design guarantees:
  * ONE shared pipe (here, in ``common/``) so no single role can silently
    revert the per-turn MD re-injection to jsonl replay.
  * Exact-md resolution via ``_history_filename(role, agent_id)`` — NO
    mtime-glob (the glob was the coder-tagging bug in the old
    ``read_latest_md`` HALT-guard). For ``coder`` + ``agent_id='coder3'`` this
    resolves ``coder/coder3.md``; for non-coder roles ``agent_id=None`` ->
    ``<role>.md``.
  * Cold spawn (no twin yet) returns ``None`` — NO HALT.
  * Per-coderN isolation (ticket a101k) is preserved by construction: the
    module reuses ``_history_filename`` which already returns ``coderN.jsonl``
    for coder+agent_id, so the ``.md`` sibling is ``coderN.md``.

Import discipline to avoid cycles: ``common/md_bridge`` imports from
``infra/artefacts`` (which does NOT import ``common``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

if TYPE_CHECKING:
    pass


def _read_exact_md(role: str, agent_id: str | None) -> str | None:
    """Return the EXACT `.md` twin content for ``role``/``agent_id``, or None.

    Resolves the filename through ``artefacts._history_filename`` so coder
    agent-isolation is honoured, then appends ``.md`` and reads it. No mtime
    glob, no "latest" guesswork — the exact sibling of the role's own jsonl.
    """
    try:
        from factory.infra.artefacts import (
            ROLE_FOLDER,
            _history_filename,
            artefacts_dir,
        )
    except Exception as exc:  # never abort the pipeline over artefacts lookup
        print(f"[WARN] md_bridge: artefacts import failed: {exc!r}", flush=True)
        return None

    # Unknown role (e.g. ops) -> no twin.
    if role not in ROLE_FOLDER:
        return None

    fname = Path(_history_filename(role, agent_id)).stem
    folder = ROLE_FOLDER[role]
    md_path = artefacts_dir() / "history" / folder / f"{fname}.md"
    if not md_path.is_file():
        return None
    try:
        return md_path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"[WARN] md_bridge: read failed for {md_path}: {exc!r}", flush=True)
        return None


def build_md_bridge(role: str, agent_id: str | None = None) -> list[ModelMessage] | None:
    """Build the per-turn MD-twin continuity bridge for ``role``.

    Returns a single-element ``message_history`` list wrapping the role's `.md`
    twin as a synthetic ``UserPromptPart`` (the agent's "journal"), or ``None``
    when no twin exists yet (cold spawn / first run).

    The MD is the re-injection source fed to ALL agents EVERY spawn — the
    token-cheap, visibility-assured view of the agent's own prior work. The
    task ``brief`` (instructions) is a SEPARATE channel injected by the caller;
    both are fed (MD as message_history, brief as the run prompt).
    """
    text = _read_exact_md(role, agent_id)
    if not text:
        return None
    # One synthetic user turn = the agent's own journal, wrapped in a
    # ModelRequest (message_history is list[ModelMessage], NOT bare parts).
    # The real prior jsonl stays internal; pydantic-ai accumulates the live
    # message_history during agent.run and persists it — only the bridge reads
    # the md twin.
    part = UserPromptPart(
        content=(
            "<!-- MD_LEDGER -->\n"
            "The following is your own prior work, rendered from your "
            "role transcript. Treat it as your working memory/journal:\n\n"
            f"{text}"
        )
    )
    return [ModelRequest(parts=[part])]
