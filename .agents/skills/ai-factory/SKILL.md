---
name: ai-factory
description: AI-Factory is a deterministic orchestrator framework (no LLM orchestrator) for multi-agent code-generation pipelines. Uses Pydantic AI for agents, Pydantic for all data contracts, and a strict FAIL-FAST/LOUD/CHEAP discipline. Load this skill when asked about this repo's architecture, running tests, or contributing.
license: MIT
compatibility: Python 3.11+
metadata:
  version: "1.0.0"
  source: https://github.com/anomalyco/ai-factory
---

# AI-Factory — Deterministic Orchestrator for Multi-Agent Code Generation

## What This Repo Is

AI-Factory is a **deterministic conductor** (NOT an LLM orchestrator) that runs multi-agent code-generation pipelines. It is a standalone MIT-licensed framework established in July 2026.

The orchestrator spawns LLM agents with focused roles (planner, coder, supervisor, red-team, ops), validates their output, and gates progress through each phase. **The conductor never delegates orchestration decisions to an LLM.**

## Critical: `temp/` Path Resolution

`temp/` paths in `user_prompt.md` scope/deliverables resolve to **`FACTORY_ROOT/factory/temp/`** (i.e. `PKG_DIR / "temp"`), NOT to the target repo. The `stage_path()` function in `context.py` strips the `temp/` prefix and joins with `TEMP_DIR`. Example: `temp/dm_strength.py` → `factory/temp/dm_strength.py`.

## CRITICAL: TARGET_REPO and the Two-Root Path Model

**This is the most commonly misunderstood part of the factory.**

### The problem: one root can't serve both harness and target

`REPO_ROOT` is used for everything: harness infra (logs, runtime, staged paths,
BD scripts) AND resolving source file paths (`src2/...`). But `src2/` lives in
the **target repo** (`baziforecaster/`), not the factory repo (`ai-factory/`).
Changing `CWD` to point at the target repo would break all harness paths.

**Fix: two independent roots.**
- **`REPO_ROOT`** = factory repo. Harness infra, staging, logs, BD, status.
  Never changes. Defined in `factory/infra/control.py` from `CWD` env var.
- **`TARGET_REPO`** = target repo (has `src2/`). Agent reads resolve here.
  Set via `target_repo:` in `user_prompt.md` frontmatter. The only person who
  knows which repo to target is the user writing the prompt.

### How `TARGET_REPO` is resolved

Two resolution functions in `factory/tools/_codebase_common.py`:

| Function | Root (fallback chain) | Used by | Resolves |
|---|---|---|---|
| `resolve_secure_path(path)` | `TARGET_REPO` → `CWD` (from `.env`) → `PROJECT_ROOT` | Read tools (`read_file.py`, `grep_codebase.py`, `list_files.py`, etc.) | `src2/...` against target repo |
| `resolve_repo_path(path)` | `PROJECT_ROOT` (= factory repo) | Write tools (`write_file.py`, `replace_text.py`, etc.) | `factory/temp/...` against factory repo |

When `TARGET_REPO` is set, ALL reads go to the target repo. Factory files
(`.env`, `runner.py`, `control.py`) become invisible — agents have no business
reading them.

**Fallback chain explained:** `_resolve_target_root()` checks `TARGET_REPO` first
(set via `target_repo:` in `user_prompt.md` frontmatter). If unset, it falls back
to `CWD` (exported by `control.py` from `factory/infra/.env`). If both are unset,
it falls back to `PROJECT_ROOT` (= the factory repo itself). This means you
ONLY need `target_repo:` in frontmatter if target repo differs from whatever
`CWD` points to in `.env` — but setting it explicitly is safer.

### The two-phase path model with TARGET_REPO

| Phase | Path base | Resolution | What it reads |
|---|---|---|---|
| Planner | `TARGET_REPO` | `resolve_secure_path()` | Live target repo files at `TARGET_REPO/src2/...` |
| Supervisor Plan | `TARGET_REPO` | `resolve_secure_path()` | Live target repo files at `TARGET_REPO/src2/...` |
| Pre-stage | `TARGET_REPO` → `TEMP_DIR` | `stage_workspace_from_draft()` | Copies `TARGET_REPO/src2/...` → `TEMP_DIR/src2/...` |
| Coder | `TEMP_DIR` | `stage_path()`, `resolve_repo_path()` | Staged copies at `TEMP_DIR/src2/...` |
| Supervisor Review | `TEMP_DIR` | `stage_path()` | Staged copies |
| Red Team | `TEMP_DIR` | `stage_path()` | Staged copies |

### How to set TARGET_REPO

Add `target_repo:` to the YAML frontmatter in `factory/prompt/user_prompt.md`:

```yaml
---
Resume: false
bd: baziforecaster-batch-a
target_repo: /home/yapilwsl/arthityap/baziforecaster
write_mode: staged
language: python
start_phase: planner
stop_phase: supervisor_plan
scope:
  - src2/engine/module1_macro.py
  - src2/core/schemas/unified.py
---
```

The harness parses this field in `read_prompt()` (`pipeline.py:144-146`,
`runner.py:105-107`) and sets `os.environ["TARGET_REPO"]` immediately — before
any tool call resolves a path.

### Why env var at call time (not module-level constant)

`_codebase_common.py` is imported at module load — before the prompt is parsed.
If `TARGET_REPO` were a module-level constant, it would be set to the fallback
(`PROJECT_ROOT`) before `read_prompt()` ever runs. Instead,
`resolve_secure_path()` checks `os.environ.get("TARGET_REPO")` on **every
invocation**, so the prompt-parsed value is picked up dynamically.

### How to diagnose scope issues

1. Check `target_repo:` is set in `user_prompt.md` frontmatter
2. Verify `TARGET_REPO / "src2"` exists and contains the expected files
3. If `batch_read` returns empty for `src2/...` paths, `TARGET_REPO` is either
   not set or pointing to the wrong directory
4. Do NOT check `factory/temp/src2/` — that's the staging area for coders, not
   the planner's source

## Quick Start

```bash
uv run python -m pytest tests/       # Run all tests (231 tests, ~50s)
uv run ruff check factory/ tests/    # Lint
```

## Architecture

```
factory/
  common/          # Shared utilities (md_bridge, operator, registry)
  infra/           # Orchestrator engine
    runner.py      # Slim conductor entrypoint (221 lines)
    control.py     # REPO_ROOT, PKG_DIR, TEMP_DIR, model registry, control sheet
    ledger.py      # inject_repo_map(), _py_tree(), coder brief builder
    _runtime.py    # Module globals (phase order, raw outputs, summaries)
    exchange.py    # Exchange-turn / status-board / JSONL persistence
    agent.py       # Agent builder & per-role agent construction
    context.py     # Staging (stage_path, stage_workspace_from_draft), tier-B context, harness patches
    validation.py  # Invariant checks, gate constants
    execution.py   # EXECUTE phase - per-task timeout, spawn-all, patching
    pipeline.py    # Gate orchestration (plan, code-review, red-team, ops)
    agents/        # 7 role specs: planner, coder, supervisor_plan,
                   #   supervisor_review, red_team, ops, healer
                   #   Each has a .py class + .yaml prompt template
    tools.py       # Shadow tooling wrappers (search, read, write, AST)
  tools/           # CLI wrappers for repo tools
  temp/            # Staging area (TEMP_DIR) — coder writes, NOT planner source
```

## Roles & Pipeline Phases

| Phase | Role | Gate | Purpose |
|---|---|---|---|
| `planner` | Planner | supervisor_plan | Parse task, build dependency DAG |
| `coder` | Coder(s) | supervisor_review | Edit files, harness-owned guardrail + re-spawn loop |
| `supervisor_review` | Supervisor | — | Review code, re-execute failing tasks, force-pass on final attempt |
| `red_team` | Red Team | — | Audit results, re-execute failing tasks, force-pass on final attempt |
| `ops` | Ops | — | Propose-only commit (no push) |

## Key Architectural Constraint: coder_fn / reviewer_fn Adapters

`runner.py` wraps `record_coder` and `load_skill` in closure adapters with signature
`(brief: str, task_id: str | None = None) -> str` / `(brief: str) -> str` before
passing them to `run_code_review_gate` and `run_red_team_gate`. This is required
because `execute_task` in `execution.py` calls `coder_fn(brief, task_id=t.id)` (2
args), but `record_coder` requires 6 args (`brief, bd, history, prior, state_dict,
task_id`). The closures capture `bd`, `history`, `prior`, and a task-local state
dict at runner scope. Reviewer closures call `load_skill(role, brief, bd)` directly
(rather than `do_role`) to ensure the caller's brief is used, not a stale
`state_dict["brief"]`.

## Agent YAML Tool Names Must Match `_TOOL_BY_NAME`

**The `tools:` list and the `Tool allow-list` instruction text in every `factory/infra/agents/<role>.yaml` MUST reference only tools registered in `_TOOL_BY_NAME`** (defined in `tools_guard.py:337`):

```
remember, batch_read, read_file, write_file, replace_text,
replace_function, add_constant, add_import, delete_file, rename_file, move_symbol
```

`agent.py:72-76` hard-HALTs if a YAML `tools:` name is not in `_TOOL_BY_NAME`. But the instruction `Tool allow-list` text is free-form prose — there is NO validation against it. If it names a tool that doesn't exist, the LLM will trust the prose, call the non-existent tool, get a 404, and may spiral into analysis-paralysis (as happened with `list_facts`). Keep them in sync.

## Tool Behaviour: Auto-Remember

**Every tool auto-persists its result via `_auto_remember()` after a successful operation.** The function calls `artefacts.remember_note()` → writes to `<role>.jsonl` → auto-converts to `.md` → re-injected as `message_history` on the agent's next turn via `build_md_bridge()`. This eliminates re-read loops: the LLM sees its own prior reads and writes in context.

| Tool | What's remembered | Where |
|---|---|---|
| `remember` | (is the mechanism) | `tools_memory.py:49` |
| `batch_read` | Raw line-numbered content of all paths read (no nudge/steer wrapping) | `tools_file.py:137` |
| `read_file` | Raw line-numbered content of the file/range (no nudge/steer wrapping) | `tools_file.py:72` |
| `write_file` | Unified diff of old→new content with line numbers | `tools_file.py:194` |
| `replace_text` | `---OLD---` / `---NEW---` sections with the actual text | `tools_shell.py:55` |
| `replace_function` | New function body (with path::scope header) | `tools_shell.py:69` |
| `add_constant` | Full constant line: `NAME = value` | `tools_shell.py:78` |
| `add_import` | Full import line | `tools_shell.py:86` |
| `delete_file` | Path of deleted file | `tools_file.py:224` |
| `rename_file` | `source → dest` paths | `tools_file.py:233` |
| `move_symbol` | `name: source → dest` paths | `tools_shell.py:95` |

Read tools (`batch_read`, `read_file`) remember the raw line-numbered content (no nudge/steer wrapping). Write/edit tools remember the actual content that changed (diff, function body, constant/import line). All notes survive across turns and across retries within the same role.

**Important: the converter (`converter.py`) must NOT truncate remembered content.** Previously it stripped `batch_read`/`read_file` results to `[N lines]` in the `.md` file, making the auto-remember feature useless. The special-case truncation was removed — full line-numbered content now renders in the `.md` history.

The `_REMEMBER_NUDGE` ("you may call `remember(...)`") is still appended to read tool returns for backwards compatibility — the LLM may still call `remember` explicitly, which writes a duplicate entry (harmless, costs tokens).

## Key Disciplines (LOAD-BEARING)

- **Fail Fast**: Ship smallest MVP. No future-proofing.
- **Fail Loudly**: Full tracebacks. No `except: pass`. Silent failure swallowing (e.g. catching a guardrail crash or `load_schema_gate.py` crash and treating it as a pass) is strictly prohibited.
- **Fail Cheaply**: Cheap assertions before expensive LLM calls.
- **Zero Dicts**: No `dict` access on Pydantic models. All lookups = Pydantic models.
- **Pydantic Only**: All domain data = strict Pydantic v2 models. No standalone Enums.
- **No model-level fallback**: Single model per role — never switch to a backup model on failure. Agent-level recovery (loopguard retry + `_recover_from_unexpected_behavior` with the SAME model) IS allowed and correct.
- **Harness-owned guardrails**: The coder only *declares* done; the harness runs ruff + pyright + smoke gates on staged files, and re-spawns the coder (up to `CODER_VALIDATION_PASSES` times) with guardrail feedback before the review phase. If a guardrail crashes or produces unparseable output, the task MUST fail/block—it is never a silent pass.
- **Red Team Integrity**: The `red_team_passed` gate relies solely on `findings` and `rubric_cells`. If both are empty, the audit is considered incomplete and the gate MUST fail.

## Structured Output Schema: Field Descriptions Are Load-Bearing

**All Pydantic output models must carry `Field(description=...)` and `Field(examples=...)` on every field.** Pydantic v2 serializes these into the JSON Schema that pydantic-ai sends to the model as the structured output tool definition. Without them, the model sees only bare types (`str`, `Literal["Yes", "No"]`) and must infer semantics from free-text prose elsewhere in the prompt.

### Why bare types aren't enough

The model fills in a form (tool call arguments). The JSON Schema is the form definition. If a field says `approved: Literal["Yes", "No"]` with no description, the model doesn't know:
- What "Yes" means (approve? proceed?)
- What "No" means (reject? block?)
- When to use which
- What goes in `comments`

Putting instructions in the YAML prompt template is not enough — the model may not connect prose instructions to the structured output fields. The descriptions must live ON the schema itself.

### The pattern

```python
class EvaluationItem(BaseModel):
    item_id: str = Field(
        description="Task ID from the DraftPlan. Must match a proposed task id exactly (e.g. coder01, coder02)."
    )
    approved: Literal["Yes", "No"] = Field(
        description="Yes = task approved, proceed. No = task rejected — MUST explain why in comments.",
        examples=["Yes", "No"]
    )
    comments: str = Field(
        description="Required when approved=No: cite file:line, explain what's wrong, reference the brief's constraints/anti-patterns. When approved=Yes: may be empty string.",
        examples=["", "Instruction tells coder to move _unified_medicine before line 216, but brief says 'Do NOT touch annual Tai Sui section (lines 340-399)'."]
    )
```

### Rules

1. **Every field** in every output model (`DraftPlan`, `ApprovedPlan`, `TaskResult`, `ReviewResult`, `AuditResult`, `GitResult`) MUST have `description=`
2. Use **`examples=`** for `Literal`/`Enum` fields so the model sees valid values in the schema
3. Put the **semantics** in descriptions, not just the type constraint. "Yes = approve, No = reject + explain" not "Must be Yes or No"
4. The `comments` / rejection-reason fields MUST say "required when rejected, empty string when approved" so the model knows when it's mandatory
5. Do NOT rely on YAML prompt templates to convey structured output semantics — the model may not correlate prose instructions with tool call fields

## Test Pattern: Monkeypatch Refactoring

## Shadow Tooling Guidelines

The orchestrator relies heavily on `factory/tools/` CLI wrappers (e.g. `read_file.py`, `investigate.py`, `replace_function.py`, `replace_text.py`).
- **Context Integrity**: File reads always prepend `N:` line numbers to guarantee precise line targeting by LLMs.
- **Context Constraints**: Token truncation limits (e.g. 12k) safely slice at the last complete newline. Overlapping pattern matches dynamically merge context blocks without dropping lines.
- **AST Edits**: Tooling prefers surgical AST-bounded string edits over wholesale AST rewrites (e.g. `ast.unparse()`) to strictly preserve code formatting, whitespace, and comments.
- **Regex Edits**: Exact string replacements gracefully handle whitespace configuration without double-escaping regex literal blocks.

After the runner.py split, monkeypatch targets **must be string-based** on the module where the name is resolved:

```python
# WRONG — patches runner, but execution.py has private import
monkeypatch.setattr(runner, "log_operator", mock)

# RIGHT — patches execution's own namespace
monkeypatch.setattr("factory.infra.execution.log_operator", mock)
```

Reason: `execution.py` does `from factory.common.operator import log_operator`, creating a private reference. Patching the re-export on `runner` has no effect.

## Session Workflow

1. `bd ready` — find available work
2. `bd show <id>` — review issue details
3. `bd update <id> --claim` — claim it
4. Make changes, run tests
5. `bd close <id1> <id2>` — close completed items
6. `git add -A && git commit -m "..."` — commit
7. `bd dolt pull` — sync beads before next commit

## Memory Protocol

Use `bd remember` to persist cross-session knowledge. Search with `bd memories <keyword>`.

---

## Session Memory (2026-07-22: Converter + Budget Transparency Fixes)

**DO NOT SCAN WHOLE REPO NEXT TIME. Read this first:**

- **Converter (`converter.py`)**: `batch_read` and `read_file` results are NO LONGER truncated to `[N lines]`. Full content (line-numbered file text + `=== File read: path ===` header) renders in `.md`. The old special-case truncation (`_render_tool_return` lines 284-291) was removed.
- **Budget markers preserved**: `_CONTENT_NOISE` regex (`converter.py:122`) was removed. `[TOOL CALL N/M]` budget markers now survive in `.md` so the agent sees its budget state every turn (before: stripped; agent blind).
- **Auto-remember (`_auto_remember`)**: All 11 tools remember full content to `.jsonl`. `read_file`/`batch_read` remember raw line-numbered content. `write_file` remembers unified diff. The remembered notes appear in `.md` via `remember` tool-return, with file headers intact.
- **READ_BUDGET**: Raised from 5 to 15 (`control.py:618`). All agents share the same `batch_read` cap (`read_budget` in `GuardToolset`). Per-role budgets (`ROLE_TOOL_BUDGET`): planner=10, planner_sup=10, coder=75.
- **Line numbers**: Absolute (`f"{s + i + 1}: {line}"`), not relative to range. `1:` = file line 1.
- **Files changed**: `converter.py`, `control.py`, `CHANGELOG.md`, `.agents/skills/ai-factory/SKILL.md`.
