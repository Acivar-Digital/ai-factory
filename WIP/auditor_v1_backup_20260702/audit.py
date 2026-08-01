"""
Red-Team Fiduciary Audit Agent
================================
Primary config: edit auditor.yaml in this directory, then run:

    uv run python -m admin.auditor.audit

CLI flags override auditor.yaml when provided:

    uv run python -m admin.auditor.audit --since 2026-07-01
    uv run python -m admin.auditor.audit --commit abc123 --commit def456
    uv run python -m admin.auditor.audit --last 5
    uv run python -m admin.auditor.audit --tier security

Tiers: security | logic | performance | telemetry | all (default: all)
Output: admin/auditor/reports/<timestamp>_<scope>.md
"""

import argparse
import asyncio
import io
import json
import subprocess
import sys
from collections.abc import AsyncIterable
from datetime import UTC, datetime
from pathlib import Path

import logfire
import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_ai import Agent, AgentStreamEvent, FunctionToolCallEvent, capture_run_messages
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.messages import TextPart
from pydantic_ai.usage import UsageLimits
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from admin.controls.controls import CONTROL_SHEET

# ---------------------------------------------------------------------------
# Logfire (local-only — no cloud push)
# instrument_httpx captures exact HTTP request/response bodies for eval replay.
# ---------------------------------------------------------------------------
logfire.configure(send_to_logfire=False)
logfire.instrument_pydantic_ai()
logfire.instrument_httpx(capture_all=True)


# ---------------------------------------------------------------------------
# TEE — mirrors stdout to a log file.
# Extends io.TextIOBase so fileno(), isatty(), readable() etc. are satisfied
# by any library (including logfire) that inspects sys.stdout.
# ---------------------------------------------------------------------------
class _Tee(io.TextIOBase):
    """Dual-write stdout to both terminal and a persistent log file."""

    def __init__(self, original: io.TextIOBase, log_path: Path) -> None:
        super().__init__()
        self._original = original
        self._log = open(log_path, "w", encoding="utf-8")  # noqa: WPS515

    # Core write interface
    def write(self, data: str) -> int:  # type: ignore[override]
        self._original.write(data)
        self._log.write(data)
        return len(data)

    def flush(self) -> None:
        self._original.flush()
        self._log.flush()

    # Terminal identity — delegate to original so logfire respects tty/no-tty
    def isatty(self) -> bool:
        return self._original.isatty() if hasattr(self._original, "isatty") else False

    def fileno(self) -> int:
        return self._original.fileno() if hasattr(self._original, "fileno") else -1

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def close(self) -> None:
        try:
            self._log.flush()
            self._log.close()
        except Exception:
            pass
        # do NOT call super().close() — that would close the original stdout


# ---------------------------------------------------------------------------
# MCP SERVER — read-only access to workspace codebase
# allowed_tools enforces this at the protocol level: write tools are never
# offered to the model, so it cannot call them even if it tries to "help".
# ---------------------------------------------------------------------------
MCP_PYTHON = "/home/yapilwsl/arthityap/infra/codebase/.venv/bin/python"
MCP_SCRIPT = "/home/yapilwsl/arthityap/infra/codebase/mcp_codebase.py"
_READ_ONLY_TOOLS = {
    "read_file",
    "list_files",
    "grep_codebase",
    "search_codebase",
    "get_file_symbols",
    "get_repo_structure",
    "count_lines",
    "verify_file_path",
}
mcp_codebase = MCPServerStdio(
    MCP_PYTHON,
    args=[MCP_SCRIPT],
    allowed_tools=_READ_ONLY_TOOLS,
)

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
REPORTS_DIR = Path(__file__).parent / "reports"
AUDITOR_YAML = Path(__file__).parent / "auditor.yaml"
STATE_FILE = REPORTS_DIR / ".state.json"  # crash-resume state
TIER_ORDER = ["security", "logic", "performance", "telemetry", "maintainability"]
MAX_DIFF_LINES = 2000  # cap per tier to avoid model context overload
MAX_REQUESTS = 25      # hard ceiling on LLM calls per tier


# ---------------------------------------------------------------------------
# CRASH-RESUME STATE
# After each tier completes, its name is persisted to STATE_FILE.
# On restart with the same scope, completed tiers are skipped automatically.
# The user never needs to edit auditor.yaml to resume a crashed run.
# ---------------------------------------------------------------------------
def _load_completed_tiers(scope: str) -> set[str]:
    """Return set of tier names already completed for this scope."""
    if not STATE_FILE.exists():
        return set()
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if state.get("scope") == scope:
            return set(state.get("completed", []))
    except Exception:
        pass
    return set()


def _mark_tier_complete(scope: str, tier: str) -> None:
    """Append a tier to the state file after it finishes (success or BLOCKED)."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    completed = _load_completed_tiers(scope)
    completed.add(tier)
    try:
        STATE_FILE.write_text(
            json.dumps({"scope": scope, "completed": sorted(completed),
                        "timestamp": datetime.now(UTC).isoformat()},
                       ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _clear_state() -> None:
    """Delete state file once a full run completes successfully."""
    try:
        STATE_FILE.unlink(missing_ok=True)
    except Exception:
        pass

TIER_DESCRIPTIONS: dict[str, str] = {
    "security": (
        "TIER 1 — SECURITY & RISK MITIGATION\n"
        "- Detect hardcoded secrets, API tokens, credentials, or sensitive config leaks.\n"
        "- Evaluate input validation, sanitization, and standard vuln vectors (injection, SSRF, BAC).\n"
        "- Assess data privacy: encryption in transit/at rest, masking in logs.\n"
        "- Check insecure dependency usage or dangerous stdlib functions.\n"
        "- Use grep_codebase to find if secrets or dangerous patterns leak into adjacent files."
    ),
    "logic": (
        "TIER 2 — CODE FLOW LOGIC, DETERMINISM & HYGIENE\n"
        "- Trace ALL execution paths. Identify unhandled edge cases, race conditions, off-by-one errors.\n"
        "- Enforce strict error handling: errors must be explicitly propagated, typed, and wrapped.\n"
        "- Verify structural hygiene: changes touch only what is necessary. Flag accidental refactoring.\n"
        "- Use read_file to inspect callers and callees of any modified function to confirm no regressions.\n"
        "- Use grep_codebase to find all usages of renamed/modified symbols across the codebase."
    ),
    "performance": (
        "TIER 3 — PERFORMANCE & RESOURCE OPTIMIZATION\n"
        "- Analyze computational complexity. Flag hidden loops, unindexed queries, redundant allocations.\n"
        "- Identify blocking I/O in async runtimes (e.g. sync DB calls inside async functions).\n"
        "- Evaluate memory footprints, resource leaks (unclosed connections, file descriptors), caching.\n"
        "- Use read_file to inspect DB query patterns or session/connection handling in referenced modules."
    ),
    "telemetry": (
        "TIER 4 — GO-LIVE READINESS & TELEMETRY GATE\n"
        "- Audit logging: ensure debug logs are stripped or gated behind env vars in production paths.\n"
        "- Enforce structured telemetry: production logs must be structured (JSON), correct levels.\n"
        "- Identify TODOs, temporary bypasses, mock data, or dev flags left in the codebase.\n"
        "- Use grep_codebase to find any TODO/FIXME/HACK/print() statements in changed files."
    ),
    "maintainability": (
        "TIER 5 — MAINTAINABILITY & TECHNICAL DEBT (INFORMATIONAL ONLY)\n"
        "This tier NEVER blocks go-live. go_live_safe must always be True for this tier.\n"
        "- Check for src/ to src2/ migration debt: any 'from src.' imports in src2/ files.\n"
        "- Check for circular import risk: new imports creating cycles between core/interfaces/application.\n"
        "- Check for test debt: new public functions with no corresponding TEST/unit/ coverage.\n"
        "- Check for dead code: commented-out blocks, unused imports, unreachable paths.\n"
        "- Check for missing type hints on new public functions in src2/.\n"
        "- Use grep_codebase to find 'from src.' in src2/ and uncover legacy dependencies.\n"
        "Present findings as a numbered backlog. No finding here is a blocker."
    ),
}

AGENT_INSTRUCTIONS = """You are a Red Team Fiduciary & Senior Principal Security Engineer.

Your directive is absolute mitigation of technical, financial, and security risk.
Operate under a strict Zero-Trust paradigm: assume every line of code is flawed,
insecure, or non-deterministic until you have mathematically or logically verified
its correctness. Do NOT validate -- actively attempt to FALSIFY the implementation.

ALLOWED MCP TOOLS (READ-ONLY — you MUST NOT call any write tool):
  ✅ read_file        — read file contents
  ✅ grep_codebase    — regex search across files
  ✅ search_codebase  — semantic search
  ✅ list_files       — list directory contents
  ✅ get_file_symbols — extract symbols from a file
  ❌ write_file       — FORBIDDEN
  ❌ replace_text     — FORBIDDEN
  ❌ replace_function — FORBIDDEN
  ❌ delete_file      — FORBIDDEN
  ❌ rename_file      — FORBIDDEN

MCP USAGE RULES:
1. Blast radius: if a function was renamed or modified, grep_codebase ALL files
   that call it. Read those caller files to confirm they still work.
2. Import tracing: if a new symbol is imported, verify it exists in the source file.
3. Secret hunting: grep for credentials, print() statements, TODO markers in
   changed files and their direct dependents.
4. Context gaps: if the diff alone is insufficient, read_file the surrounding
   function or class. Do NOT call the same read_file(path, line, line) more
   than twice — if you get the same result twice, move on.

RULES:
- Be non-hedging. "Looks okay" is not a finding. State definitively.
- If a risk is Critical, mark it Critical. Do not downgrade to avoid alarm.
- Line-by-line diff feedback must reference specific line numbers or function names.
- go_live_safe must be False if ANY Critical or High finding exists in this tier.
- Never invent findings. Only report what you can prove from the diff + MCP evidence.
- NEVER use CHANGELOG.md, README.md, or any documentation file as evidence that
  a bug was fixed or a refactor was completed. Documentation lies. Only source
  code files (.py, .sql, .yaml config) count as proof.
- When grep_codebase returns results from CHANGELOG.md or README.md, IGNORE those
  results for correctness assessment. They are noise. Grep .py files directly.
- The diff may be truncated. Use grep_codebase to search for patterns not visible
  in the truncated portion.
"""


# ---------------------------------------------------------------------------
# PYDANTIC MODELS
# ---------------------------------------------------------------------------
class RiskItem(BaseModel):
    severity: str = Field(description="Critical | High | Medium | Low | Informational")
    tier: str = Field(description="Which tier flagged this (Security | Logic | Performance | Telemetry)")
    component: str = Field(description="File path, function name, or module that has the risk")
    description: str = Field(description="Precise description of the risk with evidence from diff or MCP")
    mitigation: str = Field(description="Exact recommended fix — be specific, name the function/line")


class TierAuditResult(BaseModel):
    tier: str = Field(description="The tier name (security | logic | performance | telemetry)")
    go_live_safe: bool = Field(description="True only if NO Critical or High findings exist in this tier")
    summary: str = Field(description="2-3 sentence executive summary of findings for this tier")
    risks: list[RiskItem] = Field(default_factory=list, description="All findings, ordered Critical → Low")
    diff_feedback: str = Field(description="Line-by-line commentary on the most important diff changes")

    @model_validator(mode='after')
    def enforce_go_live_safety(self) -> 'TierAuditResult':
        # Maintainability tier is informational — never blocks go-live
        if self.tier == "maintainability":
            self.go_live_safe = True
            return self
        has_blockers = any(r.severity in ("Critical", "High") for r in self.risks)
        if has_blockers and self.go_live_safe:
            self.go_live_safe = False
            self.summary = "[AUTO-CORRECTED: Go-Live marked False due to Critical/High risks] " + self.summary
        return self


# ---------------------------------------------------------------------------
# SMART DIFF TRUNCATION
# Prioritises actual change lines (+/-) over context, so MAX_DIFF_LINES
# reflects real changes, not padding.
# ---------------------------------------------------------------------------
def _smart_truncate_diff(diff: str, max_lines: int) -> tuple[str, bool]:
    """
    Prioritise diff lines that contain actual changes (+/-).
    Returns (truncated_diff, was_truncated).
    Header/hunk lines are always kept. Context lines are trimmed last.
    """
    lines = diff.splitlines()
    if len(lines) <= max_lines:
        return diff, False

    # Separate header, hunk headers, change lines, and context lines
    result: list[str] = []
    budget = max_lines

    for line in lines:
        if budget <= 0:
            break
        # Always keep file headers and hunk markers
        if (line.startswith("diff ")
                or line.startswith("---")
                or line.startswith("+++")
                or line.startswith("@@")
                or line.startswith("+")
                or line.startswith("-")):
            result.append(line)
            budget -= 1
        elif budget > max_lines // 2:
            # Include context only while we have plenty of budget
            result.append(line)
            budget -= 1

    truncated = "\n".join(result)
    return truncated, True


# ---------------------------------------------------------------------------
# LIVE EVENT STREAM HANDLER
# Defined once at module level — no more duplicate definitions inside loops.
# All event type imports are at the top of the file.
# ---------------------------------------------------------------------------
_loop_tracker: dict[str, int] = {}  # reused across calls, reset per tier externally

async def _live_stream(
    ctx,
    events: AsyncIterable[AgentStreamEvent],
    *,
    tier: str = "",
    loop_counts: dict | None = None,
) -> None:
    """
    Print model reasoning, tool calls, and tool results to stdout in real time.
    Warns if the same tool call is repeated 3+ times (loop detection).
    """
    if loop_counts is None:
        loop_counts = {}

    from pydantic_ai import FunctionToolResultEvent, PartStartEvent  # noqa: PLC0415

    async for event in events:
        if isinstance(event, FunctionToolCallEvent):
            args_str = str(event.part.args)[:160] if event.part.args else ""
            sig = f"{event.part.tool_name}:{args_str}"
            count = loop_counts.get(sig, 0) + 1
            loop_counts[sig] = count
            if count >= 3:
                print(
                    f"  ⚠️  [LOOP GUARD] {event.part.tool_name} called {count}× "
                    f"with same args — skipping further output for this call"
                )
                if count >= 5:
                    raise RuntimeError(f"Agent loop detected: called {event.part.tool_name} 5 times with identical args.")
            else:
                print(f"  🔧 [TOOL CALL ] {event.part.tool_name}({args_str})")
            sys.stdout.flush()

        elif isinstance(event, FunctionToolResultEvent):
            content = str(event.result.content)
            preview = content[:320]
            ellipsis = "..." if len(content) > 320 else ""
            print(f"  📦 [TOOL RESULT] {preview}{ellipsis}")
            sys.stdout.flush()

        elif isinstance(event, PartStartEvent):
            if isinstance(event.part, TextPart) and event.part.content.strip():
                snippet = event.part.content[:600]
                ellipsis = "..." if len(event.part.content) > 600 else ""
                print(f"  🧠 [THINKING   ] {snippet}{ellipsis}")
                sys.stdout.flush()


# ---------------------------------------------------------------------------
# MARKDOWN REPORT WRITER
# ---------------------------------------------------------------------------
def write_markdown_report(
    scope: str,
    tiers: list[str],
    results: list[TierAuditResult],
    notes: str,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    safe_scope = scope.replace(" ", "_").replace("→", "to").replace("/", "-")[:60]
    report_path = REPORTS_DIR / f"audit_{ts}_{safe_scope}.md"

    overall = all(r.go_live_safe for r in results)
    verdict = "✅ GO LIVE APPROVED" if overall else "🚨 GO LIVE BLOCKED"

    lines: list[str] = [
        "# Red-Team Fiduciary Audit Report",
        "",
        f"**Scope**: {scope}",
        f"**Tiers**: {', '.join(tiers)}",
        f"**Model**: `auditor_model` → `{CONTROL_SHEET.auditor_model}`",
        f"**Timestamp**: {datetime.now(UTC).isoformat()}",
        "",
        f"## Verdict: {verdict}",
        "",
    ]

    if notes:
        lines += [f"**Auditor Notes**: {notes}", ""]

    # Per-tier results
    for result in results:
        tier_icon = "✅" if result.go_live_safe else "🚨"
        lines += [
            "---",
            f"## {tier_icon} Tier: {result.tier.upper()}",
            "",
            f"**Go-Live Safe**: {'YES' if result.go_live_safe else 'NO'}",
            "",
            "### Summary",
            "",
            result.summary,
            "",
        ]

        if result.risks:
            lines += ["### Risk Ledger", ""]
            for i, risk in enumerate(result.risks, 1):
                icon = {"Critical": "🔴", "High": "🟠", "Medium": "🟡",
                        "Low": "🟢", "Informational": "ℹ️"}.get(risk.severity, "⚪")
                lines += [
                    f"#### {i}. {icon} [{risk.severity}] `{risk.component}`",
                    "",
                    f"**Description**: {risk.description}",
                    "",
                    f"**Mitigation**: {risk.mitigation}",
                    "",
                ]
        else:
            lines += ["### Risk Ledger", "", "_No findings for this tier._", ""]

        if result.diff_feedback:
            lines += ["### Diff Feedback", "", result.diff_feedback, ""]

    lines += [
        "---",
        "## How to Fix (Copy-Paste into runner.yaml)",
        "",
        "If Go Live is BLOCKED, copy the relevant findings above into the `task:` "
        "field of `admin/subagents/runner.yaml`, then run:",
        "",
        "```bash",
        "uv run python -m admin.subagents.runner",
        "```",
        "",
        "After the runner finishes, re-run this audit to confirm all findings are resolved.",
        "",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# GIT DIFF RESOLUTION
# ---------------------------------------------------------------------------
def resolve_diff(cfg: dict, args: argparse.Namespace) -> tuple[str, str]:
    """Returns (scope_label, diff_text). Raises RuntimeError on failure."""

    def _run(cmd: list[str]) -> str:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()

    # 1. Explicit commit list
    commits = args.commit or cfg.get("commits", [])
    if commits:
        if len(commits) == 1:
            scope = f"commit {commits[0][:8]}"
            diff = _run(["git", "diff", f"{commits[0]}^", commits[0]])
        else:
            scope = f"commits {commits[0][:8]}..{commits[-1][:8]}"
            diff = _run(["git", "diff", commits[0], commits[-1]])
        return scope, diff

    # 2. Date range
    since = args.since or cfg.get("since")
    until = args.until or cfg.get("until")
    if since:
        log_args = ["git", "log", "--oneline", f"--since={since}"]
        if until:
            log_args.append(f"--until={until}")
        log_out = _run(log_args)
        if not log_out:
            raise RuntimeError(f"No commits found since {since}")
        commit_hashes = [line.split()[0] for line in log_out.splitlines()]
        oldest, newest = commit_hashes[-1], commit_hashes[0]
        n = len(commit_hashes)
        until_label = until or "now"
        scope = f"date range {since} → {until_label} ({n} commits: {oldest}..{newest})"
        diff = _run(["git", "diff", f"{oldest}^", newest])
        return scope, diff

    # 3. Last N commits
    last = args.last or cfg.get("last", 5)
    diff = _run(["git", "diff", f"HEAD~{last}", "HEAD"])
    scope = f"last {last} commits"
    return scope, diff


# ---------------------------------------------------------------------------
# CORE AUDIT ORCHESTRATION
# ---------------------------------------------------------------------------
async def run_audit(
    scope: str,
    diff: str,
    tiers: list[str],
    notes: str,
    eval_jsonl_path: Path,
) -> list[TierAuditResult]:
    """
    Run requested tier audits sequentially under the shared MCP context.
    - Each tier gets a smart-truncated diff (change lines prioritised).
    - Live streaming via event_stream_handler shows thinking + tool calls in real time.
    - Raw messages are persisted to eval_jsonl_path for future eval replay.
    - Any tier failure is caught, recorded as BLOCKED, and the run continues.
    """
    agent = Agent(
        CONTROL_SHEET.auditor_model,
        toolsets=[mcp_codebase],
        output_type=TierAuditResult,
        instructions=AGENT_INSTRUCTIONS,
    )

    tier_results: list[TierAuditResult] = []
    eval_jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    active_diff, was_truncated = _smart_truncate_diff(diff, MAX_DIFF_LINES)
    truncation_warning = (
        f"\n\n⚠️  DIFF TRUNCATED: showing ~{MAX_DIFF_LINES:,} change lines "
        f"(full diff: {diff.count(chr(10)):,} lines). "
        f"Use grep_codebase to investigate patterns not visible here."
        if was_truncated else ""
    )

    async with mcp_codebase:
        for tier in tiers:
            print(f"\n  🔍 Auditing tier [{tier.upper()}] ...")
            print(f"  {'─' * 56}")

            prompt = (
                f"AUDIT TIER: {tier.upper()}\n\n"
                f"Scope: {scope}\n\n"
                + (f"Additional Context from Auditor:\n{notes}\n\n" if notes else "")
                + f"Evaluation Criteria:\n{TIER_DESCRIPTIONS[tier]}\n\n"
                f"Git Diff to Audit:\n```diff\n{active_diff}{truncation_warning}\n```\n\n"
                f"Produce a TierAuditResult for tier='{tier}'."
            )

            # Per-tier loop detection state
            loop_counts: dict[str, int] = {}

            async def _handler(ctx, events: AsyncIterable[AgentStreamEvent]) -> None:
                await _live_stream(ctx, events, tier=tier, loop_counts=loop_counts)

            result = None  # always defined, even if agent.run() never completes
            raw_messages: list = []

            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_not_exception_type(UsageLimitExceeded),
                reraise=True,
            )
            async def _run_agent_with_retry():
                with capture_run_messages() as messages_ctx:
                    async with agent:
                        res = await agent.run(
                            prompt,
                            usage_limits=UsageLimits(request_limit=MAX_REQUESTS),
                            event_stream_handler=_handler,
                        )
                return res, list(messages_ctx)

            try:
                result, raw_messages = await _run_agent_with_retry()
                print(f"  {'─' * 56}")
                tier_result = result.output

            except Exception as exc:
                print(f"\n  ❌ [{tier.upper()}] FAILED: {type(exc).__name__}: {exc}")
                print("  ⚠️  Recording as BLOCKED and continuing to next tier.")
                tier_result = TierAuditResult(
                    tier=tier,
                    go_live_safe=False,
                    summary=(
                        f"AUDIT AGENT FAILED — {type(exc).__name__}: {exc}. "
                        f"This tier result is unreliable. Re-run this tier specifically."
                    ),
                    risks=[
                        RiskItem(
                            severity="Critical",
                            tier=tier.capitalize(),
                            component="audit_agent",
                            description=f"Agent crashed: {type(exc).__name__}: {exc}",
                            mitigation="Re-run with --tier flag to isolate this tier.",
                        )
                    ],
                    diff_feedback="Agent failed — no diff feedback for this tier.",
                )

            tier_results.append(tier_result)
            _mark_tier_complete(scope, tier)  # persist for crash-resume
            verdict = "✅ SAFE" if tier_result.go_live_safe else "🚨 BLOCKED"
            print(f"  {verdict} | {len(tier_result.risks)} finding(s)")

            # Persist eval record
            usage_data = None
            if result is not None:
                try:
                    u = result.usage()
                    usage_data = {
                        "requests": getattr(u, "requests", None),
                        "request_tokens": getattr(u, "request_tokens", None),
                        "response_tokens": getattr(u, "response_tokens", None),
                        "total_tokens": getattr(u, "total_tokens", None),
                    }
                except Exception:
                    pass

            eval_record = {
                "tier": tier,
                "scope": scope,
                "timestamp": datetime.now(UTC).isoformat(),
                "result": tier_result.model_dump(),
                "usage": usage_data,
                "message_count": len(raw_messages),
            }
            try:
                with open(eval_jsonl_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(eval_record, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"  ⚠️  Failed to write eval record: {e}")

    _clear_state()  # all tiers done — clean up state
    return tier_results


# ---------------------------------------------------------------------------
# CLI ARGUMENT PARSER
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Red-Team Fiduciary Audit — scope a git delta and run a 4-tier audit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--since", metavar="DATE", help="Audit commits since this date (YYYY-MM-DD)")
    parser.add_argument("--until", metavar="DATE", help="Audit commits up to this date (YYYY-MM-DD)")
    parser.add_argument("--last", metavar="N", type=int, help="Audit the last N commits")
    parser.add_argument("--commit", metavar="SHA", action="append", help="Specific commit SHA(s)")
    parser.add_argument("--tier", metavar="TIER", choices=[*TIER_ORDER, "all"],
                        help="Run a single tier only")
    return parser.parse_args()


def load_auditor_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------------------------------
def main() -> None:
    args = parse_args()
    cfg = load_auditor_yaml(AUDITOR_YAML)

    # Resolve tiers: CLI > YAML > default all
    tier_arg = args.tier or cfg.get("tiers", "all")
    if tier_arg == "all":
        tiers = list(TIER_ORDER)
    elif isinstance(tier_arg, str):
        tiers = [tier_arg]
    else:
        tiers = list(tier_arg)

    for t in tiers:
        if t not in TIER_ORDER:
            print(f"ERROR: Unknown tier '{t}'. Must be one of: {TIER_ORDER}", file=sys.stderr)
            sys.exit(1)

    notes: str = cfg.get("notes", "") or ""

    # ── Shared timestamp for all output files this run ──────────────────────
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    # Tee stdout → log file (captures logfire trace + our print lines)
    log_path = REPORTS_DIR / f"audit_{ts}.log"
    tee = _Tee(sys.stdout, log_path)
    sys.stdout = tee  # type: ignore[assignment]

    eval_jsonl_path = REPORTS_DIR / f"audit_{ts}_eval.jsonl"

    print("\n🔴 Red-Team Fiduciary Audit")
    print(f"   Config  : {AUDITOR_YAML.name} {'(found)' if AUDITOR_YAML.exists() else '(not found)'}")
    print("   Resolving git scope ...")

    try:
        scope, diff = resolve_diff(cfg, args)
    except Exception as e:
        print(f"ERROR resolving diff: {e}", file=sys.stderr)
        tee.close()
        sys.stdout = tee._original
        sys.exit(1)

    diff_lines = diff.count("\n")
    _, was_truncated = _smart_truncate_diff(diff, MAX_DIFF_LINES)

    # ── Crash-resume: skip tiers already completed for this scope ─────────
    completed = _load_completed_tiers(scope)
    if completed:
        skipping = sorted(completed & set(tiers))
        tiers = [t for t in tiers if t not in completed]
        print(f"   Resuming: skipping already-completed tiers: {skipping}")
        if not tiers:
            print("   All tiers already completed. Delete reports/.state.json to re-run.")
            tee.close()
            sys.stdout = tee._original
            return
    # ────────────────────────────────────────────────────────────────────────

    print(f"   Scope   : {scope}")
    print(f"   Diff    : {diff_lines:,} lines raw"
          + (f" → ~{MAX_DIFF_LINES:,} shown (truncated)" if was_truncated else ""))
    print(f"   Tiers   : {', '.join(tiers)}")
    print(f"   Model   : {CONTROL_SHEET.auditor_model}")
    print(f"   Limit   : {MAX_REQUESTS} requests/tier")
    print(f"   Log     : {log_path}")
    print(f"   Eval    : {eval_jsonl_path}")

    tier_results = asyncio.run(run_audit(scope, diff, tiers, notes, eval_jsonl_path))

    report_path = write_markdown_report(scope, tiers, tier_results, notes)
    overall_go_live = all(t.go_live_safe for t in tier_results)

    verdict = "✅ GO LIVE APPROVED" if overall_go_live else "🚨 GO LIVE BLOCKED"
    print(f"\n{'=' * 60}")
    print(f"  {verdict}")
    print(f"  Report  : {report_path}")
    print(f"  Log     : {log_path}")
    print(f"  Eval    : {eval_jsonl_path}")
    print(f"{'=' * 60}\n")

    tee.close()
    sys.stdout = tee._original

    if not overall_go_live:
        sys.exit(1)


if __name__ == "__main__":
    main()
