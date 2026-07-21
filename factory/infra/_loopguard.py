"""Reference loop-guard + context-compaction gate (build.md §8.2c, §8.5).

   Three knobs kill 95% of brute-force tool loops:
   1. parallel_tool_calls=False on every agent (one tool per turn).
   2. tools=[] on recovery -> forced answer; tool_choice="none" (from
      DEFAULT_AGENT_SETTINGS) reinforces text-only on providers that honor it.
   3. explicit tool results -> no retry justification.
Plus the token-budget compaction gate (dual-sink).
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.usage import UsageLimits

from factory.infra.control import (
    COMPACTION_CONFIG,
    CONTROL_SHEET,
    DEFAULT_AGENT_SETTINGS,
    ORCH_ROOT,
    PKG_DIR,
    PerRoleConfig,
)
from factory.infra.models import CompactedContext

MAX_LOOPGUARD_TURNS = 20  # hard backstop; per-run UsageLimits resets each agent.run() so the outer loop is otherwise unbounded
MAX_TOTAL_TOOL_CALLS = 10  # hard ceiling on total tool calls across all turns; after this force RECOVER

AGENT_RUN_TIMEOUT = 600.0  # hard per-run() backstop so an unresponsive model fails loudly instead of hanging forever


def dereference_schema(schema: dict) -> dict:
    """Recursively inline all $ref references from $defs/definitions and remove defs."""
    if not isinstance(schema, dict):
        return schema

    defs = schema.get("$defs", {})
    if not defs:
        defs = schema.get("definitions", {})

    def _resolve_refs(node):
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"]
                parts = ref_path.lstrip("#/").split("/")
                if len(parts) == 2 and parts[0] in ("$defs", "definitions"):
                    def_name = parts[1]
                    if def_name in defs:
                        resolved = _resolve_refs(defs[def_name].copy())
                        return resolved
            return {k: _resolve_refs(v) for k, v in node.items()}
        elif isinstance(node, list):
            return [_resolve_refs(item) for item in node]
        return node

    new_schema = _resolve_refs(schema)
    if isinstance(new_schema, dict):
        new_schema.pop("$defs", None)
        new_schema.pop("definitions", None)
    return new_schema


def extract_tool_calls(result, result_tool_name: str = "final_result") -> list[ToolCallPart]:
    """Tool calls from the FINAL ModelResponse only, EXCLUDING the result tool.

    pydantic-ai's run() aggregates the entire internal turn-loop
    (model→tool→model→...→final answer) into new_messages(). Summing EVERY
    intermediate call makes the 'model answered' gate never fire for a
    tool-using agent (the orchestrator always emits load_skill internally) →
    the loopguard re-enters and re-runs phases forever. Only the LAST
    ModelResponse is the terminal answer.

    CRITICAL: when an agent has an `output_type`, pydantic-ai returns the
    structured result by emitting a call to the RESULT TOOL (default name
    `final_result`). That call IS present in the final ModelResponse — so it
    must be EXCLUDED here, or the loopguard mistakes "the model answered"
    for "a pending tool call" and re-runs the agent forever (every role then
    loops until max_same triggers RECOVER). A run ending in `final_result`
    (with no other pending function calls) is the terminal answer.
    """
    for msg in reversed(result.new_messages()):
        if isinstance(msg, ModelResponse):
            return [
                p
                for p in msg.parts
                if isinstance(p, ToolCallPart) and p.tool_name != result_tool_name
            ]
    return []


def tool_signature(calls: list[ToolCallPart]) -> str:
    sigs = []
    for c in calls:
        args = c.args_as_dict()  # pydantic_ai: method, returns the call args as a dict
        sigs.append(f"{c.tool_name}:{json.dumps(args, sort_keys=True)}")
    return "|".join(sigs)


def extract_tool_returns(result) -> list[tuple[str, str]]:
    """This turn's tool returns as (tool_name, content_str) for no-progress detection."""
    out = []
    for msg in result.new_messages():
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    content = part.content
                    out.append(
                        (part.tool_name, content if isinstance(content, str) else str(content))
                    )
    return out


def result_signature(returns: list[tuple[str, str]]) -> str:
    """Hash the tool-return CONTENT (not just args) for no-progress detection.

    A model that keeps re-calling a tool and getting the SAME non-empty result
    is spinning in place. Two distinct calls with identical results trips
    neither the identical-signature guard (different args) nor the miss-streak
    guard (non-empty results), so we hash the content and watch for repeats.
    """
    return "|".join(f"{n}:{hash(c)}" for n, c in returns)


def _dump_failure(fail_dir: Path, phase, role, history, limits, exc, agent_id: str | None = None) -> None:
    """Persist the agent's accumulated 'thinking' even when a phase FAILS.

    Failed runs previously wrote nothing (eval/transcript only fire on success),
    so post-mortems were impossible. We dump current_history (all turns up to the
    failing one) + the error + the request cap. Never let logging mask the real error.
    """
    try:
        payload = {
            "phase": phase,
            "role": role,
            "error": f"{type(exc).__name__}: {exc}",
            "request_limit": getattr(limits, "request_limit", None),
            "messages": json.loads(ModelMessagesTypeAdapter.dump_json(history)),
        }
        out = fail_dir / f"fail_{phase or 'run'}_{role or 'agent'}.json"
        out.write_text(json.dumps(payload, indent=2, default=str))
    except Exception as _exc:
        print(
            f"[loopguard._dump_failure] FAILED to persist failure dump: "
            f"{type(_exc).__name__}: {_exc}",
            file=sys.stderr,
            flush=True,
        )

    # Infra-level guarantee: the failure transcript MUST land in the same role
    # folder the operator expects (artefacts/history/<role>/), not only in
    # logs/runtime/fail_*.json. Without this, the coder/EXECUTE phase leaves
    # zero debuggable history on a crash/hang (SA5-F2). Additive + never fatal.
    try:
        from factory.infra.artefacts import persist_messages

        persist_messages(role, list(history), tag="FAILED", agent_id=agent_id)
    except Exception as _exc:
        print(
            f"[loopguard._dump_failure] FAILED to persist role history: "
            f"{type(_exc).__name__}: {_exc}",
            file=sys.stderr,
            flush=True,
        )


def _log_turn(io_dir: Path, phase, role, tag: str, prompt: str,
              sent_history: list, received: list) -> None:
    """Persist BOTH directions every turn so a run is fully investigable:
    what we SENT (prompt + message_history) and what we RECEIVED (new messages).
    No more digging blind proxy logs to see what the model was fed / returned.
    """
    try:
        path = io_dir / f"io_{phase or 'run'}_{role or 'agent'}.log"
        sent_json = ModelMessagesTypeAdapter.dump_json(sent_history).decode()
        recv_json = ModelMessagesTypeAdapter.dump_json(received).decode()
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n===== {tag} | phase={phase} role={role} =====\n")
            f.write(f"--- SENT prompt ---\n{prompt}\n")
            f.write(f"--- SENT history ({len(sent_history)} msgs) ---\n{sent_json}\n")
            f.write(f"--- RECEIVED ({len(received)} msgs) ---\n{recv_json}\n")
    except Exception as _exc:
        print(
            f"[loopguard._log_turn] FAILED to persist io log: "
            f"{type(_exc).__name__}: {_exc}",
            file=sys.stderr,
            flush=True,
        )


async def run_with_loopguard(
    agent: Agent,
    prompt: str,
    history: list[ModelMessage] | None = None,
    max_same: int = 3,
    max_miss: int = 3,
    state=None,
    phase: str | None = None,
    role: str | None = None,
    deps=None,
    timeout: float = AGENT_RUN_TIMEOUT,
    require_transcript: bool = False,
    agent_id: str | None = None,
) -> Any:
    if not role:
        raise RuntimeError("[HALT] run_with_loopguard called without a 'role'. Role is mandatory for transcript persistence.")

    seen: dict[str, int] = {}
    miss_streak: int = 0
    current_history = list(history) if history else []
    # CHANGE 2 (01_fix.md): A-B-A-B alternation detector.
    # Track the last distinct signature; when it differs from the previous one
    # twice in a row (X→Y→X→Y) we have a ping-pong loop that NEVER trips the
    # identical-signature guard. Force RECOVER — reuse the recovery block below.
    alt_prev: str | None = None
    alt_count: int = 0
    # CHANGE 2b: no-op same-result detector. Hash the tool-return content (not
    # just args); if the SAME result keeps coming back the model is spinning in
    # place. Track repeats and force RECOVER at the same max_same threshold.
    last_result_sig: str | None = None
    result_repeat: int = 0
    # Align the hard request cap with each role's GuardToolset tool budget.
    # pydantic-ai counts MODEL REQUESTS (~2 per tool call: call + result), so the
    # cap is budget * 2. Coder (75) -> 150; planner (10) -> 20; others (15) -> 30.
    # Replaces the old fixed 40 that killed tool-looping coders before they could
    # emit final_result (see session_crash.md coder_4 UsageLimitExceeded).
    role_request_cap = {
        "planner": 20, "planner_sup": 20, "supervisor_plan": 20,
        "coder": 150, "supervisor_review": 30, "red_team": 30, "ops": 30,
    }
    limits = UsageLimits(request_limit=role_request_cap.get(role, 30))
    fail_dir = ORCH_ROOT / "logs" / "runtime"
    fail_dir.mkdir(parents=True, exist_ok=True)
    io_dir = fail_dir / "io"
    io_dir.mkdir(parents=True, exist_ok=True)
    turn = 0
    total_tool_calls = 0

    # ── INTERCEPT MODEL.REQUEST FOR LIVE PER-TURN MD LOGGING ──────────
    if hasattr(agent, 'model') and agent.model and role:
        from factory.infra.artefacts import persist_messages, read_latest_md

        original_request = agent.model.request

        import types

        async def intercepted_request(self, messages, model_settings, *args, **kwargs):
            # This fires BEFORE every internal model request in pydantic-ai
            from pydantic import BaseModel
            from pydantic_ai.messages import ModelRequest, ToolReturnPart

            # Dereference schemas for all tools to prevent Vertex AI / Gemini API $ref failures
            mrp = kwargs.get("model_request_parameters")
            if mrp is None and args:
                mrp = args[0]
            if mrp is not None:
                for tools_list in (getattr(mrp, "function_tools", []), getattr(mrp, "output_tools", [])):
                    if tools_list:
                        for tool in tools_list:
                            if hasattr(tool, "parameters_json_schema") and isinstance(tool.parameters_json_schema, dict):
                                tool.parameters_json_schema = dereference_schema(tool.parameters_json_schema)
                            if hasattr(tool, "return_schema") and isinstance(tool.return_schema, dict):
                                tool.return_schema = dereference_schema(tool.return_schema)
                output_obj = getattr(mrp, "output_object", None)
                if output_obj is not None:
                    if hasattr(output_obj, "json_schema") and isinstance(output_obj.json_schema, dict):
                        output_obj.json_schema = dereference_schema(output_obj.json_schema)

            result_tool_name = getattr(agent, "result_tool_name", "final_result")
            output_type = getattr(agent, "output_type", None)
            if output_type and isinstance(output_type, type) and issubclass(output_type, BaseModel):
                for msg in messages:
                    if isinstance(msg, ModelRequest):
                        for part in msg.parts:
                            if isinstance(part, ToolReturnPart) and part.tool_name == result_tool_name:
                                from factory.infra.output_sanitizer import generate_simplified_schema
                                schema_str = generate_simplified_schema(output_type)
                                enrichment = (
                                    f"\n\n=== EXPECTED SCHEMA FORMAT ===\n"
                                    f"Your output must conform to the following Pydantic schema structure:\n"
                                    f"{schema_str}\n"
                                    f"Please ensure all fields are present with correct types and format."
                                )
                                if enrichment not in str(part.content):
                                    if isinstance(part.content, str):
                                        part.content += enrichment
                                    else:
                                        part.content = f"{part.content}{enrichment}"

            persist_messages(role, messages, tag=f"live_{turn}", agent_id=agent_id)
            if require_transcript:
                # Production path: a persist layer is active, so the role's MD
                # transcript is expected to exist (reloaded via D2 continuity).
                # Absence means the run never started — HALT loudly.
                md_content = read_latest_md(role)
                if not md_content:
                    raise RuntimeError(f"[HALT] MD transcript for role '{role}' was not generated or is empty!")
            return await original_request(messages, model_settings, *args, **kwargs)

        agent.model.request = types.MethodType(intercepted_request, agent.model)
        _patched_model_request = agent.model  # restore in finally (shared-model safety)
        _original_request = original_request
    else:
        _patched_model_request = None
        _original_request = None
    # ──────────────────────────────────────────────────────────────────

    try:
        while True:
            turn += 1
            if turn > MAX_LOOPGUARD_TURNS:
                raise RuntimeError(
                    f"[HALT] Loopguard hard limit reached ({turn} turns) for {role or 'RUN'}. "
                    f"Agent is stuck exploring without progress."
                )
            print(f"[{phase or 'RUN'}] turn {turn} → calling model...", flush=True)
            try:
                res = await asyncio.wait_for(
                    agent.run(
                        prompt,
                        message_history=current_history,
                        usage_limits=limits,
                        deps=deps,
                    ),
                    timeout=timeout,
                )
            except UsageLimitExceeded as exc:
                # CHANGE 3 (01_fix.md): a coder that exhausts the (now generous) request
                # cap is NOT a hard failure — force a best-effort answer with tools=[] so
                # the pipeline continues. Without this, UsageLimitExceeded propagated as a
                # [HALT] that marked the task blocked and aborted the whole EXECUTE phase
                # (see session_crash.md coder_4). `res` is undefined on this exception, so
                # recover from current_history.
                _dump_failure(fail_dir, phase, role, current_history, limits, exc, agent_id=agent_id)
                print(
                    f"[{phase or 'RUN'}] request_limit hit for {role}; forcing RECOVER (no HALT)",
                    flush=True,
                )
                recovery_agent = Agent(
                    agent.model,
                    output_type=agent.output_type,
                    tools=[],
                    model_settings=DEFAULT_AGENT_SETTINGS,
                )
                recovered = await asyncio.wait_for(
                    recovery_agent.run(
                        "You exhausted the request budget without finishing. Return your "
                        "best answer now (or state you are BLOCKED) using final_result.",
                        message_history=current_history,
                    ),
                    timeout=AGENT_RUN_TIMEOUT,
                )
                _log_turn(io_dir, phase, role, f"RECOVER-USAGE {turn}", "UsageLimitExceeded", current_history, recovered.new_messages())
                return recovered
            except ModelHTTPError as exc:
                if exc.status_code == 400:
                    attempts = getattr(agent, '_malformed_retries', 0) + 1
                    agent._malformed_retries = attempts
                    if attempts <= 3:
                        delay = 5 * attempts
                        print(
                            f"[{phase or 'RUN'}] turn {turn} got 400 (attempt {attempts}/3); "
                            f"retrying in {delay}s...",
                            flush=True,
                        )
                        await asyncio.sleep(delay)
                        continue
                _dump_failure(fail_dir, phase, role, current_history, limits, exc, agent_id=agent_id)
                raise
            except Exception as exc:
                # FAIL LOUDLY — but persist the thinking first so the failure is readable.
                _dump_failure(fail_dir, phase, role, current_history, limits, exc, agent_id=agent_id)
                raise
            print(f"[{phase or 'RUN'}] turn {turn} ← returned", flush=True)

            _log_turn(io_dir, phase, role, f"TURN {turn}", prompt, current_history, res.new_messages())
            calls = extract_tool_calls(res, getattr(agent, "result_tool_name", "final_result"))

            # ── Total tool call ceiling ────────────────────────────────────────
            if calls:
                total_tool_calls += len(calls)
                if total_tool_calls > MAX_TOTAL_TOOL_CALLS:
                    print(f"[{phase or 'RUN'}] turn {turn}: {total_tool_calls} tool calls exceeded limit → force RECOVER", flush=True)
                    recovery_prompt = (
                        f"You made {total_tool_calls} research tool calls across {turn} turns "
                        f"(limit {MAX_TOTAL_TOOL_CALLS}). Stop researching. Return your best "
                        f"answer now, or state you are BLOCKED."
                    )
                    recovery_agent = Agent(
                        agent.model,
                        output_type=agent.output_type,
                        tools=[],
                        model_settings=DEFAULT_AGENT_SETTINGS,
                    )
                    recovered = await asyncio.wait_for(
                        recovery_agent.run(
                            recovery_prompt, message_history=res.all_messages()
                        ),
                        timeout=AGENT_RUN_TIMEOUT,
                    )
                    _log_turn(io_dir, phase, role, f"FORCED-RECOVER {turn}", recovery_prompt, res.all_messages(), recovered.new_messages())
                    return recovered
            # ─────────────────────────────────────────────────────────────────

            # ── Per-turn MD transcript write ──────────────────────────────────
            md_content = None
            if role:
                from factory.infra.artefacts import persist_messages, read_latest_md
                persist_messages(role, res.all_messages(), tag=f"turn_{turn}", agent_id=agent_id)
                if require_transcript:
                    # Production path: a persist layer is active, so the role's MD
                    # transcript must have been written. Absence means the persist
                    # layer failed — HALT loudly rather than proceed blind.
                    md_content = read_latest_md(role)
                    if not md_content:
                        raise RuntimeError(f"[HALT] MD transcript for role '{role}' was not generated or is empty!")
            # ──────────────────────────────────────────────────────────────────

            if not calls:
                return res  # model answered

            # Compaction gate (SINK-1 live-loop relief). The compacted history REPLACES
            # current_history so the agent resumes with bounded context. We must NOT
            # overwrite it with the un-compacted res.all_messages() afterward — that was
            # the dead-code bug (current_history reset every turn, compaction discarded).
            if state is not None and phase is not None:
                current_history = await maybe_compact(
                    res.all_messages(), agent.model, state, phase, role=role
                )
            else:
                current_history = res.all_messages()

            # ── Inject the transcript into the surviving history ──────────────
            if md_content:
                from pydantic_ai.messages import ModelRequest, SystemPromptPart
                current_history.insert(
                    0,
                    ModelRequest(parts=[SystemPromptPart(content=f"<!-- MD_LEDGER -->\n{md_content}")])
                )
                print(f"[{phase or 'RUN'}] ✅ Injected MD transcript ({len(md_content)} bytes) into agent memory for next turn", flush=True)
            # ──────────────────────────────────────────────────────────────────

            sig = tool_signature(calls)
            seen[sig] = seen.get(sig, 0) + 1

            # CHANGE 2a (01_fix.md): A-B-A-B alternation detector. Two DISTINCT sigs
            # ping-ponging (X→Y→X→Y) never trips the identical-signature guard above, so
            # detect it explicitly and force RECOVER early (before the request cap burns).
            if alt_prev is not None and sig != alt_prev:
                alt_count += 1
            else:
                alt_count = 0
            alt_prev = sig

            # No-progress detector: a tool returned empty / "NOT FOUND" (the LLM got
            # nothing useful). A model that cycles DIFFERENT empty calls (e.g. guessing
            # recall_fact keys) never trips the identical-signature guard above — so we
            # track empty/miss returns and tell it to STOP and move on (fail cheaply).
            returns = extract_tool_returns(res)
            miss_tools = sorted(
                {n for n, c in returns if (c or "").strip() == "" or "NOT FOUND" in (c or "")}
            )
            if miss_tools:
                miss_streak += 1
            else:
                miss_streak = 0

            # CHANGE 2b (01_fix.md): no-op same-result detector. The SAME tool-return
            # content keeps coming back — the model is spinning in place. Hash content
            # (not args) and watch for repeats; reuse the identical-sig threshold.
            rsig = result_signature(returns)
            if rsig and rsig == last_result_sig:
                result_repeat += 1
            else:
                result_repeat = 0
            last_result_sig = rsig

            if seen[sig] >= max_same or miss_streak >= max_miss or alt_count >= 2 or result_repeat >= max_same:
                # KNOB 2: RECOVER, never raise. tools=[] forces an answer on ANY provider.
                if seen[sig] >= max_same:
                    stalled = calls[0].tool_name
                    reason = f"repeated tool(s) {max_same}x with no progress"
                elif miss_streak >= max_miss:
                    stalled = ", ".join(miss_tools) if miss_tools else calls[0].tool_name
                    reason = f"tool(s) [{stalled}] returned empty / NOT FOUND {max_miss}x"
                elif alt_count >= 2:
                    stalled = sig
                    reason = "A-B-A-B tool ping-pong (no progress)"
                else:
                    stalled = ", ".join(n for n, _ in returns) or calls[0].tool_name
                    reason = f"no-op same result repeated {max_same}x"
                recovery_prompt = (
                    f"You stalled: {reason}. Stop tool-calling. "
                    "Return your best answer now, or state you are BLOCKED."
                )
                recovery_agent = Agent(
                    agent.model,
                    output_type=agent.output_type,
                    tools=[],
                    model_settings=DEFAULT_AGENT_SETTINGS,
                )
                recovered = await asyncio.wait_for(
                    recovery_agent.run(
                        recovery_prompt, message_history=res.all_messages()
                    ),
                    timeout=AGENT_RUN_TIMEOUT,
                )
                _log_turn(io_dir, phase, role, f"RECOVER {turn}", recovery_prompt, res.all_messages(), recovered.new_messages())
                return recovered

            prompt = ""  # clear prompt for subsequent turns
            if miss_tools:
                # Tell the LLM to fuck off the dead tool and move on (cheap nudge before
                # the hard recovery above fires). Injected as the next user turn.
                prompt = (
                    f"HALT: tool(s) {miss_tools} returned empty / NOT FOUND. Do NOT re-call "
                    "them with guessed variants. Move on — take the next phase step or return "
                    "your best answer. If you are BLOCKED, say so explicitly instead of looping."
                )
    finally:
        # Shared-model safety: roles like planner + supervisor_plan resolve to the
        # SAME model object (control.CONTROL_SHEET). The intercepted
        # `request` closure captures `role`, so leaving it patched leaks one role's
        # per-turn persist into another role's history folder. Always restore the
        # original request on exit (normal return OR exception).
        if _patched_model_request is not None:
            _patched_model_request.request = _original_request


# ── Context Compaction Gate (§8.5) ──────────────────────────────────────
KEEP_RECENT = COMPACTION_CONFIG.keep_recent_messages


def get_safe_recent_messages(
    agent_msgs: list[ModelMessage], keep: int
) -> list[ModelMessage]:
    """Last `keep` messages, walked FORWARD past any leading ToolReturnPart.

    The compacted summary (a SystemPromptPart) is prepended before this slice, so
    the slice must not begin mid tool-call/return — an orphan ToolReturnPart (a tool
    result whose call was churned) would make the API reject the request with 400.
    A leading ModelRequest that is purely tool-returns is skipped until we hit a
    valid turn boundary (user/system request or a model response with tool calls).
    """
    if len(agent_msgs) <= keep:
        return agent_msgs
    recent = agent_msgs[-keep:]
    idx = 0
    while idx < len(recent):
        first = recent[idx]
        if isinstance(first, ModelRequest) and any(
            isinstance(p, ToolReturnPart) for p in first.parts
        ):
            idx += 1
            continue
        break
    return recent[idx:]


def _serialize(msg: ModelMessage) -> str:
    return ModelMessagesTypeAdapter.dump_json([msg]).decode()  # type: ignore[list-item]


_CJK_RE = re.compile(r"[\u3000-\u303F\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")


def estimate_tokens(msgs: list[ModelMessage]) -> int:
    if COMPACTION_CONFIG.token_estimate == "tiktoken":
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return sum(len(enc.encode(_serialize(m) or "")) for m in msgs)
    total = 0
    for m in msgs:
        s = _serialize(m) or ""
        cjk = len(_CJK_RE.findall(s))
        non_cjk = len(s) - cjk
        total += non_cjk // 4 + cjk // 2
    return total


async def maybe_compact(
    agent_msgs: list[ModelMessage],
    agent_model,
    state,
    phase: str,
    role: str | None = None,
) -> list[ModelMessage]:
    """Token-budget trigger. SINK-1 (live loop).

    The cross-phase L3 food chain is owned by `run_phase` (role-keyed
    `state.phase_summaries[role]`); this gate NEVER writes to phase_summaries
    (Q2) — its job is strictly intra-task survival so a long-running agent does
    not crash on ContextWindowExceeded.
    """
    profile = getattr(agent_model, "profile", None)
    window_obj = getattr(profile, "context_window", None) if profile else None
    window: int = int(window_obj) if window_obj is not None else 128000  # fall back if the running model exposes no window

    # Per-role budget (Q3/Q4): orchestrator gets the higher (~200K) window key and
    # a larger ceiling; workers stay small. We compact conservatively BEFORE the
    # provider latency wall (~200K) so both stay zippy.
    role_cfg = COMPACTION_CONFIG.per_role.get(role or "", PerRoleConfig())
    fraction = role_cfg.compact_at_fraction if role_cfg.compact_at_fraction is not None else COMPACTION_CONFIG.compact_at_fraction
    hard_max = role_cfg.hard_max_tokens if role_cfg.hard_max_tokens is not None else COMPACTION_CONFIG.hard_max_tokens
    budget = min(int(window * fraction), hard_max)
    if estimate_tokens(agent_msgs) <= budget:
        return agent_msgs

    # Resolve the summarizer MODEL (not the raw string key).
    summarizer_key = COMPACTION_CONFIG.summarizer_model
    summarizer_model = CONTROL_SHEET.model(summarizer_key)

    # Load the summarizer prompt from the orchestrator sandbox (no inline strings).
    prompt_path = PKG_DIR / "prompt" / "summarizer.yaml"
    try:
        with open(prompt_path) as f:
            summarizer_prompt = yaml.safe_load(f).get("system_instruction", "")
    except FileNotFoundError:
        summarizer_prompt = (
            "Compress the preceding tool-call trajectory into a neutral summary: "
            "what was searched, what was found, what remains open."
        )

    # Summarize the churned prefix (safe boundary so the summarizer never sees an
    # orphan tool-return as the first message).
    summary_history = get_safe_recent_messages(
        agent_msgs, max(len(agent_msgs) - KEEP_RECENT, 1)
    )
    summary_agent = Agent(
        summarizer_model,
        output_type=CompactedContext,
        model_settings=DEFAULT_AGENT_SETTINGS,
    )
    summary = await asyncio.wait_for(
        summary_agent.run(
            f"{summarizer_prompt}\n\nPhase: {phase}",
            message_history=summary_history,
        ),
        timeout=AGENT_RUN_TIMEOUT,
    )

    # SINK 1: live loop — agent resumes with bounded history (safe boundary).
    summary_text = (summary.output.summary or "").strip()
    if not summary_text or summary_text.upper() == "SUMMARY" or len(summary_text) < 40:
        return get_safe_recent_messages(agent_msgs, KEEP_RECENT)
    compacted = [
        ModelRequest(parts=[SystemPromptPart(content=summary_text)])
    ] + get_safe_recent_messages(agent_msgs, KEEP_RECENT)

    return compacted


# ── Cross-turn "keep_memory" Compaction Gate (§8.5 addendum) ──────────────
# Prior history is prepended into the next subagent's message_history UNCAPPED
# today (700K+ bloat). This gate bounds it using the SAME WORKING LLM — no
# separate compaction agent. Function A (the gate) lives in runner.load_skill;
# Function B (this module) is the compaction loop + summarizer fallback.
CONTEXT_COMPACT_CEILING = COMPACTION_CONFIG.CONTEXT_COMPACT_CEILING
CONTEXT_COMPACT_FLOOR = COMPACTION_CONFIG.CONTEXT_COMPACT_FLOOR
EMPTY_EXT_RETRIES = COMPACTION_CONFIG.EMPTY_EXT_RETRIES

_COMPACT_PROMPT_PATH = PKG_DIR / "prompt" / "compact_memory.yaml"

_COMPACT_INSTRUCTION = (
    "Your prior working memory is included below. It is too large to carry "
    "forward verbatim. Compact it NOW into a single dense memory dump you can "
    "continue from: keep only durable facts, decisions, constraints, open "
    "questions, and unresolved threads — drop chatter, raw file dumps, and "
    "redundant retries. Then call the keep_memory tool EXACTLY ONCE with that "
    "compacted text. Do NOT return the text as a normal answer; you MUST call "
    "keep_memory."
)

_COMPACT_RETRY = (
    "That dump is still too large to carry forward. Compact it FURTHER — "
    "collapse it to only the absolute essentials you need to continue, then call "
    "keep_memory AGAIN with the smaller text. Keep calling keep_memory with "
    "progressively tighter text until it fits."
)


def _load_compact_prompts() -> tuple[str, str]:
    """Load the compact_memory.yaml instructions; inline fallbacks if missing."""
    try:
        with open(_COMPACT_PROMPT_PATH) as f:
            data = yaml.safe_load(f) or {}
        return (
            data.get("compact_instruction", _COMPACT_INSTRUCTION),
            data.get("compact_retry", _COMPACT_RETRY),
        )
    except FileNotFoundError:
        return _COMPACT_INSTRUCTION, _COMPACT_RETRY


def _estimate_text_tokens(text: str) -> int:
    """Token estimate of a bare string (wraps it as a single SystemPromptPart)."""
    return estimate_tokens([ModelRequest(parts=[SystemPromptPart(content=text)])])


def _extract_keep_memory_text(messages: list[ModelMessage]) -> str | None:
    """Pull the externalized text the LLM passed to its `keep_memory` tool call."""
    for m in messages:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, ToolCallPart) and p.tool_name == "keep_memory":
                    args = p.args_as_dict()
                    txt = args.get("note") or args.get("text")
                    if isinstance(txt, str):
                        return txt
    return None


def _as_compacted(text: str, prior_history: list[ModelMessage]) -> list[ModelMessage]:
    """[SystemPromptPart(keep_memory)] + safe recent tail from prior_history."""
    return [ModelRequest(parts=[SystemPromptPart(content=text)])] + get_safe_recent_messages(
        prior_history, KEEP_RECENT
    )


async def _compact_memory_fallback(
    prior_history: list[ModelMessage],
    agent_model,
    state,
    phase: str,
    role: str | None,
) -> list[ModelMessage]:
    """Safety net: summarizer machinery (maybe_compact) → SystemPromptPart + tail.

    Reuses maybe_compact's summarizer-agent build + get_safe_recent_messages +
    COMPACTION_CONFIG["summarizer_model"]. Fails loudly if the reseeded memory
    still violates the 60K floor.
    """
    compacted = await maybe_compact(prior_history, agent_model, state, phase, role=role)
    summary_text: str | None = None
    for m in compacted:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, SystemPromptPart) and isinstance(p.content, str):
                    summary_text = p.content
    if not summary_text or _estimate_text_tokens(summary_text) < CONTEXT_COMPACT_FLOOR:
        raise RuntimeError(
            f"[HALT] compact_memory fallback for role {role!r} still violates the "
            f"{CONTEXT_COMPACT_FLOOR}-token floor after summarizer pass — refusing "
            f"to prepend an unbounded/empty memory."
        )
    if role:
        from factory.infra.artefacts import rotate_role_transcript

        rotate_role_transcript(role, compacted)
    return compacted


async def compact_memory_gate(
    prior_history: list[ModelMessage],
    agent_model,
    state,
    phase: str,
    role: str | None = None,
    agent_id: str | None = None,
) -> list[ModelMessage]:
    """Function B: keep_memory compaction loop + summarizer fallback.

    Called by Function A (runner.load_skill) ONLY when prior_history already
    exceeds CONTEXT_COMPACT_CEILING. Runs up to EMPTY_EXT_RETRIES passes with an
    agent whose ONLY tool is `keep_memory` (the working LLM, no separate agent),
    then falls back to the summarizer if still too large. Returns the compacted
    `message_history` ready to prepend. For an isolated coder agent, `agent_id`
    is forwarded to `rotate_role_transcript` so the snapshot is `coderN.compactM.jsonl`
    (ticket a101k, Q6 never-prune per agent).
    """
    compact_instruction, compact_retry = _load_compact_prompts()
    from factory.infra.tools import keep_memory

    memory: list[ModelMessage] = list(prior_history)
    for attempt in range(1, EMPTY_EXT_RETRIES + 1):
        prompt = compact_instruction if attempt == 1 else compact_retry
        agent = Agent(
            agent_model,
            tools=[keep_memory],
            model_settings=DEFAULT_AGENT_SETTINGS,
        )
        try:
            res = await asyncio.wait_for(
                agent.run(prompt, message_history=memory),
                timeout=AGENT_RUN_TIMEOUT,
            )
        except Exception as exc:
            raise RuntimeError(
                f"[HALT] keep_memory compaction pass {attempt} for role {role!r} "
                f"failed: {exc!r}"
            ) from exc

        text = _extract_keep_memory_text(res.all_messages())
        if not text or not text.strip():
            raise RuntimeError(
                f"[HALT] keep_memory returned an EMPTY externalization for role "
                f"{role!r} on pass {attempt} — refusing to prepend empty memory."
            )

        if _estimate_text_tokens(text) < CONTEXT_COMPACT_FLOOR:
            compacted = _as_compacted(text, prior_history)
            if role:
                from factory.infra.artefacts import rotate_role_transcript

                rotate_role_transcript(role, compacted, agent_id=agent_id)
            return compacted

        # Still too large: reseed the loop with the current compacted dump and
        # tell the LLM to compress further.
        memory = _as_compacted(text, prior_history)

    # 3 failed passes — fall back to the summarizer safety net.
    print(
        f"[compact_memory_gate] role={role!r}: {EMPTY_EXT_RETRIES} keep_memory "
        f"passes exceeded floor; falling back to summarizer",
        file=sys.stderr,
        flush=True,
    )
    return await _compact_memory_fallback(
        prior_history, agent_model, state, phase, role
    )
