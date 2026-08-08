"""
Proposed Integration: OpenWorker Patterns -> AI-Factory

Purpose
=======
Document which openworker (coworker/agent loop) patterns ai-factory can adopt
to fix the core problem: LLM keeps failing with rubbish + hallucination.
The 10 OW-KC cards identify concrete mechanisms from openworker's engine.py,
tools/registry.py, permissions.py, and router.py that close the
self-correction gap in ai-factory's deterministic 3-tier harness.

This is a living spec — not executable code, but typed Python illustrating
the intended shapes. All code uses Pydantic-AI v2.0+ (pydantic-ai 2.14.1).

Constraints (must not violate)
------------------------------
1. ai-factory MUST use Pydantic-AI (v2.0+) for agents.
2. Shadow tools MUST remain CLI wrappers (`uv run python factory/tools/*.py`).
3. No phantom role names. Only intern/engineer/senior.
4. All edits confined to `factory/` (sandbox). Target repo accessed
   read-only via `stage_path()` -> `factory/temp/` mirroring.

=========================================================================
WHAT TO EMBRACE (ranked by impact, per OW-KC cards)
=========================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


# =====================================================================
# 1. ERROR FEEDBACK INTO CONTEXT  (OW-01 — HIGHEST IMPACT)
# =====================================================================
# openworker: engine.py:782-787 (_execute_sync)
#   Catches ALL exceptions, returns {"error": str(exc),
#   "error_type": type(exc).__name__} as a tool message so the LLM SEES
#   the failure in its next turn and self-corrects inline.
#
# openworker: engine.py:757 (_authorize) — denied tools get _tool_error_message
# openworker: engine.py:651 (_interrupted_tool) — interrupted tools get error msg
#   => NO orphaned/silent tool calls. Every pending call gets feedback.
#
# ai-factory gap: GuardToolset.call_tool returns results directly; tool
#   exceptions propagate as unstructured tracebacks that kill the turn or
#   get swallowed. No {"error": ..., "error_type": ...} envelope is
#   injected into the conversation history. output_sanitizer.py only
#   repairs broken JSON OFFLINE — no boundary guard rejects
#   schema-valid-but-hallucinated output.
#
# Insertion point: factory/infra/tools_guard.py:260 (GuardToolset.call_tool)
#   - Wrap _MODIFY_TOOLS execution in try/except
#   - raise ToolError(json.dumps({"error": ..., "error_type": ...}))
#   - Pydantic-AI injects ToolError as a tool message -> ModelRetry
#   - LLM sees the failure and self-corrects on next invocation


class ToolExecutionError(BaseModel):
    """Typed error fed back to the model on a tool failure.

    Mirrors openworker's _execute_sync error envelope (engine.py:782).
    Injected into the conversation as a tool message so the LLM
    self-corrects inline instead of repeating the same bad call.
    """

    model_config = ConfigDict(extra="forbid")

    error_type: str
    status_code: int | None = None
    retryable: bool = True
    detail: str
    tool_name: str | None = None
    escalate: bool = False


# --- Insertion example (factory/infra/tools_guard.py:260 call_tool) ---
# Before (current):
#   result = await asyncio.to_thread(spec.func, **args)
#   return result
#
# After:
#   try:
#       result = await asyncio.to_thread(spec.func, **args)
#       return result
#   except Exception as exc:
#       err = ToolExecutionError(
#           error_type=type(exc).__name__,
#           detail=str(exc)[:2000],
#           tool_name=tool_name,
#           retryable=not isinstance(exc, PermissionError),
#       )
#       raise ToolError(err.model_dump_json())  # enters conversation history


# =====================================================================
# 2. DENY-BY-DEFAULT PERMISSION ENGINE  (OW-02)
# =====================================================================
# openworker: permissions.py — RiskClass + Mode, deny-by-default.
#   Every tool call classified by risk (read, write, exec, destroy).
#   Mode controls which risk classes are allowed. Denied calls surface
#   a structured error so the LLM sees WHY it was rejected.
#
# openworker: engine.py:757 (_authorize) — denied/unknown → _tool_error_message
#
# ai-factory gap: GuardToolset has _READ_ONLY_TOOLS / _MODIFY_TOOLS split
#   (factory/infra/tools_guard.py:97) but NO RiskClass classification gate.
#   No structured PermissionDenied path that feeds back into context.
#
# Insertion point: factory/infra/tools_guard.py:152 (GuardToolset.call_tool)
#   - Classify each tool call by RiskClass before dispatch
#   - Check against Mode allow-list (deny-by-default)
#   - On denial: raise ToolError(json.dumps({"error": "permission_denied",
#     "reason": "RiskClass X not allowed in Mode Y"}))


RiskClass = Literal["read", "write", "execute", "destroy"]


class PermissionDenied(BaseModel):
    """Raised when a tool call is classified but denied by Mode.

    openworker mirror: engine.py:757 (_authorize denied tool →
    _tool_error_message). The denial message enters the conversation
    so the LLM learns it cannot call that tool in this context.
    """

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    risk_class: RiskClass
    mode: str
    reason: str


# --- Insertion example (factory/infra/tools_guard.py:152) ---
# RISK_TABLE: dict[str, RiskClass] = {
#     "write_file": "write", "replace_function": "write", "replace_text": "write",
#     "shell": "execute", "apply_patch": "destroy",
#     # read-only tools: read_file, batch_read, search, etc.
# }
#
# def _classify_and_gate(self, tool_name: str, mode: str) -> None:
#     risk = RISK_TABLE.get(tool_name, "read")
#     if mode == "plan" and risk in ("write", "execute", "destroy"):
#         denied = PermissionDenied(
#             tool_name=tool_name, risk_class=risk, mode=mode,
#             reason=f"RiskClass '{risk}' not allowed in Mode '{mode}'",
#         )
#         raise ToolError(denied.model_dump_json())


# =====================================================================
# 3. PROVIDER ROUTER & CONFIG INVALIDATION  (OW-03)
# =====================================================================
# openworker: router.py:70 (_bare) — strips KNOWN provider prefixes from
#   model string. invalidate() drops stale clients.
# openworker: config.py — layered settings, no imperative post-load env merge.
# openworker: secrets.py — SecretStore resolves ${ENV_VAR} at lookup time.
#
# ai-factory gap: factory/infra/control.py:221 (_PROVIDERS_CACHE) caches
#   provider clients; CONTROL_SHEET (line 550) is a static dict.
#   http_client.py:141 (_orch_http_client) reuses a single HTTP client
#   with no invalidation path. Config is read via os.getenv at module
#   level with no pydantic-settings validation — typos fail LLM runs
#   mid-turn and get blamed on the model.
#
# Insertion point: factory/infra/control.py:221 (_PROVIDERS_CACHE)
#   - Add invalidate() to drop stale clients
#   - factory/infra/http_client.py:141 — add client reset hook


# --- Insertion example (factory/infra/control.py:221) ---
# _PROVIDERS_CACHE: dict[str, tuple[float, Any]] = {}
#
# def invalidate_provider(provider_name: str) -> None:
#     """Mirror openworker router.invalidate() — drops stale client."""
#     _PROVIDERS_CACHE.pop(provider_name, None)
#
# def _maybe_provider(name: str, force: bool = False):
#     if force:
#         invalidate_provider(name)
#     ...


# =====================================================================
# 4. FRIENDLY ERROR TRANSLATION  (OW-04)
# =====================================================================
# openworker: tools/registry.py — friendly_model_error() translates raw
#   vendor JSON into actionable sentences.
# openworker: llm.py — provider ABC, capability matrix.
# openworker: agent.py — token_usage normalization.
#
# ai-factory gap: factory/common/subprocess.py:83 (_run_tool) returns
#   stdout/stderr JSON error on non-zero exit, but the error is a raw
#   string. factory/infra/tools_shell.py (lines 54, 89, 110) raises
#   ModelRetry but with unstructured messages. No capability matrix
#   maps model features (thinking, caching, builtin_function) to
#   Pydantic-AI ModelSettings.
#
# Insertion point: factory/common/subprocess.py:83 (_run_tool)
#   - Wrap error as ToolExecutionError with classified error_type
#   - factory/infra/tools_shell.py:54/89/110 (ModelRetry recovery)


class FriendlyError(BaseModel):
    """openworker's friendly_model_error port — translates raw vendor
    errors into actionable sentences for the LLM context.

    openworker mirror: kosong.chat_provider.kimi.friendly_model_error()
    """

    model_config = ConfigDict(extra="forbid")
    error_type: str
    status_code: int | None
    retryable: bool
    detail: str
    suggestion: str


def friendly_error(exc: Exception) -> FriendlyError:
    """Map an exception to a friendly, actionable error envelope.

    Mirrors openworker tools/registry.py friendly_model_error().
    """
    s = str(exc).lower()
    if "429" in s or "rate limit" in s:
        return FriendlyError(
            error_type="rate_limit", status_code=429, retryable=True,
            detail=str(exc)[:500], suggestion="Wait 5s, reduce parallelism, or switch model.",
        )
    if "context" in s or "too long" in s or "max_tokens" in s:
        return FriendlyError(
            error_type="context_overflow", status_code=400, retryable=True,
            detail=str(exc)[:500], suggestion="Compact context or reduce prompt length.",
        )
    return FriendlyError(
        error_type="other", status_code=None, retryable=False,
        detail=str(exc)[:500], suggestion="Inspect traceback and correct the tool call.",
    )


# =====================================================================
# 5. TOOL REGISTRY & SCHEMA VALIDATION  (OW-05)
# =====================================================================
# openworker: tools/registry.py — aisuite Tools schema gen + timeout bounds.
# openworker: tools/shell.py — _NONINTERACTIVE_ENV + timeout caps.
#
# ai-factory gap: factory/infra/tools_guard.py:311 (FunctionToolset with
#   max_retries=20) generates schemas but has no per-tool timeout bounds
#   and no schema validation at registration (only runtime in
#   load_schema_gate.py:69-72). write_file (tools_file.py:163/183) has
#   _src_write_guard but no schema pre-check.
#
# Insertion point: factory/infra/tools_guard.py:311 (FunctionToolset)
#   - Add per-tool timeout= parameter
#   - Validate schema at registration (not just runtime)
#   - factory/infra/tools_file.py:163/183 (_src_write_guard, write_file)


# =====================================================================
# 6. AUTO-COMPACTION & CONTEXT MANAGEMENT  (OW-06)
# =====================================================================
# openworker: agent.py — compact_memory_gate triggers at 85% context
#   utilization; trim fallback compacts old messages.
# openworker: context.py — compact_context_if_needed().
# openworker: exchange.py:149 — mark_compaction events.
#
# ai-factory gap: factory/infra/_loopguard.py:834 (compact_memory_gate)
#   has a compaction gate but it's a single threshold. _loopguard.py:801
#   (_compact_memory_fallback) and :662 (maybe_compact) exist but lack
#   the 85% utilization trigger and trim fallback.
#   factory/infra/context.py:371 (compact_context_if_needed) is called
#   but not tied to token utilization ratio.
#   factory/infra/_loopguard.py:210 (_scrub_old_read_returns) scrubs
#   read returns but not proactively triggers compaction.
#
# Insertion point: factory/infra/_loopguard.py:834 (compact_memory_gate)
#   - Add 85% utilization trigger (mirror openworker agent.py compact ratio)
#   - Add trim fallback (_compact_memory_fallback at :801)
#   - factory/infra/context.py:371 (compact_context_if_needed)


# =====================================================================
# 7. SUBAGENT ISOLATION  (OW-07)
# =====================================================================
# openworker: subagent.py — child engine in PLAN mode, read-only, no
#   recursion depth > 1. Child agents get their own message history
#   (forked from parent at spawn time).
# openworker: agent.py — subagent isolation via forked context.
#
# ai-factory gap: factory/infra/tools_skill.py:362 (build_worker_spec)
#   builds subagents but they share the SAME context (no fork).
#   tools_skill.py:281 (load_skill delegation) and :399 (agent creation)
#   use MODIFY_TOOLS ACL wrapping (:380-383) but subagents can still
#   recursively spawn subagents without isolation.
#
# Insertion point: factory/infra/tools_skill.py:362 (build_worker_spec)
#   - Fork message history at spawn time
#   - Enforce PLAN mode (read-only) for exploration subagents
#   - Block recursive subagent spawning (depth <= 1)


# =====================================================================
# 8. SHELL SAFETY & TIMEOUT  (OW-08)
# =====================================================================
# openworker: tools/shell.py — _NONINTERACTIVE_ENV (strips interactive
#   prompts), 120s/600s timeout bounds, SIGINT on timeout.
#
# ai-factory gap: factory/common/subprocess.py:41 (subprocess.run) uses
#   no _NONINTERACTIVE_ENV guard. Timeout override at :26 can be set
#   to None (infinite). :51 (SIGKILL) only fires after timeout — no
#   SIGINT-first policy. factory/tools/shell.py (dedicated bash wrapper)
#   does NOT exist.
#
# Insertion point: factory/common/subprocess.py:41 (subprocess.run)
#   - Inject _NONINTERACTIVE_ENV (strip PS1, disable prompts)
#   - Cap timeout at 120s (default), 600s (max override)
#   - Send SIGINT at timeout, then SIGKILL after 5s grace
#   - factory/tools/shell.py (new file — dedicated bash wrapper)


# --- Insertion example (factory/common/subprocess.py:41) ---
# import os, signal, subprocess
#
# _NONINTERACTIVE_ENV = {
#     **os.environ,
#     "PS1": "", "PS2": "",
#     "DEBIAN_FRONTEND": "noninteractive",
#     "PYTHONUNBUFFERED": "1",
# }
#
# def _run_shell(cmd: str, timeout: int = 120) -> str:
#     timeout = min(max(timeout, 1), 600)  # cap: 1s..600s
#     proc = subprocess.run(
#         cmd, shell=True, capture_output=True, text=True,
#         env=_NONINTERACTIVE_ENV,
#         timeout=timeout,
#         preexec_fn=os.setsid,  # new process group for clean SIGINT
#     )
#     return proc.stdout


# =====================================================================
# 9. NO ORPHAN TOOL CALLS  (OW-09)
# =====================================================================
# openworker: engine.py:651 (_interrupted_tool) — on stop/interrupt/deny,
#   every PENDING tool_call gets a _tool_error_message appended so no
#   tool call is left orphaned in the conversation.
# openworker: engine.py:757 (_authorize) — denied tools get error feedback.
#
# ai-factory gap: factory/infra/_loopguard.py:614 (get_safe_recent_messages)
#   handles compaction boundaries only. No orphan-tool prevention on
#   stop/cancel/deny/interrupt. factory/infra/tools_guard.py:160-168
#   (current gates) raises RuntimeError/warning but does NOT inject a
#   ToolError message into the conversation for pending calls.
#
# Insertion point: factory/infra/tools_guard.py:160 (call_tool stop path)
#   - On stop/cancel/deny/unknown: raise ToolError(json.dumps({...}))
#     for EVERY pending tool_call so none is orphaned
#   - factory/infra/_loopguard.py:614 (get_safe_recent_messages)


# =====================================================================
# 10. TESTING STRATEGY & MOCK PROVIDER  (OW-10)
# =====================================================================
# openworker: tests/test_engine.py — MockChatProvider with scripted
#   ToolError responses + inline-snapshot on normalized event sequences.
#
# ai-factory gap: factory/tests/ only has test_dynamic_budget.py.
#   tests/test_loopguard.py:29 uses TestModel (pydantic-ai mock) but
#   no MockChatProvider pattern. tests/_probe.py:28 (HarnessProbe)
#   records BIFR events but no snapshot-based eval gate.
#   tests/bifr/ has replay/freeze/boundary tests but no inline-snapshot
#   on normalized event/message sequences.
#
# Insertion point: factory/tests/test_ow_evals.py (new file)
#   - MockChatProvider with scripted ToolError responses
#   - inline-snapshot on normalized event/message sequences
#   - factory/tests/test_loopguard.py:29 (existing TestModel usage to extend)
#   - tests/bifr/ (replay harness to extend)
#   - tests/_probe.py:28 (HarnessProbe — add snapshot comparison)


# =====================================================================
# IMPLEMENTATION PRIORITY (for LLM reliability fix)
# =====================================================================

# Priority 1 (OW-01 + OW-09): Error feedback + no orphan calls
#   -> Tools_guard.py call_tool: try/except + ToolError injection on ALL exit
#      paths. This is the single highest-impact anti-hallucination fix.

# Priority 2 (OW-02): Deny-by-default permission engine
#   -> GuardToolset.call_tool: RiskClass + Mode gate prevents hallucinated
#      destructive tool calls from ever executing.

# Priority 3 (OW-08): Shell safety
#   -> subprocess.py: _NONINTERACTIVE_ENV + timeout bounds prevents bad
#      LLM commands from hanging the harness.

# Priority 4 (OW-06): Auto-compaction
#   -> _loopguard.py: 85% trigger + trim fallback prevents overflow corruption.

# Priority 5 (OW-10): Testing strategy
#   -> factory/tests/test_ow_evals.py: MockChatProvider + snapshot gates
#      prevent regressions of OW-01 through OW-08.

# =====================================================================
# WHAT NOT TO ADOPT (openworker-specific interactive UX)
# =====================================================================

# - openworker's TUI / approval facade (interactive UX for terminal agents)
#   — ai-factory is a deterministic batch conductor, no interactive approval
# - openworker's OAuth2 device-flow — ai-factory uses static ControlSheet
# - openworker's Session model (context.jsonl + wire.jsonl per workdir) —
#   ai-factory uses factory/artefacts/ + factory/orch/reports/ (different layout)
# - Phantom role names (coder/planner/red_team/supervisor) — map to
#   intern/engineer/senior only
