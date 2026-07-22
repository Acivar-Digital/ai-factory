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

## CRITICAL: REPO_ROOT and Scope Path Resolution

**This is the most commonly misunderstood part of the factory.**

### How REPO_ROOT is resolved

`REPO_ROOT` (defined in `factory/infra/control.py`) determines where the target repo lives:

```python
_CWD = os.environ.get("CWD") or _RUNTIME_ENV.get("CWD") or str(Path.cwd().resolve())
REPO_ROOT = Path(_CWD)
```

Priority:
1. `$CWD` environment variable
2. `CWD=` in `factory/infra/.env` (or `<repo-root>/.env`)
3. `Path.cwd()` — the current working directory

### Where scope paths resolve

The prompt's YAML `scope:` field lists paths like `src2/engine/module1_macro.py`. These resolve relative to **`REPO_ROOT`** — NOT relative to `TEMP_DIR` or `factory/temp/`.

The planner phase reads code through these functions, all of which read from `REPO_ROOT`:
- `ledger._py_tree()` → walks `REPO_ROOT / "src2"` and `REPO_ROOT / "tests"`
- `ledger._is_dir(rel)` → checks `REPO_ROOT / rel`
- `ledger.get_file_symbols(rel)` → resolves via `_codebase_common.resolve_secure_path()` which uses `PROJECT_ROOT` (= factory repo root, same as `REPO_ROOT` in practice)
- Planner's `batch_read` tool → resolves relative to `PROJECT_ROOT`

**The coder phase** works differently — it reads/writes through `stage_path()` which maps to `TEMP_DIR` (`factory/temp/`). The `stage_workspace_from_draft()` function copies files from `REPO_ROOT / src2/...` to `TEMP_DIR / src2/...` BEFORE the coder runs.

### The two-phase path model

| Phase | Path base | Function | What it reads |
|---|---|---|---|
| Planner | `REPO_ROOT` | `inject_repo_map()`, `batch_read` | Live target repo files at `REPO_ROOT/src2/...` |
| Supervisor Plan | `REPO_ROOT` | `batch_read` | Live target repo files at `REPO_ROOT/src2/...` |
| Pre-stage | `REPO_ROOT` → `TEMP_DIR` | `stage_workspace_from_draft()` | Copies `REPO_ROOT/src2/...` → `TEMP_DIR/src2/...` |
| Coder | `TEMP_DIR` | `stage_path()`, `read_file`, `write_file` | Staged copies at `TEMP_DIR/src2/...` |
| Supervisor Review | `TEMP_DIR` | `stage_path()` | Staged copies |
| Red Team | `TEMP_DIR` | `stage_path()` | Staged copies |

### What this means in practice

- The target repo (with `src2/`) MUST be accessible at `REPO_ROOT`.
- If `CWD` is the factory repo itself (e.g. `/home/.../ai-factory`), the target repo is NOT in the scope path unless `src2/` exists at the factory root.
- To run the factory against a separate target repo (e.g. `baziforecaster`), set `CWD` env var to the target repo root OR ensure the target's `src2/` is at the factory `REPO_ROOT`.
- **Never create symlinks or copy files into the factory repo** without understanding `REPO_ROOT` resolution. Check `$CWD`, `.env`, and `Path.cwd()` first.
- The factory's `factory/temp/` directory contains STAGED COPIES of target repo files, managed by `stage_workspace_from_draft()` and `stage_path()`. These are NOT the source of truth for the planner phase.

### How to diagnose scope issues

1. Check `REPO_ROOT`: look at `$CWD` env var, `factory/infra/.env`, and `Path.cwd()`
2. Verify `REPO_ROOT / "src2"` exists and contains the expected files
3. If the planner's `batch_read` returns empty results for `src2/...` paths, the target repo is not at `REPO_ROOT`
4. Do NOT check `factory/temp/src2/` — that's the staging area for coders, not the planner's source

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
| `batch_read` | Full line-numbered content of all paths read | `tools_file.py:137` |
| `read_file` | Full line-numbered content of the file/range | `tools_file.py:72` |
| `write_file` | Summary: `[write_file] path (N lines)` | `tools_file.py:195` |
| `replace_text` | Summary: `[replace_text] path: replaced X chars with Y chars` | `tools_shell.py:54` |
| `replace_function` | Summary: `[replace_function] path: scope` | `tools_shell.py:66` |
| `add_constant` | Summary: `[add_constant] path: NAME = value` | `tools_shell.py:75` |
| `add_import` | Summary: `[add_import] path: import line` | `tools_shell.py:83` |
| `delete_file` | Summary: `[delete_file] path` | `tools_file.py:218` |
| `rename_file` | Summary: `[rename_file] source → dest` | `tools_file.py:226` |
| `move_symbol` | Summary: `[move_symbol] name: source → dest` | `tools_shell.py:91` |

Read tools (`batch_read`, `read_file`) remember the full content so the LLM can pick up exactly where it left off. Write/edit tools remember a short summary — the LLM already knows what it wrote, it just needs confirmation. All notes survive across turns and across retries within the same role.

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
