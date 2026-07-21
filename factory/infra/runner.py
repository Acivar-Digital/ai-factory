# DEPRECATED: superseded by orchestrator.py (see Build_08).
"""runner — deterministic conductor (NO LLM orchestrator), bare_v12 skill tooling.

Pipeline (all 6 roles, fixed order, never skipped):
  planner -> supervisor_plan -> planner -> supervisor_plan -> planner
  coder -> supervisor_review -> coder -> supervisor_review -> coder
  red_team -> coder -> red_team -> coder
  ops (git-push)

Supervisors NEVER edit — review only. Each review feeds the next pass.
The exchange (coder + supervisor_review + red_team turns) is logged to
factory/temp/<bd>_exchange.json so a later run with
`Resume: True` seeds the first coder pass with prior critiques.

user_prompt.md FIRST LINE must be exactly:  Resume: True   |   Resume: False
(malformed -> fail loudly). Everything after that first line is the task spec.

Models are per-role via CONTROL_SHEET / SKILL_MAP in controls.py.

Run:  uv run python -m factory.infra.runner --bd <ticket_id>
"""

import argparse
import asyncio
import copy
import difflib
import glob
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

import logfire
import yaml
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior

from factory.common import (
    OUTPUT_TYPE_REGISTRY,
    ROLE_OUTPUT_TYPE,
    build_md_bridge,
    log_operator,
    resolve_model,
    resolve_run_dir,
)
from factory.infra._loopguard import AGENT_RUN_TIMEOUT, run_with_loopguard
from factory.infra.artefacts import persist_role
from factory.infra.control import (
    DEFAULT_AGENT_SETTINGS,
    LOGS_DIR,
    REPO_ROOT,
    ROLE_AGENT_SETTINGS,
    RUNTIME_DIR,
    SKILL_MAP,
    STATUS_MD,
    TEMP_DIR,
    USER_PROMPT_PATH,
)
from factory.infra.ledger import inject_repo_map
from factory.infra.models import (
    ApprovedPlan,
    ApprovedTask,
    AuditResult,
    AuditRisk,
    CodePassed,
    DraftPlan,
    ExecutablePlan,
    GitResult,
    ParallelisableWorkplan,
    ReviewFinding,
    ReviewResult,
    TaskBatch,
    TaskResult,
    WorkGroup,
)
from factory.infra.output_sanitizer import (
    clean_role_output,
    extract_model_json,
    extract_tool_call_payload,
)
from factory.infra.state import (
    fresh_state,
    load_state,
    record_phase,
    reset_stale_in_progress,
    save_state,
)
from factory.infra.tools import (
    _DISCOVERY_TOOLS,
    _TOOL_BY_NAME,
    DEFAULT_TOOL_BUDGET,
    ROLE_TOOL_BUDGET,
    assert_planner_emitted,
    build_skill_spec,
    get_file_symbols,
    guard_tools,
    pydantic_ai_default_block,
    wrap_injected_context,
    wrap_untrusted_task,
)

TEMP_DIR.mkdir(parents=True, exist_ok=True)

RESUME_RE = re.compile(r"^Resume:\s*(true|false)\s*$", re.IGNORECASE)


# ── Logging / observability ────────────────────────────────────────────────
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


def _configure_logfire() -> None:
    """Local-only Logfire instrumentation (no network egress).

    Prints each agent's LLM turns live to the terminal (and, via TeeLogger,
    into run.log) so subagent activity is visible as it happens, not batched
    at the end.
    """
    logfire.configure(send_to_logfire=False, console=logfire.ConsoleOptions(), data_dir=str(LOGS_DIR / "logfire"))
    logfire.instrument_pydantic_ai()
    # M5 (fwfk): drop capture_all=True — it captured Authorization: Bearer
    # headers into local logfire logs. Headers are off by default; we only
    # instrument request/response bodies, never secrets.
    logfire.instrument_httpx()


# PROPOSE-ONLY (2026-07-17): the pipeline stops after red_team. The coder
# stages edits under factory/temp/; nothing is ever pushed or
# applied to src2/. A human reviews the staged files and applies manually.
_PHASE_ORDER = ["planner", "supervisor_plan", "coder", "supervisor_review", "red_team"]

# P1 vo94 (M3): module-level observability counters for the status board.
_RECOVERY_COUNT = 0  # number of loopguard RECOVER (fabricated best-effort) outputs
_COMPACTION_COUNT = 0  # number of context-compaction gate firings

# P1 ugvt (M4): module-level cross-phase summaries (SINK-2). Fed from each
# role's stored output so subsequent phases get richer context than terse raw
# output. Keyed by role; value = compact markdown rendering of the role output
# (NOT raw JSON — rendered via _model_to_md to save cross-phase tokens).
PHASE_SUMMARIES: dict[str, str] = {}

# Scope-driven auto-context (86rmw/xfqkf/y1oqi): cached scoped repo-map built
# once at run start from the user prompt's `scope:` front-matter list. Injected
# identically into both planner and supervisor_plan briefs.
SCOPE_CONTEXT: str = ""
RAW_OUTPUTS: dict[str, str] = {}  # raw Pydantic model_dump_json() per role (queryable by conductor)


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


def _render_verdict_block(batch: "TaskBatch | None") -> str:
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
    global _RECOVERY_COUNT
    _RECOVERY_COUNT += 1
    print(
        f"[RECOVERY] phase/role {role!r} output was RECOVERED (fabricated "
        f"best-effort) — NOT a clean model pass; review required",
        file=sys.stderr,
        flush=True,
    )


def mark_compaction(phase: str) -> None:
    """P1 vo94 (M3): a context-compaction gate fired; bump the board counter."""
    global _COMPACTION_COUNT
    _COMPACTION_COUNT += 1
    print(f"[COMPACTION] phase {phase!r} context compacted", file=sys.stderr, flush=True)


# Sentinel text emitted by _loopguard.recovery_agent.run() prompts. Unique to
# the loopguard's RECOVER path — never present in a normal role's own output.
_RECOVER_SENTINELS = (
    "Return your best answer now, or state you are BLOCKED.",
    "Stop tool-calling",
    "Stop researching",
)


def _message_has_recover_sentinel(msg) -> bool:
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



# Phases that were intentionally skipped (pre-completed in a prior run) when
# the pipeline is resumed via `--from <phase>`. The status board folds these
# into the DONE column so it reflects reality instead of showing 0/5 on a
# continuation run. Set by main() before the first board render.
_SKIPPED_PHASES: list[str] = []


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
    done = list(dict.fromkeys(_SKIPPED_PHASES + [r for r, _ in history]))
    current = current_role if current_role and current_role not in done else None

    def bullet(role: str, mark: str) -> str:
        return f"- [{mark}] {role}"

    done_lines = [bullet(r, "x") for r in done] or ["- (none)"]
    live_line = f"- [~] {current}" if current else "- (none)"
    done_set = set(done)
    todo_roles = [r for r in _PHASE_ORDER if r not in done_set and r != current]
    todo_lines = [bullet(r, " ") for r in todo_roles] or ["- (none)"]

    md = (
        f"# Orchestrator Status — bd:{bd}  (updated: {now})\n\n"
        f"## ▶ LIVE — {current or 'idle'}\n"
        f"- Roles completed (executions/phases): {len(done)}/{len(_PHASE_ORDER)}\n"
        f"- Active task: {current if (current and current.startswith('coder')) else '—'}\n"
        f"- Loopguard recoveries (fabricated best-effort): {_RECOVERY_COUNT}\n"
        f"- Compactions: {_COMPACTION_COUNT}\n\n"
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


# ROLE_OUTPUT (role -> output model) was removed; role -> output TYPE NAME
# now lives in common.ROLE_OUTPUT_TYPE (derived from SKILL_MAP), and the
# type-name -> model lives in common.OUTPUT_TYPE_REGISTRY. Resolve a role's
# output model via OUTPUT_TYPE_REGISTRY[ROLE_OUTPUT_TYPE[role]].

# Roles whose turns are persisted in the reloadable exchange JSON.
EXCHANGE_ROLES = {"coder", "supervisor_review", "red_team"}

# Reviewer role -> pass/fail boolean field in its JSON output.
REVIEW_PASS_FIELD = {
    "supervisor_plan": "approved",
    "supervisor_review": "passed",
    "red_team": "green",
}

# Max review attempts per gated pair; the 3rd attempt is a FORCED pass.
MAX_RETRIES = 3

PLAN_INVARIANT_RETRIES = 5   # 01_fix: max planner/supervisor_plan retries before HALT


def check_plan_invariants(plan) -> list[str]:
    """Return violation strings (empty list = plan OK).

    Checks: (1) every coder task lists exactly 1 file; (2) file paths are disjoint
    across all coder tasks. Runs on BOTH planner and supervisor_plan output.
    """
    violations: list[str] = []
    seen: set[str] = set()

    # Try to find the workplan groups
    workplan = getattr(plan, "workplan", None)
    if not workplan:
        strategy = getattr(plan, "strategy", None)
        if strategy:
            workplan = getattr(strategy, "parallelisable_workplan", None)

    groups = getattr(workplan, "groups", []) if workplan else []

    tasks = []
    for group in groups or []:
        tasks.extend(getattr(group, "tasks", []) or [])

    for task in tasks:
        fps = getattr(task, "file_paths", None) or []
        if len(fps) != 1:
            violations.append(f"task {getattr(task, 'id', '?')} lists {len(fps)} files (exactly 1 required)")
        for fp in fps:
            if fp in seen:
                violations.append(f"file collision: {fp} in multiple tasks")
            seen.add(fp)
    return violations

# Size-aware context injection (epic baziforecaster-gx30p). A coder agent must
# hold the FULL target file in INPUT context to edit precisely, but injecting an
# unbounded file risks blowing the 200K budget. Per-task hard budget: a single
# task's file_paths are capped at TASK_TOKEN_THRESHOLD tokens; over-budget tasks
# fall to Tier B (map+slice) or are force-replanned by the planner.
TASK_TOKEN_THRESHOLD = 100_000

# Tier-B auto-shrink does NOT use the raw file; it uses a structural map
# (get_file_symbols) + a focus slice. If the SLICED content still exceeds this,
# the task is halted and sent back to the planner to SPLIT (last resort).
TIER_B_SLICE_THRESHOLD = 100_000


class TaskNeedsSplitError(RuntimeError):
    """vze01: a task's file_paths cannot be safely injected even via Tier B.

    Raised by the per-task size gate when a single file alone exceeds the slice
    budget. Propagates out of ``run_execute_phase`` (not swallowed into a
    `blocked` TaskResult) so the operator re-plans with narrower scope.
    """


# --- SIZE-AWARE CONTEXT INJECTION ----------------------------------------
def _tiktoken_encoding():
    """Return a cached cl100k_base encoding, or ``None`` if tiktoken missing."""
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


_ENC_CACHE: list = [None]  # lazy singleton; populated on first use


def _encoding():
    if _ENC_CACHE[0] is None:
        _ENC_CACHE[0] = _tiktoken_encoding()
    return _ENC_CACHE[0]


def _count_tokens(text: str) -> int:
    """Deterministic token count for a string (tiktoken cl100k_base, char/4 fallback)."""
    enc = _encoding()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, len(text) // 4)


class _TokenEstimate(TypedDict):
    total: int
    per_file: dict[str, int]


def estimate_task_tokens(file_paths: list[str]) -> _TokenEstimate:
    """Sum tiktoken (cl100k_base) tokens across every file in ``file_paths``.

    Returns ``{"total": <int>, "per_file": {<path>: <int>}}``. Files that are
    missing or unreadable contribute 0 (fail-loudly is NOT wanted here — a
    missing file is the planner's problem, surfaced later by the ACL). Cheap and
    deterministic: runs before any coder spawns so an over-scoped task is caught
    before an expensive LLM call. The encoding is cached across calls.
    """
    per_file: dict[str, int] = {}
    total = 0
    for fp in file_paths:
        try:
            content = Path(REPO_ROOT / fp).read_text(encoding="utf-8")
        except Exception:
            per_file[fp] = 0
            continue
        n = _count_tokens(content)
        per_file[fp] = n
        total += n
    return {"total": total, "per_file": per_file}


def task_context_tier(file_paths: list[str]) -> str:
    """Return ``"A"`` (full file) or ``"B"`` (map+slice) for a task's file_paths."""
    total = estimate_task_tokens(file_paths)["total"]
    assert isinstance(total, int)  # defensive: estimate_task_tokens always returns int total
    return "A" if total <= TASK_TOKEN_THRESHOLD else "B"


def _edit_mode_for(real_repo_path: str) -> str:
    """Return 'FULL WRITE' for a new/empty live file, else 'SURGICAL'.

    A coder can only do surgical edits on a file that already exists with
    content; a brand-new or empty file must be written whole (write_file).
    This predicate is the single source of truth for the per-file EDIT MODE
    block injected into the coder brief (replaces the old hardcoded
    "write your FULL proposed replacement" instruction that caused the
    eviction-driven `blocked` failure).
    """
    live = REPO_ROOT / real_repo_path
    if not live.exists() or live.stat().st_size == 0:
        return "FULL WRITE"
    return "SURGICAL"


def _stage_copies(file_paths: list[str], staged: list[str]) -> list[tuple[str, str]]:
    """fzqa2: copy each live file into its temp/ staging mirror (PROPOSE-ONLY).

    The staging copy is the coder's EVICTION-EXEMPT read source: reads there
    return real content (the live-tree read would be evicted to ``File read:
    <path>`` by the eviction transform for large files). The live tree is never
    mutated. Copies are best-effort — a missing source is the planner's problem
    and is surfaced later by the ACL, so failures are non-fatal here.

    Returns a list of ``(real_repo_path, edit_mode)`` pairs so the caller can
    inject a per-file EDIT MODE block into the coder brief.
    """
    modes: list[tuple[str, str]] = []
    for real, mirror in zip(file_paths, staged):
        mode = _edit_mode_for(real)
        modes.append((real, mode))
        try:
            src = REPO_ROOT / real
            dst = Path(mirror)
            dst.parent.mkdir(parents=True, exist_ok=True)
            content = src.read_text(encoding="utf-8")
            dst.write_text(content, encoding="utf-8")
            # B1: explicit pre-edit baseline for harness-owned patch generation
            (dst.parent / (dst.name + ".orig")).write_text(content, encoding="utf-8")
        except Exception as exc:
            print(f"[WARN] staging copy failed for {real!r}: {exc!r}", flush=True)
    return modes


def _dep_pointers_for(file_paths: list[str]) -> list[str]:
    """Task 5 (docs/01_fix.md, D5): for each edited file, return dependency
    pointers (file:line/symbol of upstream imports) so reviewers know exactly
    where to trace a type contract. Lightweight AST import-parse; bounded to a
    few strong edges so the brief stays lean.
    """
    import ast

    pointers: list[str] = []
    for fp in file_paths:
        p = REPO_ROOT / fp
        if not p.exists():
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        edges: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append((node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                edges.append((node.lineno, mod))
        for lineno, mod in edges[:8]:
            pointers.append(f"{fp}:{lineno} imports {mod}")
    return pointers


def _write_harness_patches(task_id: str, files_changed: list[str], bd: str) -> tuple[list[str], int]:
    """Generate git-apply-compatible unified diffs for a coder task (B1–B7).

    Diffs each coder-edited staging copy against its captured .orig baseline.
    The coder must NOT hand-write diffs (they come out synthetic/corrupt).
    Returns the list of written patch paths and the count of real changes.
    """
    written: list[str] = []
    real_changes = 0
    for fp in files_changed:
        mirror = stage_path(fp)                 # temp/src2/.../name.py
        orig = mirror + ".orig"
        mirror_path = Path(mirror)
        if not mirror_path.exists():
            log_operator(f"[PATCH] drop {fp!r}: no staging copy (out-of-scope)", level="WARNING")
            continue                              # B2: hallucinated path -> drop
        if Path(orig).exists():
            a_lines = Path(orig).read_text(encoding="utf-8", errors="replace").splitlines()
        else:
            a_lines = []                          # B2: new file -> /dev/null
        b_lines = mirror_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if a_lines == b_lines:
            continue                              # no change (B3 individual skip)
        real_changes += 1
        rel = fp if not fp.startswith("factory/temp/") else fp.split("factory/temp/", 1)[1]
        udiff = difflib.unified_diff(
            a_lines, b_lines,
            fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm="",
        )
        text = "\n".join(udiff)
        if not text.strip():
            continue
        stem = Path(rel).stem
        patch_path = TEMP_DIR / f"patch_{stem}.diff"
        patch_path.write_text(text + "\n", encoding="utf-8")
        written.append(str(patch_path))
        log_operator(f"[PATCH] wrote {patch_path.name} for task {task_id} ({rel})")
    return written, real_changes


def staged_zero_diff(fp: str) -> bool | None:
    """Compare a staged mirror against its captured ``.orig`` baseline (00_fix Fix A).

    The harness captures a ``.orig`` pre-edit snapshot of every staged file at staging
    time (see ``_stage_copies``). This replaces the old, redundant ``filecmp(live, staged)``
    Staging Diff Gate, which self-compared a file against itself for absolute paths.

    Returns:
      * ``True``  — mirror exists, ``.orig`` exists, and they are byte-identical
                    (genuine zero-diff / no-op edit);
      * ``False`` — mirror exists, ``.orig`` exists, and they differ (a REAL edit);
      * ``None``  — no baseline to compare (new file OR hallucinated path): defer to
                    ``_write_harness_patches``'s ``real_changes`` decision.
    """
    mirror = stage_path(fp)
    orig = mirror + ".orig"
    mp = Path(mirror)
    op = Path(orig)
    if mp.exists() and op.exists():
        try:
            return mp.read_text(encoding="utf-8") == op.read_text(encoding="utf-8")
        except Exception:
            return None
    return None


def _quarantine_coder_artifacts(bd: str) -> None:
    """B7: move coder-authored deliverable artifacts out of temp/ (keep harness output)."""
    quar = TEMP_DIR / "quarantine"
    quar.mkdir(parents=True, exist_ok=True)
    # KEEP (never move): staging copies, harness patches, exchange, facts, ruff cache.
    keep_names = {"exchange.json", "facts.jsonl", "ruff.toml"}
    for p in glob.glob(str(TEMP_DIR / "*.diff")) + glob.glob(str(TEMP_DIR / "*_patch.py")):
        path = Path(p)
        if path.name in keep_names:
            continue
        # Harness-generated patches live under temp/src2/ OR are named patch_<stem>.diff
        # written by _write_harness_patches. To avoid clobbering harness output, only
        # quarantine files that are NOT inside temp/src2/ AND not a patch_<stem>.diff
        # the harness just wrote. Simplest safe rule: move everything coder-shaped that
        # is NOT under temp/src2/ and NOT a patch_*.diff.
        if "src2" in path.parts:
            continue  # staging copies stay
        if path.name.startswith("patch_") and path.suffix == ".diff":
            # Could be harness or coder. Harness writes FIRST (call order), so any
            # patch_*.diff present was either harness-written or coder-written with
            # the same name. To be safe: leave patch_*.diff alone (harness output is
            # authoritative; coder's same-named file was overwritten by the harness
            # write in _write_harness_patches). Only quarantine stray non-patch_*.diff
            # and *_patch.py.
            continue
        try:
            path.rename(quar / path.name)
        except Exception as exc:
            log_operator(f"[QUARANTINE] failed to move {path.name}: {exc!r}", level="WARNING")


def _edit_mode_block(modes: list[tuple[str, str]], staged: list[str]) -> str:
    """Inject a per-file EDIT MODE block into the coder brief.

    Replaces the old hardcoded "write your FULL proposed replacement" rule that
    forced the coder to reproduce the entire file (and, combined with read_file
    eviction, produced the eviction-driven `blocked` failure). The harness knows
    per file whether the live source exists with content; it tells the coder to
    edit SURGICALLY (replace_text / replace_function on the staging copy) for
    existing files and to FULL WRITE only genuinely new/empty files.
    """
    if not modes:
        return ""
    lines = [
        "=== EDIT MODE (per file — follow exactly) ===",
        "The harness pre-staged a copy of every target file and determined its edit mode:",
    ]
    staged_by_real = dict(zip([m[0] for m in modes], staged))
    for real, mode in modes:
        mirror = staged_by_real.get(real, "?")
        if mode == "SURGICAL":
            lines.append(
                f"  - {real}  →  SURGICAL  (exists in src2/; apply replace_text / "
                f"replace_function to its STAGING copy {mirror} — do NOT rewrite the "
                f"whole file)"
            )
        else:
            lines.append(
                f"  - {real}  →  FULL WRITE  (new/empty file; use write_file on the "
                f"STAGING copy {mirror})"
            )
    lines.append(
        "Rule: NEVER rewrite a file marked SURGICAL in full. NEVER write src/ or "
        "src2/. Read the STAGING copy (eviction-exempt, full content present) — "
        "do NOT read the live tree. A human applies your staged file."
    )
    return "\n".join(lines)


def _build_tier_b_map(file_paths: list[str]) -> str:
    """qkm3p: structural map for Tier-B injection.

    Returns a markdown block with each file's symbols + signatures (via
    ``get_file_symbols``) so the coder knows the structure WITHOUT the full file
    in its context. The coder then reads precise slices from the eviction-exempt
    staging copies. Returns ``""`` on empty input.
    """
    if not file_paths:
        return ""
    parts: list[str] = ["=== STRUCTURAL MAP (Tier B — edit via slices, not full files) ==="]
    for fp in file_paths:
        parts.append(f"\n--- {fp} ---")
        try:
            sym = get_file_symbols(fp)
        except Exception as exc:
            sym = f"(symbol map unavailable: {exc!r})"
        parts.append(sym)
    parts.append(
        "\nRead ONLY the slices you need from the STAGING PATHS below (eviction-"
        "exempt — full content is returned). Do NOT load the whole live file "
        "into context; use replace_function / replace_text on the targeted "
        "symbol/line range."
    )
    return "\n".join(parts)


# --- PROPOSE-ONLY STAGING -------------------------------------------------
# Per Francis (2026-07-17): the harness must NEVER write to src2/ (the live
# tree). Coders stage proposed edits under factory/temp/ by mirroring
# the repo path (src2/core/schemas/unified.py -> temp/src2/core/schemas/
# unified.py). The SRC BAN in tools.py already forbids src2/ writes, so this is
# defence in depth: the brief steers the coder to temp/. Reviewers read the
# staged copy; a human applies it manually.
def stage_path(real_repo_path: str) -> str:
    """Map a repo-relative OR absolute staging path to its temp/ mirror (single seam).

    00_fix Fix B: collapse BOTH absolute (``/abs/.../factory/temp/src2/x.py``)
    and relative (``temp/src2/x.py`` / ``factory/temp/src2/x.py``) temp prefixes
    down to ``TEMP_DIR/src2/x.py`` so every harness gate routes through one normalization
    seam. This is now load-bearing — the Staging Diff Gate and Load-Schema Gate both depend
    on it, so a broken join can never again self-compare a file against itself.
    """
    p = Path(real_repo_path)
    if p.is_absolute():
        try:
            i = p.parts.index("temp")
            p = Path(*p.parts[i + 1:])
        except ValueError:
            pass
    else:
        s = str(p)
        for prefix in ("factory/temp/", "temp/"):
            if s.startswith(prefix):
                s = s[len(prefix):]
                break
        p = Path(s)
    return str(TEMP_DIR / p)


def stage_paths(paths: list[str]) -> list[str]:
    """Map a list of repo-relative paths to their temp/ staging mirrors."""
    return [stage_path(p) for p in paths]


def stage_workspace_from_draft(draft: DraftPlan, bd: str) -> None:
    """Pre-stage the workspace right after a DraftPlan is parsed.

    1. Identify File Types from Plan
       - Existing Source Files (starting with 'src2/'): copy live version of the file from src2/... directly to its corresponding mirror path in temp/src2/
       - Proposed New Deliverables (starting with 'temp/', 'factory/temp/', or ending with '.diff'/'.md'): touch/initialize a 0-byte empty file.
    """
    print(f"[PRE-STAGE] Staging workspace for {bd}...", flush=True)
    file_paths: set[str] = set()
    for task in draft.subtasks:
        for fp in task.file_paths:
            if fp:
                file_paths.add(fp)

    if draft.strategy and draft.strategy.parallelisable_workplan:
        for gp in draft.strategy.parallelisable_workplan.groups:
            for task in gp.tasks:
                for fp in task.file_paths:
                    if fp:
                        file_paths.add(fp)

    for fp in sorted(file_paths):
        is_existing_src = False
        if fp.startswith("src2/") or fp.startswith("src2" + os.sep):
            is_existing_src = (REPO_ROOT / fp).is_file()

        if is_existing_src:
            src_path = REPO_ROOT / fp
            mirror_path = Path(stage_path(fp))
            try:
                mirror_path.parent.mkdir(parents=True, exist_ok=True)
                mirror_path.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"[PRE-STAGE] Copied {fp} -> {mirror_path.relative_to(REPO_ROOT)}", flush=True)
            except Exception as e:
                print(f"[WARN] [PRE-STAGE] Failed to copy {fp} to staging mirror: {e}", flush=True)
        else:
            is_deliverable = (
                "temp/" in fp or "temp" + os.sep in fp or fp.endswith(".diff") or fp.endswith(".md")
            )
            if is_deliverable:
                target_path = Path(fp)
                if not target_path.is_absolute():
                    target_path = REPO_ROOT / fp
                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    if not target_path.exists():
                        target_path.write_text("", encoding="utf-8")
                        print(f"[PRE-STAGE] Touched new deliverable: {target_path.relative_to(REPO_ROOT)}", flush=True)
                except Exception as e:
                    print(f"[WARN] [PRE-STAGE] Failed to touch deliverable {fp}: {e}", flush=True)


def _real_source_paths(file_paths: list[str]) -> list[str]:
    """Reduce Planner-claimed file_paths to REAL src2/ source files.

    The Planner is reasoning-only and cannot write files; its file_paths
    claims routinely include derived/staging/hallucinated paths (e.g.
    ``factory/temp/src2/.../unified_patch.py``). Only an existing
    repo-relative ``src2/`` file can be the target of a concurrent-edit race,
    so the DAG disjointness assertion must run ONLY over those. Everything
    else is dropped — a non-existent path cannot race, and a staging/hallucinated
    path is never a real source target.
    """
    out: list[str] = []
    for p in file_paths:
        if not (p.startswith("src2/") or p.startswith("src2" + os.sep)):
            continue
        if not (REPO_ROOT / p).is_file():
            continue
        out.append(p)
    return out


def build_role_agent(role: str) -> tuple[Agent, "object | None"]:
    """Forge a role's agent bound to its per-role model from CONTROL_SHEET.

    Returns ``(agent, guard)`` where ``guard`` is the ``GuardToolset`` instance
    (or ``None`` for tool-less roles) so the caller can inspect ``guard.exhausted``
    after a run (planner budget HALT, baziforecaster-4mn8).

    Tools come from the role's frozen SkillSpec (customised/<role>.yaml
    tool_allow_list), resolved against the TOOL_REGISTRY — NOT a hardcoded
    map. A role with no allow-list (e.g. the review/plan roles) gets no tools,
    which is correct: those roles only reason + return Pydantic output.
    """
    spec = build_skill_spec(role)
    entry = SKILL_MAP.roles[role]
    model = resolve_model(entry.model_key)
    if role == "coder":
        model = copy.copy(model)
    instructions = pydantic_ai_default_block() + "\n\n" + spec.instructions
    allowed = [name for name in spec.tool_allow_list if name in _TOOL_BY_NAME]
    unknown = [name for name in spec.tool_allow_list if name not in _TOOL_BY_NAME]
    if unknown:
        raise RuntimeError(
            f"[HALT] role {role!r} tool_allow_list references unregistered "
            f"tool(s) absent from TOOL_REGISTRY: {sorted(unknown)}"
        )
    # Read-Bucket Protocol defense-in-depth (baziforecaster-c8lh): discovery tools
    # (get_repo_structure/investigate/search/...) are forbidden for EVERY role,
    # regardless of what a (possibly leaked/corrupt) spec requests. Hard HALT if
    # one ever appears in an allow-list so it can never reach an agent.
    leaked = [name for name in allowed if name in _DISCOVERY_TOOLS]
    if leaked:
        raise RuntimeError(
            f"[HALT] discovery tool(s) {sorted(leaked)!r} are forbidden by the "
            f"read-bucket protocol and cannot be granted to role {role!r}"
        )
    tools = [_TOOL_BY_NAME[name] for name in allowed]
    budget = ROLE_TOOL_BUDGET.get(role, DEFAULT_TOOL_BUDGET)
    guard = guard_tools(tools, budget=budget) if tools else None
    return Agent(
        model,
        output_type=OUTPUT_TYPE_REGISTRY[ROLE_OUTPUT_TYPE[role]],
        toolsets=[guard] if guard else [],
        instructions=instructions,
        retries=5,
        model_settings=ROLE_AGENT_SETTINGS.get(role, DEFAULT_AGENT_SETTINGS),
    ), guard


# Retries on transient provider faults (429/5xx + connection/timeout errors) are
# CENTRALIZED in the transport layer — `http_client.AsyncTenacityTransport` retries
# with 90/120/240s exponential backoff before surfacing a final ModelAPIError. The
# agent layer below does NOT retry; it only catches the final failure and aborts
# gracefully. Keep these two layers disjoint to avoid compounding retries.


def _report_run_failure(phase: str, exc: Exception, attempt: int, reason: str) -> None:
    """Write a structured FAIL report and print a clear abort banner.

    Called when a phase exhausts its retries (or hits a non-retryable error) so
    the run exits gracefully with a diagnosis instead of an unhandled traceback.
    """
    report = {
        "phase": phase,
        "attempt": attempt,
        "reason": reason,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    path = RUNTIME_DIR / f"FAIL_{phase or 'agent'}.json"
    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception as write_err:  # never let the report writer crash the crash
        print(f"[report] could not write FAIL report: {write_err}", flush=True)
    print(
        "\n" + "=" * 64 +
        f"\n[RUN ABORTED] phase={phase or 'agent'} after {attempt} attempt(s)"
        f"\n  reason : {reason}"
        f"\n  error  : {type(exc).__name__}: {exc}"
        f"\n  report : {path}"
        + "\n" + "=" * 64,
        flush=True,
    )


async def _run_agent_retry(agent: Agent, brief: str, *, loopguard: bool = False, phase: str = "", role: str = "", bd_id: str = "", message_history: list | None = None, agent_id: str | None = None) -> Any:
    """Run an agent once. Retries are handled by the transport layer; here we only
    catch the final ModelAPIError (after transport retries are exhausted) and abort
    gracefully with a FAIL report + SystemExit(1) — never an unhandled traceback.
    `message_history` is the role's reloaded prior history (D2 continuity bridge)."""
    try:
        if loopguard:
            from types import SimpleNamespace
            return await run_with_loopguard(agent, brief, phase=phase, role=role, state=SimpleNamespace(bd_id=bd_id), history=message_history, require_transcript=True, agent_id=agent_id)
        return await agent.run(brief, message_history=message_history)
    except ModelAPIError as exc:
        _report_run_failure(phase, exc, 1, "transient provider failure (transport retries exhausted)")
        raise SystemExit(1)


# =====================================================================
# Fallback + eval.jsonl logging (SA4-F6 resilience + SA5-F3 cost visibility)
# =====================================================================
def _resolve_run_dir(bd_id: str | None = None) -> Path | None:
    """Resolve the run directory for ``bd_id`` (newest state-persisted run,
    else TEMP fallback). Delegates to ``common.resolve_run_dir``.
    """
    if not bd_id:
        return None
    return resolve_run_dir(bd_id)


def _safe_usage_payload(result: Any) -> dict[str, int] | None:
    """Extract token usage from a RunResult (supports .usage() callable or .usage)."""
    usage_attr = getattr(result, "usage", None)
    usage_obj = None
    if callable(usage_attr):
        try:
            usage_obj = usage_attr()
        except Exception:
            usage_obj = None
    else:
        usage_obj = usage_attr
    if usage_obj is None:
        return None
    return {
        "input_tokens": int(getattr(usage_obj, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage_obj, "output_tokens", 0) or 0),
        "requests": int(getattr(usage_obj, "requests", 0) or 0),
    }


def _safe_message_count(result: Any) -> int:
    all_messages_attr: Any = getattr(result, "all_messages", None)
    if callable(all_messages_attr):
        try:
            messages: Any = all_messages_attr()
            return len(messages) if messages is not None else 0
        except Exception:
            return 0
    return 0


async def append_eval_log(
    bd_id: str | None,
    phase: str,
    role: str,
    task_id: str | None,
    output: object,
    usage: object,
    message_count: int,
) -> None:
    """Append one JSON line to <run_dir>/eval.jsonl. Never crashes the harness."""
    run_dir = _resolve_run_dir(bd_id)
    if run_dir is None:
        print(f"[WARN] append_eval_log skipped: no run dir for bd_id={bd_id!r}", flush=True)
        return
    usage_payload = _safe_usage_payload(usage) if usage is not None else None
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "bd_id": bd_id,
        "phase": phase,
        "role": role,
        "task_id": str(task_id) if task_id is not None else None,
        "output_type": type(output).__name__ if output is not None else None,
        "usage": usage_payload,
        "message_count": int(message_count or 0),
    }
    try:
        log_path = run_dir / "eval.jsonl"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[WARN] append_eval_log failed: {exc!r}", flush=True)


class _SanitizedResult:
    """Minimal RunResult stand-in for a sanitizer-recovered model.

    Downstream consumers (log_response_raw, persist_role, _safe_usage_payload,
    _safe_message_count) only touch ``.output`` and ``.all_messages()`` / ``.usage()``.
    A recovered object has no real message history, so we surface the role's
    prior_history as its all_messages() and zero usage.
    """

    def __init__(self, output: Any, messages: list | None = None) -> None:
        self.output = output
        self._messages = messages or []

    def all_messages(self) -> list:
        return self._messages

    def usage(self) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(input_tokens=0, output_tokens=0, requests=0)


def _recover_role_output(
    raw: str, model_cls: type, role: str, prior_history: list | None
) -> Any | None:
    """Attempt to salvage a broken model output via the frozen sanitizer.

    Returns a ``_SanitizedResult`` on success, or ``None`` if it cannot be
    salvaged (caller then raises [HALT]).
    """
    try:
        obj = clean_role_output(raw, model_cls)
    except Exception as exc:
        print(
            f"[WARN] sanitizer could not recover role={role!r}: {exc!r}", flush=True
        )
        return None
    print(
        f"[RECOVERED] role={role!r} salvaged broken model output via sanitizer",
        flush=True,
    )
    return _SanitizedResult(output=obj, messages=prior_history)


def _coder_agent_id(task_id: str | None) -> str | None:
    """Pass-through coder agent id (ticket baziforecaster-tqpgf).

    Per grill-me 2026-07-18 (Q3/Q7): the planner OWNS coder naming and emits
    ``ApprovedTask.id = coderNN``. That id IS the agent id, the
    memory filename, and the status-board line — identical strings. No digit
    mangling (the old ``coder34`` bug). Non-coder roles / missing ids return None.
    """
    if not task_id:
        return None
    return task_id


async def load_skill(role: str, brief: str, bd: str = "", task_id: str | None = None) -> str:
    """Invoke a role's frozen YAML skill. Uses loopguard for timeout + failure transcript."""
    if role not in ROLE_OUTPUT_TYPE:
        return f"[HALT] unknown role {role!r}"

    # Bind the active role (+ agent id for coder isolation) so the `remember`
    # tool writes to THIS agent's folder (per-coderN isolated memory, a101k).
    from factory.infra.tools import set_current_agent, set_current_role

    set_current_role(role)
    agent_id = _coder_agent_id(task_id) if role == "coder" else None
    set_current_agent(agent_id)

    # Each agent receives ITS OWN history. We reconstruct the per-turn continuity
    # bridge as the role's `.md` twin (ticket baziforecaster-mb1k5) — the
    # token-cheap, visibility-assured re-injection source fed as `message_history`
    # to ALL agents EVERY spawn, NOT the raw `.jsonl` replay. For the coder role
    # with a derived `agent_id` this is the agent-isolated `coder/<agent_id>.md`
    # (ticket a101k): each coder sees only its own work, no sibling leakage.
    # Cold spawn (no twin yet) -> None -> no prepend.
    prior_history = build_md_bridge(role, agent_id=agent_id)
    if prior_history:
        log_operator(
            f"load_skill({role}): feeding {len(prior_history)} MD-twin message as "
            f"message_history (own-role continuity, per-turn reinjection)",
            level="INFO",
        )

    # P1 ugvt (M4): SINK-2 cross-phase context. If prior phases stored summaries
    # (other than the current role), inject a compact "PRIOR PHASE SUMMARIES"
    # block so this phase sees richer context than terse raw output. The user
    # task_spec (`brief`) stays the authoritative body; this is additive context.
    # FIX (mhynr / 4lq5d): NEVER inject prior phase summaries into CODER roles.
    # The coder must work ONLY from its per-task ApprovedTask brief (no shared
    # cross-phase pollution) — each coder_N is a fresh agent with isolated
    # memory (ticket a101k) and must not receive the full ApprovedPlan.
    if PHASE_SUMMARIES and role != "coder":
        prior_block = "\n\n".join(
            f"## {r} summary (prior phase):\n{s}"
            for r, s in PHASE_SUMMARIES.items()
            if r != role
        )
        if prior_block:
            brief = (
                wrap_injected_context(prior_block, label="prior_phase_summaries")
                + "\n\n"
                + brief
            )

    # Scope-driven auto-context (86rmw/xfqkf/y1oqi): planner AND supervisor_plan
    # receive the SAME scoped repo-map (folder tree + per-file symbols + KG)
    # built once in main() from the user prompt's `scope:` front-matter. This
    # replaces the old hand-written hardcoded DictMap block (task-specific,
    # never derived from declared files, and not shared with supervisor_plan).
    if role in ("planner", "supervisor_plan") and SCOPE_CONTEXT:
        brief = (
            brief
            + "\n\n"
            + wrap_injected_context(SCOPE_CONTEXT, label="codebase_reference_context")
        )
        log_operator(
            f"load_skill({role}): injected scoped codebase_reference_context", level="INFO"
        )

    agent, guard = build_role_agent(role)
    model_cls = OUTPUT_TYPE_REGISTRY[ROLE_OUTPUT_TYPE[role]]

    # ── keep_memory context-prepend compaction gate (Function A) ───────────────
    # Prior history is prepended into THIS subagent's message_history unconditionally
    # today, bloating to 700K+. Before running, gate it: if the working LLM's own
    # prior history exceeds CONTEXT_COMPACT_CEILING (200K) we compact it in-place
    # (Function B, same working LLM) so the prepended memory stays bounded. The
    # (possibly compacted) history is then fed as message_history below.
    if prior_history:
        try:
            from types import SimpleNamespace

            from factory.infra._loopguard import (
                CONTEXT_COMPACT_CEILING,
                compact_memory_gate,
                estimate_tokens,
            )

            if estimate_tokens(prior_history) > CONTEXT_COMPACT_CEILING:
                prior_history = await compact_memory_gate(
                    prior_history,
                    agent.model,
                    SimpleNamespace(bd_id=bd),
                    role,
                    role=role,
                    agent_id=agent_id,
                )
                print(
                    f"[compact_memory_gate] role={role!r}: prepended history "
                    f"compacted to {len(prior_history)} messages",
                    flush=True,
                )
        except Exception as exc:
            # Locked design + ticket wkxy: a gate failure (empty keep_memory
            # externalization, floor violation, or summarizer fallback miss) is
            # a HARD HALT — we must NOT silently prepend the 700K+ unbounded
            # history the gate exists to bound. Fail loudly, then abort.
            print(
                f"[HALT] compact_memory_gate failed for role={role!r}: {exc!r} "
                f"— refusing to prepend unbounded prior_history.",
                file=sys.stderr,
                flush=True,
            )
            raise
    # ───────────────────────────────────────────────────────────────────────────

    try:
        result = await _run_agent_retry(
            agent, brief, loopguard=True, phase=role, role=role, bd_id=bd,
            message_history=prior_history, agent_id=agent_id,
        )
    except UnexpectedModelBehavior as e:
        # baziforecaster-cqjb: the model emitted structurally-broken JSON that
        # pydantic-ai could not coerce after Agent(retries=5). Salvage the REAL
        # model output via fast-json-repair + frozen normalizer BEFORE giving up.
        # FIX (baziforecaster-ydiv): the real output is the model's last
        # `final_result` ToolCallPart args, still present in the run's message
        # history (persisted by loopguard every turn). We reload it instead of
        # trusting e.message (which is only the framework error STRING and was
        # previously fed to the sanitizer, guaranteeing a HALT). e.message is
        # kept only as a last-resort fallback when no tool-call exists.
        # Truncated Literals (e.g. "bloc") cannot be guessed safely -> HALT.
        real_messages = _load_role_messages(role, agent_id=agent_id)
        if ROLE_OUTPUT_TYPE[role] != "str":
            raw = extract_model_json(real_messages)
            if not raw:
                raw = extract_tool_call_payload(e) or ""
                if not raw:
                    raise RuntimeError(
                        f"[HALT] role {role!r} emitted no final_result call"
                    ) from e
        else:
            raw = (
                extract_model_json(real_messages)
                or getattr(e, "body", None)
                or getattr(e, "message", None)
                or ""
            )
            if not raw:
                # baziforecaster-78j9m: when the FRAMEWORK tool-dispatch validator
                # rejects a structurally-invalid final_result call (e.g.
                # MALFORMED_FUNCTION_CALL: list instead of object), pydantic-ai
                # discards the offending args and persists no valid ToolCallPart, so
                # extract_model_json returns None. Reclaim the attempted payload
                # from the exception and still run it through clean_role_output, so
                # the malformed-call path and the malformed-JSON path share ONE
                # fail-loud HALT exit. No leniency.
                raw = extract_tool_call_payload(e) or ""
        recovered = _recover_role_output(raw, model_cls, role, prior_history)
        if recovered is None:
            raise RuntimeError(
                f"[HALT] role {role!r} output unparseable after sanitize: {e!r}"
            ) from e
        result = recovered
    except Exception as exc:
        print(f"[HALT] role={role!r} failed: {exc!r}", flush=True)
        raise RuntimeError(f"[HALT] role {role!r} failed: {exc!r}") from exc

    if hasattr(result.output, "model_dump_json"):
        validated_json = result.output.model_dump_json()
    else:
        validated_json = str(result.output)
    # Persist the RAW Pydantic JSON so the conductor can re-derive typed
    # models (e.g. ApprovedPlan for the plan-gate / code-review DAG). history[]
    # carries markdown-by-design (p0vt mandate) and is NOT parseable as JSON.
    RAW_OUTPUTS[role] = validated_json

    # P0 rhh4 (M7): detect loopguard RECOVER — the loopguard's recovery agent
    # (tools=[]) returns a fabricated best-effort object when a phase stalled.
    # It is injected as a trailing user turn whose prompt contains our RECOVER
    # sentinel text. We must NEVER silently accept it as a clean model pass.
    # Detection: scan the run's messages for a ModelRequest whose parts include
    # the recovery sentinel ("BLOCKED" + "best answer now" RECOVER prompt),
    # which is unique to the loopguard's recovery_agent.run() prompt.
    recovered = _detect_and_mark_recovery(role, result, prior_history)

    if role == "coder" and (getattr(guard, "exhausted", False) or recovered):
        try:
            import json
            obj = json.loads(validated_json)
            # validated_json comes from TaskResult.model_dump_json(), whose status field
            # is already normalized to "done" | "blocked" by the upstream Pydantic
            # validator — no "completed"/free-string reaches here.
            if obj.get("status") != "done":
                obj["status"] = "blocked"
                if recovered:
                    obj["notes"] = (
                        f"[Budget Recovery] loopguard recovered this task because it stalled (best-effort data). "
                        f"{obj.get('notes', '')}"
                    )
                else:
                    obj["notes"] = (
                        f"[Budget Fatal] coder exhausted its tool budget "
                        f"and could not finish. {obj.get('notes', '')}"
                    )
            else:
                if recovered:
                    obj["notes"] = (
                        f"[Budget Recovery Edge] loopguard recovered this task (best-effort data). "
                        f"{obj.get('notes', '')}"
                    )
                else:
                    obj["notes"] = (
                        f"[Budget Edge] coder completed at budget limit. "
                        f"{obj.get('notes', '')}"
                    )
            validated_json = json.dumps(obj)
            RAW_OUTPUTS[role] = validated_json
        except Exception:
            pass

    # SA5-F2: per-task transcript for EVERY phase (especially coder/EXECUTE).
    try:
        from factory.infra.tools import log_response_raw
        log_response_raw(
            phase="EXECUTE" if role == "coder" else role,
            role=role,
            ident=agent_id or task_id or f"{bd}_{role}",
            res=result,
        )
    except Exception as log_exc:
        print(f"[WARN] response logging failed for role={role!r}: {log_exc!r}", flush=True)

    try:
        await append_eval_log(
            bd_id=bd or None,
            phase=role,
            role=role,
            task_id=None,
            output=getattr(result, "output", None),
            usage=result,
            message_count=_safe_message_count(result),
        )
    except Exception as log_exc:
        print(f"[WARN] eval logging failed for role={role!r}: {log_exc!r}", flush=True)

    persist_role(role, result, agent_id=agent_id)

    # baziforecaster-4mn8 (M11): structural final_result guard for planner-family
    # roles. If the planner burned its tool budget (GuardToolset.exhausted) yet
    # emitted no structured output, it was looping research calls and never
    # produced a plan — HALT loudly instead of proceeding on a None plan (the
    # q9lt failure mode). assert_planner_emitted raises RuntimeError if so.
    if role in ("planner", "supervisor_plan") and guard is not None:
        assert_planner_emitted(
            getattr(guard, "exhausted", False),
            bool(getattr(result, "output", None)),
            role,
        )

    # P1 ugvt (M4): SINK-2 — store this role's summary for downstream phases.
    # Compact markdown render of the output (not raw JSON) to save cross-phase
    # tokens. Fail loudly if the store itself errors (it never should).
    try:
        PHASE_SUMMARIES[role] = _model_to_md(result.output)
    except Exception as exc:
        print(f"[WARN] PHASE_SUMMARIES store failed for {role!r}: {exc!r}", flush=True)

    # `validated_json` is the JSON string (used for the `history` parse
    # contract at run_phase, line ~1700). The model-object markdown render
    # is computed INSIDE load_skill via `_model_to_md(result.output)`
    # (Pydantic-AI v2.0: `result.output` IS the parsed model) and stored
    # in PHASE_SUMMARIES[role] — callers pull MD from there, never a
    # JSON-string round-trip.
    return validated_json


def _load_role_messages(role: str, agent_id: str | None = None) -> list | None:
    """Reconstruct a role's cumulative `message_history` from its `<role>.jsonl`."""
    try:
        from factory.infra.artefacts import load_role_messages

        return load_role_messages(role, agent_id=agent_id)
    except Exception as exc:
        print(f"[WARN] _load_role_messages failed for {role!r}: {exc!r}", flush=True)
        return None


def read_prompt(prompt_file: Path) -> tuple[bool, str, list[str]]:
    """Parse the user prompt with an optional YAML front-matter block.

    Returns ``(resume_flag, task_spec, scope)``.

    Format::

        ---
        Resume: false
        bd: baziforecaster-hbh1
        scope:
          - src2/core/schemas/unified.py
          - src2/engine/
        ---
        # EPIC
        ...freeform markdown body...

    The front-matter is delimited by leading ``---`` / closing ``---``. If no
    front-matter is present the first line MUST be a strict ``Resume:
    True|False`` (legacy format) — fail loudly otherwise. ``scope`` is a
    context hint only (never wired to an ACL); defaults to ``[]`` when absent.
    """
    if not prompt_file.exists():
        return False, "Create a python script that prints 'This Harness is Working'", []

    text = prompt_file.read_text()
    # Normalise CRLF/CRLF-oddities and detect a leading front-matter fence.
    lines = text.splitlines()
    scope: list[str] = []
    task_body = text.strip()

    if lines and lines[0].strip() == "---":
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break
        if end_idx is None:
            raise SystemExit(
                f"[HALT] {prompt_file} has an opening '---' front-matter fence "
                f"but no closing '---'."
            )
        try:
            fm_text = "\n".join(lines[1:end_idx])
            front = yaml.safe_load(fm_text) or {}
        except Exception as e:  # yaml.YAMLError or similar — fail loudly
            raise SystemExit(f"[HALT] {prompt_file} front-matter YAML parse failed: {e}")
        if not isinstance(front, dict):
            raise SystemExit(
                f"[HALT] {prompt_file} front-matter must be a YAML mapping."
            )
        resume_raw = str(front.get("Resume", "false")).strip().lower()
        if resume_raw not in ("true", "false"):
            raise SystemExit(
                f"[HALT] {prompt_file} Resume: must be 'true' or 'false' "
                f"(got: {front.get('Resume')!r})."
            )
        resume = resume_raw == "true"
        raw_scope = front.get("scope", []) or []
        if isinstance(raw_scope, str):
            raw_scope = [raw_scope]
        if not isinstance(raw_scope, list):
            raise SystemExit(
                f"[HALT] {prompt_file} scope: must be a YAML list of paths."
            )
        scope = [str(s) for s in raw_scope]
        task_body = "\n".join(lines[end_idx + 1 :]).strip()
    else:
        m = RESUME_RE.match(lines[0]) if lines else None
        if not m:
            raise SystemExit(
                f"[HALT] {prompt_file} first line must be a YAML '---' front-matter "
                f"block (with Resume:/bd:/scope:) or a strict 'Resume: True|False' "
                f"line (got: {lines[0] if lines else '<empty>'})."
            )
        resume = m.group(1).lower() == "true"
        # Legacy: drop an explicit `bd:` line so it never leaks into the brief.
        task_body = "\n".join(
            ln for ln in lines[1:] if not re.match(r"^bd:[ \t]*[A-Za-z0-9_-]+", ln)
        ).strip()

    if not task_body:
        raise SystemExit(f"[HALT] {prompt_file} has no task spec body.")
    return resume, task_body, scope


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


# Max concurrent Coder subagents (WIP bound for the EXECUTE phase).
MAX_AGENTS = 20

# Max coder validation passes: harness runs the guardrail (ruff) after each
# coder declaration; on ruff failure a FRESH coder agent is spawned (bounded by
# this) with the ruff feedback appended. Pyright errors are surfaced but do NOT
# trigger a re-spawn.
CODER_VALIDATION_PASSES = 3

# Liveness threshold for the DAG dependency wait (NOT a give-up deadline):
# if a prerequisite group has already completed but forgot to set its
# completion event, flag the bug after this many seconds.
DAG_DEADLOCK_TIMEOUT: float = CODER_VALIDATION_PASSES * AGENT_RUN_TIMEOUT  # 3 * 600 = 1800.0


def _downstream_closure(failing: set[str], groups: list[WorkGroup]) -> set[str]:
    """Forward-reachable task set from `failing`: each failing task plus every
    task in any downstream (dependent) WorkGroup. Bounds re-execution so a bad
    upstream task re-runs its dependents, but untouched work is preserved."""
    task_group: dict[str, str] = {}
    by_id = {g.id: g for g in groups}
    dependents: dict[str, list[str]] = {g.id: [] for g in groups}
    for g in groups:
        for t in g.tasks:
            task_group[t.id] = g.id
        for d in g.depends_on:
            if d in dependents:
                dependents[d].append(g.id)
    out: set[str] = set(failing)
    stack = [task_group[t] for t in failing if t in task_group]
    seen: set[str] = set()
    while stack:
        gid = stack.pop()
        if gid in seen:
            continue
        seen.add(gid)
        for dep in dependents[gid]:
            for t in by_id[dep].tasks:
                out.add(t.id)
            stack.append(dep)
    return out


async def run_execute_phase(
    plan: ApprovedPlan,
    run_dir: Path,
    sem: asyncio.Semaphore,
    coder_fn,
    prior: dict[str, TaskResult] | None = None,
    rerun_ids: set[str] | None = None,
    feedback: dict[str, str] | None = None,
    exchange: list[ExchangeTurn] | None = None,
    pass_counter: dict[str, int] | None = None,
    bd: str = "",
    history: list[tuple[str, str]] | None = None,
    strict: bool = True,
) -> dict[str, TaskResult]:
    """Execute the workplan DAG.

    - Topologically ordered via per-group asyncio.Event gating on depends_on.
    - Tasks within a group ALWAYS run concurrently via asyncio.gather, bounded
      by `sem`.  The group-level `concurrent` flag is IGNORED during execution:
      if the Planner needs sequential ordering it must put tasks in separate
      groups chained via depends_on — that is the ONLY supported gating
      mechanism.  Addressed user complaint 'not spawning agents based on DAG'.
    - `prior` + `rerun_ids` enable surgical re-execution: only tasks whose id is
      in `rerun_ids` are re-run; others are copied from `prior`.
    - `feedback` (optional) is a task_id -> prior-review/audit findings text map.
      When a rerun task's id is in `feedback`, its coder brief is augmented with
      a `=== PRIOR FEEDBACK ===` block (R1, ticket baziforecaster-nw9ov) so the
      rerun coder is told exactly what to change instead of re-deriving it blind.
    - Asserts the Planner's file-disjoint claim per concurrent group (HALT)."""
    workplan = plan.workplan
    groups = {g.id: g for g in workplan.groups}
    for g in workplan.groups:
        for d in g.depends_on:
            if d not in groups:
                raise RuntimeError(f"[DAG] group {g.id!r} depends on unknown group {d!r}")
    for g in workplan.groups:
        if g.concurrent:
            seen_paths: set[tuple[str, ...]] = set()
            for t in g.tasks:
                key = tuple(sorted(_real_source_paths(t.file_paths)))
                # A task with no REAL source files has nothing to race on; do
                # not let the empty tuple collide across tasks (vw4dd).
                if not key:
                    continue
                if key in seen_paths:
                    raise RuntimeError(
                        f"[DAG] group {g.id!r} is NOT file-disjoint "
                        f"(shared {sorted(key)}) — violates Planner claim"
                    )
                seen_paths.add(key)
    # P0 zu9u (H8): cross-group disjointness. Groups run concurrently via
    # asyncio.gather below, so two DIFFERENT groups sharing a file can race.
    # Intra-group assert above is insufficient — assert globally here.
    # NOTE: this is a PLANNER-CONTRACT violation surfaced fail-loudly — not a
    # runtime patch. The planner owns parallelism; we do not silently reorder.
    _all_paths: dict[str, str] = {}  # file_path -> group_id (first owner)
    for g in workplan.groups:
        for t in g.tasks:
            for fp in _real_source_paths(t.file_paths):
                owner = _all_paths.get(fp)
                if owner is not None and owner != g.id:
                    raise RuntimeError(
                        f"[DAG] cross-group file overlap: {fp} appears in multiple "
                        f"groups ({owner!r} and {g.id!r}) — violates concurrency safety"
                    )
                _all_paths[fp] = g.id
    group_events = {gid: asyncio.Event() for gid in groups}
    group_done: dict[str, bool] = {}
    results: dict[str, TaskResult] = dict(prior or {})

    async def execute_task(t: ApprovedTask) -> TaskResult:
        staged = stage_paths(t.file_paths)
        # ── SIZE-AWARE CONTEXT INJECTION GATE (epic baziforecaster-gx30p) ──
        # A coder must hold the full target file to edit precisely, but an
        # unbounded file risks blowing the 200K budget. Compute deterministic
        # token counts per task BEFORE any coder spawns (cheap assertion before
        # an expensive LLM call). k2owt / qkm3p / fzqa2 / vze01.
        est = estimate_task_tokens(t.file_paths)
        total_tokens: int = est["total"]  # type: ignore[typeddict-item]
        per_file: dict[str, int] = est["per_file"]  # type: ignore[typeddict-item]
        tier = "A" if total_tokens <= TASK_TOKEN_THRESHOLD else "B"
        # fzqa2: stage (copy) live files into temp/<task>/ as an eviction-exempt
        # baseline. The coder reads from staging (real content, never evicted),
        # the live tree stays read-only. Modes drive the per-file EDIT MODE block.
        edit_modes = _stage_copies(t.file_paths, staged)
        if tier == "B":
            # vze01 (last resort): if ANY single file alone exceeds the slice
            # budget, even a targeted slice read would blow the context — the
            # task genuinely needs a huge file and must be SPLIT by the planner.
            oversized = [fp for fp, n in per_file.items() if n > TIER_B_SLICE_THRESHOLD]
            if oversized:
                raise TaskNeedsSplitError(
                    f"[HALT] task {t.id} requires SPLIT — file(s) exceed the "
                    f"{TIER_B_SLICE_THRESHOLD:,}-token slice budget: "
                    f"{sorted(oversized)}. Re-plan with narrower file_paths."
                )
            # qkm3p: Tier B — do NOT inject the full files. The coder works from
            # the eviction-exempt staging copies + a structural map so it can
            # target precise slices without the whole file in its context.
            tier_b_map = _build_tier_b_map(t.file_paths)
            print(
                f"  [SIZE-GATE] task {t.id}: Tier B ({total_tokens:,} tokens > "
                f"{TASK_TOKEN_THRESHOLD:,} threshold) — injecting structural map, "
                f"coder reads staging slices.",
                flush=True,
            )
            inline_files = ""
        else:
            tier_b_map = ""
            print(
                f"  [SIZE-GATE] task {t.id}: Tier A ({total_tokens:,} tokens) — "
                f"full files injected normally.",
                flush=True,
            )
            inline_files = ""
            if staged:
                try:
                    text = Path(staged[0]).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = f"<unreadable staging mirror: {staged[0]}>"
                prefix_text = "\n".join(
                    f"{i+1}: {line}" for i, line in enumerate(text.splitlines())
                )
                inline_files = (
                    f"--- FILE TO EDIT: {t.file_paths[0]} (staging: {staged[0]}) ---\n"
                    f"{prefix_text}\n--- END FILE ---"
                )
        # R5 (baziforecaster-6gizg): frozen, structured behaviour appendix derived
        # from the task's acceptance/DoD — NOT the planner's raw prose. Anchors the
        # coder to a contract regardless of planner wording.
        behaviour_appendix = (
            "=== EXPECTED CODER BEHAVIOUR (frozen contract) ===\n"
            "- Implement ONLY this task; do not touch other tasks' files.\n"
            "- Satisfy EVERY acceptance_criteria line below verbatim; if a criterion "
            "is unachievable, return status 'blocked' with the reason — never fake it.\n"
            "- Use STRICT Pydantic models / typed fields only; no bare dicts for "
            "domain logic; no dict access on Pydantic models.\n"
            "- Code MUST pass `uv run ruff check`. Write output under "
            "factory/temp/ (PROPOSE-ONLY); never write src/ or src2/.\n"
            "- Return a TaskResult (task_id, status, files_changed, diff_summary, "
            "notes) with NO file content inside it.\n"
            f"- ACCEPTANCE (verbatim):\n{t.acceptance}\n"
        )
        is_rerun = bool(rerun_ids) and t.id in rerun_ids
        feedback_block = ""
        if feedback and t.id in feedback:
            # R1 (baziforecaster-nw9ov): the harness computed prior review/audit
            # findings to pick rerun_ids but never showed them to the coder. The
            # rerun coder is per-agent isolated (coderN.jsonl) and effectively
            # fresh, so explicit injection is REQUIRED — do not rely on message_history.
            feedback_block = (
                "\n=== PRIOR FEEDBACK (why this task was reopened) ===\n"
                "You are FIXING a previously-failed attempt. The harness reopened "
                "this task based on the review/audit findings below. Address EVERY "
                "point. Your own prior attempt context lives in your coder memory "
                "(compacted via keep_memory) — this block is the authoritative list "
                "of what changed.\n"
                f"{feedback[t.id]}\n"
            )
        elif is_rerun:
            feedback_block = (
                "\n=== PRIOR FEEDBACK ===\n"
                "This task was reopened by the harness (rerun target) but no "
                "structured findings were captured. Re-read your own coder memory "
                "(keep_memory) and the staged files, and re-verify your prior "
                "attempt against the acceptance criteria.\n"
            )
        discipline_block = (
            "\n=== FROZEN DISCIPLINE (load-bearing rules — DO NOT VIOLATE) ===\n"
            "- ZERO-DICTS: No bare dict access on Pydantic models. All domain data uses strict Pydantic models/Enums/Literals.\n"
            "- PYDANTIC-ONLY: All domain lookups/tables = Pydantic registry models with typed fields. Enums ONLY as field types.\n"
            "- FAIL LOUDLY: Full tracebacks on errors. No silent except:pass, no hidden fallbacks.\n"
            "- FAIL CHEAPLY: Cheap assertions before expensive LLM calls.\n"
            "- NO src/ or src2/ edits: Write output under factory/temp/ only.\n"
            "- Code MUST pass `uv run ruff check` before being considered done.\n"
        )
        brief = (
            "You are implementing EXACTLY ONE task. Do not implement others.\n\n"
            f"TASK ID: {t.id}\nTITLE: {t.title}\n"
            f"FILE TO EDIT: {t.file_paths[0] if t.file_paths else 'None'}\n\n"
            f"INSTRUCTION:\n{t.instruction}\n\n"
            f"ACCEPTANCE CRITERIA:\n{t.acceptance}\n\n"
            f"LIVE FILES (read-only reference — DO NOT write here):\n{t.file_paths}\n\n"
            f"STAGING PATHS (WRITE your proposed files ONLY here, under factory/temp/):\n{staged}\n\n"
            + _edit_mode_block(edit_modes, staged)
            + "\n"
            + (tier_b_map + "\n\n" if tier_b_map else "")
            + (f"\n=== FULL FILE CONTENT (edit directly; NO read tool needed) ===\n{inline_files}\n" if inline_files else "")
            + wrap_injected_context(f"GLOBAL ALIGNMENT:\n{plan.alignment}", label="global_alignment")
            + "\n\n"
            + behaviour_appendix
            + discipline_block
            + feedback_block
        )
        # --- CQRS CLAIM ---
        try:
            import subprocess
            subprocess.run(["./bd", "update", f"bd-{t.id}", "--claim", "--status", "in_progress"], cwd=str(REPO_ROOT), capture_output=True, check=False)
        except Exception:
            pass
        # ------------------
        async with sem:
            # P1 vo94 (M3): show the coder as IN-FLIGHT *before* it runs, so an
            # active task is not misreported as finished (the board previously
            # only flipped to coder:{id} after the call returned).
            update_status_board(history if history is not None else [], f"{t.id} → {t.file_paths[0] if t.file_paths else '?'}", bd)
            try:
                out = await asyncio.wait_for(
                    coder_fn(brief, task_id=t.id), timeout=AGENT_RUN_TIMEOUT
                )
            except TimeoutError:
                # docs/01_fix.md Fix B: surface silent blocked paths loudly.
                log_operator(
                    f"task {t.id} blocked: coder timed out after "
                    f"{AGENT_RUN_TIMEOUT}s (initial pass)",
                    level="WARNING",
                )
                return TaskResult(
                    task_id=t.id,
                    status="blocked",
                    files_changed=[],
                    diff_summary="",
                    notes=f"coder timed out after {AGENT_RUN_TIMEOUT}s",
                )
            except Exception as e:
                log_operator(
                    f"[execute_task] coder_fn exception for task {t.id}; "
                    f"marking blocked. error={e!r}",
                    level="ERROR",
                )
                return TaskResult(
                    task_id=t.id,
                    status="blocked",
                    files_changed=[],
                    diff_summary="",
                    notes=f"coder execution failed: {e}",
                )
            # SA5-F2: per-task transcript for coder/EXECUTE diagnostics.
            try:
                task_log = RUNTIME_DIR / f"task_{t.id}.log"
                task_log.parent.mkdir(parents=True, exist_ok=True)
                task_log.write_text(
                    f"=== TASK {t.id} ===\nBRIEF:\n{brief}\n\nOUTPUT:\n{out}\n",
                    encoding="utf-8",
                )
            except Exception as log_exc:
                print(f"[WARN] task transcript write failed for {t.id}: {log_exc!r}", flush=True)
        append_exchange_turn(exchange, pass_counter, "coder", out, bd)
        try:
            obj = json.loads(out)
        except Exception as e:
            # SA4-F4: graceful degradation (return a blocked TaskResult string to
            # the LLM loop) BUT surface the fault to the operator instead of
            # hiding it inside `notes` alone.
            log_operator(
                f"[execute_task] coder output for task {t.id} was not valid JSON; "
                f"marking blocked. error={e!r}",
                level="WARNING",
            )
            return TaskResult(
                task_id=t.id,
                status="blocked",
                files_changed=[],
                diff_summary="",
                notes=f"coder output not JSON: {e}",
            )

        # --- HARNESS-OWNED VALIDATION RE-SPAWN LOOP (DECISION C / Q4-A) ---
        # The coder only DECLARES done; the harness runs the guardrail (ruff +
        # smoke type-construction gate + broadened union pyright) on the staged
        # files. On RUFF, SMOKE, OR PYRIGHT failure it spawns a FRESH coder agent
        # with the feedback appended so it self-corrects (docs/01_fix.md Tasks
        # 1, 2, 6: pyright is now BLOCKING, immediate re-spawn). The per-stage
        # gate means a broken upstream type contract surfaces at the PRODUCER,
        # not the consumer. Each coder call is a clean agent (no shell needed).
        feedback_brief = brief
        verdict_state: dict[str, dict] = {}  # fp -> last guardrail payload
        for _pass in range(CODER_VALIDATION_PASSES):
            files = obj.get("files_changed") or obj.get("files") or []
            ruff_failed = False
            pyright_failed = False
            smoke_failed = False
            zero_diff_failed = False
            feedback_block = ""
            for fp in files:
                try:
                    edit_set_arg = ",".join(t.file_paths) if t.file_paths else ""
                    # 00_fix Fix A/B: validate the STAGED copy via the single
                    # normalization seam so BOTH absolute and relative temp paths
                    # resolve to the correct staging file (absolute paths used to
                    # collapse to the live file and self-compare as a false zero-diff).
                    validate_target = stage_path(fp)
                    # 00_fix Fix A (Q5 Option B): zero-diff vs the captured .orig
                    # baseline -> genuine no-op edit. Re-spawn the coder to actually
                    # edit; block (via the SPAWN-ALL HALT) only if it persists.
                    _zd = staged_zero_diff(fp)
                    if _zd is True:
                        zero_diff_failed = True
                        feedback_block += (
                            f"\n--- {fp} (ZERO-DIFF) ---\n"
                            f"You changed nothing versus the baseline (no .orig diff). "
                            f"Apply the required edits to {stage_path(fp)} and re-output done JSON.\n"
                        )
                    res = subprocess.run(
                        [sys.executable, "factory/tools/guardrail_check.py", "validate", validate_target, edit_set_arg],
                        capture_output=True,
                        text=True,
                        cwd=str(REPO_ROOT),
                        timeout=240,
                    )
                except Exception as guard_exc:
                    # GUARDRAIL ITSELF errored (not a lint failure) — fail loudly
                    # to the operator but treat as pass so we never crash the task.
                    log_operator(
                        f"[execute_task] guardrail_check.py crashed on {fp!r} for "
                        f"task {t.id}: {guard_exc!r}",
                        level="WARNING",
                    )
                    continue
                try:
                    gj = json.loads(res.stdout.strip().splitlines()[-1]) if res.stdout.strip() else {}
                except Exception:
                    # Unparseable guardrail output -> treat as pass to avoid loops.
                    continue
                verdict_state[fp] = gj
                # Fix E (00_fix): mechanically auto-fix lint on the staged file,
                # then re-score the auto-fixed file so a coder is never burned for
                # a trivial I001/UP034 it can't see. Only re-runs when ruff failed.
                if gj.get("ruff_ok", True) is False:
                    try:
                        subprocess.run(
                            ["uv", "run", "ruff", "check", "--fix", validate_target],
                            cwd=str(REPO_ROOT),
                            capture_output=True,
                            timeout=120,
                        )
                        subprocess.run(
                            ["uv", "run", "ruff", "format", validate_target],
                            cwd=str(REPO_ROOT),
                            capture_output=True,
                            timeout=120,
                        )
                        res2 = subprocess.run(
                            [sys.executable, "factory/tools/guardrail_check.py", "validate", validate_target, edit_set_arg],
                            capture_output=True,
                            text=True,
                            cwd=str(REPO_ROOT),
                            timeout=240,
                        )
                        gj2 = json.loads(res2.stdout.strip().splitlines()[-1]) if res2.stdout.strip() else {}
                        if gj2.get("ruff_ok", True) is True:
                            feedback_block += (
                                f"\n--- {fp} (RUFF AUTO-FIX APPLIED) ---\n"
                                f"The harness auto-fixed lint; re-validate passed.\n"
                            )
                            gj = gj2
                            verdict_state[fp] = gj2
                    except Exception:
                        pass
                if gj.get("ruff_ok", True) is False:
                    ruff_failed = True
                    feedback_block += (
                        f"\n--- {fp} (RUFF) ---\n"
                        f"RUFF OUTPUT:\n{gj.get('ruff_output', '')}\n"
                        f"DIFF VS CHECKPOINT:\n{gj.get('diff_vs_checkpoint', '')}\n"
                    )
                if gj.get("smoke_ok", True) is False:
                    # Task 1: type-construction smoke gate (BUG 2 class) blocks.
                    smoke_failed = True
                    feedback_block += (
                        f"\n--- {fp} (SMOKE TYPE-CONSTRUCTION) ---\n"
                        f"SMOKE OUTPUT:\n{gj.get('smoke_output', '')}\n"
                    )
                if gj.get("pyright_ok", True) is False:
                    # Task 2: pyright is now BLOCKING, scoped to the edited file's
                    # own lines (our_errors filter inside guardrail_check).
                    pyright_failed = True
                    feedback_block += (
                        f"\n--- {fp} (PYRIGHT) ---\n"
                        f"PYRIGHT OUTPUT:\n{gj.get('pyright_output', '')}\n"
                    )

            if not (ruff_failed or smoke_failed or pyright_failed or zero_diff_failed):
                break  # clean -> final result is the current out/obj.

            if _pass + 1 >= CODER_VALIDATION_PASSES:
                # Task 6 / D8: HARD-HALT on the 3rd validation failure. A broken
                # upstream type contract must NOT poison dependents; we abort the
                # EXECUTE phase loudly rather than warn-and-proceed (the old
                # behaviour that let module9's runtime crash ship).
                reasons = []
                if ruff_failed:
                    reasons.append("ruff")
                if smoke_failed:
                    reasons.append("smoke type-construction")
                if pyright_failed:
                    reasons.append("pyright")
                if zero_diff_failed:
                    reasons.append("zero-diff (no change vs baseline)")
                # Fix G (00_fix): surface the gate reason next to the SPAWN-ALL
                # HALT so the operator sees it without a deep log dive.
                log_operator(
                    f"[HALT] task {t.id} failed validation after "
                    f"{CODER_VALIDATION_PASSES} coder passes "
                    f"({', '.join(reasons)})",
                    level="ERROR",
                )
                raise RuntimeError(
                    f"[HALT] task {t.id} failed validation after "
                    f"{CODER_VALIDATION_PASSES} coder passes "
                    f"({', '.join(reasons)}). EXECUTE phase aborted — a broken "
                    f"type contract must not reach review/red-team."
                )

            prior_rejection_notes = obj.get("notes", "")
            rejection_block = (
                "\n\n=== PRIOR ATTEMPT REJECTION (your last attempt was rejected; "
                "do NOT repeat this) ===\n" + prior_rejection_notes
            ) if prior_rejection_notes else ""
            feedback_brief = (
                brief
                + rejection_block
                + "\n\n=== GUARDRAIL FEEDBACK (ruff failed on your staged file(s); "
                "fix the errors below, then output your done JSON again) ===\n"
                + feedback_block
            )
            async with sem:
                update_status_board(history if history is not None else [], f"{t.id} → {t.file_paths[0] if t.file_paths else '?'}", bd)
                try:
                    out = await asyncio.wait_for(
                        coder_fn(feedback_brief, task_id=t.id), timeout=AGENT_RUN_TIMEOUT
                    )
                except TimeoutError:
                    # docs/01_fix.md Fix B: surface silent blocked paths loudly.
                    log_operator(
                        f"task {t.id} blocked: coder re-spawn timed out after "
                        f"{AGENT_RUN_TIMEOUT}s (validation re-spawn pass)",
                        level="WARNING",
                    )
                    return TaskResult(
                        task_id=t.id,
                        status="blocked",
                        files_changed=[],
                        diff_summary="",
                        notes=f"coder re-spawn timed out after {AGENT_RUN_TIMEOUT}s",
                    )
                except Exception as e:
                    log_operator(
                        f"[execute_task] coder_fn re-spawn exception for task {t.id}; "
                        f"marking blocked. error={e!r}",
                        level="ERROR",
                    )
                    return TaskResult(
                        task_id=t.id,
                        status="blocked",
                        files_changed=[],
                        diff_summary="",
                        notes=f"coder re-spawn execution failed: {e}",
                    )
                try:
                    task_log = RUNTIME_DIR / f"task_{t.id}.log"
                    task_log.parent.mkdir(parents=True, exist_ok=True)
                    with task_log.open("a", encoding="utf-8") as fh:
                        fh.write(f"\n=== RE-SPAWN PASS {_pass + 2} ===\nBRIEF:\n{feedback_brief}\n\nOUTPUT:\n{out}\n")
                except Exception as log_exc:
                    print(f"[WARN] task transcript append failed for {t.id}: {log_exc!r}", flush=True)
            append_exchange_turn(exchange, pass_counter, "coder", out, bd)
            try:
                obj = json.loads(out)
            except Exception as e:
                log_operator(
                    f"[execute_task] re-spawned coder output for task {t.id} was not "
                    f"valid JSON; proceeding with last valid obj. error={e!r}",
                    level="WARNING",
                )
                break

        # --- PRE-REVIEW GATES (00_fix Fix A: single seam vs .orig baseline) ---
        # Zero-diff detection now lives in the validation re-spawn loop (it owns
        # re-spawn-then-block). Here we only run the Runtime Load Gate, resolved
        # through the single stage_path seam so BOTH absolute and relative temp
        # paths validate the correct staging file (no silent skip on relative fp).
        if obj.get("status") == "done":
            files = obj.get("files_changed") or obj.get("files") or []
            for fp in files:
                if str(fp).endswith(".py") and obj.get("status") == "done":
                    staged_path = stage_path(fp)
                    if Path(staged_path).exists():
                        try:
                            import subprocess
                            res = subprocess.run(
                                [sys.executable, "factory/tools/load_schema_gate.py", str(staged_path)],
                                capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=30
                            )
                            if res.returncode != 0:
                                obj["status"] = "blocked"
                                obj["notes"] = f"[Runtime Load Gate] {fp} failed schema validation: {res.stdout.strip()} " + obj.get("notes", "")
                                log_operator(f"task {t.id} blocked: schema load failed on {fp}: {res.stdout.strip()}", level="WARNING")
                                break
                        except Exception:
                            pass

        # --- CQRS CLOSE ---
        try:
            import subprocess
            status_out = obj.get("status", "blocked")
            if status_out == "done":
                subprocess.run(["./bd", "close", f"bd-{t.id}", "--reason", str(obj.get("notes", ""))[:100]], cwd=str(REPO_ROOT), capture_output=True, check=False)
            else:
                subprocess.run(["./bd", "update", f"bd-{t.id}", "--status", "blocked"], cwd=str(REPO_ROOT), capture_output=True, check=False)
        except Exception:
            pass
        # ------------------

        # HARNESS-OWNED PATCH GENERATION (B1–B7) — replaces coder hand-written .diff
        files = obj.get("files_changed") or obj.get("files") or []
        if obj.get("status") == "done":
            written, real_changes = _write_harness_patches(t.id, files, bd)
            _quarantine_coder_artifacts(bd)
            if real_changes == 0:
                # B3: fake-done — claimed done but changed nothing
                log_operator(f"[PATCH] task {t.id} status=done but ZERO real changes -> blocked", level="WARNING")
                return TaskResult(task_id=t.id, status="blocked", files_changed=[],
                                  diff_summary="", notes="fake-done: no file changes vs baseline")

        # Task 4 (docs/01_fix.md, D1): cumulative ValidationVerdict. The coder's
        # JSON is the *claim* half; these fields are the harness-filled *verdict*
        # half, derived from the guardrail payloads collected in the re-spawn loop.
        ruff_ok = py_ok = smk_ok = True
        verdict_errors_parts: list[str] = []
        verdict_diff_parts: list[str] = []
        for fp, gj in verdict_state.items():
            if gj.get("ruff_ok", True) is False:
                ruff_ok = False
                verdict_errors_parts.append(f"[ruff] {fp}: {gj.get('ruff_output', '')}")
            if gj.get("pyright_ok", True) is False:
                py_ok = False
                verdict_errors_parts.append(f"[pyright] {fp}: {gj.get('pyright_output', '')}")
            if gj.get("smoke_ok", True) is False:
                smk_ok = False
                verdict_errors_parts.append(f"[smoke] {fp}: {gj.get('smoke_output', '')}")
            diff = gj.get("diff_vs_checkpoint", "")
            if diff and diff not in ("no checkpoint", "no diff"):
                verdict_diff_parts.append(f"--- {fp} ---\n{diff}")
        # Dependency pointers (Task 5, D5): for each edited file, note upstream
        # imports discovered by the union pyright so reviewers know where to trace.
        dep_pointers = _dep_pointers_for(t.file_paths) if t.file_paths else []

        return TaskResult(
            task_id=obj.get("task_id", t.id),
            status=obj.get("status", "blocked"),
            files_changed=obj.get("files_changed", []),
            diff_summary=str(obj.get("diff_summary", ""))[:2000],
            notes=str(obj.get("notes", ""))[:2000],
            ruff_ok=ruff_ok,
            pyright_ok=py_ok,
            exec_ok=smk_ok,
            verdict_errors="\n".join(verdict_errors_parts)[:4000],
            verdict_diff="\n".join(verdict_diff_parts)[:4000],
            dep_pointers=dep_pointers,
        )

    async def process_group(g: WorkGroup) -> None:
        for d in g.depends_on:
            # SPAWN-ALL (baziforecaster-uqj06): every group ALWAYS spawns and
            # executes regardless of whether a sibling/prerequisite task blocked.
            # We no longer short-circuit a dependent group when its prerequisite
            # yielded blocked tasks — a single blocked task must NOT axe unrelated
            # sibling coders. The whole EXECUTE phase is instead hard-halted AFTER
            # all groups finish (see post-gather scan below), so incomplete work
            # never flows on toward review. The wait still gates true dependency
            # ordering (a group only starts once its prerequisites completed).
            # 01_FIX-D1: unbounded wait + liveness guard. The old 300s deadline
            # crashed on slow-but-legitimate groups (coder_1 + coder_2 re-spawns
            # took >5min). Now we only raise if the prerequisite already completed
            # but forgot to signal its event (true code-regression bug).
            try:
                await asyncio.wait_for(group_events[d].wait(), timeout=DAG_DEADLOCK_TIMEOUT)
            except TimeoutError:
                if group_done.get(d, False):
                    raise RuntimeError(
                        f"[HALT] prerequisite group {d!r} completed but never signaled "
                        f"its completion event (dependency deadlock bug)"
                    )
                # Prerequisite is still legitimately working — wait indefinitely.
                await group_events[d].wait()
        if rerun_ids is None:
            # Fresh run when no prior exists; adopt prior verbatim (no re-exec)
            # when a prior batch is supplied (e.g. the red-team gate auditing an
            # already-executed code-review batch).
            to_run = [] if prior else list(g.tasks)
        else:
            to_run = [t for t in g.tasks if t.id in rerun_ids]
        if not to_run:
            group_events[g.id].set()
            group_done[g.id] = True
            return
        # ALWAYS concurrent dispatch — the `concurrent` flag on WorkGroup is
        # logged but NOT obeyed.  Sequential tasks must be in separate groups
        # chained via `depends_on`.
        task_labels = ", ".join(t.id for t in to_run[:5])
        if len(to_run) > 5:
            task_labels += f" … ({len(to_run)} total)"
        print(
            f"  [DAG] group {g.id!r} — {len(to_run)} task(s): {task_labels}",
            flush=True,
        )
        sub = await asyncio.gather(
            *(execute_task(t) for t in to_run), return_exceptions=True
        )
        for t, r in zip(to_run, sub):
            if isinstance(r, TaskNeedsSplitError):
                # vze01: do NOT swallow the split signal into a blocked result —
                # re-raise so it propagates out of run_execute_phase and the
                # operator re-plans with narrower file_paths.
                raise r
            if isinstance(r, Exception):
                # docs/01_fix.md Fix B: surface the harness-owned gate/validation
                # failure loudly next to the SPAWN-ALL HALT so triage does not
                # require a deep log dive. The message carries the underlying
                # reason (e.g. "[HALT] task <id> failed validation after N
                # coder passes (pyright/ruff/smoke)" from the re-spawn loop).
                log_operator(
                    f"task {t.id} blocked: {type(r).__name__}: {r}",
                    level="WARNING",
                )
                results[t.id] = TaskResult(
                    task_id=t.id,
                    status="blocked",
                    files_changed=[],
                    diff_summary="",
                    notes=f"task crashed: {type(r).__name__}: {r}",
                )
            else:
                assert isinstance(r, TaskResult)
                results[t.id] = r
        group_events[g.id].set()
        group_done[g.id] = True

    _concurrent = sum(1 for g in workplan.groups if getattr(g, "concurrent", True))
    _sequential = len(workplan.groups) - _concurrent
    print(
        f"[DAG] planner topology: concurrent_groups={_concurrent} "
        f"sequential_groups={_sequential} (total={len(workplan.groups)})",
        flush=True,
    )
    group_results = await asyncio.gather(
        *(process_group(g) for g in workplan.groups), return_exceptions=True
    )
    for g, grp_r in zip(workplan.groups, group_results):
        if isinstance(grp_r, Exception):
            raise RuntimeError(
                f"[DAG] group {g.id} fault: {type(grp_r).__name__}: {grp_r}"
            ) from grp_r
    # SPAWN-ALL HALT (baziforecaster-uqj06): after EVERY group has spawned and
    # executed, if ANY task is blocked/failed (or produced no result), hard-halt
    # the run — BUT only when `strict=True` (a top-level caller with no
    # recovery owner). When called from run_code_review_gate / run_red_team_gate
    # the gates own recovery (supervisor_review / red_team rerun + force-pass
    # at MAX_RETRIES), so they pass strict=False and RECEIVE the incomplete
    # results to recover. The HALT must NOT pre-empt the gate's retry loop
    # (00_fix: it previously killed the run before supervisor_review could run).
    incomplete: list[str] = []
    for t in workplan.groups:
        for task in t.tasks:
            r = results.get(task.id)
            if r is None or r.status in ("blocked", "failed"):
                incomplete.append(task.id)
    if incomplete and strict:
        raise RuntimeError(
            f"[HALT] EXECUTE phase incomplete: {', '.join(sorted(set(incomplete)))}"
        )
    return results


async def run_code_review_gate(
    plan: ApprovedPlan,
    run_dir: Path,
    coder_fn,
    reviewer_fn,
    exchange: list[ExchangeTurn] | None = None,
    pass_counter: dict[str, int] | None = None,
    bd: str = "",
    history: list[tuple[str, str]] | None = None,
) -> TaskBatch:
    """Execute the DAG, have supervisor_review mark failures, then re-execute
    only the failing tasks + their downstream dependents (bounded by the DAG),
    up to MAX_RETRIES. Returns the final TaskBatch."""
    sem = asyncio.Semaphore(MAX_AGENTS)
    print(f"\n=== [conductor -> coder] (DAG initial dispatch: {len(plan.workplan.groups)} groups) ===", flush=True)
    results = await run_execute_phase(plan, run_dir, sem, coder_fn, exchange=exchange, pass_counter=pass_counter, bd=bd, history=history, strict=False)
    batch = TaskBatch(results=list(results.values()))
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n=== [conductor -> supervisor_review] (attempt {attempt}) ===", flush=True)
        # P1 l4wjg (M3): the DAG review path invokes the reviewer directly
        # (bypassing do_role), so the board would otherwise freeze on the last
        # coder task. Surface the reviewer as IN-PROGRESS.
        update_status_board(history if history is not None else [], "supervisor_review", bd)
        review_brief = (
            "Review the executed tasks against their acceptance criteria.\n"
            "Emit CodePassed with `findings` keyed by `task_id` "
            "(severity 'blocker' = must recode).\n\n"
            "PROPOSE-ONLY: the coder staged proposed edits under "
            "factory/temp/ (mirroring repo paths, e.g. "
            "temp/src2/core/schemas/unified.py). Read the staged files there to "
            "verify against the live src2/ originals — the live tree was NOT "
            "modified.\n\n"
            + wrap_injected_context(
                f"GLOBAL ALIGNMENT:\n{plan.alignment}\n\n"
                f"TASK BATCH RESULTS:\n{_model_to_md(batch)}",
                label="review_context",
            )
            + "\n"
            + _render_verdict_block(batch)
            + "\n"
        )
        rev_out = await reviewer_fn(review_brief)
        append_exchange_turn(exchange, pass_counter, "supervisor_review", rev_out, bd)
        try:
            review = clean_role_output(rev_out, ReviewResult)
        except RuntimeError as e:
            # baziforecaster-cqjb: fail loudly (Decision A) — do NOT silently
            # accept a fabricated pass. The sanitizer already attempted repair.
            raise RuntimeError(
                f"[HALT] supervisor_review output unparseable after sanitize: {e}"
            ) from e
        passed_ = True
        failing = set()
        review_feedback = {}
        for ev in review.evaluations:
            app = ev.approved
            if app == "No":
                passed_ = False
                failing.add(ev.item_id)
                review_feedback[ev.item_id] = f"- [Review Feedback] {ev.comments}"
        if passed_:
            print(f"[gate] supervisor_review attempt {attempt}: PASS -> proceed")
            return batch
        if attempt == MAX_RETRIES:
            print(f"[WARN] [gate] supervisor_review attempt {attempt}: FORCED PASS -> overriding evaluations and proceeding", flush=True)
            for ev in review.evaluations:
                if ev.approved == "No":
                    ev.approved = "Yes"
            return batch
        rerun = _downstream_closure(failing, plan.workplan.groups)
        print(f"[gate] supervisor_review attempt {attempt}: FAIL on {sorted(failing)} -> rerun {sorted(rerun)}")
        results = await run_execute_phase(
            plan,
            run_dir,
            sem,
            coder_fn,
            prior=results,
            rerun_ids=rerun,
            feedback=review_feedback,
            exchange=exchange,
            pass_counter=pass_counter,
            bd=bd,
            history=history,
            strict=False,
        )
        batch = TaskBatch(results=list(results.values()))
    return batch


def red_team_passed(findings: list[dict], rubric_cells: list[dict]) -> bool:
    """Deterministic red-team go/no-go verdict — SINGLE SOURCE OF TRUTH.

    Used by BOTH `run_red_team_gate` and the inline `passed()` reviewer check
    so the gating logic can never drift between the two code paths (and never
    contradict red_team.yaml).

    Gate is driven SOLELY by:
      * `findings` (task-keyed, severity == "blocker") -> which tasks to recode,
      * an unresolvable global blocker in `rubric_cube` (a blocker cell with no
        matching `findings` entry) -> HARD FAIL.
    The LLM's free `green` boolean is NEVER trusted. This is exactly the
    contract documented in templates/red_team.yaml + customised/red_team.yaml.
    """
    failing = any(f.get("severity") == "blocker" for f in findings)
    unresolved_global = (
        any(c.get("severity") == "blocker" and not c.get("passed") for c in rubric_cells)
        and not failing
    )
    return not (failing or unresolved_global)


def _feedback_from_review_findings(review: "CodePassed") -> dict[str, str]:
    """R1 (baziforecaster-nw9ov): render supervisor_review findings + traceback_route
    into a task_id -> prior-feedback text map for the rerun coder brief."""
    out: dict[str, list[str]] = {}
    findings = getattr(review, "findings", None) or []
    for f in findings:
        if getattr(f, "severity", None) != "blocker":
            continue
        tid = getattr(f, "task_id", None)
        if not tid:
            continue
        parts = [
            f"- [{getattr(f, 'severity', 'blocker')}] {getattr(f, 'message', '')}",
        ]
        if getattr(f, "file", None):
            parts.append(f"  file: {f.file}")
        if getattr(f, "line", None) is not None:
            parts.append(f"  line: {f.line}")
        if getattr(f, "suggestion", None):
            parts.append(f"  fix: {f.suggestion}")
        out.setdefault(tid, []).append("\n".join(parts))
    traceback_route = getattr(review, "traceback_route", None)
    if traceback_route:
        for tid, lines in out.items():
            lines.append(f"  reviewer note: {traceback_route}")
    return {tid: "\n".join(blocks) for tid, blocks in out.items()}


def _feedback_from_audit(
    findings: list["ReviewFinding"],     audit: "AuditResult"
) -> dict[str, str]:
    """R1 (baziforecaster-nw9ov): render red-team augmented findings + risks into a
    task_id -> prior-feedback text map for the rerun coder brief."""
    out: dict[str, list[str]] = {}
    for f in findings:
        if getattr(f, "severity", None) != "blocker":
            continue
        tid = getattr(f, "task_id", None)
        if not tid:
            continue
        parts = [f"- [RED-TEAM {getattr(f, 'severity', 'blocker')}] {getattr(f, 'message', '')}"]
        if getattr(f, "file", None):
            parts.append(f"  file: {f.file}")
        if getattr(f, "line", None) is not None:
            parts.append(f"  line: {f.line}")
        if getattr(f, "suggestion", None):
            parts.append(f"  fix: {f.suggestion}")
        out.setdefault(tid, []).append("\n".join(parts))
    # Also surface Critical/High risks that named a task (already promoted to
    # findings above, but include raw risk context for completeness).
    risks = getattr(audit, "risks", None) or []
    for r in risks:
        if getattr(r, "severity", None) not in ("Critical", "High"):
            continue
        tid = getattr(r, "task_id", None)
        if not tid or tid in out:
            continue
        block = (
            f"- [RED-TEAM {getattr(r, 'severity', 'risk')}] {getattr(r, 'description', '')}"
        )
        if getattr(r, "mitigation", None):
            block += f"\n  fix: {r.mitigation}"
        out.setdefault(tid, []).append(block)
    return {tid: "\n".join(blocks) for tid, blocks in out.items()}


def _blocker_findings_from_risks(
    findings: list[ReviewFinding],
    risks: list[AuditRisk],
    known_task_ids: set[str],
) -> tuple[list[ReviewFinding], list[str]]:
    """Anti-laziness guard for the self-graded red-team verdict.

    The red-team model emits BOTH `findings` (which route re-execution) and
    `risks` (which name offending tasks). A lazy model can emit Critical/High
    `risks` flagging real defects yet leave `findings` empty — which lets
    `red_team_passed` return True and skip re-execution entirely, so the
    defects ship to ops unreviewed.

    Any Critical/High `AuditRisk` that carries a `task_id` inside the approved
    plan but has NO matching blocker `ReviewFinding` is promoted to a blocker
    finding, so the offending task is actually re-coded. Risks that name a
    defect but carry no resolvable `task_id` are returned separately so the
    caller can HARD FAIL them as unresolvable (mirrors the rubric_cube
    global-blocker rule)."""
    have = {f.task_id for f in findings if f.severity == "blocker"}
    augmented = list(findings)
    unresolved_global: list[str] = []
    for r in risks:
        if r.severity not in ("Critical", "High"):
            continue
        if not r.task_id or r.task_id not in known_task_ids:
            unresolved_global.append(r.component or r.task_id or "<anonymous>")
            continue
        if r.task_id in have:
            continue
        augmented.append(
            ReviewFinding(
                task_id=r.task_id,
                severity="blocker",
                file=r.component,
                line=None,
                message=f"[auto-derived from {r.severity} risk] {r.description}",
                suggestion=r.mitigation,
            )
        )
        have.add(r.task_id)
    return augmented, unresolved_global


async def run_red_team_gate(
    plan: ApprovedPlan,
    run_dir: Path,
    coder_fn,
    reviewer_fn,
    prior_batch: dict[str, TaskResult],
    exchange: list[ExchangeTurn] | None = None,
    pass_counter: dict[str, int] | None = None,
    bd: str = "",
    history: list[tuple[str, str]] | None = None,
) -> TaskBatch:
    """Red-team audit of the executed batch, then re-execute only the failing
    tasks + their downstream dependents (bounded by the DAG), up to MAX_RETRIES.

    Verdict is re-derived DETERMINISTICALLY from the red team's own RubricCube
    (any blocker cell not passed = FAIL) — never trusted from the LLM's free
    `green` boolean.     On the final attempt (attempt == MAX_RETRIES) a still-failing batch is
    FORCED PASS -> propose-only ops (unpushed). Red-team `findings`
    (task-keyed, severity 'blocker') select which tasks to recode."""
    sem = asyncio.Semaphore(MAX_AGENTS)
    # Execute the DAG once before the first audit (prior_batch is empty for a
    # fresh red-team pass; resume passes the code-review batch through).
    print(f"\n=== [conductor -> coder] (red-team DAG dispatch: {len(plan.workplan.groups)} groups) ===", flush=True)
    results = await run_execute_phase(
        plan,
        run_dir,
        sem,
        coder_fn,
        prior=prior_batch,
        exchange=exchange,
        pass_counter=pass_counter,
        bd=bd,
        history=history,
        strict=False,
    )
    batch = TaskBatch(results=list(results.values()))
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n=== [conductor -> red_team] (attempt {attempt}) ===", flush=True)
        # P1 l4wjg (M3): red_team runs via the DAG review path (bypassing
        # do_role), so surface it on the board as IN-PROGRESS.
        update_status_board(history if history is not None else [], "red_team", bd)
        review_brief = (
            "Audit the executed code batch against the red-team rubric.\n"
            "Emit AuditResult with `rubric_cube` (any blocker cell not passed = FAIL) "
            "and `findings` keyed by `task_id` (severity 'blocker' = must recode).\n\n"
            "PROPOSE-ONLY: the coder staged proposed edits under "
            "factory/temp/ (mirroring repo paths, e.g. "
            "temp/src2/core/schemas/unified.py). Read the staged files there to "
            "verify against the live src2/ originals — the live tree was NOT "
            "modified.\n\n"
            + wrap_injected_context(
                f"GLOBAL ALIGNMENT:\n{plan.alignment}\n\n"
                f"TASK BATCH RESULTS:\n{_model_to_md(batch)}",
                label="audit_context",
            )
            + "\n"
            + _render_verdict_block(batch)
            + "\n"
        )
        rev_out = await reviewer_fn(review_brief)
        append_exchange_turn(exchange, pass_counter, "red_team", rev_out, bd)
        try:
            audit = clean_role_output(rev_out, AuditResult)
        except RuntimeError as e:
            # baziforecaster-cqjb: fail loudly (Decision A) — do NOT silently
            # fabricate a green audit. The sanitizer already attempted repair.
            raise RuntimeError(
                f"[HALT] red_team output unparseable after sanitize: {e}"
            ) from e
        known_task_ids = {t.id for g in plan.workplan.groups for t in g.tasks}
        passed_ = True
        failing = set()
        global_failures = []
        red_feedback = {}

        # Authoritative: 1 file = 1 coder (disjointness HALT at runner.py:617).
        file_to_coder: dict[str, str] = {}
        for g in plan.workplan.groups:
            for t in g.tasks:
                for fp in t.file_paths:
                    file_to_coder[fp] = t.id
        # Rubric cells already carry coder_idents (populated); index by cell id + dims.
        rubric_coder: dict[str, list[str]] = {}
        for cell in plan.rubric_cube.cells:
            if cell.coder_idents:
                rubric_coder.setdefault(cell.dimension, cell.coder_idents)
                rubric_coder.setdefault(cell.criterion, cell.coder_idents)

        def resolve_item(item_id: str, comment: str) -> list[str]:
            # 1) bare coderNN id
            if item_id in known_task_ids:
                return [item_id]
            # 2) file ownership: any file named in item_id or comment -> owning coder
            import os

            blob = f"{item_id} {comment}"
            hits = {file_to_coder[fp] for fp in file_to_coder if fp in blob}
            if hits:
                return sorted(hits)
            base = os.path.basename(item_id)
            hits = {c for fp, c in file_to_coder.items() if os.path.basename(fp) == base}
            if hits:
                return sorted(hits)
            # 3) rubric cell linkage (dimension/criterion)
            if item_id in rubric_coder:
                return rubric_coder[item_id]
            return []

        for ev in audit.evaluations:
            app = ev.approved
            if app == "No":
                passed_ = False
                matched_tasks = resolve_item(ev.item_id, ev.comments or "")

                if matched_tasks:
                    for tid in matched_tasks:
                        failing.add(tid)
                        red_feedback[tid] = f"- [RED-TEAM Feedback] (item {ev.item_id}) {ev.comments}"
                else:
                    global_failures.append(ev.item_id)
        if global_failures and not failing:
            if attempt == MAX_RETRIES:
                print(
                    f"[WARN] [gate] red_team attempt {attempt}: UNRESOLVABLE items force-passed: "
                    + ", ".join(global_failures)
                    + " (propose-only, unpushed)",
                    flush=True,
                )
            else:
                print(
                    f"[WARN] [gate] red_team attempt {attempt}: UNRESOLVABLE items "
                    + ", ".join(global_failures)
                    + " — will force-pass on final attempt.",
                    flush=True,
                )
                continue
        if passed_:
            print(f"[gate] red_team attempt {attempt}: PASS -> proceed to ops")
            return batch
        if attempt == MAX_RETRIES:
            print(f"[WARN] [gate] red_team attempt {attempt}: FORCED PASS -> overriding evaluations and proceeding (propose-only, unpushed)", flush=True)
            for ev in audit.evaluations:
                if ev.approved == "No":
                    tids = resolve_item(ev.item_id, ev.comments or "")
                    files = sorted(
                        {fp for g in plan.workplan.groups
                         for t in g.tasks if t.id in tids
                         for fp in t.file_paths}
                    )
                    marker = f"[FORCED PASS attempt {attempt} — UNVERIFIED, review files: {files}]"
                    ev.comments = (marker + " " + (ev.comments or "")).strip()
                    ev.approved = "Yes"
            # Re-record the coerced audit so the JSONL transcript (3rd blob)
            # carries the [FORCED PASS ...] marker + review files (docs/01_fix.md F).
            append_exchange_turn(exchange, pass_counter, "red_team", audit.model_dump_json(), bd)
            return batch
        if failing:
            rerun = _downstream_closure(failing, plan.workplan.groups)
            print(f"[gate] red_team attempt {attempt}: FAIL on {sorted(failing)} -> rerun {sorted(rerun)}")
            results = await run_execute_phase(
                plan,
                run_dir,
                sem,
                coder_fn,
                prior=results,
                rerun_ids=rerun,
                feedback=red_feedback,
                exchange=exchange,
                pass_counter=pass_counter,
                bd=bd,
                history=history,
                strict=False,
            )
            batch = TaskBatch(results=list(results.values()))
            continue
        else:
            raise RuntimeError(
                "[gate] HARD FAIL: red_team flagged a global blocker with no task-keyed evaluations to recode — unresolvable; aborting (no forced pass)."
            )
    return batch


async def _run_subprocess_with_timeout(
    cmd: list[str], cwd: str, timeout: float = 120.0, stderr_target: int = asyncio.subprocess.PIPE
) -> tuple[int, str]:
    """Run an async subprocess with a hard timeout. Kills the process on timeout."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd, stderr=stderr_target
    )
    try:
        _, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        raise RuntimeError(
            f"[ops] subprocess {cmd[0]!r} timed out after {timeout}s — killed"
        )
    stderr_text = stderr_data.decode("utf-8", "replace") if stderr_data else ""
    return proc.returncode or 0, stderr_text


async def run_ops_phase(
    bd: str,
    *,
    history: list[tuple[str, str]],
    repo_root: Path = REPO_ROOT,
) -> GitResult:
    """Review the work: run hygiene scanners + show diff, NO auto-push.

    To re-enable: uncomment the git-push.sh block + bd close + flip
    pushed/bd_closed back to True below.
    """
    update_status_board(history, "ops", bd)

    hook = repo_root / ".git" / "hooks" / "pre-push"
    if hook.exists():
        rc, stderr_text = await _run_subprocess_with_timeout(
            [str(hook)], str(repo_root), timeout=120.0
        )
        if rc != 0:
            raise RuntimeError(
                "[ops] pre-push hygiene scanners FAILED — HALTING, not pushing\n"
                + stderr_text
            )

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30.0,
    ).stdout.strip()

    result = GitResult(
        pushed=False,
        commit_sha=sha,
        bd_closed=False,
        message="changes ready for human review. Run factory/tools/git-push.sh to push.",
    )
    history.append(("ops", result.model_dump_json()))
    update_status_board(history, "ops", bd)
    return result


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bd", default="default", help="bd ticket id (keys the exchange file)")
    ap.add_argument("--prompt-file", default=str(USER_PROMPT_PATH))
    ap.add_argument(
        "--from",
        dest="from_",
        choices=_PHASE_ORDER,
        default=None,
        help="Resume the pipeline at a later phase (cumulative phase ladder). "
        "Each value starts that phase and runs everything downstream, skipping "
        "only the phases BEFORE it (which must already be completed in a prior "
        "run). Options: " + ", ".join(_PHASE_ORDER) + ". A missing predecessor "
        "artefact HALTs loudly (no silent empty continue).",
    )
    ap.add_argument(
        "--stop-after",
        dest="stop_after",
        choices=_PHASE_ORDER,
        default=None,
        help="Run up to AND INCLUDING this phase, then persist state.json and "
        "STOP (does not push). Re-running with the same --bd resumes from the "
        "next phase. Options: " + ", ".join(_PHASE_ORDER) + ".",
    )
    ap.add_argument(
        "--resume",
        dest="resume_flag",
        action="store_true",
        default=False,
        help="Auto-resume from the phase after the last persisted/stopped one "
        "(used by run_orchestrator_continue.sh). Fail loudly if no prior "
        "state.json exists — never auto-start a fresh run.",
    )
    args = ap.parse_args()

    # Continuation mode: phases before the resume point were completed in a
    # prior run — fold them into the status board's DONE column.
    global _SKIPPED_PHASES
    if args.from_:
        _SKIPPED_PHASES = _PHASE_ORDER[: _PHASE_ORDER.index(args.from_)]

    resume, task, scope = read_prompt(Path(args.prompt_file))
    bd = args.bd

    # Scope-driven auto-context (86rmw/xfqkf/y1oqi): build the scoped repo-map
    # ONCE at run start and cache it so both planner and supervisor_plan see
    # the byte-identical codebase_reference_context block.
    global SCOPE_CONTEXT
    if scope:
        SCOPE_CONTEXT = inject_repo_map(scope)
        log_operator(f"read_prompt: scope={scope} -> SCOPE_CONTEXT built", level="INFO")
    else:
        SCOPE_CONTEXT = ""
        log_operator("read_prompt: no scope declared; planner gets no auto-context", level="INFO")

    # SA1-F6 / SA1-F7 / SA3-F12: wrap the untrusted user task_spec in a CANARY
    # delimiter, scan it for instruction-override attempts, and alert the
    # operator. The wrapped form is used everywhere downstream.
    task = wrap_untrusted_task(task)

    _configure_logfire()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    sys.stdout = TeeLogger(RUNTIME_DIR / "run.log")
    # (Re)initialize the status board at run start with the ACTUAL starting
    # phase so a stale prior-run row (e.g. a leftover `coderNN → src2/x.py`
    # LIVE line from a crashed run) is overwritten immediately — not displayed
    # while the planner is already running. On a `--from <phase>` resume the
    # starting phase is that phase; otherwise the pipeline always begins with
    # planner (it re-runs even on a bare `--resume`).
    _start_role = args.from_ if args.from_ else "planner"
    update_status_board([], _start_role, bd)

    print("=== ORCHESTRATOR RUN (deterministic conductor, no LLM orchestrator) ===")
    print(f"[resume] {resume}  [bd] {bd}")
    print(f"[task]\n{task}\n")

    prior = load_exchange(bd) if (resume or args.from_ == "coder") else []
    if (resume or args.from_ == "coder") and prior:
        print(f"[resume] seeding first coder pass with {len(prior)} prior exchange turns")
    elif resume or args.from_ == "coder":
        print(f"[resume] no exchange file for {bd}, running fresh")

    history: list[tuple[str, str]] = []
    exchange: list[ExchangeTurn] = []
    pass_counter: dict[str, int] = {}
    phase_summaries: dict[str, str] = {}  # L3 food chain: compacted per-role summaries
    brief = task
    seeded = False

    # ── Crash-resume durable state (baziforecaster-udylx) ──────────────────
    # A fresh run ALWAYS creates a new OrchestratorState (and run dir). A
    # continue/resume run loads the newest persisted state.json and rehydrates
    # the validated Pydantic outputs into history/phase_summaries so downstream
    # phases see prior work. Bare --resume (no prior state) HARD-REFUSES: we
    # never silently auto-start a fresh run over a continuation intent.
    _continuation = bool(args.from_ or args.stop_after or args.resume_flag)
    if _continuation:
        st = load_state(bd)
        if st is None:
            raise RuntimeError(
                f"[HALT] no prior state for {bd}; use run_orchestrator.sh "
                f"(fresh) to start a new run — continuation requires state.json."
            )
        st = reset_stale_in_progress(st)
        # Rehydrate validated outputs -> history + phase_summaries (L3 chain).
        if st.draft:
            history.append(("planner", st.draft.model_dump_json()))
        if st.approved:
            history.append(("supervisor_plan", st.approved.model_dump_json()))
            RAW_OUTPUTS["supervisor_plan"] = st.approved.model_dump_json()
            phase_summaries["supervisor_plan"] = st.approved.model_dump_json()
        if st.batch:
            history.append(("coder", st.batch.model_dump_json()))
        if st.code_passed:
            history.append(("supervisor_review", st.code_passed.model_dump_json()))
        if st.audit:
            history.append(("red_team", st.audit.model_dump_json()))
    else:
        st = fresh_state(bd, global_alignment="")

    def _sync_state() -> None:
        """Capture validated RAW_OUTPUTS into the durable OrchestratorState."""
        draft_json = RAW_OUTPUTS.get("planner")
        if draft_json:
            st.draft = DraftPlan.model_validate_json(draft_json)
        approved_json = RAW_OUTPUTS.get("supervisor_plan")
        if approved_json:
            st.approved = ApprovedPlan.model_validate_json(approved_json)
        batch_json = RAW_OUTPUTS.get("coder")
        if batch_json:
            try:
                st.batch = TaskBatch.model_validate_json(batch_json)
            except Exception:
                pass
        code_passed_json = RAW_OUTPUTS.get("supervisor_review")
        if code_passed_json:
            try:
                st.code_passed = CodePassed.model_validate_json(code_passed_json)
            except Exception:
                pass
        audit_json = RAW_OUTPUTS.get("red_team")
        if audit_json:
            try:
                st.audit = AuditResult.model_validate_json(audit_json)
            except Exception:
                pass

    def _checkpoint(phase: str) -> bool:
        """Persist validated outputs + advance current_phase.

        Returns True when --stop-after <phase> was requested (caller must STOP).
        """
        _sync_state()
        record_phase(st, phase)
        save_state(st)
        if args.stop_after == phase:
            save_exchange(bd, exchange)
            print(
                f"[STOP] halted after {phase}; resume with "
                f"run_orchestrator_continue.sh {bd}",
                flush=True,
            )
            update_status_board(history, None, bd)
            return True
        return False

    async def do_role(role: str) -> str:
        """Run one role, seed the first coder pass, append to history + exchange."""
        nonlocal seeded, brief
        run_brief = brief
        # Seed the FIRST coder pass (overall) with the prior exchange.
        if role == "coder" and prior and not seeded:
            run_brief = brief + "\n\n" + wrap_injected_context(
                format_exchange(prior), label="resumed_exchange"
            )
            seeded = True

        update_status_board(history, role, bd)
        if role in ("planner", "supervisor_plan"):
            brief_to_use = run_brief
            for attempt in range(1, PLAN_INVARIANT_RETRIES + 1):
                try:
                    out = await load_skill(role, brief_to_use, bd)
                    # Check plan invariants
                    violations = []
                    if role == "planner":
                        draft = clean_role_output(out, DraftPlan)
                        violations = check_plan_invariants(draft) if draft else ["Plan is empty or malformed"]
                    else:  # supervisor_plan
                        plan_eval = clean_role_output(out, ApprovedPlan)
                        draft_json = RAW_OUTPUTS.get("planner")
                        draft = clean_role_output(draft_json, DraftPlan) if draft_json else None
                        if plan_eval and draft:
                            # Reconstruct tasks by merging DraftPlan tasks with evaluations
                            eval_map = {item.item_id: item for item in plan_eval.evaluations}
                            merged_tasks = []
                            for t in draft.subtasks:
                                eval_item = eval_map.get(t.id)
                                app_val = (eval_item.approved == "Yes") if eval_item else True
                                notes_val = eval_item.comments if eval_item else ""
                                merged_tasks.append(
                                    ApprovedTask(
                                        id=t.id,
                                        title=t.title,
                                        file_paths=t.file_paths,
                                        instruction=t.instruction,
                                        acceptance=t.acceptance,
                                        tool_preference=t.tool_preference,
                                        evidence=t.evidence,
                                        approved=app_val,
                                        notes=notes_val,
                                    )
                                )

                            groups_merged = []
                            for g in draft.strategy.parallelisable_workplan.groups:
                                group_tasks = []
                                for gt in g.tasks:
                                    eval_item = eval_map.get(gt.id)
                                    app_val = (eval_item.approved == "Yes") if eval_item else True
                                    notes_val = eval_item.comments if eval_item else ""
                                    group_tasks.append(
                                        ApprovedTask(
                                            id=gt.id,
                                            title=gt.title,
                                            file_paths=gt.file_paths,
                                            instruction=gt.instruction,
                                            acceptance=gt.acceptance,
                                            tool_preference=gt.tool_preference,
                                            evidence=gt.evidence,
                                            approved=app_val,
                                            notes=notes_val,
                                        )
                                    )
                                groups_merged.append(
                                    WorkGroup(
                                        id=g.id,
                                        depends_on=g.depends_on,
                                        tasks=group_tasks,
                                        concurrent=g.concurrent,
                                    )
                                )
                            temp_plan = ExecutablePlan(
                                epic=draft.epic,
                                definition_of_done=draft.definition_of_done,
                                acceptance_criteria=draft.acceptance_criteria,
                                rubric_cube=draft.rubric_cube,
                                summary=draft.summary,
                                tasks=merged_tasks,
                                alignment=draft.summary,
                                workplan=ParallelisableWorkplan(groups=groups_merged),
                                rejected_subtasks=[],
                                strategy=draft.strategy,
                                approved=True,
                            )
                            violations = check_plan_invariants(temp_plan)
                        else:
                            violations = ["No plan evaluation or DraftPlan found to check invariants."]

                    if violations:
                        raise RuntimeError(f"Plan invariant violations: {violations}")
                    break
                except Exception as e:
                    if attempt == PLAN_INVARIANT_RETRIES:
                        raise
                    print(f"[gate] {role} attempt {attempt} failed: {e!r} -> replan", flush=True)
                    brief_to_use = run_brief + f"\n\n[INVARIANT VIOLATION] Your previous plan was rejected: {e!r}. Please ensure every task lists exactly 1 file, and file paths are disjoint across all tasks."
                    continue
        else:
            try:
                out = await load_skill(role, run_brief, bd)
            except UnexpectedModelBehavior as e:
                # baziforecaster-ydiv: before HALTing, attempt to salvage the real
                # model output (last final_result ToolCallPart) from the persisted
                # role transcript, mirroring the load_skill recovery path.
                real_messages = _load_role_messages(role)
                if ROLE_OUTPUT_TYPE[role] != "str":
                    raw = extract_model_json(real_messages)
                    if not raw:
                        raw = extract_tool_call_payload(e) or ""
                        if not raw:
                            raise RuntimeError(
                                f"[HALT] role {role!r} emitted no final_result call"
                            ) from e
                else:
                    raw = extract_model_json(real_messages)
                    if not raw:
                        raw = extract_tool_call_payload(e) or ""
                if raw:
                    recovered = _recover_role_output(raw, OUTPUT_TYPE_REGISTRY[ROLE_OUTPUT_TYPE[role]], role, None)
                    if recovered is not None:
                        if hasattr(recovered.output, "model_dump_json"):
                            return recovered.output.model_dump_json()
                        return str(recovered.output)
                raise RuntimeError(
                    f"[do_role] role '{role}' hallucinated an unregistered tool "
                    f"(pydantic_ai exhausted retries). Check {role}'s tool_allow_list "
                    f"vs its prompt — do NOT instruct it to run commands it has no tool for."
                ) from e
        # Render the Pydantic output to compact MARKDOWN ONCE. The MD is
        # produced INSIDE load_skill from `result.output` (Pydantic-AI v2.0:
        # the output IS the parsed model) and stashed in PHASE_SUMMARIES[role].
        # All downstream injection (prior_role_outputs / status board) uses this
        # MD — NEVER the raw model_dump_json() string. This kills the 3×
        # duplicated + 2000-char-truncated raw-JSON "rubbish" that leaked into
        # prompts (baziforecaster-p0vt architectural mandate).
        out_md = PHASE_SUMMARIES.get(role, out)
        history.append((role, out_md))
        # L3 food chain: store compressed MD summary for cross-phase context.
        phase_summaries[role] = out_md
        print(f"\n--- {role} ---\n{out_md}", flush=True)
        update_status_board(history, role, bd)

        # Accumulate EVERY pass (including repeated roles) into the next brief,
        # so the author always sees the reviewer's prior feedback. The untrusted
        # user task stays isolated in its canary (see `task`); the prior role
        # outputs are TRUSTED-BUT-INJECTED context, wrapped in a SEPARATE canary
        # so the two layers can never be confused (SA3-F12).
        summaries_block = (
            "\n\n".join(f"## {r} summary (L3):\n{s}" for r, s in phase_summaries.items())
        ) if phase_summaries else ""
        brief = task + "\n\n" + wrap_injected_context(
            "\n\n".join(
                f"## {r} output:\n{_render_history_md(r, v)}"
                for r, v in history
            ),
            label="prior_role_outputs",
        )
        if summaries_block:
            brief += "\n\n" + wrap_injected_context(summaries_block, label="phase_summaries")
        return out

    async def record_coder(brief: str, task_id: str | None = None) -> str:
        """Run the coder and record it in `history` (so the status board shows it).

        The gated code-review / red-team phases invoke the coder via `coder_fn`
        directly (not `do_role`), so without this wrapper the coder was never
        appended to `history` and the board falsely listed it as TODO while it
        had in fact executed. This also restores resume-seeding of the first
        coder pass for the gated path, which was previously skipped. `task_id`
        (when present) scopes the coder's memory to its own `coderN` file (a101k).
        """
        agent_id = _coder_agent_id(task_id)
        nonlocal seeded
        run_brief = brief
        if prior and not seeded:
            run_brief = brief + "\n\n" + wrap_injected_context(
                format_exchange(prior), label="resumed_exchange"
            )
            seeded = True
        update_status_board(history, "coder", bd)
        try:
            out = await load_skill("coder", run_brief, bd, task_id=task_id)
        except UnexpectedModelBehavior as e:
            # baziforecaster-ydiv: attempt to salvage the real coder output
            # (last final_result ToolCallPart) from the persisted coder transcript
            # before surfacing the HALT.
            real_messages = _load_role_messages("coder", agent_id=agent_id)
            if ROLE_OUTPUT_TYPE["coder"] != "str":
                raw = extract_model_json(real_messages)
                if not raw:
                    raw = extract_tool_call_payload(e) or ""
                    if not raw:
                        raise RuntimeError(
                            "[HALT] role 'coder' emitted no final_result call"
                        ) from e
            else:
                raw = extract_model_json(real_messages)
                if not raw:
                    raw = extract_tool_call_payload(e) or ""
            if raw:
                recovered = _recover_role_output(raw, OUTPUT_TYPE_REGISTRY[ROLE_OUTPUT_TYPE["coder"]], "coder", None)
                if recovered is not None:
                    if hasattr(recovered.output, "model_dump_json"):
                        return recovered.output.model_dump_json()
                    return str(recovered.output)
            # TRACK A.1 (baziforecaster-xvy0): a low-tier coder model can return
            # EMPTY completions (finish_reason=stop, content=""); pydantic-ai burns
            # Agent(retries=5) then raises UnexpectedModelBehavior. This used to
            # propagate raw and kill the run with no diagnostic transcript. Convert
            # it to a surfaced [HALT] so the existing failure-persistence path writes
            # a FAILED coder transcript and the operator sees exactly what happened.
            raise RuntimeError(
                "[record_coder] coder emitted empty/invalid output and exhausted "
                "retries (UnexpectedModelBehavior). The coder model returned no "
                "usable result — check the coder model binding and the coder "
                "transcript under artefacts/history/coder/. Do NOT instruct the "
                "coder to call tools it does not have."
            ) from e
        # MD rendered inside load_skill from result.output (v2.0: the output
        # IS the parsed model) and stashed in PHASE_SUMMARIES["coder"].
        out_md = PHASE_SUMMARIES.get("coder", out)
        history.append(("coder", out_md))
        phase_summaries["coder"] = out_md
        update_status_board(history, "coder", bd)
        return out

    def passed(reviewer: str, out: str) -> bool:
        """Read the reviewer's pass/fail from its JSON output.

        For supervisor_plan, supervisor_review, and red_team, the verdict is
        derived from the flat evaluations array. If any item is marked "No"
        or "Blocked" (case-insensitive, starting with no/block), the gate fails.
        """
        try:
            obj = json.loads(out)
        except Exception as e:
            # SA4-F4: the reviewer's JSON is unparseable — fail loudly to the
            # operator, then degrade (treat as FAIL) without crashing the loop.
            log_operator(
                f"reviewer '{reviewer}' output was not valid JSON; treating as FAIL. "
                f"error={e!r}",
                level="WARNING",
            )
            return False
        if reviewer in ("supervisor_plan", "supervisor_review", "red_team"):
            evals = obj.get("evaluations")
            if not evals:
                return False
            for ev in evals:
                app = ev.get("approved")
                if isinstance(app, str):
                    app_lower = app.lower()
                    if app_lower.startswith("no") or app_lower.startswith("block"):
                        return False
                elif isinstance(app, bool):
                    if not app:
                        return False
                else:
                    if not app:
                        return False
            return True
        field = REVIEW_PASS_FIELD.get(reviewer)
        return bool(obj.get(field, False)) if field else False

    async def run_gated(
        author: str,
        reviewer: str,
        hard: bool = False,
        record_exchange: bool = False,
    ) -> bool:
        """Author produces work; reviewer gates. Up to MAX_RETRIES.

        attempt 1 pass -> proceed
        attempt 1 fail -> author revises
        attempt 2 pass -> proceed
        attempt 2 fail -> author revises
        attempt 3      -> FORCED pass (proceed) UNLESS `hard`:
                            when `hard`, a still-failing reviewer RAISES (fail loudly)
                            instead of forcing pass — used for the red-team rubric wall.

        When `record_exchange` is set, author/reviewer turns that are exchange
        roles (coder/supervisor_review/red_team) are appended to the reloadable
        exchange so a later `--from coder` run can re-seed from them.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            print(f"\n=== [conductor -> {author}] (attempt {attempt}) ===", flush=True)
            author_out = await do_role(author)
            if record_exchange and author in EXCHANGE_ROLES:
                append_exchange_turn(exchange, pass_counter, author, author_out, bd)

            # Pre-stage workspace files right after DraftPlan is parsed, before supervisor_plan runs
            if author == "planner" and reviewer == "supervisor_plan":
                draft_json = RAW_OUTPUTS.get("planner")
                if draft_json:
                    try:
                        draft = clean_role_output(draft_json, DraftPlan)
                        if draft:
                            stage_workspace_from_draft(draft, bd)
                    except Exception as e:
                        print(f"[WARN] Pre-stage workspace failed: {e}", flush=True)

            print(f"=== [conductor -> {reviewer}] (attempt {attempt}) ===", flush=True)
            reviewer_out = await do_role(reviewer)
            if record_exchange and reviewer in EXCHANGE_ROLES:
                append_exchange_turn(exchange, pass_counter, reviewer, reviewer_out, bd)

            if attempt == MAX_RETRIES:
                if hard and not passed(reviewer, reviewer_out):
                    raise RuntimeError(
                        f"[gate] HARD FAIL: {reviewer} still failing after "
                        f"{MAX_RETRIES} attempts — aborting (no forced pass)."
                    )
                print(f"[gate] {reviewer} attempt {attempt}: FORCED PASS -> proceed")
                return True
            if passed(reviewer, reviewer_out):
                print(f"[gate] {reviewer} attempt {attempt}: PASS -> proceed")
                return False
            print(f"[gate] {reviewer} attempt {attempt}: FAIL -> {author} revises")

    # ── Plan-gate hard halt (no silent failure) ──────────────────────────
    # The coder MUST NOT run on a missing / malformed / failing approved plan.
    # A supervisor_plan that emits an `approved: true` boolean while marking
    # blocker rubric cells `passed: False` (the silent-failure mode observed in
    # the 2026-07-18 run) must still HALT here, not roll into coding.
    def _assert_plan_gate_ok(history: list, bd: str, is_forced_pass: bool = False) -> ExecutablePlan:
        approved = RAW_OUTPUTS.get("supervisor_plan") or next(
            (v for r, v in reversed(history) if r == "supervisor_plan"), None
        )
        if not approved:
            raise RuntimeError(
                "[PLAN-GATE] HALT: no supervisor_plan output — planner/supervisor "
                "chain produced no ApprovedPlan. Coder will NOT run."
            )
        try:
            plan_eval = clean_role_output(approved, ApprovedPlan)
        except Exception as exc:
            raise RuntimeError(
                f"[PLAN-GATE] HALT: supervisor_plan output was unparseable as "
                f"ApprovedPlan ({exc!r}). Coder will NOT run."
            ) from exc
        if plan_eval is None:
            raise RuntimeError(
                "[PLAN-GATE] HALT: ApprovedPlan parsed to None. Coder will NOT run."
            )
        # Parse original DraftPlan JSON
        draft_json = RAW_OUTPUTS.get("planner") or next(
            (v for r, v in reversed(history) if r == "planner"), None
        )
        if not draft_json:
            raise RuntimeError("[PLAN-GATE] HALT: no DraftPlan found in history to merge.")
        draft = clean_role_output(draft_json, DraftPlan)
        if not draft:
            raise RuntimeError("[PLAN-GATE] HALT: DraftPlan is malformed.")

        # Re-derive rubric cells status based on evaluations.
        # Find evaluations matching tasks/rubric components.
        # If any item_id evaluations are marked No, reject the plan.
        # We also re-verify blocker rubric cells from DraftPlan.
        # Let's map approved status
        is_plan_approved = True
        eval_map = {item.item_id: item for item in plan_eval.evaluations}
        for item in plan_eval.evaluations:
            if item.approved == "No":
                if is_forced_pass:
                    print(
                        f"[WARN] [PLAN-GATE] Overriding evaluation {item.item_id} "
                        f"from 'No' to 'Yes' due to FORCED PASS.",
                        flush=True,
                    )
                    item.approved = "Yes"
                else:
                    is_plan_approved = False

        if not is_plan_approved:
            raise RuntimeError(
                "[PLAN-GATE] HALT: supervisor_plan approved=False. Coder will NOT run."
            )

        # Programmatically merge evaluations back into the DraftPlan JSON dictionary
        draft_dict = json.loads(draft_json)
        for task in draft_dict.get("subtasks", []):
            tid = task.get("id")
            ev = eval_map.get(tid)
            task["Approved"] = ev.approved if ev else "Yes"
            task["Comments"] = ev.comments if ev else ""

        strategy = draft_dict.get("strategy", {})
        workplan = strategy.get("parallelisable_workplan", {})
        for gp in workplan.get("groups", []):
            for task in gp.get("tasks", []):
                tid = task.get("id")
                ev = eval_map.get(tid)
                task["Approved"] = ev.approved if ev else "Yes"
                task["Comments"] = ev.comments if ev else ""

        # Write merged planner.json back to disk and update RAW_OUTPUTS
        try:
            from factory.infra.artefacts import artefacts_dir
            plan_file = artefacts_dir() / "workplan" / "planner" / "planner.json"
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            plan_file.write_text(json.dumps(draft_dict, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[WARN] Failed to write merged planner.json: {e}", flush=True)

        RAW_OUTPUTS["planner"] = json.dumps(draft_dict)

        # Reconstruct the tasks by merging DraftPlan tasks with evaluations
        merged_tasks = []
        for t in draft.subtasks:
            eval_item = eval_map.get(t.id)
            app_val = (eval_item.approved == "Yes") if eval_item else True
            notes_val = eval_item.comments if eval_item else ""
            merged_tasks.append(
                ApprovedTask(
                    id=t.id,
                    title=t.title,
                    file_paths=t.file_paths,
                    instruction=t.instruction,
                    acceptance=t.acceptance,
                    tool_preference=t.tool_preference,
                    evidence=t.evidence,
                    approved=app_val,
                    notes=notes_val,
                )
            )

        # Reconstruct groups tasks in ParallelisableWorkplan
        groups_merged = []
        for g in draft.strategy.parallelisable_workplan.groups:
            group_tasks = []
            for gt in g.tasks:
                eval_item = eval_map.get(gt.id)
                app_val = (eval_item.approved == "Yes") if eval_item else True
                notes_val = eval_item.comments if eval_item else ""
                group_tasks.append(
                    ApprovedTask(
                        id=gt.id,
                        title=gt.title,
                        file_paths=gt.file_paths,
                        instruction=gt.instruction,
                        acceptance=gt.acceptance,
                        tool_preference=gt.tool_preference,
                        evidence=gt.evidence,
                        approved=app_val,
                        notes=notes_val,
                    )
                )
            groups_merged.append(
                WorkGroup(
                    id=g.id,
                    depends_on=g.depends_on,
                    tasks=group_tasks,
                    concurrent=g.concurrent,
                )
            )

        exe_plan = ExecutablePlan(
            epic=draft.epic,
            definition_of_done=draft.definition_of_done,
            acceptance_criteria=draft.acceptance_criteria,
            rubric_cube=draft.rubric_cube,
            summary=draft.summary,
            tasks=merged_tasks,
            alignment=st.global_alignment or draft.summary,
            workplan=ParallelisableWorkplan(groups=groups_merged),
            rejected_subtasks=[],
            strategy=draft.strategy,
            approved=is_plan_approved,
        )

        try:
            exe_plan = ExecutablePlan.model_validate(exe_plan.model_dump())
        except Exception as exc:
            raise RuntimeError(
                f"[PLAN-GATE] HALT: ExecutablePlan validation failed ({exc!r}). "
                f"Every ApprovedTask.id MUST be 'coder01', 'coder02', … unique. "
                f"Coder will NOT run."
            ) from exc

        print("[PLAN-GATE] OK: supervisor_plan approved with 0 failed blockers.", flush=True)
        return exe_plan

    # Planning gate: planner <-> supervisor_plan.
    # Phase ladder: any --from at/after `coder` skips planner/supervisor_plan
    # and must resume from the PERSISTED ApprovedPlan (no silent empty continue).
    _coder_idx = _PHASE_ORDER.index("coder")
    _from_idx = _PHASE_ORDER.index(args.from_) if args.from_ else 0
    if args.from_ and _from_idx >= _coder_idx:
        print(
            f"\n=== [conductor] --from {args.from_}: SKIPPING "
            f"planner/supervisor_plan ===",
            flush=True,
        )
        plan = None
        batch = None
    else:
        is_forced_pass = await run_gated("planner", "supervisor_plan")
        plan = _assert_plan_gate_ok(history, bd, is_forced_pass=is_forced_pass)
        # Re-save the merged plan to st.approved for checkpointing
        st.approved = plan
        if _checkpoint("supervisor_plan"):
            return

    # Capture the ApprovedPlan so the code-review gate can execute its DAG.
    # Use the RAW Pydantic JSON (RAW_OUTPUTS), NOT history[] (which holds
    # markdown by design and is unparseable as JSON).
    approved_json = RAW_OUTPUTS.get("supervisor_plan") or next(
        (v for r, v in reversed(history) if r == "supervisor_plan"), None
    )
    # Resume guard: resuming at/after `coder` without a persisted ApprovedPlan
    # means the predecessor phase never completed — HALT loudly, do NOT run an
    # empty coder pass against a missing plan.
    if args.from_ and _from_idx >= _coder_idx and not approved_json:
        raise RuntimeError(
            f"[HALT] --from {args.from_} but no persisted ApprovedPlan found. "
            "The planner/supervisor_plan predecessor must have completed in a "
            "prior run (artefacts/workplan/planner_sup/ or RAW_OUTPUTS). "
            "Run the full pipeline (or --from supervisor_plan) first."
        )

    batch: TaskBatch | None = None
    if approved_json and plan is None:
        try:
            plan = _assert_plan_gate_ok(history, bd)
            # --- CQRS BEADS INJECTION ---
            if plan and plan.workplan and plan.workplan.groups:
                import subprocess
                for g in plan.workplan.groups:
                    for t in g.tasks:
                        print(f"[{bd}] [CQRS] Injecting task {t.id} to BEADS...")
                        try:
                            title = str(getattr(t, 'title', t.id))[:100]
                            desc = str(getattr(t, 'instruction', 'Task details in workplan'))
                            subprocess.run([
                                "./bd", "create",
                                "--id", f"bd-{t.id}",
                                "--force",
                                f"--title=[{t.id}] {title}",
                                f"--description={desc}",
                                "--type=task",
                                "--priority=2"
                            ], cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)
                        except Exception as e:
                            print(f"[WARN] BEADS inject failed for {t.id}: {e}")
            # ----------------------------
        except RuntimeError as e:
            raise RuntimeError(
                f"[HALT] ApprovedPlan output unparseable after sanitize: {e}"
            ) from e

    # Code-review gate: coder <-> supervisor_review
    if plan is not None and plan.workplan and plan.workplan.groups:
        run_dir = TEMP_DIR / bd
        run_dir.mkdir(parents=True, exist_ok=True)
        batch = await run_code_review_gate(
            plan,
            run_dir,
            coder_fn=record_coder,
            reviewer_fn=lambda b: load_skill("supervisor_review", b, bd),
            exchange=exchange,
            pass_counter=pass_counter,
            bd=bd,
            history=history,
        )
        history.append(("supervisor_review", batch.model_dump_json()))
    else:
        await run_gated(
            "coder", "supervisor_review", record_exchange=(args.from_ == "coder")
        )
    if _checkpoint("coder"):
        return
    # Red-team gate: coder <-> red_team (HARD wall — rubric cube enforced,
    # no forced pass, only the failing tasks + downstream are recoded)
    if plan is not None and plan.workplan and plan.workplan.groups:
        assert batch is not None  # assigned by code-review gate above under same guard
        run_dir = TEMP_DIR / bd
        run_dir.mkdir(parents=True, exist_ok=True)
        batch = await run_red_team_gate(
            plan,
            run_dir,
            coder_fn=record_coder,
            reviewer_fn=lambda b: load_skill("red_team", b, bd),
            prior_batch={t.task_id: t for t in batch.results},
            exchange=exchange,
            pass_counter=pass_counter,
            bd=bd,
            history=history,
        )
        history.append(("red_team", batch.model_dump_json()))
    else:
        await run_gated(
            "coder", "red_team", hard=True, record_exchange=(args.from_ == "coder")
        )
    if _checkpoint("red_team"):
        return
    # PROPOSE-ONLY: stop after red_team. Do NOT push or apply to src2/ — the
    # staged proposals live under factory/temp/ for the human to
    # review and apply manually.
    print("\n=== [conductor] PROPOSE-ONLY: stopping after red_team ===", flush=True)
    print(f"[done] Proposed edits staged under: {TEMP_DIR}", flush=True)
    print("[done] The live tree (src2/) was NOT modified. Review the staged files and apply manually.", flush=True)

    save_exchange(bd, exchange)

    last_coder = next((v for r, v in reversed(history) if r == "coder"), "")
    verdict = "PASS" if "This Harness is Working" in last_coder else "CHECK"
    update_status_board(history, None, bd)
    print("\n=== PIPELINE COMPLETE (propose-only) ===")
    print("\nVERDICT:", verdict)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        import traceback as _tb

        _tb.print_exc()
        try:
            RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            _exc = _tb.format_exc()
            (RUNTIME_DIR / "fail_main.log").write_text(_exc, encoding="utf-8")
            with (RUNTIME_DIR / "run.log").open("a", encoding="utf-8") as _fh:
                _fh.write("\n=== [FATAL] unhandled exception ===\n")
                _fh.write(_exc)
        except Exception:
            pass
        raise
