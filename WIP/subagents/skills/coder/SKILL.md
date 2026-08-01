---
name: coder
description: Execute surgical codebase changes using MCP tools (read, write, search, replace)
---

# Skill: Coder

Make precise, surgical code changes using the workspace-codebase MCP toolset. Never introduce unrelated changes.

## Available Tools

| Tool | Purpose |
|------|---------|
| `read_file` | Read code before editing |
| `write_file` | Create NEW files only |
| `grep_codebase` | Search for patterns |
| `search_codebase` | Semantic search |
| `replace_function` | AST-safe function replacement |
| `replace_text` | Exact string replacement |
| `add_import` | Add imports via AST |
| `add_constant` | Add constants via AST |
| `get_file_symbols` | List functions/classes in file |
| `verify_file_path` | Check if path exists |
| `run_shell_command` | Execute verify commands |

## Rules

1. **Read first**: Use `grep_codebase` or `read_file` BEFORE writing. Quote existing code before changing it.
2. **Prefer AST tools**: Use `replace_function` over `replace_text` when possible.
3. **New files only**: `write_file` is for brand-new files only. Never overwrite existing files with it.
4. **No `src/`**: Only modify `src2/`, `admin/`, `migrations/`, `infrastructure/`.
5. **Minimal diffs**: Do NOT reformat unrelated lines or change quote styles.
6. **Verify**: Always run verify commands after changes.
