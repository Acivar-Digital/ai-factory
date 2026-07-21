from __future__ import annotations


def handoff_note(bd_id: str, summary: str) -> str:
    return f"[{bd_id}] {summary} — shared via bd remember"
