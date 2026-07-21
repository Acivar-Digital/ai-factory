# User Prompt Template (YAML front-matter + markdown body)

The harness reads `prompt/user_prompt.md` as the task spec. It MUST begin with a
YAML front-matter block delimited by `---` lines, followed by a freeform markdown
body. The markdown body is injected verbatim into the planner's brief; the YAML
block is parsed by `read_prompt()` (runner.py) into `{Resume, bd, scope}`.

## Front-matter schema

| Key      | Type            | Required | Meaning                                                                 |
|----------|-----------------|----------|-------------------------------------------------------------------------|
| `Resume` | `true`/`false` | yes      | Whether to seed the first coder pass with a prior exchange JSON.        |
| `bd`     | string          | yes      | bd ticket id (keys the exchange file + status board).                   |
| `scope`  | list[str]       | no       | Files/folders the change touches. **Context hint only — NOT an ACL.**  |

`scope` is a HINT. The harness auto-appends a scoped repo-map (folder tree +
per-file symbols + knowledge-graph) into the planner AND supervisor_plan briefs
so they see the byte-identical codebase context. The planner is still free to
expand beyond the declared scope. Leave `scope` out (or empty) to fall back to a
shallow whole-repo tree + a "no scope declared" note.

## Example

```markdown
---
Resume: false
bd: baziforecaster-xxxx
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

## STATE
must_be_pydantic: true

## REQUIREMENTS & CONSTRAINTS
- ALL work saved in `admin/orchestrator/temp/`.
- DO NOT edit anything outside `admin/orchestrator/temp/`.
- Reuse existing patterns; do not invent new conventions.
- Fail loudly; no `except: pass`.

## ANTI-PATTERNS (CRITICAL)
- Things the agent must NOT do.
- Code that must NOT be touched.
- Patterns that must NOT be reintroduced.

## ACCEPTANCE
1. `uv run ruff check ...` → clean.
2. List verifiable criteria.
```

## Recommended body sections
- `# EPIC` — one-line goal.
- `## CONTEXT` — background + evidence pointers (include pre-audit findings).
- `## DELIVERABLES` — batch-structured, file:line-anchored actions.
- `## STATE` — machine flags the planner should respect.
- `## REQUIREMENTS & CONSTRAINTS` — sandbox/writable rules.
- `## ANTI-PATTERNS (CRITICAL)` — explicit don'ts (what NOT to touch).
- `## ACCEPTANCE` — checklist the run must satisfy.

## Notes for authors
- Keep `scope` to the files/folders you actually touch — smaller scope = less
  token bloat for the planner/supervisor.
- The `bd:` line inside the front-matter is also grepped by `run_orchestrator.sh`
  to auto-select the ticket when `--bd` is omitted on the CLI.
- **Include a pre-audit section in CONTEXT** showing what's already done vs what
  remains. This saves the planner from rediscovering completed work.
- This file is a GUIDE only — edit `prompt/user_prompt.md` (NOT this template)
  to set the real task.
