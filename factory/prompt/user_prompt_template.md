# User Prompt Template

> **First read**: `factory/prompt/GUIDE.md` for architecture, setup, and operator workflow.
> This file is a **reference template** — the harness never reads it.
> The real task spec goes in `factory/prompt/user_prompt.md`.

## Purpose

This is a starter/cheat-sheet for writing `factory/prompt/user_prompt.md`. It documents
the YAML frontmatter schema, shows examples for common targets, and lists recommended
markdown body sections for generating clean prompt specs.

The harness reads `factory/prompt/user_prompt.md` as the task spec. The file MUST begin
with a YAML frontmatter block delimited by `---` lines, followed by a freeform markdown
body. The markdown body is injected verbatim into the brief; the YAML block
is parsed by `read_prompt()` (runner.py) for machine-level configuration.

---

## Frontmatter schema

| Key | Type | Required | Default | Meaning |
|-----|------|----------|---------|---------|
| `Resume` | bool | yes | — | Seed the first pass with a prior exchange JSON (`true` \| `false`) |
| `bd` | string | yes | — | bd ticket id (keys exchange file + status board) |
| `scope` | list[str] | no | `[]` | Files/folders the change touches. **Context hint for repo-map auto-injection.** |
| `write_mode` | `"direct"` \| `"staged"` | no | `"direct"` | `direct` = edit target files in-place; `staged` = copy to factory temp, edit there, apply at end |
| `language` | string | no | `"python"` | Project language hint (`python`, `typescript`, `rust`, `html`, etc.) |
| `lint_command` | string | no | `"uv run ruff check"` | Command to run for acceptance lint gate. Set to `""` to skip. |
| `start_phase` | string | no | — | Pipeline phase or review tier to start from (e.g. `intern`, `engineer`, `senior`, `planner`, `coder`). |
| `stop_phase` | string | no | — | Pipeline phase or review tier to stop after (e.g. `intern`, `engineer`, `senior`, `ops`). |

---

## Model Control Tiers (`factory/infra/control.py`)

When configuring task execution, the harness maps tiers to specific models via `CONTROL_SHEET`:
- **Intern Tier (`intern_model`)**: `ling_flash` (`openrouter/inclusionai/ling-3.0-flash:free`) — fast initial code generation.
- **Engineer Tier (`engineer_model`)**: `gemini_3_6_flash_high` (`gemini-3.6-flash-high`) — AST verification, type-check & lint fix.
- **Senior Tier (`senior_model`)**: `gemini_3_1_pro_high` (`gemini-pro-agent`) — final security audit gate & production approval.

---

## Standard `user_prompt.md` Structure

```markdown
---
Resume: false
bd: task-ticket-id
write_mode: staged
language: python
start_phase: intern
stop_phase: senior
scope:
  - path/to/target_file.py
---

# EPIC
One-line summary of the core objective.

## CONTEXT
Background info, motivation, or root cause of the bug/feature.

## DELIVERABLES
1. Concrete, file:line-anchored edits required.
2. Step-by-step checklist of deliverables.

## REQUIREMENTS & CONSTRAINTS
- Strict Pydantic v2 domain models; no raw dicts for business logic.
- AST-preserving edits (preserve existing docstrings and high-value comments).
- Surgical diffs; zero unrequested refactoring.
- Fail loudly on unexpected exceptions.

## ANTI-PATTERNS (CRITICAL)
- Do NOT swallow exceptions with bare `except: pass`.
- Do NOT modify files outside the declared `scope`.

## ACCEPTANCE
1. Passes AST verification and `uv run ruff check <file>`.
2. All unit tests in test suite pass without regression.
```
