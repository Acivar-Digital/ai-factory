"""Artefacts sink — persist each role's message history + structured output.

Lives INSIDE the orchestrator sandbox (factory/), NEVER at repo root.
Mirrors the harness's per-role execution into a clean, role-organised tree:

    factory/artefacts/
      history/   <role>/<role>.jsonl   (full message transcript, native re-injectable)
      history/   <role>/<role>.md       (human-readable twin)
      workplan/  <role>/<role>.json      (parsed Pydantic output)

Role -> folder mapping (matches the requested artefact layout):
    planner            -> planner
    supervisor_plan    -> planner_sup
    coder              -> coder
    supervisor_review  -> coder_sup
    red_team           -> red_team

`ops` is intentionally excluded (not in ROLE_FOLDER).

ONE aggregated `<role>.jsonl` (+ `.md` twin) per role folder. Content accumulates
across turns/subtasks — the framework's `message_history` is cumulative, so each
turn we take `result.all_messages()`, EVICT read-bloat, and rewrite the whole
file. A fresh D2 subagent has no inherited history, so this file IS its continuity
bridge (runner.load_skill reconstructs `message_history` from it).

Additive only: every write is wrapped so a failure here can NEVER abort the
pipeline. Wired from runner.load_skill (the single spawn seam for all 5 roles).
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from factory.infra.control import REPO_ROOT

from . import converter

# ── Eviction ("evict reads, keep writes") constants ──────────────────────────
# Reads whose returned content exceeds this char count are collapsed to a
# 1-line anchor (`File read: <path>`); the full content is dropped into a
# write-only `file_cache` (keyed by (path, mtime)) that is NEVER read back.
SIZE_THRESHOLD = 2000

# Write/edit tools: keep a bundle (old vs new) in history (high-value, small).
WRITE_BUNDLE_TOOLS = {
    "replace_text",
    "replace_function",
    "write_file",
    "add_constant",
    "add_import",
}

# Structural tools: one-line action note only.
STRUCTURAL_TOOLS = {"delete_file", "rename_file", "move_symbol"}

# Dead-store: full read content keyed by (path, mtime). Write-only by design
# (the spec's `file_cache`); never consulted on replay, so it cannot go stale.
file_cache: dict[tuple[str, float], str] = {}

# factory/infra/artefacts.py -> parents[1] == factory (sandbox root)
PKG_DIR = Path(__file__).resolve().parents[1]


def artefacts_dir() -> Path:
    """Resolve the artefacts root, allowing an env override.

    Overridable via ``ORCHESTRATOR_ARTEFACTS_DIR`` so tests can redirect
    role-history writes (rotate_role_transcript / persist_messages) to a
    tmp_path instead of the live sandbox sink. Resolved lazily (per-call)
    so a ``monkeypatch.setenv`` installed AFTER this module was imported
    still takes effect. Defaults to the persistent ``artefacts/`` tree.
    """
    return Path(os.environ.get("ORCHESTRATOR_ARTEFACTS_DIR", PKG_DIR / "artefacts")).resolve()

ROLE_FOLDER: dict[str, str] = {
    "planner": "planner",
    "supervisor_plan": "planner_sup",
    "coder": "coder",
    "supervisor_review": "coder_sup",
    "red_team": "red_team",
}


def read_latest_md(role: str) -> str | None:
    """Return the content of the most recent MD transcript for *role*, or None."""
    folder = ROLE_FOLDER.get(role)
    if not folder:
        return None
    hist = artefacts_dir() / "history" / folder
    if not hist.is_dir():
        return None
    mds = sorted(hist.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mds:
        return None
    return mds[0].read_text(encoding="utf-8")


_CLEARED_FOLDERS: set[Path] = set()

def _clear_folder(d: Path) -> None:
    """Delete all files in the given directory once per Python session."""
    if d in _CLEARED_FOLDERS:
        return
    _CLEARED_FOLDERS.add(d)

    if not d.is_dir():
        return
    import shutil
    for item in d.iterdir():
        if item.is_file():
            try:
                item.unlink()
            except OSError:
                pass
        elif item.is_dir():
            try:
                shutil.rmtree(item)
            except OSError:
                pass



def _tag(result: object) -> str:
    out = getattr(result, "output", None)
    tid = getattr(out, "task_id", None)
    return tid or "run"


def persist_role(role: str, result: object, agent_id: str | None = None) -> None:
    """Persist a role's RunResult to artefacts/history + artefacts/workplan.

    `result` is a pydantic_ai RunResult (has .output and .all_messages()).
    No-op (silent) if the role is not in ROLE_FOLDER. On ANY persist failure we
    log loudly to stderr/run.log but DO NOT raise — the pipeline must continue.
    For the coder role with a non-None `agent_id`, the transcript is isolated to
    ``coder/<agent_id>.jsonl`` (per-coderN memory, ticket a101k).
    """
    folder = ROLE_FOLDER.get(role)
    if not folder or result is None:
        return

    # 1. Structured output -> workplan/<role>/ (single file per role).
    try:
        out_obj = getattr(result, "output", None)
        if out_obj is not None:
            wp = artefacts_dir() / "workplan" / folder
            wp.mkdir(parents=True, exist_ok=True)
            _clear_folder(wp)
            (wp / f"{folder}.json").write_text(
                out_obj.model_dump_json(indent=2), encoding="utf-8"
            )
    except Exception as exc:  # never abort the pipeline over artefacts
        print(f"[PERSIST ERROR] workplan write failed for {role}: {exc!r}", flush=True)

    # 2. Full message transcript -> history/<role>/ (EVICTED, whole-file rewrite).
    try:
        _persist_transcript(folder, role, result.all_messages(), agent_id=agent_id)  # type: ignore[attr-defined]
    except Exception as exc:  # never abort the pipeline over artefacts
        print(f"[PERSIST ERROR] transcript write failed for {role}: {exc!r}", flush=True)


def persist_messages(
    role: str,
    messages: list[ModelMessage],
    *,
    tag: str = "run",
    agent_id: str | None = None,
) -> None:
    """Persist a raw message list to artefacts/history/<role>/ even when no RunResult exists.

    Used on failure paths (e.g. the loopguard crash-dump) so EVERY agent — especially
    the coder/EXECUTE phase — leaves a debuggable transcript under its role folder,
    not only on success. For the coder role with a non-None `agent_id`, the transcript
    is isolated to ``coder/<agent_id>.jsonl``. `messages` may be any iterable of
    pydantic-ai ModelMessages. No-op (silent) if the role is unknown. On error we
    log loudly but do NOT raise.
    """
    folder = ROLE_FOLDER.get(role)
    if not folder or not messages:
        return
    try:
        _persist_transcript(folder, role, messages, agent_id=agent_id)
    except Exception as exc:
        print(f"[PERSIST ERROR] persist_messages failed for {role}: {exc!r}", flush=True)


def _clean_messages(messages: list[ModelMessage] | Any) -> list[ModelMessage]:
    from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart
    import dataclasses
    clean = []
    for m in messages:
        if isinstance(m, ModelRequest) and m.parts:
            new_parts = []
            for p in m.parts:
                if isinstance(p, (SystemPromptPart, UserPromptPart)):
                    if str(p.content).startswith("<!-- MD_LEDGER -->"):
                        continue
                new_parts.append(p)
            if not new_parts:
                continue
            if len(new_parts) != len(m.parts):
                m = dataclasses.replace(m, parts=new_parts)
        clean.append(m)
    return clean

def _file_cache_store(path: str, content: str) -> None:
    """Write-only dead-store of full read content keyed by (path, mtime).

    The content is deliberately NEVER read back — it exists only so a full file
    read is verifiably removed from the token stream (the `file_cache` pattern
    from context.md). Coder is fresh per task (D2) so no other subagent mutates
    its files mid-run → staleness is impossible.
    """
    try:
        mtime = os.path.getmtime(REPO_ROOT / path) if (REPO_ROOT / path).exists() else 0.0
    except OSError:
        mtime = 0.0
    file_cache[(path, mtime)] = content


def _write_bundle(tool_name: str, args: dict[str, Any]) -> str:
    """Build an old-vs-new bundle for a write/edit tool from its tool-CALL args."""
    path = args.get("relative_path", args.get("source_relative_path", "?"))
    old = args.get("target_text") or args.get("function_name") or "(new content)"
    new = (
        args.get("replacement_text")
        or args.get("new_function_code")
        or args.get("content")
        or args.get("constant_code")
        or args.get("import_code")
        or ""
    )
    label = {
        "replace_text": "replaced text",
        "replace_function": "replaced function body",
        "write_file": "wrote file",
        "add_constant": "added constant",
        "add_import": "added import",
    }.get(tool_name, "edited")
    return (
        f"\n\n[WRITE] {tool_name} ({label}) path={path}\n"
        f"--- original ---\n{old}\n"
        f"--- your write ---\n{new}"
    )


def _structural_note(tool_name: str, args: dict[str, Any]) -> str:
    """One-line action note for a structural (no-content) tool."""
    if tool_name == "delete_file":
        return f"\n\n[ACTION] deleted {args.get('relative_path', '?')}"
    if tool_name == "rename_file":
        return (
            f"\n\n[ACTION] renamed "
            f"{args.get('source_relative_path', '?')} -> "
            f"{args.get('destination_relative_path', '?')}"
        )
    if tool_name == "move_symbol":
        return (
            f"\n\n[ACTION] moved {args.get('symbol_name', '?')} "
            f"from {args.get('source_path', '?')} to {args.get('dest_path', '?')}"
        )
    return f"\n\n[ACTION] {tool_name}"


def _evict_dicts(dicts: list[dict]) -> list[dict]:
    """Apply the EVICTION transform on a list of message dicts.

    - `read_file` returns over SIZE_THRESHOLD → collapse to `File read: <path>`
      (+ dead-store the full content in `file_cache`).
    - write/edit tool-returns → append an old-vs-new bundle (from the matching
      tool-CALL args).
    - structural tool-returns → append a one-line action note.
    - `investigate` / `search` (and all other tools) → left untouched (they are
      LLM-refined, not bloat).
    """
    # Index tool-call args by tool_call_id so we can pair a return with its call.
    call_args: dict[str, dict[str, Any]] = {}
    for m in dicts:
        for p in m.get("parts", []):
            if p.get("part_kind") == "tool-call":
                cid = p.get("tool_call_id")
                args = p.get("args")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                if not isinstance(args, dict):
                    args = {}
                call_args[cid] = args

    out: list[dict] = []
    for m in dicts:
        new_parts: list[dict] = []
        for p in m.get("parts", []):
            if p.get("part_kind") != "tool-return":
                new_parts.append(p)
                continue
            name = p.get("tool_name")
            cid = p.get("tool_call_id")
            content = p.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            elif isinstance(content, str) and content.strip().startswith(("{", "[")):
                try:
                    content = json.loads(content)
                except Exception:
                    pass
            if name == "read_file":
                args = call_args.get(cid, {})
                path = args.get("relative_path", "?")
                if len(content) > SIZE_THRESHOLD:
                    _file_cache_store(path, content)
                    p = dict(p, content=f"File read: {path}")
            elif name == "batch_read":
                # batch_read historically returned a JSON envelope
                # {"success": true, "data": [{"file_path", "content", ...}]}
                # (or a single dict). Evict that envelope + full file bodies to
                # file_cache and collapse to `File read: <path>` anchors, exactly
                # like read_file. WITHOUT this, the envelope + every file's full
                # content leaked verbatim into the transcript.
                #
                # BUT as of the read_file.py fix, batch_read returns SCOPED PLAIN
                # text (a `=== File read: <path> ===` header + file text, possibly
                # several files joined). In that case `content` is a plain string
                # with NO envelope — keep it AS-IS (it is already clean + small
                # enough). Wiping it would destroy the transcript (the bug we hit
                # on the 2026-07-18 re-run).
                if isinstance(content, dict) and "data" in content:
                    paths: list[str] = []
                    try:
                        data = content["data"]
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            fpath = item.get("file_path") or item.get("path") or "?"
                            fcontent = item.get("content", "")
                            if isinstance(fcontent, str) and len(fcontent) > SIZE_THRESHOLD:
                                _file_cache_store(fpath, fcontent)
                            paths.append(f"File read: {fpath}")
                    except Exception:
                        paths = ["File read: (batch_read envelope)"]
                    p = dict(p, content="\n".join(paths))
                # else: plain-text batch_read output — leave content untouched.
            elif name in WRITE_BUNDLE_TOOLS:
                args = call_args.get(cid, {})
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False)
                p = dict(p, content=content + _write_bundle(name, args))
            elif name in STRUCTURAL_TOOLS:
                args = call_args.get(cid, {})
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False)
                p = dict(p, content=content + _structural_note(name, args))
            # investigate / search / others: untouched.
            new_parts.append(p)
        out.append(dict(m, parts=new_parts))
    return out


def _evict_messages(messages: list[ModelMessage] | Any) -> list[ModelMessage]:
    """Round-trip `messages` through JSON to apply `_evict_dicts`."""
    raw = ModelMessagesTypeAdapter.dump_json(messages)
    dicts = json.loads(raw)
    evicted = _evict_dicts(dicts)
    return list(ModelMessagesTypeAdapter.validate_json(json.dumps(evicted)))


def _persist_transcript(
    folder: str,
    role: str,
    messages: list[ModelMessage] | Any,
    tag: str = "",
    agent_id: str | None = None,
) -> None:
    """Write ONE aggregated transcript + `.md` under history/<folder>/.

    The framework's `message_history` is cumulative, so we rewrite the WHOLE
    file each call (no per-turn file sprawl). The JSONL is the native,
    re-injectable source (`ModelMessagesTypeAdapter`); the MD is the human twin.
    The EVICTION transform is applied to the messages BEFORE serializing so the
    accumulated file stays bounded and safely re-injectable. For the coder role
    with a non-None `agent_id`, the file is the agent-isolated ``<agent_id>.jsonl``
    (per-coderN memory, ticket a101k) — distinct from the shared ``coder.jsonl``.
    """
    messages = _clean_messages(messages)
    evicted = _evict_messages(messages)
    hist = artefacts_dir() / "history" / folder
    hist.mkdir(parents=True, exist_ok=True)
    fname = Path(_history_filename(role, agent_id)).stem  # one aggregated file per (role|agent)
    jsonl_path = hist / f"{fname}.jsonl"
    jsonl_path.write_text(
        ModelMessagesTypeAdapter.dump_json(evicted).decode(), encoding="utf-8"
    )
    # Per-message RECORD-time timestamps (context.md Req 4). The transcript is
    # cumulative and rewritten whole-file each persist, so a message's true
    # record time must be frozen from its own pydantic-ai timestamp, not the
    # whole-file rewrite time. ModelResponse carries a message-level `timestamp`;
    # ModelRequest's timestamp is None but its parts (e.g. UserPromptPart) carry
    # one. Guard both: fall back to now() per message if no usable timestamp.
    ts_fmt = "%Y-%m-%d-%H:%M:%S"

    def _record_ts(m: object) -> str:
        try:
            msg_ts = getattr(m, "timestamp", None)
            if isinstance(msg_ts, datetime):
                return msg_ts.strftime(ts_fmt)
            for part in getattr(m, "parts", []) or []:
                part_ts = getattr(part, "timestamp", None)
                if isinstance(part_ts, datetime):
                    return part_ts.strftime(ts_fmt)
        except Exception:
            pass
        return datetime.now().strftime(ts_fmt)

    timestamps = [_record_ts(m) for m in evicted]
    md_path = converter.convert_file(
        jsonl_path, timestamps=timestamps if len(timestamps) == len(evicted) else None
    )
    print(f"[artefacts] +md {md_path.name} ({md_path.stat().st_size} bytes)", flush=True)


def _history_filename(role: str, agent_id: str | None) -> str:
    """Resolve the transcript filename for a role, honouring per-agent isolation.

    Per locked design (baziforecaster-a101k / grill-me 2026-07-18): when `role`
    is the coder and an `agent_id` is supplied (e.g. ``coder3`` derived from the
    planner's ``ApprovedTask.id``), the transcript is scoped to that SINGLE agent
    (``coder/coder3.jsonl``) so parallel coders never share one store. Without an
    `agent_id` the legacy role-scoped filename is used (backwards-compatible).
    """
    folder = ROLE_FOLDER.get(role)
    if not folder:
        return f"{role}.jsonl"
    if role == "coder":
        # Per-coderN isolation (ticket a101k / baziforecaster-chq80): a coder
        # transcript MUST be scoped to a concrete `agent_id` (e.g. `coder3`).
        # Refusing to fall back to the legacy shared `coder.jsonl` guarantees the
        # shared file can never be recreated after the loopguard persist paths were
        # fixed to thread `agent_id`.
        if not agent_id:
            raise ValueError(
                "[HALT] _history_filename called for role 'coder' with "
                "agent_id=None — a shared coder.jsonl would recreate the legacy "
                "context-bloat store. Every coder spawn must pass agent_id."
            )
        return f"{agent_id}.jsonl"
    return f"{folder}.jsonl"


def load_role_messages(role: str, agent_id: str | None = None) -> list[ModelMessage] | None:
    """Reconstruct a role's cumulative `message_history` from its `<role>.jsonl`.

    Returns None when the role is unknown or no transcript exists yet. Used by
    runner.load_skill to feed a fresh D2 subagent its continuity bridge. For the
    coder role with a non-None `agent_id`, the transcript is the agent-isolated
    ``coder/<agent_id>.jsonl`` (per-coderN isolated memory, ticket a101k).
    """
    folder = ROLE_FOLDER.get(role)
    if not folder:
        return None
    jsonl_path = artefacts_dir() / "history" / folder / _history_filename(role, agent_id)
    if not jsonl_path.exists():
        return None
    dicts = converter.read_messages(jsonl_path)
    if not dicts:
        return None
    try:
        return list(ModelMessagesTypeAdapter.validate_json(json.dumps(dicts)))
    except Exception as exc:
        print(f"[artefacts] load_role_messages failed for {role}: {exc!r}", flush=True)
        return None


def rotate_role_transcript(
    role: str,
    compacted_messages: list[ModelMessage],
    agent_id: str | None = None,
) -> None:
    """Write-back rotation for the keep_memory compaction gate.

    The compacted `message_history` (a leading `SystemPromptPart(keep_memory)` +
    the safe recent tail) becomes the role's new official transcript (``<role>.jsonl``
    or, for an isolated coder agent, ``coder/<agent_id>.jsonl``) + `.md`. The
    PREVIOUS aggregated file is renamed to ``<name>.compact<N>.jsonl`` (a SNAPSHOT —
    never deleted; N increments per compaction: compact1, compact2…) before the
    fresh aggregated file is written, so every prior state stays recoverable. The
    `.md` twin is re-rendered from the fresh jsonl. For the coder role, the snapshot
    is also agent-scoped (``coderN.compactM.jsonl``) — never-prune applies per agent.

    No-op (silent) if the role is unknown. On ANY failure we log loudly but do
    NOT raise — rotation must never abort the pipeline.
    """
    folder = ROLE_FOLDER.get(role)
    if not folder or not compacted_messages:
        return
    try:
        messages = _clean_messages(compacted_messages)
        evicted = _evict_messages(messages)
        hist = artefacts_dir() / "history" / folder
        hist.mkdir(parents=True, exist_ok=True)
        fname = _history_filename(role, agent_id)
        jsonl_path = hist / fname

        # Snapshot the current aggregated file (if any) as compact<N>.
        n = 1
        while (hist / f"{Path(fname).stem}.compact{n}.jsonl").exists():
            n += 1
        if jsonl_path.exists():
            jsonl_path.rename(hist / f"{Path(fname).stem}.compact{n}.jsonl")

        # Fresh aggregated write = [SystemPromptPart(keep_memory)] + recent tail.
        jsonl_path.write_text(
            ModelMessagesTypeAdapter.dump_json(evicted).decode(), encoding="utf-8"
        )
        ts_fmt = "%Y-%m-%d-%H:%M:%S"

        def _record_ts(m: object) -> str:
            try:
                msg_ts = getattr(m, "timestamp", None)
                if isinstance(msg_ts, datetime):
                    return msg_ts.strftime(ts_fmt)
                for part in getattr(m, "parts", []) or []:
                    part_ts = getattr(part, "timestamp", None)
                    if isinstance(part_ts, datetime):
                        return part_ts.strftime(ts_fmt)
            except Exception:
                pass
            return datetime.now().strftime(ts_fmt)

        timestamps = [_record_ts(m) for m in evicted]
        md_path = converter.convert_file(
            jsonl_path, timestamps=timestamps if len(timestamps) == len(evicted) else None
        )
        print(
            f"[artefacts] rotated {role}: snapshot compact{n}, "
            f"fresh {jsonl_path.name} +md {md_path.name}",
            flush=True,
        )
    except Exception as exc:
        print(f"[PERSIST ERROR] rotate_role_transcript failed for {role}: {exc!r}", flush=True)


def remember_note(role: str, note: str, agent_id: str | None = None) -> None:
    """Append a `remember` note to the agent's OWN role history (<role>.jsonl + .md).

    Write-only to the own role folder. For the coder role with a non-None
    `agent_id`, the note lands in that agent's isolated ``coder/<agent_id>.jsonl``
    (keep_memory stays PRIVATE to coderN, never promoted to global_alignment —
    ticket a101k, Q5). The note is stored as a synthetic `tool-return` message so
    it round-trips through `ModelMessagesTypeAdapter` and is re-injected as context
    on the agent's next turn. No-op if role unknown.
    """
    folder = ROLE_FOLDER.get(role)
    if not folder:
        return
    hist = artefacts_dir() / "history" / folder
    hist.mkdir(parents=True, exist_ok=True)
    jsonl_path = hist / _history_filename(role, agent_id)
    ts = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
    msg = {
        "kind": "request",
        "parts": [
            {
                "part_kind": "tool-return",
                "tool_name": "remember",
                "content": note,
                "tool_call_id": f"remember-{ts}",
            }
        ],
    }
    dicts: list[dict] = []
    if jsonl_path.exists():
        dicts = converter.read_messages(jsonl_path)
    dicts.append(msg)
    jsonl_path.write_text(json.dumps(dicts, ensure_ascii=False), encoding="utf-8")
    converter.convert_file(jsonl_path)
