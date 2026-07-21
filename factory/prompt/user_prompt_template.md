# User Prompt Template

> **First read**: `factory/prompt/GUIDE.md` for architecture, setup, and operator workflow.
> This file is a **reference template** — the harness never reads it.
> The real task spec goes in `factory/prompt/user_prompt.md`.

## Purpose

This is a starter/cheat-sheet for writing `factory/prompt/user_prompt.md`. It documents
the YAML frontmatter schema, shows examples for common targets, and lists recommended
markdown body sections.

The harness reads `factory/prompt/user_prompt.md` as the task spec. The file MUST begin
with a YAML frontmatter block delimited by `---` lines, followed by a freeform markdown
body. The markdown body is injected verbatim into the planner's brief; the YAML block
is parsed by `read_prompt()` (runner.py) for machine-level configuration.

---

## Frontmatter schema

| Key | Type | Required | Default | Meaning |
|-----|------|----------|---------|---------|
| `Resume` | bool | yes | — | Seed the first coder pass with a prior exchange JSON |
| `bd` | string | yes | — | bd ticket id (keys exchange file + status board) |
| `scope` | list[str] | no | `[]` | Files/folders the change touches. **Context hint only — NOT an ACL.** |
| `write_mode` | `"direct"` \| `"staged"` | no | `"direct"` | `direct` = edit target files in-place via shadow tools; `staged` = copy to TEMP_DIR, edit there, apply at end |
| `language` | string | no | `"python"` | Project language hint (`python`, `typescript`, `rust`, `html`, etc.) |
| `lint_command` | string | no | `"uv run ruff check"` | Command to run for acceptance lint gate. Set to `""` to skip. |
| `start_phase` | string | no | — | Pipeline phase to start from (seeks to this phase, skipping prior ones). One of: planner, supervisor_plan, coder, supervisor_review, red_team. |
| `stop_phase` | string | no | — | Pipeline phase to stop after (halts after this phase completes). One of: planner, supervisor_plan, coder, supervisor_review, red_team. |

### `scope` clarification

`scope` is a **hint**, not an ACL. The harness auto-appends a scoped repo-map (folder
tree + per-file symbols + knowledge-graph) into the planner and supervisor_plan briefs.
The planner may expand beyond declared scope. Leave `scope` out (or empty) to fall back
to a shallow whole-repo tree.

**Important**: `_py_tree()` in `ledger.py` hardcodes `src2/` + `tests/` walk roots.
For targets that don't use those paths (factory itself, a Bun project, an HTML site),
the auto-context will be empty. **Always set `scope` for non-`src2` targets.**

### `Resume: true` workflow

1. After a run, find the exchange JSON at `factory/artefacts/history/exchange.json`
2. Create a new `user_prompt.md` with `Resume: true` and set `scope` to the same files
3. The first coder pass will receive the prior exchange as conversation seed
4. Re-run with `./run.sh` — the runner detects `Resume: true` and feeds the history

---

## Example: repairing baziforecaster

```markdown
---
Resume: false
bd: baziforecaster-xxxx
write_mode: staged
language: python
start_phase: planner
stop_phase: supervisor_plan
scope:
  - src2/engine/module3_interaction.py
  - src2/engine/module11_probability.py
  - src2/engine/shen_classifier.py
  - src2/engine/module8_scoring.py
  - src2/engine/module4_medicine.py
---

# EPIC
One-line statement of the goal.

## CONTEXT
Why this work exists; link the audit/report that found the problem.
Include a pre-audit summary of what's already implemented vs still broken.

## DELIVERABLES
1. Concrete, file:line-anchored actions.
2. Group related actions into batches.

## REQUIREMENTS & CONSTRAINTS
- ALL work staged in factory temp, applied to target repo under src2/
- Edits go directly into the target repo via shadow tools
- Target codebase is at REPO_ROOT/src2/
- Reuse existing patterns; do not invent new conventions
- Fail loudly; no `except: pass`

## ANTI-PATTERNS (CRITICAL)
- Things the agent must NOT do
- Code that must NOT be touched
- Patterns that must NOT be reintroduced

## ACCEPTANCE
1. `uv run ruff check ...` → clean
2. List verifiable criteria
```

---

## Example: self-hosting (repairing factory)

```markdown
---
Resume: false
bd: factory-xxxx
write_mode: direct
language: python
start_phase: planner
stop_phase: supervisor_plan
scope:
  - factory/infra/runner.py
  - factory/infra/control.py
  - factory/common/subprocess.py
---
...
```

---

## Example: Bun/TypeScript project

```markdown
---
Resume: false
bd: bun-project-xxxx
write_mode: direct
language: typescript
lint_command: biome check
start_phase: planner
stop_phase: supervisor_plan
scope:
  - src/routes/
  - src/components/
---
...
```

---

## Recommended body sections

| Section | Purpose |
|---------|---------|
| `# EPIC` | One-line goal |
| `## CONTEXT` | Background + evidence pointers (include pre-audit findings) |
| `## DELIVERABLES` | Batch-structured, file:line-anchored actions |
| `## REQUIREMENTS & CONSTRAINTS` | Writable paths, coding conventions, fail-loudly |
| `## ANTI-PATTERNS (CRITICAL)` | Explicit don'ts (what NOT to touch) |
| `## ACCEPTANCE` | Checklist the run must satisfy |

---

## Notes for authors

- Keep `scope` tight — smaller scope = less token bloat for the planner/supervisor.
- The `bd:` line inside the frontmatter is also grepped by `run.sh` to auto-select the ticket when `--bd` is omitted.
- `start_phase` / `stop_phase` let you run a segment of the pipeline. Set both to run only the desired phases — useful for iterating on a plan before committing to a full coder run.
- **Include a pre-audit section in CONTEXT** showing what's already done vs what remains. This saves the planner from rediscovering completed work.
- This file is a REFERENCE — edit `factory/prompt/user_prompt.md` (NOT this template) to set the real task.
