"""Exchange module for turn tracking and status board."""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from factory.infra.control import STATUS_MD, TEMP_DIR
import factory.infra._runtime as runtime


class TeeLogger:
    """Mirror every stdout write to a log file so the tmux dashboard's
    ``tail -F run.log`` pane works (live runner never wired this before)."""

    def __init__(self, log_file: Path):
        self.terminal = sys.stdout
        self.log_file = open(log_file, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.flush()

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()


def _model_to_md(obj: object, limit: int = 4000) -> str:
    """Compact markdown rendering of a Pydantic output — no JSON braces/quotes.

    Pure-Python (no LLM): walks model_dump() so field names appear once per
    leaf instead of repeated `"key":` syntax. ~2-3x lighter than raw JSON when
    injected as cross-phase context. Truncated at `limit` chars.
    """
    try:
        dump = getattr(obj, "model_dump", None)
        d = dump() if callable(dump) else obj
    except Exception:
        d = str(obj)
    lines: list[str] = []

    def walk(prefix: str, val: object) -> None:
        if isinstance(val, dict):
            for k, v in val.items():
                walk(f"{prefix}{k}.", v)
        elif isinstance(val, list):
            for i, v in enumerate(val):
                walk(f"{prefix}{i}.", v)
        else:
            lines.append(f"- {prefix[:-1]}: {val}")

    walk("", d)
    text = "\n".join(lines)
    return text[:limit]


def _render_verdict_block(batch: Any) -> str:
    """Task 5 (docs/01_fix.md, D5): render the harness-filled ValidationVerdict
    per task so the reviewer audits MACHINE-CHECKED facts (ruff/pyright/smoke
    verdict + real unified diff + dependency pointers) instead of the coder's
    self-report alone.
    """
    if batch is None:
        return ""
    lines: list[str] = ["=== HARNESS VALIDATION VERDICT (machine-checked) ==="]
    for tr in batch.results:
        verdict = "PASS" if (tr.ruff_ok and tr.pyright_ok and tr.exec_ok) else "FAIL"
        lines.append(f"- task {tr.task_id}: {verdict}")
        lines.append(
            f"    ruff_ok={tr.ruff_ok} pyright_ok={tr.pyright_ok} exec_ok={tr.exec_ok}"
        )
        if tr.verdict_errors:
            lines.append(f"    ERRORS:\n{tr.verdict_errors}")
        if tr.dep_pointers:
            lines.append("    DEP POINTERS (trace these upstream imports):")
            for dp in tr.dep_pointers[:8]:
                lines.append(f"      - {dp}")
        if tr.verdict_diff:
            lines.append(f"    UNIFIED DIFF VS BASELINE:\n{tr.verdict_diff}")
    return "\n".join(lines)


def _render_upfront_diffs(batch: Any) -> str:
    """Render ONLY the verdict_diff strings from a TaskBatch into a highly
    visible block, placed at the absolute start of the reviewer's brief so the
    Code Supervisor and Red-Team agents see exactly what code changed right at
    the beginning of their prompt.
    """
    if batch is None:
        return ""
    parts: list[str] = []
    for tr in batch.results:
        if tr.verdict_diff:
            parts.append(f"--- {tr.task_id} ---\n{tr.verdict_diff}")
    if not parts:
        return ""
    return (
        "=== PROPOSED CODE CHANGES (DIFF) ===\n"
        + "\n\n".join(parts)
        + "\n====================================\n"
    )


def _render_history_md(role: str, v: object) -> str:
    """Render a `history` entry to markdown for brief injection.

    `history` is intentionally KEPT as raw JSON for the `approved_json`
    parse contract (run_phase, line ~1700). But when we inject `history`
    into the NEXT role's brief we must show markdown, never raw JSON.
    So: if `v` is already markdown (a str that is NOT json) -> return as-is;
    if `v` is a raw JSON string -> parse to dict then `_model_to_md`;
    if `v` is already a model/dict -> `_model_to_md` directly.
    Pydantic-AI v2.0: wherever a model object exists we render from
    `.model_dump()`, never a JSON-string round-trip of our own output.
    """
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                return _model_to_md(json.loads(s))
            except Exception:
                return v  # leaked raw JSON: still inject, do not crash
        return v  # already markdown text
    return _model_to_md(v)  # model object or dict


def mark_recovered(role: str) -> None:
    """P0 rhh4 (M7): a phase/role output came from loopguard RECOVER.

    The recovery agent (tools=[]) fabricates a best-effort object that must
    NEVER be silently accepted as a clean model pass. Loudly warn + bump the
    board counter so the operator knows review is required.
    """
    runtime._RECOVERY_COUNT += 1
    print(
        f"[RECOVERY] phase/role {role!r} output was RECOVERED (fabricated "
        f"best-effort) — NOT a clean model pass; review required",
        file=sys.stderr,
        flush=True,
    )


def mark_compaction(phase: str) -> None:
    """P1 vo94 (M3): a context-compaction gate fired; bump the board counter."""
    runtime._COMPACTION_COUNT += 1
    print(f"[COMPACTION] phase {phase!r} context compacted", file=sys.stderr, flush=True)


_RECOVER_SENTINELS = (
    "Return your best answer now, or state you are BLOCKED.",
    "Stop tool-calling",
    "Stop researching",
)


def _message_has_recover_sentinel(msg: Any) -> bool:
    from pydantic_ai.messages import ModelRequest, SystemPromptPart, ToolReturnPart

    if not isinstance(msg, ModelRequest):
        return False
    for part in msg.parts:
        if isinstance(part, SystemPromptPart):
            text = part.content if isinstance(part.content, str) else str(part.content)
        elif isinstance(part, ToolReturnPart):
            text = part.content if isinstance(part.content, str) else str(part.content)
        else:
            continue
        if any(s in text for s in _RECOVER_SENTINELS):
            return True
    return False


def _detect_and_mark_recovery(role: str, result: Any, prior_history: list | None) -> bool:
    """P0 rhh4 (M7): scan the run result for the loopguard RECOVER sentinel.

    Detection method: the loopguard's recovery_agent.run() is fed a prompt
    containing our RECOVER sentinel text ("BLOCKED"/"best answer now"); that
    prompt lands in the result's all_messages() as a ModelRequest/ToolReturn
    part. If found, the output is a fabricated best-effort, not a clean pass.
    Also detects context compaction (SINK-1): when a leading SystemPromptPart
    summary appears that was NOT in the prior_history — the loopguard's
    maybe_compact() prepends a compacted summary. Heuristic, non-fatal.
    """
    try:
        all_msgs = result.all_messages()
    except Exception:
        return False

    recovered = any(_message_has_recover_sentinel(m) for m in all_msgs)
    if recovered:
        mark_recovered(role)

    # Best-effort compaction detection (P1 vo94 M3): a leading ModelRequest whose
    # SystemPromptPart summary was not present in the role's prior_history.
    if prior_history:
        from pydantic_ai.messages import ModelRequest, SystemPromptPart

        prior_set = {
            (p.content if isinstance(p, SystemPromptPart) else None)
            for m in prior_history
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, SystemPromptPart)
        }
        for m in all_msgs:
            if not isinstance(m, ModelRequest):
                continue
            for p in m.parts:
                if isinstance(p, SystemPromptPart) and isinstance(p.content, str):
                    # A compact summary is a sizeable standalone summary not seen before.
                    if len(p.content) > 200 and p.content not in prior_set:
                        mark_compaction(role)
                        return recovered
            break  # only the leading message is the compacted summary

    return recovered


def update_status_board(history: list[tuple[str, str]], current_role: str | None, bd: str) -> None:
    """Write STATUS.md — the single real status board file.

    The live conductor keeps no OrchestratorState, so the board is derived
    from the flat ``history`` list of (role, output) plus the role now in
    flight.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    # Fold pre-completed (skipped) phases into DONE so a `--from` continuation
    # run shows the true state instead of 0/5 with planner/supervisor_plan as
    # spurious TODO.
    done = list(dict.fromkeys(runtime._SKIPPED_PHASES + [r for r, _ in history]))
    # When a gate blocks (red_team/supervisor_review FAIL with rerun needed),
    # show loop-back to coder so status board reflects what's going on.
    loop_back = current_role in ("red_team", "supervisor_review") and any(
        "FAIL" in (v if isinstance(v, str) else str(v)) for r, v in history[-3:] if r == current_role
    )
    if loop_back:
        current = "coder"
    else:
        current = current_role if current_role and current_role not in done else None

    def bullet(role: str, mark: str) -> str:
        return f"- [{mark}] {role}"

    done_lines = [bullet(r, "x") for r in done] or ["- (none)"]
    live_suffix = " (BACK TO CODER)" if (current and loop_back) else ""
    live_line = f"- [~] {current}{live_suffix}" if current else "- (none)"
    done_set = set(done)
    todo_roles = [r for r in runtime._PHASE_ORDER if r not in done_set and r != current]
    todo_lines = [bullet(r, " ") for r in todo_roles] or ["- (none)"]

    md = (
        f"# Orchestrator Status — bd:{bd}  (updated: {now})\n\n"
        f"## ▶ LIVE — {current or 'idle'}\n"
        f"- Roles completed (executions/phases): {len(done)}/{len(runtime._PHASE_ORDER)}\n"
        f"- Active task: {current if (current and current.startswith('coder')) else '—'}\n"
        f"- Loopguard recoveries (fabricated best-effort): {runtime._RECOVERY_COUNT}\n"
        f"- Compactions: {runtime._COMPACTION_COUNT}\n\n"
        f"## ✓ DONE\n" + "\n".join(done_lines) + "\n\n"
        f"## ◐ IN-PROGRESS\n{live_line}\n\n"
        f"## □ TODO (remaining pipeline)\n" + "\n".join(todo_lines) + "\n"
    )
    STATUS_MD.write_text(md, encoding="utf-8")


class ExchangeTurn(BaseModel):
    """One persisted turn in the reloadable coder<->checker exchange."""

    role: str
    pass_no: int
    content: str


def exchange_path(bd: str) -> Path:
    return TEMP_DIR / f"{bd}_exchange.json"


def load_exchange(bd: str) -> list[ExchangeTurn]:
    p = exchange_path(bd)
    if p.exists():
        try:
            return [ExchangeTurn.model_validate(d) for d in json.loads(p.read_text())]
        except Exception as e:
            print(f"[resume] WARN could not parse {p}: {e}")
    return []


def format_exchange(entries: list[ExchangeTurn]) -> str:
    blocks = [f"### {e.role.upper()} pass {e.pass_no}\n{e.content}" for e in entries]
    return "## PRIOR EXCHANGE (resumed from previous run)\n" + "\n\n".join(blocks)


def save_exchange(bd: str, entries: list[ExchangeTurn]) -> None:
    exchange_path(bd).write_text(json.dumps([e.model_dump() for e in entries], indent=2))


def append_exchange_turn(
    exchange: list[ExchangeTurn] | None,
    pass_counter: dict[str, int] | None,
    role: str,
    content: str,
    bd: str = "",
) -> int | None:
    """Append an exchange turn with dedup guard — skip if (role, pass_no) exists.

    Returns the computed pass_no, or None if exchange is None (not tracked).
    """
    if exchange is None:
        return None
    n = (pass_counter or {}).get(role, 0) + 1
    if pass_counter is not None:
        pass_counter[role] = n
    if any(e.role == role and e.pass_no == n for e in exchange):
        return n
    exchange.append(ExchangeTurn(role=role, pass_no=n, content=content))
    if bd:
        save_exchange(bd, exchange)
    return n

def compact_exchange_transcript(
    exchange: list[ExchangeTurn] | None, 
    max_turns: int = 10, 
    bd: str = ""
) -> None:
    """Rolling window on the exchange transcript to prevent unbounded growth."""
    if exchange is None:
        return
    if len(exchange) > max_turns:
        # Retain the oldest 2 (e.g., initial plan/context) and the newest N-2
        preserved = exchange[:2] + exchange[-(max_turns - 2):]
        exchange.clear()
        exchange.extend(preserved)
        if bd:
            save_exchange(bd, exchange)

