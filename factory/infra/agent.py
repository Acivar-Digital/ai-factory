"""Agent lifecycle, spawning, recovery, and telemetry."""
from __future__ import annotations

import copy
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import logfire

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior

from factory.common import (
    OUTPUT_TYPE_REGISTRY, ROLE_OUTPUT_TYPE,
    build_md_bridge, log_operator, resolve_model, resolve_run_dir,
)
from factory.infra._loopguard import run_with_loopguard, CONTEXT_COMPACT_CEILING, compact_memory_gate, estimate_tokens
from factory.infra.artefacts import persist_role
from factory.infra.control import (
    DEFAULT_AGENT_SETTINGS, LOGS_DIR, ROLE_AGENT_SETTINGS,
    RUNTIME_DIR, SKILL_MAP,
)
from factory.infra._runtime import RAW_OUTPUTS, PHASE_SUMMARIES, SCOPE_CONTEXT
from factory.infra.exchange import (
    _detect_and_mark_recovery, _model_to_md,
)
from factory.infra.output_sanitizer import clean_role_output, extract_model_json, extract_tool_call_payload
from factory.infra.tools import (
    _DISCOVERY_TOOLS, _TOOL_BY_NAME, DEFAULT_TOOL_BUDGET, ROLE_TOOL_BUDGET,
    assert_planner_emitted, build_skill_spec, guard_tools,
    pydantic_ai_default_block, wrap_injected_context, set_current_agent, set_current_role, log_response_raw,
)


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


def _load_role_messages(role: str, agent_id: str | None = None) -> list | None:
    """Reconstruct a role's cumulative `message_history` from its `<role>.jsonl`."""
    try:
        from factory.infra.artefacts import load_role_messages

        return load_role_messages(role, agent_id=agent_id)
    except Exception as exc:
        print(f"[WARN] _load_role_messages failed for {role!r}: {exc!r}", flush=True)
        return None


async def load_skill(role: str, brief: str, bd: str = "", task_id: str | None = None) -> str:
    """Invoke a role's frozen YAML skill. Uses loopguard for timeout + failure transcript."""
    if role not in ROLE_OUTPUT_TYPE:
        return f"[HALT] unknown role {role!r}"

    # Bind the active role (+ agent id for coder isolation) so the `remember`
    # tool writes to THIS agent's folder (per-coderN isolated memory, a101k).
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
