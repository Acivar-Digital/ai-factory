"""Convert orchestrator artefacts (pydantic-ai message dumps) to markdown.

Reusable infra utility. Reads a JSON/JSONL dump produced by
`ModelMessagesTypeAdapter.dump_json(res.all_messages())` (the `artefacts/history`
sink) and writes a readable markdown twin alongside it (same folder, same stem,
`.md`). Keeps the JSON as the lossless/replayable source; the MD is the
human/analyzer-readable, token-cheaper view (~2.5x lighter on this corpus).

Usage:
    uv run python factory/infra/converter.py <input.jsonl> [--out <path.md>]
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _unwrap_json(value: object, _depth: int = 0) -> object:
    if not isinstance(value, str) or _depth > 5:
        return value
    try:
        parsed = json.loads(value)
    except Exception:
        return value
    if isinstance(parsed, str):
        return _unwrap_json(parsed, _depth + 1)
    return parsed


_READ_HDR = re.compile(r"===\s*File read:\s*(.+?)\s*(?:\(lines[^)]*\))?\s*===", re.IGNORECASE)


def _extract_envelope_body(text: str) -> str:
    """Given a `=== File read: <path> ===\n{...json envelope...}` block,
    pull out `data.content` (the real file text) and drop the
    `{"success": true, "message":..., "data": {...}}` cruft."""
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        parsed = json.loads(text[start:end])
    except Exception:
        return text  # not parseable -> leave as-is
    if not isinstance(parsed, dict) or "data" not in parsed:
        return text
    data = parsed["data"]
    if isinstance(data, list):
        return "\n".join(
            d.get("content", "") if isinstance(d, dict) else str(d)
            for d in data
        )
    if isinstance(data, dict):
        return data.get("content", "")
    return text


def _strip_read_envelope(content: object) -> object:
    """Clean a read-tool return for markdown rendering.

    Handles every stored shape:
      - a bare JSON envelope string `{"success": true, "data": {...}}`
      - a string with one or more `=== File read: <path> ===\n{...}` blocks
        (what batch_read actually persisted)
      - already-clean plain text (the new read_file output)
    Only the file *content* survives; the envelope keys never render.
    """
    if not isinstance(content, str):
        return content
    s = content.strip()
    # (a) bare envelope
    if (s.startswith("{") or s.startswith("[")) and '"success"' in s:
        return _extract_envelope_body(s)
    # (b) one or more '=== File read: ===' blocks wrapping a JSON envelope
    if "=== File read:" in s and '"success"' in s:
        out_parts: list[str] = []
        pos = 0
        for m in _READ_HDR.finditer(s):
            # text before this header (if any) — keep only if meaningful
            between = s[pos:m.start()].strip()
            if between and not between.startswith("==="):
                out_parts.append(between)
            block = s[m.start():]
            nxt = _READ_HDR.search(block[m.end() - m.start():])
            seg = block[: (nxt.start() + m.end() - m.start()) if nxt else len(block)]
            out_parts.append(f"{m.group(0)}\n{_extract_envelope_body(seg)}")
            pos = m.start() + len(seg)
        tail = s[pos:].strip()
        if tail:
            out_parts.append(tail)
        return "\n\n".join(out_parts)
    return content


_EDIT_TOOLS = {
    "replace_text",
    "replace_function",
    "write_file",
    "add_constant",
    "add_import",
    "delete_file",
    "rename_file",
    "move_symbol",
}

_CONTENT_NOISE = re.compile(r"\n*\[TOOL CALL[^\n]*")


def _strip_write_bundles(content: object) -> object:
    """Drop the `[WRITE] …` / `[TOOL CALL N/M]` bundles that tools.py appends
    to edit/write tool-returns. They are pure noise in the readable twin."""
    if not isinstance(content, str):
        return content
    content = _CONTENT_NOISE.sub("", content)
    idx = content.find("[WRITE]")
    if idx != -1:
        content = content[:idx].rstrip()
    return content


def _as_json_list(content: object) -> list | None:
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        s = content.strip()
        if s.startswith("["):
            try:
                parsed = json.loads(s)
            except Exception:
                return None
            return parsed if isinstance(parsed, list) else None
    return None


def _extract_edit_return(content: object, name: str) -> str:
    """Render an edit/write tool-return envelope verbatim.

    The tool prints ``{"success", "message", "data": {"diff": ...}}`` (the
    `diff` is a real unified-diff *string*, already JSON-encoded by the tool,
    so ``json.loads`` decodes ``\\u2014`` em-dashes etc. back to real chars).
    We surface ``data.diff`` inside a ```diff fence — this is the actual
    replacement block, no truncation, no re-escaping. The envelope may be
    trailed by harness noise (e.g. ``[WRITE] …`` / ``[TOOL CALL N/M]``), so
    isolate the JSON between the first `{` and last `}` before parsing."""
    if not isinstance(content, str):
        return _text(content)
    s = content.strip()
    d = None
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            d = json.loads(s[start : end + 1])
        except Exception:
            d = None
    if isinstance(d, dict):
        data = d.get("data") or {}
        msg = (d.get("message") or "").strip()
        if d.get("success") is False:
            err = d.get("error") or {}
            emsg = err.get("message") if isinstance(err, dict) else str(err)
            return f"❌ FAILED: {emsg or msg}"
        diff = data.get("diff") if isinstance(data, dict) else None
        if diff:
            return f"{msg}\n\n```diff\n{diff}\n```"
        return msg or s
    return s


def _json_to_ascii(obj: object) -> str:
    """Convert a JSON value into markdown-friendly ASCII (no ```json fences).

    dicts → `- **key**: value` bullets; lists → `- item` bullets; strings that
    look like paths get backticked; bools/None normalised."""
    if isinstance(obj, dict):
        if "evaluations" in obj and isinstance(obj["evaluations"], list):
            evals = obj["evaluations"]
            if evals:
                lines = [
                    "| Item ID | Approved | Comments |",
                    "| :--- | :--- | :--- |"
                ]
                for item in evals:
                    if isinstance(item, dict):
                        item_id = item.get("item_id", "?")
                        app = item.get("approved", "?")
                        comm = item.get("comments", "")
                        lines.append(f"| `{item_id}` | {app} | {comm} |")
                return "\n".join(lines)
        if not obj:
            return "_(empty)_"
        return "\n".join(f"- **{k}**: {_json_to_ascii(v)}" for k, v in obj.items())
    if isinstance(obj, list):
        if not obj:
            return "_(empty)_"
        # Detect list payloads that match the evaluation shape and format as table
        if all(isinstance(v, dict) and "item_id" in v and "approved" in v and "comments" in v for v in obj):
            lines = [
                "| Item ID | Approved | Comments |",
                "| :--- | :--- | :--- |"
            ]
            for item in obj:
                item_id = item.get("item_id", "?")
                app = item.get("approved", "?")
                comm = item.get("comments", "")
                lines.append(f"| `{item_id}` | {app} | {comm} |")
            return "\n".join(lines)
        return "\n".join(f"- {_json_to_ascii(v)}" for v in obj)
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if obj is None:
        return "(none)"
    if isinstance(obj, str) and (obj.startswith("src2/") or obj.startswith("admin/") or obj.endswith(".py")):
        return f"`{obj}`"
    return str(obj)


def _render_tool_call(p: dict) -> str:
    r"""Render a tool-call by CONVERTING its JSON args to markdown-friendly ASCII.

    - Code-body tools (write_file and friends) carry a full file/code body; the
      body is converted to a real ```python code block (not JSON-escaped, not
      dropped).
    - Every other tool's args are converted to a readable bullet list.
    No raw ```json fence is ever emitted.
    """
    name = p.get("tool_name", "?")
    args = p.get("args") or {}
    if isinstance(args, str):
        args = _unwrap_json(args)
    header = f"### Tool call: `{name}`"

    if isinstance(args, dict):
        body_field = next(
            (
                k
                for k in ("content", "new_function_code", "constant_code", "import_code")
                if k in args
            ),
            None,
        )
        if body_field:
            path = args.get(
                "relative_path",
                args.get(
                    "destination_relative_path",
                    args.get("source_relative_path", "?"),
                ),
            )
            code = args.get(body_field) or ""
            nlines = code.count("\n") + 1 if isinstance(code, str) and code else 0
            label = {
                "content": "Wrote file",
                "new_function_code": "Replaced function",
                "constant_code": "Added constant",
                "import_code": "Added import",
            }.get(body_field, "Edited")
            return f"{header}\n\n{label} `{path}` ({nlines} lines):\n\n```python\n{code}\n```"

    return f"{header}\n\n{_json_to_ascii(args)}"


def _render_tool_return(p: dict) -> str:
    name = p.get("tool_name", "")
    content = p.get("content", "")
    content = _strip_write_bundles(content)

    if name in _EDIT_TOOLS:
        return f"### Tool result: `{name}`\n\n{_extract_edit_return(content, name)}"

    if name == "list_facts":
        items = _as_json_list(content)
        if items is not None:
            bullets = "\n".join(f"- {i}" for i in items)
            return f"### Tool result: `{name}`\n\n{bullets}"

    if name == "recall_fact":
        if isinstance(content, str) and content.strip().startswith("{"):
            try:
                d = json.loads(content)
                if isinstance(d, dict) and "value" in d:
                    return f"### Tool result: `{name}`\n\n{d['value']}"
            except Exception:
                pass

    content = _strip_read_envelope(content)
    if not isinstance(content, str):
        content = _json_to_ascii(content)
    return f"### Tool result: `{name}`\n\n{content}"


def _render_part(p: dict) -> str:
    pk = p.get("part_kind")
    if pk == "system-prompt":
        return f"## System\n\n{_text(p.get('content', ''))}"
    if pk == "user-prompt":
        return f"## User\n\n{_text(p.get('content', ''))}"
    if pk == "text":
        return _text(p.get("content", ""))
    if pk == "thinking":
        return f"### Thinking\n\n{_text(p.get('content', ''))}"
    if pk == "tool-call":
        return _render_tool_call(p)
    if pk == "tool-return":
        return _render_tool_return(p)
    return f"### {pk}\n\n{json.dumps(p, ensure_ascii=False, indent=2)}"


def messages_to_md(
    messages: list[dict], timestamps: list[str] | None = None
) -> str:
    blocks = []
    # Monotonic `msg N` counter + local `YYYY-MM-DD-HH:MM:SS` timestamp. The
    # counter resets per render (each persist's full history), so the header is
    # a linearly navigable, sortable index of this transcript (context.md Req 4).
    # When `timestamps` (same length as `messages`) is supplied, each message is
    # stamped with its own FROZEN record-time (the per-message pydantic-ai
    # `timestamp`), not the whole-file rewrite time — otherwise every message in
    # a cumulative transcript would carry an identical rewrite-time stamp.
    fallback_ts = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
    for i, m in enumerate(messages):
        kind = m.get("kind", "?")
        parts = m.get("parts", [])
        seen: set[str] = set()
        for p in parts:
            if isinstance(p, dict):
                pk = p.get("part_kind")
                if isinstance(pk, str):
                    seen.add(pk)
        label = "+".join(sorted(seen)) if seen else kind
        ts = timestamps[i] if timestamps and i < len(timestamps) else fallback_ts
        body = "\n\n".join(_render_part(p) for p in parts)
        blocks.append(f"<!-- msg {i} | {ts} | {label} -->\n\n{body}")
    return "\n\n---\n\n".join(blocks)


def read_messages(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            if obj and isinstance(obj[0], dict) and "kind" in obj[0]:
                return obj
            if obj and isinstance(obj[0], list):
                return [m for run in obj for m in run]
    except Exception:
        pass
    msgs: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if isinstance(o, list):
            msgs.extend(o)
        elif isinstance(o, dict):
            msgs.append(o)
    return msgs


def convert_file(
    path: Path, out: Path | None = None, timestamps: list[str] | None = None
) -> Path:
    messages = read_messages(path)
    md = messages_to_md(messages, timestamps=timestamps)
    target = out or path.with_suffix(".md")
    target.write_text(md, encoding="utf-8")
    return target


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert orchestrator message dumps to markdown.")
    ap.add_argument("input", type=Path, help="JSON/JSONL message dump")
    ap.add_argument("--out", type=Path, default=None, help="output .md path (default: same stem)")
    args = ap.parse_args()
    target = convert_file(args.input, args.out)
    print(f"[converter] wrote {target} ({len(read_messages(args.input))} messages)")


if __name__ == "__main__":
    main()
