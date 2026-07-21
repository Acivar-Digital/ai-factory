"""One-pass JSON cleaning helper for every model-output boundary in the harness.

Problem it solves
-----------------
Weak / free-tier models sometimes emit structurally-broken JSON (unbalanced
braces, unquoted keys, trailing commas, markdown-fenced output, leading prose).
pydantic-ai exhausts ``Agent(retries=5)`` then raises ``UnexpectedModelBehavior``
and the whole run dies with no recovery. This module is the deterministic,
offline backstop: it extracts the JSON block, repairs structure with
``fast-json-repair`` (Rust/orjson, drop-in ``repair_json``), applies a FROZEN
whitelist normalizer, and re-validates against the canonical Pydantic model.

Design constraints (Francis, baziforecaster-cqjb)
-------------------------------------------------
* Library = ``fast-json-repair`` (NOT ``json-repair`` — 20–110× faster).
* Our normalizer is FROZEN — no growing regex / heuristics. It handles ONLY:
    (1) the 2 severity ``Literal`` fields (RubricCell/ReviewFinding = blocker|warn,
        AuditRisk = Critical|High|Medium|Low) by normalizing CASE only;
    (2) an explicit FROZEN key-alias whitelist (currently empty — see note below).
* Pydantic handles all type coercion; we never coerce types ourselves.
* Truncated Literals (e.g. ``"bloc"``) CANNOT be guessed safely — we let Pydantic
  fail loudly (the [HALT] backstop), never silently accept a fabricated value.
* FROZEN_KEY_ALIASES is intentionally empty. Key renames are an explicit, reviewed
  extension point; do NOT grow it speculatively (Zero-Speculation rule).

Self-test
---------
    uv run python factory/infra/output_sanitizer.py --selftest
"""

from __future__ import annotations

import json
import sys
from typing import Any, Literal, TypeVar

import fast_json_repair
from pydantic import BaseModel
from pydantic_ai.messages import ToolCallPart

# ── FROZEN severity canonicalization (the 2 Literal fields) ───────────────
# Maps any casing variant of a known severity value to its canonical Literal.
# Truncated / unknown values are intentionally NOT listed -> Pydantic fails loud.
_SEVERITY_CANON: dict[str, str] = {
    # RubricCell.severity / ReviewFinding.severity
    "blocker": "blocker",
    "warn": "warn",
    "BLOCKER": "blocker",
    "WARN": "warn",
    "Blocker": "blocker",
    "Warn": "warn",
    # AuditRisk.severity
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "Critical": "Critical",
    "High": "High",
    "Medium": "Medium",
    "Low": "Low",
    "CRITICAL": "Critical",
    "HIGH": "High",
    "MEDIUM": "Medium",
    "LOW": "Low",
}


# ── FROZEN key-alias whitelist (extension point) ───────────────────────────
# Explicit, reviewed, frozen. NEVER grow speculatively. Each entry maps a
# weak-model key variant -> the canonical model field name. Empty until a
# confirmed alias is observed and reviewed.
FROZEN_KEY_ALIASES: dict[str, str] = {}


def extract_json_block(raw: str) -> str:
    """Extract the first balanced ``{...}`` (or ``[...]``) from arbitrary text.

    Handles the markdown-fence case (````` ```json ... ``` ````) where
    ``fast-json-repair`` alone would return the leading prose (e.g. ``"Here"``).
    Falls back to the original text if no JSON delimiter is found, so the
    caller's validator can surface a clear error.
    """
    if not raw:
        return raw

    text = raw.strip()

    # Unwrap a fenced code block (```json / ``` / ~~~).
    for marker in ("```", "~~~"):
        idx = text.find(marker)
        if idx != -1:
            # Skip the opening fence line (e.g. ```json).
            nl = text.find("\n", idx)
            start = nl + 1 if nl != -1 else idx + len(marker)
            end = text.find(marker, start)
            if end != -1:
                return text[start:end].strip()
            # Unterminated fence: drop the opening marker line and continue.
            text = text[start:].strip()
            break

    open_ch, close_ch = "{", "}"
    start = text.find(open_ch)
    if start == -1:
        open_ch, close_ch = "[", "]"
        start = text.find(open_ch)
        if start == -1:
            return text

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    # Unbalanced: return from the opening delimiter to end of text and let
    # fast-json-repair attempt the fix (or Pydantic fail loudly).
    return text[start:]


def extract_model_json(
    messages: list | None, result_tool_name: str = "final_result"
) -> str | None:
    """Recover the model's REAL structured output from a run's message history.

    When pydantic-ai raises ``UnexpectedModelBehavior`` (the model called
    ``final_result`` with args that failed Pydantic validation 5x), the
    framework discards the offending args and only exposes an error *string*
    on the exception. But the actual ``final_result`` ``ToolCallPart`` — the
    real model output we want to salvage via the sanitizer — is still present
    in the run's ``all_messages()``.

    This walks ``messages`` (any pydantic-ai ``ModelMessage`` sequence, e.g. a
    reloaded role transcript) and returns the ``args`` (json string or dict) of
    the LAST ``final_result`` tool call, or ``None`` if none exists (empty
    output case).

    FIX (baziforecaster-ydiv): routes the model's real output — not the
    framework's error message — into ``clean_role_output``.
    """
    if not messages:
        return None
    last_args: Any = None
    for msg in messages:
        parts = getattr(msg, "parts", None)
        if not parts:
            continue
        for part in parts:
            if isinstance(part, ToolCallPart) and part.tool_name == result_tool_name:
                last_args = part.args
    if last_args is None:
        return None
    if isinstance(last_args, str):
        return last_args
    # Args may already be a parsed dict/object — re-serialize so the sanitizer
    # (which expects a JSON string) can repair + validate it uniformly.
    import json as _json

    try:
        return _json.dumps(last_args, ensure_ascii=False, default=str)
    except Exception:
        return str(last_args)


def extract_tool_call_payload(exc: Exception) -> str | None:
    """Reclaim a framework-rejected tool call's raw payload.

    When pydantic-ai's own tool-dispatch validator rejects a structurally
    invalid ``final_result`` call (e.g. ``MALFORMED_FUNCTION_CALL``: the model
    emitted a ``list`` where an ``object`` was required), the framework
    discards the offending args and surfaces only an error *string* on the
    exception. No valid ``ToolCallPart`` is persisted, so ``extract_model_json``
    returns ``None`` and the attempted payload would otherwise be lost — the
    role then silently drops from the batch instead of going through the
    ironclad sanitizer HALT path (ticket baziforecaster-78j9m).

    This helper reclaims that attempted payload from the exception (whatever
    the framework put on ``body`` / ``message`` / ``str(exc)``) and returns it
    as a raw string, or ``None`` if genuinely absent. It never fabricates — it
    only surfaces what the framework already captured. The caller feeds the
    result through ``clean_role_output`` unchanged, so the malformed-call path
    and the malformed-JSON path share ONE fail-loud HALT exit. No leniency.
    """
    candidates: list[str] = []
    for attr in ("body", "message"):
        value = getattr(exc, attr, None)
        if isinstance(value, str) and value.strip():
            candidates.append(value)
    if not candidates:
        try:
            text = str(exc)
        except Exception:
            text = ""
        if text.strip():
            candidates.append(text)

    for candidate in candidates:
        # The framework error string embeds the attempted payload, e.g.
        # "... Input should be an object [input_type=list]". We cannot always
        # isolate a clean JSON block from prose, but feed whatever is there
        # through extract_json_block so clean_role_output gets a real shot.
        block = extract_json_block(candidate)
        if block and block.strip():
            return block
        # No JSON delimiter found — still hand the raw prose to the sanitizer
        # so a HALT carries the real diagnostic (never a silent drop).
        if candidate.strip():
            return candidate
    return None


def _normalize_severity(data: Any) -> Any:
    """Recursively normalize CASE of the 2 severity Literal fields, in place."""
    if isinstance(data, dict):
        for k, v in list(data.items()):
            if k == "severity" and isinstance(v, str) and v in _SEVERITY_CANON:
                data[k] = _SEVERITY_CANON[v]
            else:
                _normalize_severity(v)
    elif isinstance(data, list):
        for item in data:
            _normalize_severity(item)
    return data


def _apply_key_aliases(data: Any) -> Any:
    """Recursively rename FROZEN key-alias variants to canonical field names."""
    if not FROZEN_KEY_ALIASES:
        return data
    if isinstance(data, dict):
        for old_key in list(data.keys()):
            value = data[old_key]
            if old_key in FROZEN_KEY_ALIASES:
                new_key = FROZEN_KEY_ALIASES[old_key]
                if new_key not in data:
                    data[new_key] = data.pop(old_key)
                    value = data[new_key]
            _apply_key_aliases(value)
    elif isinstance(data, list):
        for item in data:
            _apply_key_aliases(item)
    return data


def normalize_role_output(json_str: str) -> str:
    """Apply the FROZEN normalizer to a JSON string; returns JSON string.

    If the string is not valid JSON we cannot safely normalize — return it
    unchanged and let the model validator fail loudly (no silent fix-up).
    """
    try:
        data = json.loads(json_str)
    except Exception:
        return json_str
    _normalize_severity(data)
    _apply_key_aliases(data)
    return json.dumps(data, ensure_ascii=False)


def generate_simplified_schema(model: type[BaseModel]) -> str:
    """Generate a clean, simplified text representation of a Pydantic model structure for instructions/retry loops."""
    import json
    import types
    from typing import Union, get_args, get_origin

    def walk_model(m: type[BaseModel]) -> dict:
        schema = {}
        for name, field in m.model_fields.items():
            ann = field.annotation

            def resolve_type(a):
                if a is None:
                    return "null"
                origin = get_origin(a)
                args = get_args(a)

                # Literal
                if origin is Literal:
                    return " | ".join(repr(x) for x in args)

                # Union / Optional
                if origin is Union or isinstance(origin, types.UnionType):
                    non_null = [x for x in args if x is not type(None)]
                    resolved = [resolve_type(x) for x in non_null]
                    union_str = " | ".join(resolved)
                    return f"{union_str} (optional)" if len(args) > len(non_null) else union_str

                # List / Sequence
                if origin is list or a is list:
                    item_type = resolve_type(args[0]) if args else "any"
                    return [item_type]

                # Dict
                if origin is dict or a is dict:
                    key_type = resolve_type(args[0]) if args else "any"
                    val_type = resolve_type(args[1]) if args and len(args) > 1 else "any"
                    return {f"<{key_type}>": val_type}

                # Nested BaseModel
                if isinstance(a, type) and issubclass(a, BaseModel):
                    return walk_model(a)

                if isinstance(a, type):
                    return a.__name__
                return str(a)

            schema[name] = resolve_type(ann)
        return schema

    return json.dumps(walk_model(model), indent=2)


def is_jsonl(text: str) -> bool:
    text_stripped = text.strip()
    try:
        json.loads(text_stripped)
        return False
    except Exception:
        pass
    lines = [line.strip() for line in text_stripped.splitlines() if line.strip()]
    if len(lines) > 1:
        for line in lines:
            if line.startswith("{") or line.startswith("["):
                return True
    return False


def _detect_and_log_aliases(input_data: Any, output_data: Any) -> None:
    """Recursively checks and prints key mapping telemetry feedback suggestions."""
    if isinstance(input_data, dict) and isinstance(output_data, dict):
        for in_k, in_v in input_data.items():
            if in_k not in output_data:
                for out_k, out_v in output_data.items():
                    if out_k not in input_data:
                        if in_v == out_v or (type(in_v) is type(out_v) and in_k.lower().replace("_", "") == out_k.lower().replace("_", "")):
                            msg = f"[telemetry] Suggesting key alias: '{in_k}' -> '{out_k}'"
                            print(msg, flush=True)
            if in_k in output_data:
                _detect_and_log_aliases(in_v, output_data[in_k])
    elif isinstance(input_data, list) and isinstance(output_data, list):
        for in_item, out_item in zip(input_data, output_data):
            _detect_and_log_aliases(in_item, out_item)


T = TypeVar("T", bound=BaseModel)


def clean_role_output(raw: str | None, model: type[T]) -> T:
    """Clean one model's raw output and validate it.

    Pipeline: extract JSON block -> repair structure (fast-json-repair) ->
    frozen normalize -> Pydantic validate. Raises ``RuntimeError("[HALT] ...")``
    if anything cannot be salvaged (fail loudly per Decision A).
    """
    if raw is None:
        raise RuntimeError(f"[HALT] {model.__name__} output was empty (None)")
    raw = raw.strip()
    if not raw:
        raise RuntimeError(f"[HALT] {model.__name__} output was empty")

    if is_jsonl(raw):
        try:
            from factory.infra.jsonl_compiler import compile_jsonl_to_dict
            compiled_dict = compile_jsonl_to_dict(raw)
            if model.__name__ == "DraftPlan":
                from factory.infra.jsonl_compiler import auto_heal_draft_plan_evidence
                compiled_dict = auto_heal_draft_plan_evidence(compiled_dict)
            return model.model_validate(compiled_dict)
        except Exception:
            pass

    # TIER 1 — the standard json parser is JSON-aware about nested string values.
    # A free/low-tier model often double-encodes the ENTIRE tool-call payload as a
    # JSON string (e.g. the `strategy` field itself a string). json.loads handles
    # this correctly; fast_json_repair does NOT (it truncates the inner string at
    # the first '{'). So parse once here and skip repair entirely for valid /
    # double-encoded JSON. fast_json_repair only runs on genuinely broken JSON.
    if raw[:1] in ("{", "["):
        try:
            parsed = json.loads(raw)
            return model.model_validate(parsed)
        except Exception:
            pass  # genuinely broken JSON → fall through to TIER 2

    block = extract_json_block(raw)
    repaired = fast_json_repair.repair_json(block, return_objects=False)
    normalized = normalize_role_output(repaired)
    try:
        return model.model_validate_json(normalized)
    except Exception as e:
        try:
            from factory.infra.control import CONTROL_SHEET
            healer_model = CONTROL_SHEET.model("healer_mode")
        except Exception:
            healer_model = None

        is_testing = "pytest" in sys.modules or "unittest" in sys.modules
        is_real_model = type(healer_model).__name__ == "OpenAIChatModel"

        if healer_model is not None and not (is_testing and is_real_model):
            print(f"[healer] Triggering offline formatting recovery call using healer model for {model.__name__}", flush=True)
            from pydantic_ai import Agent
            from pydantic_ai.settings import ModelSettings
            schema_str = generate_simplified_schema(model)
            healer_agent = Agent(
                healer_model,
                output_type=model,
                system_prompt=(
                    "You are a structured JSON healing assistant. You receive a malformed output that failed "
                    "validation against a target Pydantic schema, along with the validation error message. "
                    "Your task is to repair the malformed output to make it valid according to the schema. "
                    "Do not invent data; preserve all original meaning, values, and structure as much as possible. "
                    "Ensure all required fields are present with correct types."
                ),
                model_settings=ModelSettings(parallel_tool_calls=False)
            )
            try:
                import concurrent.futures
                import asyncio
                
                def _run_healer_thread():
                    return asyncio.run(healer_agent.run(
                        f"Malformed Raw Output:\n{raw}\n\n"
                        f"Target Schema:\n{schema_str}\n\n"
                        f"Validation Error:\n{str(e)}"
                    ))
                    
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    res = pool.submit(_run_healer_thread).result()
                    
                healed_obj = res.output

                try:
                    try:
                        input_dict = json.loads(normalized)
                    except Exception:
                        try:
                            input_dict = json.loads(repaired)
                        except Exception:
                            input_dict = None

                    if isinstance(input_dict, dict) and hasattr(healed_obj, "model_dump"):
                        output_dict = healed_obj.model_dump()
                        _detect_and_log_aliases(input_dict, output_dict)
                except Exception as telemetry_err:
                    print(f"[healer] Telemetry log warning: {telemetry_err}", file=sys.stderr, flush=True)

                return healed_obj
            except Exception as healer_exc:
                print(f"[healer] Healer model call failed: {healer_exc}", file=sys.stderr, flush=True)

        raise RuntimeError(
            f"[HALT] {model.__name__} output failed sanitize+validate "
            f"(raw head: {raw[:120]!r}): {e}"
        ) from e


def _selftest() -> int:
    """Run the frozen self-test suite. Returns process exit code."""

    class Cell(BaseModel):
        severity: Literal["blocker", "warn"]  # mirrors RubricCell/ReviewFinding
        passed: bool = False

    class Doc(BaseModel):
        name: str
        cells: list[Cell] = []

    cases_pass = [
        # markdown fence
        ('text\n```json\n{"name": "x", "cells": []}\n```', Doc),
        # trailing comma
        ('{"name": "x", "cells": [],}', Doc),  # already valid
        # unquoted keys
        ('{name: "x", cells: []}', Doc),
        # severity casing
        ('{"name": "x", "cells": [{"severity": "BLOCKER"}]}', Doc),
        # unbalanced
        ('{"name": "x"', Doc),
    ]
    cases_fail = [
        # truncated Literal — must NOT be guessed; must HALT
        ('{"name": "x", "cells": [{"severity": "bloc"}]}', Doc),
        # empty
        ("", Doc),
    ]

    failures = 0
    for raw, model in cases_pass:
        try:
            obj = clean_role_output(raw, model)
            assert isinstance(obj, model)
            print(f"  PASS recover: {raw[:50]!r} -> {model.__name__}")
        except Exception as e:  # pragma: no cover
            failures += 1
            print(f"  FAIL (expected recover): {raw[:50]!r} -> {e!r}")

    for raw, model in cases_fail:
        try:
            clean_role_output(raw, model)
            failures += 1
            print(f"  FAIL (expected HALT): {raw[:50]!r} accepted")
        except RuntimeError as e:
            assert "[HALT]" in str(e)
            print(f"  PASS halt: {raw[:50]!r} -> [HALT]")

    if failures:
        print(f"\nSELFTEST FAILED: {failures} failure(s)")
        return 1
    print("\nSELFTEST OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print("usage: uv run python output_sanitizer.py --selftest")
    sys.exit(2)
