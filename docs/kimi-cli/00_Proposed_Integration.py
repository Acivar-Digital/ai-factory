"""
Proposed Integration: Kimi-CLI Patterns → AI-Factory

Purpose
=======
Document which kimi-cli architectural patterns ai-factory can adopt,
the concrete integration approach, insertion points, and hard constraints.
This is a living spec — not executable code, but typed Python illustrating
the intended shapes.

Constraints (must not violate)
------------------------------
1. ai-factory MUST use Pydantic-AI (v2.0+) for agents. kimi-cli's `kosong`
   LLM abstraction is NOT adoptable as a replacement framework.
2. Shadow tools MUST remain CLI wrappers (`uv run python factory/tools/*.py`).
   Never use raw MCP tools if a CLI wrapper exists. MCP may be an *optional
   consumption* path for external tools only.
3. No phantom role names. kimi-cli subagent types `coder`/`planner` must map
   to intern/engineer/senior if ever adopted.
4. All edits confined to `factory/` (sandbox). Target repo files accessed
   read-only via `stage_path()` → `factory/temp/` mirroring.

=========================================================================
WHAT TO EMBRACE (ranked by impact/reach)
=========================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

# =====================================================================
# 1. EVENT HOOK ENGINE  (highest value, lowest risk)
# =====================================================================
# kimi-cli: src/kimi_cli/hooks/ — HookEngine + HookDef/HookEventType
#   Events: PreToolUse, PostToolUse, PostToolUseFailure, Stop,
#           SessionStart/End, SubagentStart/Stop,
#           PreCompact, PostCompact, Notification
#   Shell-script execution, JSON stdin, fail-open on timeout.
#
# ai-factory gap: only Pydantic-AI Hooks.before_model_request (msg scrub).
#   No lifecycle events for tool calls, compaction, phase transitions.
#
# Insertion point: factory/infra/hooks/ (new module)
#   - PostCompact → fire in factory/infra/_loopguard.py:compact_memory_gate
#   - PreCompact  → fire in factory/infra/context.py:compact_context_if_needed
#   - PreToolUse/PostToolUse → fire in factory/infra/tools_guard.py:GuardToolset
#   - SessionStart → fire in factory/infra/runner.py:main()
#   - SessionEnd → fire in runner cleanup / _checkpoint


HookEventType = Literal[
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Stop",
    "SessionStart",
    "SessionEnd",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
    "PostCompact",
    "Notification",
]


class HookDef(BaseModel):
    """Mirror of kimi-cli hooks/config.py HookDef — pydantic v2 only."""

    model_config = ConfigDict(extra="forbid")

    event: HookEventType
    command: str  # shell command; receives JSON on stdin
    matcher: str = ""  # regex to filter (e.g. tool name pattern)
    timeout: int = Field(default=30, ge=1, le=600)  # fail-open on timeout


@dataclass
class HookResult:
    """Mirror of kimi-cli hooks/runner.py HookResult."""

    action: Literal["allow", "block"] = "allow"
    reason: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False


@dataclass
class HookEngine:
    """
    kimi-cli HookEngine port for ai-factory.

    Loads HookDef list (from factory/infra/hooks/config.toml or
    factory/infra/hooks/Hooks.json — mirror kimi-cli's config.toml pattern).
    Runs matched hooks in parallel via asyncio.create_subprocess_shell,
    JSON-dumps input_data to stdin, fail-open on any error/timeout.

    ai-factory integration: instantiate a global singleton in
    factory/infra/_runtime.py, fire events from the insertion points above.
    """

    hooks: list[HookDef] = field(default_factory=list)
    cwd: str = "."
    _on_triggered: Any | None = None
    _on_resolved: Any | None = None

    def _match(self, event: str, matcher_value: str) -> list[HookDef]:
        """Return hooks for `event` whose matcher regex matches `matcher_value`."""
        import re

        matched = []
        for h in self.hooks:
            if h.event != event:
                continue
            if not h.matcher:
                matched.append(h)
            elif re.search(h.matcher, matcher_value):
                matched.append(h)
        return matched

    async def fire(
        self,
        event: HookEventType,
        matcher_value: str,
        input_data: dict[str, Any],
    ) -> list[HookResult]:
        """Run all matching hooks in parallel. Fail-open on timeout/error."""
        import asyncio
        import json

        matched = self._match(event, matcher_value)  # HookEventType is Literal[str], not Enum
        if not matched:
            return []

        procs: list[asyncio.subprocess.Process] = []
        for h in matched:
            proc = asyncio.create_subprocess_shell(
                h.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
            )
            procs.append(await proc)  # await creates the Process

        results: list[HookResult] = []
        for h, proc in zip(matched, procs):
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(input=json.dumps(input_data).encode()),
                    timeout=h.timeout,
                )
            except (asyncio.TimeoutError, Exception):
                proc.kill()
                await proc.wait()
                results.append(HookResult(action="allow", timed_out=True,
                    stderr=f"Hook timed out after {h.timeout}s"))
                continue

            stdout = stdout_b.decode(errors="replace")
            stderr = stderr_b.decode(errors="replace")
            exit_code = proc.returncode or 0

            # Exit 2 = block (kimi-cli convention)
            if exit_code == 2:
                results.append(HookResult(action="block", reason=stderr.strip(),
                    stdout=stdout, stderr=stderr, exit_code=exit_code))
            else:
                results.append(HookResult(action="allow", stdout=stdout,
                    stderr=stderr, exit_code=exit_code))
        return results


# --- ai-factory insertion example (factory/infra/tools_guard.py) ---
# In GuardToolset.get_tools or _run, before dispatching:
#
#   from factory.infra.hooks import HOOK_ENGINE
#   await HOOK_ENGINE.fire("PreToolUse", tool_name, {
#       "session_id": bd, "cwd": str(REPO_ROOT),
#       "tool_name": tool_name, "tool_input": args, "tool_call_id": call_id,
#   })
#
# After dispatch (in PostToolUse / PostToolUseFailure depending on outcome):
#   await HOOK_ENGINE.fire("PostToolUse", tool_name, {
#       "session_id": bd, "cwd": str(REPO_ROOT),
#       "tool_name": tool_name, "tool_input": args,
#       "tool_output": result_str, "tool_call_id": call_id,
#   })

# --- ai-factory insertion example (factory/infra/_loopguard.py) ---
# In compact_memory_gate, before keep_memory loop:
#   await HOOK_ENGINE.fire("PreCompact", role, {
#       "session_id": state.bd_id, "phase": phase,
#       "trigger": "token_budget", "token_count": _estimate_text_tokens(history_text),
#   })
# After compaction completes:
#   await HOOK_ENGINE.fire("PostCompact", role, {
#       "session_id": state.bd_id, "phase": phase,
#       "trigger": "token_budget", "estimated_token_count": len(compacted_text),
#   })


# =====================================================================
# 2. TYPED WIRE EVENT PROTOCOL  (medium value, low risk)
# =====================================================================
# kimi-cli: src/kimi_cli/wire/types.py — typed BaseModel events
#   TurnBegin/End, StepBegin/Retry/Interrupted, ToolCallRequest,
#   StatusUpdate, CompactionBegin/End, HookTriggered/Resolved,
#   SubagentEvent, Notification, MCPLoadingBegin/End
#   + WireFile (file-backed JSONL recording) + RootWireHub (broadcast)
#
# ai-factory gap: STATUS.md (plain text), eval.jsonl (flat), artefacts/*.jsonl
#   (per-role). No unified typed event stream for monitoring/dashboarding.
#
# Insertion point: factory/infra/models.py (event models) +
#   factory/infra/wire.py (new module: WireFile recording + simple publish)
#   Emit alongside existing STATUS.md / eval.jsonl writes.


class WireEvent(BaseModel):
    """Base envelope — mirrors kimi-cli WireMessageEnvelope structure."""

    event_type: str
    session_id: str  # bd_id
    phase: str | None = None
    role: str | None = None
    timestamp: float = Field(default_factory=lambda: __import__("time").time())


class TurnBeginEvent(WireEvent):
    pass


class TurnEndEvent(WireEvent):
    output_type: str = ""
    token_usage: dict[str, int] | None = None


class ToolCallEvent(WireEvent):
    tool_name: str
    tool_input: dict[str, Any] | None = None
    tool_output: str | None = None
    duration_ms: int = 0
    status: Literal["success", "failure"] = "success"


class CompactionEvent(WireEvent):
    trigger: str
    token_count_before: int
    token_count_after: int


class HookEvent(WireEvent):
    hook_event: str
    hook_name: str
    action: Literal["allow", "block"]
    duration_ms: int
    reason: str = ""


# kimi-cli's WireFile: file-backed JSONL recording with metadata header.
# ai-factory adaptation: factory/orch/reports/run_<ts>_<bd>/wire.jsonl
class WireFile:
    """Minimal file-backed event recorder (subset of kimi-cli WireFile)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def append(self, event: WireEvent) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")


# =====================================================================
# 3. SKILL FLOW ENGINE  (declarative workflow graphs)
# =====================================================================
# kimi-cli: src/kimi_cli/skill/flow/{d2.py,mermaid.py}
#   Parses d2/mermaid flowcharts into Flow(nodes/edges, begin/end/task/decision)
#   parse_choice() for <choice> directives, validation (exactly 1 begin, 1 end,
#   all nodes reachable from begin).
#
# ai-factory gap: static YAML agent specs; no declarative workflow graphs.
#   compact_memory.yaml and the intern→engineer→senior handoff are currently
#   coded imperatively in pipeline.py / execution.py.
#
# Insertion point: factory/infra/skills/flow/ (new module)
#   - Parse <flow> blocks in skill YAML into Flow objects
#   - Execute via graph traversal (BFS from begin node)
#   - <choice> directives → branch selection via model output

# (These types are adapted from kimi-cli skill/flow/__init__.py — frozen dataclasses,
#  no new Pydantic models introduced into the harness, per anti-hallucination rule.)
@dataclass(frozen=True, slots=True)
class FlowNode:
    id: str
    label: str
    kind: Literal["begin", "end", "task", "decision"]


@dataclass(frozen=True, slots=True)
class FlowEdge:
    src: str
    dst: str
    label: str | None = None


@dataclass(slots=True)
class Flow:
    """Directed graph: begin → ... → end, validated."""

    nodes: dict[str, FlowNode]
    outgoing: dict[str, list[FlowEdge]]
    begin_id: str
    end_id: str


# =====================================================================
# 4. SUBAGENT REGISTRY & LIFECYCLE  (future enhancement)
# =====================================================================
# kimi-cli: src/kimi_cli/subagents/{registry, builder, core, runner, store, models}.py
#   LaborMarket (registry), AgentTypeDefinition (with ToolPolicy inherit/allowlist),
#   SubagentBuilder, prepare_soul, foreground/background runners,
#   SubagentStore (persistent context), AgentInstanceRecord (status tracking).
#
# ai-factory gap: `task` tool spawns intern subagents via build_worker_spec,
#   but no formal registry, no persistent subagent store, no ToolPolicy.
#   AgentDependencies in models.py tracks tool_budget/tools_used only.
#
# Insertion point: factory/infra/subagents/ (new module, future phase)
#   - LaborMarket ↔ factory/infra/models.py AgentDependencies
#   - ToolPolicy mode "inherit" → reuse parent's GuardToolset ACL
#   - ToolPolicy mode "allowlist" → restrict to named tools only
#   - SubagentStore → extends factory/artefacts/ per-subagent persistence
# NOTE: Lower priority — current DAG executor (execution.py) works.
#       Only adopt if subagent concurrency needs exceed current asyncio.gather.

ToolPolicyMode = Literal["inherit", "allowlist"]


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolPolicy:
    mode: ToolPolicyMode
    tools: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentTypeDefinition:
    """Mirror of kimi-cli subagents/models.py AgentTypeDefinition."""

    name: str
    description: str
    when_to_use: str
    default_model: str | None = None
    tool_policy: ToolPolicy = field(default_factory=lambda: ToolPolicy(mode="inherit"))
    supports_background: bool = True


# =====================================================================
# 5. CONFIG: DYNAMIC MODEL DISCOVERY + PROVIDER FACTORY
# =====================================================================
# kimi-cli: src/kimi_cli/llm.py — create_llm() maps config to kosong ChatProvider
#   instances; dynamic model discovery via GET /v1/models; capability derivation
#   from model name heuristics.
#
# ai-factory uses factory/infra/control.py:ControlSheet with hardcoded model dict.
#   This is a STATIC design choice — ai-factory's models are local/edge LLMs
#   (OpenRouter, Gemini via LiteRouter), not a managed platform with a
#   /v1/models endpoint. Dynamic discovery is NOT applicable.
#   However, the Provider Factory pattern (create_llm mapping config → provider)
#   is already present in _make_providers() in control.py.

# =====================================================================
# 6. FASTMCP MCP BRIDGING  (optional consumption only)
# =====================================================================
# kimi-cli: src/kimi_cli/soul/toolset.py — KimiToolset loads tools by import
#   path, injects deps, dispatches tool calls, bridges fastmcp MCP tools.
#
# ai-factory constraint: "NEVER use raw MCP tools if a CLI wrapper exists."
#   Shadow tools (factory/tools/*.py) are the primary interface.
#
# Embrace strategy: Add MCP as an OPTIONAL consumption layer ONLY for tools
#   that have NO shadow tool equivalent. e.g. a remote MCP server providing
#   specialized domain tools. Would live in factory/tools/_mcp_bridge.py
#   and must NOT replace any factory/tools/*.py wrapper.

# =====================================================================
# 7. OBSERVABILITY: STRUCTURED ERROR CLASSIFICATION  (low-risk complement)
# =====================================================================
# kimi-cli: src/kimi_cli/soul/kimisoul.py classify_api_error()
#   Maps exceptions → (error_type, status_code) tuple for telemetry:
#   rate_limit, auth, overloaded, 5xx_server, context_overflow, 4xx_client,
#   network, timeout, empty_response, other
#
# ai-factory gap: errors are caught in _run_agent_retry (agent.py:171) and
#   _loopguard run_with_loopguard (usage limit, HTTP 400). No structured
#   classification for telemetry.
#
# Insertion point: factory/infra/observability.py (new, small module)
#   - Hook into _run_agent_retry's except clauses
#   - Emit classified error_type to wire.jsonl (item #2) + eval.jsonl

ErrorClassification = Literal[
    "rate_limit",
    "auth",
    "overloaded",
    "5xx_server",
    "context_overflow",
    "4xx_client",
    "network",
    "timeout",
    "empty_response",
    "other",
]


def classify_api_error(exc: Exception) -> tuple[ErrorClassification, int | None]:
    """Mirror of kimi-cli's classify_api_error — pure function, no deps."""
    from pydantic_ai.exceptions import ModelHTTPError

    if isinstance(exc, ModelHTTPError):
        sc = getattr(exc, "status_code", None)
        if sc == 429:
            return "rate_limit", sc
        if sc in (401, 403):
            return "auth", sc
        if sc == 529:
            return "overloaded", sc
        if sc is not None and sc >= 500:
            return "5xx_server", sc
        if sc is not None and 400 <= sc < 500:
            s = str(exc).lower()
            if "context" in s or "max_tokens" in s or "too long" in s:
                return "context_overflow", sc
            return "4xx_client", sc
    if isinstance(exc, TimeoutError):
        return "timeout", None
    if isinstance(exc, (ConnectionError, OSError)):
        return "network", None
    return "other", None


# =====================================================================
# 8. IN-CONTEXT SELF-CORRECTION LOOP  (HIGH PRIORITY — rank #2 after Item 1)
# =====================================================================
# GOAL: make the bounded in-context correction the PRIMARY loop, with the
# 3-tier cascade (intern→engineer→senior) as the OUTER backstop rather
# than the first-resort reaction to a wrong write. Give the SAME agent a
# cheap in-context correction loop (kimi-cli 2e.6→2e.8) before anyone
# escalates a persona — AND cap that loop so a flail never burns to
# kimi-cli's max_steps_per_turn=1000 default (too generous for a simple
# task; the real money risk). This is the lever for the user's
# "so many feedback loops" pain.
#
# Safety caps (mirror kimi-cli but TIGHTER):
#   - tier_step_cap         = 30   <- hard per-tier LLM-step / tool-call cap
#                                    (ai-factory MAX_TOTAL_TOOL_CALLS is global
#                                     40 in factory/infra/_loopguard.py:43; 30/turn
#                                     is the per-tier slice). Mirrors but does
#                                     NOT copy kimi-cli's 1000.
#   - identical_call_streak = 12   <- mirror kimi-cli
#                                    soul/toolset.py _REPEAT_FORCE_STOP_STREAK;
#                                    force-stop a SAME name+args repeat BEFORE
#                                    the step cap. Catches the null-return loop.
#   - write_correct         = 3    <- same-agent correction passes before
#                                    tier escalation (kimi-cli config.py max_retries_per_step).
# => A bad write: retry in-turn ≤ 3 (capped at 30 steps, 12-identical forced)
#    → escalate tier only on exhaustion. Never 1000.
#
# kimi-cli reference (src/kimi_cli/soul/kimisoul.py):
#   2e.6. Tool execution  - wait for all tool results.  (_step, ~line 1111)
#   2e.7. Context growth  - append assistant + tool messages (incl. errors)
#            so the model SEES the failure in the next micro-step.
#   2e.8. Outcome resolution - ToolRejectedError(has_feedback=True)
#            keeps the SAME agent looping; only pure-rejection-no-feedback
#            (root agent) stops the turn. Bounded by max_retries_per_step=3
#            (config.py:84, default=3). stop_after_attempt(max_attempts)
#            at kimisoul.py:1228. Compaction trigger ratio=0.85 (config.py:92).
#   Also: _checkpoint() before each step (kimisoul.py:619/1036) +
#   revert_to(checkpoint_id) to undo a bad turn (kimisoul.py:1100,
#   BackToTheFuture D-Mail). Per-step tool-call dedup (begin_step resets).
#
# ai-factory STATUS (verified by terminal scan, NOT summary — corrected):
#   - Inline verify_edit IS already live on all three writers:
#       * verify_edit(relative_path, function_name=None) -> str  (JSON)
#         factory/infra/tools_shell.py:151
#       * replace_function: tools_shell.py:102 verify_edit(staged, function_name)
#       * replace_text    : tools_shell.py:58  verify_edit(staged, None)
#       * write_file      : factory/infra/tools_file.py:206 verify_edit(staged, None)
#       * all raise ModelRetry on SyntaxError / duplicate-def / CC>5 / lint
#         regression, with auto-restore from .orig baseline (tools_shell.py:51-57).
#   - ModelRetry IS imported: factory/infra/tools_shell.py:10
#     `from pydantic_ai import ModelRetry`  (pydantic-ai 2.14.1; resolves under
#     `uv run python` — the pydantic_ai.exceptions LSP squiggle at doc line 424 is
#     a pre-existing editor venv-resolve quirk, not a code bug).
#   - FunctionToolset(max_retries=20) wraps all tools (tools_guard.py:311), so a
#     failed write re-enters the SAME agent run up to 20x — kimi-cli 2e.7 for free.
#   => So the "inline verify never happens" gap is CLOSED. One bad edit no longer
#      auto-escalates: replace_text/replace_function/write_file self-correct in run.
#
# REAL OPEN GAP (this is what Item 8 should now target):
#   - The 20x is an in-place retry but there is NO per-tier STEP CAP — a flail that
#     keeps emitting DIVERGENT (non-identical) tool calls never trips dedup and can
#     burn toward MAX_TOTAL_TOOL_CALLS=40 (factory/infra/_loopguard.py:43) without
#     the kimi-cli identical-call guard, and there is no kimi-cli-style
#     _REPEAT_FORCE_STOP_STREAK (12) for same-name+args repeats. That is the
#     1000-call-equivalent exposure, just bounded looser (40) and unobservable.
#   - No tier-level step accounting: state_dict["write_failure_count"] (pipeline.py:
#     809) counts write failures but NOT per-tier LLM steps, so a runaway turn is
#     not visible in docs/21_Factory_Workflow_jobids.json before it hits 40.
#   - No revert_to / checkpoint rewind in the agent loop (only .orig restore on
#     SyntaxError); "undo a bad turn" is still tier escalation. (Option B.)
#   => Remaining money/quality risk: a divergent null-return loop inside a tier is
#      not surfaced until the global 40-call halt — late and unobservable.
#      Add tier_step_cap=30 + identical_call_streak=12 to make the budget SAFE and
#      OBSERVABLE (per-tier step_no logged to jobids.json).
#
# ADOPT STRATEGY (mirror 2e.6→2e.8 as an INNER loop in the same role run):
#   A. INLINE VERIFY (port of 2e.6 + 2e.7): the write tools MUST call
#      verify_edit() and, on failure, raise ModelRetry with a typed error
#      payload. Pydantic-AI's ModelRetry appends the error to the message
#      stream and re-invokes the SAME agent run = kimi-cli 2e.7 for free.
#      PREREQ: fix the verify_edit double-prefix path bug — verify_edit()
#      calls stage_path(relative_path) on an already-staged path
#      (factory/temp/factory/temp/...). Per memory
#      `verify-edit-path-fix-must-run-on-target-function`, verify_edit must
#      stage_path() idempotently. Without this, inline verification writes
#      to a wrong path and the loop feeds garbage diagnostics.
#      Insertion: centralize in GuardToolset._GuardToolsetTool.__call__
#      (tools_guard.py:70) so ALL _MODIFY_TOOLS get inline verification
#      uniformly, rather than patching all three writers independently.
#   B. CONTEXT GROWTH (port of 2e.7): achieved via ModelRetry's built-in
#      retry-message injection. Ensure _loopguard.intercepted_request
#      scrubbing (_loopguard.py:359/379/402/462) does NOT strip the
#      ModelRetry error payload before the retry turn.
#   C. BOUND THE SAME-AGENT LOOP (the genuinely-open work): inline
#      verify_edit + ModelRetry via FunctionToolset(max_retries=20) already
#      re-prompt the SAME agent (tools_shell.py:58/102, tools_file.py:206,
#      tools_guard.py:311). C adds the SAFETY CAPS so a flail can't reach
#      that 20 / the global MAX_TOTAL_TOOL_CALLS=40:
#        - tier_step_cap (30): per-tier LLM-step counter -> escalate on breach.
#        - identical_call_streak (12): force-stop same name+args repeats
#          (mirror kimi-cli soul/toolset.py _REPEAT_FORCE_STOP_STREAK).
#      Track per-tier step_no in state_dict; LOG it to jobids.json so a
#      runaway turn is visible BEFORE the 40-call halt. Reuse the existing
#      state_dict["write_failure_count"] (pipeline.py:809) for write passes.
#   D. OUTCOME RESOLUTION: escalate tiers ONLY when:
#        (a) SelfCorrectionBudget.model_config_inner (3 write passes) exhausted, OR
#        (b) tier_step_cap (30 steps) breached, OR
#        (c) identical_call_streak (12) forced a stop.
#      A single verify FAIL is NOT an auto-halt: it's ModelRetry → same agent
#      (up to the caps). Refactor run_tier (pipeline.py:811/826) so halt
#      (RuntimeError) fires only on cap exhaustion, not on a recoverable fail.
#
# OPTION A — MINIMAL (safety caps only): inline verify_edit + ModelRetry (20x)
#   and FunctionToolset(max_retries=20) are ALREADY live (tools_shell.py:58/102,
#   tools_file.py:206, tools_guard.py:311). A = add the SelfCorrectionBudget
#   caps (C+D): tier_step_cap=30 + identical_call_streak=12, per-tier step
#   accounting logged to jobids.json, escalate ONLY on cap exhaustion (not on a
#   single recoverable verify fail). Stops the cascade for self-correctable
#   AST/ruff failures AND prevents the 1000-call-equivalent burn. Low risk; ~3
#   files (tools_guard.py, _loopguard.py, pipeline.py run_tier).
#
# OPTION B — FULL PORT (checkpoint + rewind): additionally add a revert_to()
#   analog so a bad turn is UNDONE instead of retried. Mirror kimi-cli
#   soul/context.py:123 checkpoint() + :135 revert_to() + BackToTheFuture
#   (kimisoul.py:1100). Needs snapshotting before each tool batch in
#   _loopguard / do_role. Highest fidelity to kimi-cli; highest risk
#   (~5 files, state model change).
#
# OPTION C — STATUS QUO: keep FunctionToolset(max_retries=20) live but add NO
#   caps — accept the loose global MAX_TOTAL_TOOL_CALLS=40 as the only guard
#   and rely on tier escalation for everything. Acceptable only if senior-tier
#   audit value outweighs the 40-step / observability gap.

class ToolExecutionError(BaseModel):
    """Typed error fed back to the model on an inline verify failure.
    Mirrors the structured envelope kimi-cli returns via ToolError return
    values (kosong.ToolError / ToolReturnValue)."""

    model_config = ConfigDict(extra="forbid")

    error_type: str
    status_code: int | None = None
    retryable: bool = True
    detail: str
    tool_name: str | None = None
    # ai-factory-specific: lets the same-tier loop decide escalate-vs-retry
    escalate: bool = False


class SelfCorrectionBudget(BaseModel):
    """kimi-cli LoopControl.max_retries_per_step port for ai-factory's
    inner same-agent correction loop."""

    model_config = ConfigDict(extra="forbid")

    model_config_inner: int = Field(
        default=3, ge=1,
        description="Max same-agent correction passes on a wrong write "
                    "before tier escalation. Mirrors kimi-cli's "
                    "max_retries_per_step (default=3, src/kimi_cli/config.py:10).",
    )
    # 2e.8 semantics
    escalate_on_pure_rejection: bool = True   # no_feedback + budget exhausted → stop/escape
    feedback_keeps_looping: bool = True        # has_feedback → continue same agent
    # --- SAFETY CAPS (the new reason Item 8 matters): do NOT copy kimi-cli's
    # 1000-step generosity. Bound the same-agent loop so a flail can't burn. ---
    tier_step_cap: int = Field(
        default=30, ge=1,
        description="Hard per-tier LLM-step / tool-call cap. Prevents the "
                    "1000-call-equivalent burn: a divergent null-return loop "
                    "(same-name+args NOT identical) is caught HERE, not at "
                    "the global MAX_TOTAL_TOOL_CALLS=40 (_loopguard.py:43).",
    )
    identical_call_streak: int = Field(
        default=12, ge=1,
        description="Force-stop after this many CONSECUTIVE identical "
                    "(function_name, arguments) calls — mirror of kimi-cli "
                    "soul/toolset.py _REPEAT_FORCE_STOP_STREAK=12. Stops the "
                    "'tool returns null, keep hammering same call' loop well "
                    "before the step cap / tier escalation.",
    )


# --- Insertion example A+B (factory/infra/tools_guard.py _GuardToolsetTool) ---
# After a _MODIFY_TOOLS write succeeds, inline-verify and surface a typed
# error that Pydantic-AI re-prompts the SAME agent with (2e.7):
#
    #   def _post_write_verify(self, name: str, relative_path: str,
    #                          function_name: str | None = None) -> None:
    #       import json as _json
    #       from factory.infra.tools_shell import verify_edit
    #       from pydantic_ai import ModelRetry   # ALREADY imported (tools_shell.py:10)
    #       raw = verify_edit(relative_path, function_name)  # FIX path bug first (see PREREQ)
#       payload = _json.loads(raw)
#       if not payload.get("ok"):
#           err = ToolExecutionError(
#               error_type="ast_or_lint_violation",
#               retryable=True,
#               detail=payload.get("error", "")[:2000],
#               tool_name=name,
#           )
#           raise ModelRetry(
#               "Verify failed; correct and retry. " + err.model_dump_json()
#           )
#
# --- Insertion example C+D (factory/infra/pipeline.py run_tier ~811) ---
# Inline verify_edit->ModelRetry (A+B) ALREADY re-prompts the same agent
# (FunctionToolset max_retries=20, tools_guard.py:311). C+D add the SAFETY
# CAPS so the loop can't run to the global MAX_TOTAL_TOOL_CALLS=40 or, worse,
# mimic kimi-cli's 1000-step generosity. Track per-tier step_no in state_dict
# and log to jobids.json; escalate tiers only when caps (not single fails)
# are breached (see SelfCorrectionBudget.tier_step_cap / identical_call_streak).
#
#   budget = SelfCorrectionBudget()
#   for attempt in range(1, MAX_ATTEMPTS + 1):               # MAX_ATTEMPTS=1 (pipeline.py:49)
#       steps_here = state_dict.setdefault("tier_step_no", {}).get(tier, 0)
#       if steps_here >= budget.tier_step_cap:                # C: hard per-tier cap
#           raise RuntimeError(f"[{tier}] step cap {budget.tier_step_cap} breached; escalating")
#       out = await do_role(tier, task, bd, history, exchange, pass_counter, prior, state_dict)
#       # FAIL-LOUDLY gate stays (pipeline.py:822-833): non-done status -> halt.
#       _verify_result = _run_verify_edit(tier, bd, state_dict, target_fn=fn_name)
#       if _verify_result is None:                            # verified clean -> done
#           return out
#       # wrong write (capped, not auto-halt): count + continue same agent
#       passes = state_dict["write_failure_count"].get(fn_name, 0) + 1
#       state_dict["write_failure_count"][fn_name] = passes
#       if passes >= budget.model_config_inner:               # D(a): write passes exhausted
#           raise RuntimeError(f"[{tier}] verify failed {passes}x; escalating to next tier. Last: {_verify_result}")
#       # else: inline ModelRetry (A+B) already re-prompted the SAME agent;
#       # the identical_call_streak guard (D(b)) is enforced in _loopguard via
#       # the per-step dedup state (tools_guard.py / _loopguard.py MAX_TOTAL_TOOL_CALLS).
#       # loop continues -> same agent corrects in run, never 1000-calls.
#
# PREREQ NOTE: verify_edit double-prefix path bug (factory/temp/factory/temp/...)
# must be fixed in stage_path() BEFORE the inline loop is SAFE — otherwise
# the model is fed a wrong-path diagnosis and "corrects" against a non-existent
# file. See memory `verify-edit-path-fix-must-run-on-target-function`.




# - kosong (LLM abstraction) — violates Pydantic-AI requirement
# - kimi-cli's KimiSoul.run loop — replaced by pydantic-ai Agent.run + loopguard
# - kimi-cli's D-Mail / BTW side-questions / approval facade — interactive UX
#    for terminal agents; ai-factory is a deterministic batch conductor
# - kimi-cli's Session model (context.jsonl + wire.jsonl per workdir) —
#    ai-factory uses factory/artefacts/ + factory/orch/reports/ (different layout)
# - kimi-cli's OAuth2 device-flow + managed platform auth — ai-factory uses
#    static ControlSheet model configs (OpenRouter, Gemini via LiteRouter)
# - Phantom role names (coder/planner/red_team/supervisor) — map to
#    intern/engineer/senior only
