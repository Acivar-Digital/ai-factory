# Tool Behaviour Audit (2026-07-22)

## `remember` — ✅ correct
- Persists note → `.jsonl` → auto-converts to `.md` → auto-reinjected next turn via `build_md_bridge()`
- No changes needed.

## `batch_read` — 🔧 planned
- Currently returns content + `_REMEMBER_NUDGE` telling LLM to call `remember` manually
- **Wanted**: auto-`remember_note()` after successful read with summary of what was read (paths, line ranges, line count)
- Saves LLM roundtrips re-reading files next turn at cost of extra context tokens

## `read_file` — 🔧 planned
- Same as `batch_read`: auto-`remember_note()` after successful read
- Must include line numbers in the remembered content

## `write_file` — 🔧 planned
- After successful write, auto-`remember_note()` with **only the section that changed** (line-numbered)
- NOT the full file content
- So LLM can see its edit in context next turn instead of re-reading to verify
- write → remember changed section only → auto-reinjected next turn

## `replace_text` — 🔧 planned
- Auto-`remember_note()` with old→new diff + line numbers

## `replace_function` — 🔧 planned
- Auto-`remember_note()` with replaced function body + line numbers

## `add_constant` — 🔧 planned
- Auto-`remember_note()` with the constant line added

## `add_import` — 🔧 planned
- Auto-`remember_note()` with the import line added

## `delete_file` — 🔧 planned
- Auto-`remember_note()` with the file path deleted

## `rename_file` — 🔧 planned
- Auto-`remember_note()` with source→destination paths

## `move_symbol` — 🔧 planned
- Auto-`remember_note()` with the relocated symbol info
