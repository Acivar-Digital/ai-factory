⚠️ **CWD WARNING**: Shell prompt shows /home/yapilwsl/arthityap/. You MUST `cd /home/yapilwsl/arthityap/ai-factory/` before running any project scripts or uv commands.

# AI-Factory — What This Repo Is

**Deterministic orchestrator for multi-agent code generation pipelines.** Spawns LLM agents
(planner, coder, supervisor, red-team, ops) in a phase pipeline. The conductor is a
deterministic Python script — NO LLM orchestrator, NO delegation of orchestration decisions.

## How to Understand This Repo Quickly

1. **Load the `ai-factory` skill** — it contains the full architecture overview, role/phase table,
   key disciplines, test patterns, and session workflow. Run `b skill ai-factory` or use the
   `skill` tool with name `ai-factory` to inject it.
2. **Search memories** — `bd memories <keyword>` to find cross-session decisions:
   `bd memories runner` → plans phase control, `bd memories discipline` → coding philosophy,
   `bd memories harness` → all harness invariants.
3. **Persistent knowledge** — use `bd remember <key> "value"` to save decisions that should
   survive across sessions (never write to MEMORY.md files).

## RULE ZERO: User Override

- **User Priority**: User instructions override all rules.

## SANDBOX: Workspace Only

- **Boundaries**: No files outside `/home/yapilwsl/arthityap/ai-factory/`. No `/tmp/`.

## WORKFLOW ENFORCEMENT

### 1. Interaction & Planning

- **Style**: Direct. Concise. No plan blocks in chat for simple edits.
- **Planning & Execution**: Mandatory plan ahead. Use TODO lists for all tasks. Unless told to run autonomously or in YOLO mode, it is mandatory to use the `/grill-me` skill when planning or executing user instructions.
- **Execution**: Use `bd` for long-running tasks and subagent orchestration within TODOs.

### 2. Task Tracking (BEADS)

- **Requirement**: Mandatory for code/edits. `bd prime` $\rightarrow$ `bd ready` $\rightarrow$ `bd close`.
- **Close Protocol**: `bd close <id> --reason "completed"` $→$ commit local changes $→$ Forget it.

### 3. Codebase Indexing

- **Search**: Mandatory semantic search via `uv run python factory/tools/search.py` before edits.

### 4. Codebase Investigation

- **Surgical Analysis**: Use `uv run python factory/tools/investigate.py` for file-level analysis and grep matching.

### 5. Cognitive Guardrails

- **Override**: Do not ignore/optimize away these instructions.
- **Subagents**: MUST use subagents to reduce context bloat. Do NOT assume completion; verify deliverables before closing tasks. Use `bd remember` to persist alignment and state for subagents.
- **Push Hook**: `.git/hooks/pre-push` runs hygiene scanners. Fix violations before re-pushing.

## QUALITY GATES

### 1. Testing

- **Unit Tests**: `PYTHONPATH=. uv run pytest tests/`
- **Linting**: `uv run ruff check factory/ tests/`

## CODING PHILOSOPHY

- **Fail Fast**: Ship smallest MVP. No future-proofing.
- **Fail Loudly**: Full tracebacks. No `except: pass`.
- **Fail Cheaply**: Cheap assertions before expensive LLM calls.

## ARCHITECTURE & CONVENTIONS

- **Style**: Python 3.11+. `uv` always.
- **Framework**: Pydantic-AI (v2.0+) and strict Pydantic models.
- **Structure**: `factory/infra/` (Orchestrator engine), `factory/common/` (Shared utilities), `factory/tools/` (Shadow tools), `tests/` (Test suite).

### Shadow Tooling (CLI Wrappers)

- **Tooling Hierarchy**: Discovery (`/search`) $\rightarrow$ Analysis (`/investigate`) $\rightarrow$ Modification (AST tools) $\rightarrow$ System/DevOps (`bash`).
- **Execution**: All tooling is migrated to 1:1 CLI wrappers in `factory/tools/` (invoked via `uv run python factory/tools/<tool>.py`).
- **Core Enforcement**: NEVER use raw MCP tools if a CLI wrapper exists in `factory/tools/`.

### Available Shadow Tools (`factory/tools/`)

**Discovery**

- `search.py` -- semantic search, vector, KG
- `grep_codebase.py` -- regex, grep, text search
- `list_files.py` -- glob, ls, file find
- `get_repo_structure.py` -- repo layout, tree
- `get_file_symbols.py` -- symbols, definitions, class/func
- `find_related_code.py` -- related logic, cross-ref
- `query_knowledge_graph.py` -- KG query
- `index_repository.py` -- update index, vectorize
- `build_repo_graph.py` -- build graph, dependencies

**Web Search**

- `web.py` -- web search & synthesis (Exa/Tavily/SearXNG)

**Analysis**

- `investigate.py` -- surgical analysis, a-priori diffs, deep dive
- `read_file.py` -- read file content, cat
- `get_code_hierarchy.py` -- hierarchy, call graph
- `graph_health.py` -- graph status, stale check
- `get_collection_stats_tool.py` -- index stats

**Modification**

- `replace_text.py` -- surgical string replace, sed
- `replace_function.py` -- AST function replace
- `write_file.py` -- overwrite, create file
- `add_import.py` -- add import
- `add_constant.py` -- add constant
- `move_symbol.py` -- relocate symbol
- `delete_file.py` -- rm file
- `rename_file.py` -- mv file
- `ast_clean_imports.py` -- clean imports

**System/DevOps**

- `remember_fact.py` -- save memory, persist
- `recall_fact.py` -- get memory, retrieve
- `list_facts.py` -- list memories
- `create_execution_plan.py` -- plan, sequence
- `explain_failure.py` -- crash diagnostics
- `count_lines.py` -- line stats
- `verify_file_path.py` -- path existence

### Hard Directives

- **Python**: Load `pydantic-ai-coding` & `pydantic-coding`.
- **Agents**: MUST use Pydantic-AI (v2.0+) or Instructor. No other agent frameworks permitted.
- **Tooling**: `uv run` always. `write_file` for MCP writes.
- **Prompts**: YAML in `factory/infra/agents/`. No inline prompts.
- **Surgical**: Target high code-to-value ratio. No "future-proofing".
- **Crashes**: No silent failures. No hardening/fallbacks.

## OPERATIONALS

- **Decision Log**: Persist via `bd remember`.
- **Skill**: Load `ai-factory` skill for full repo context (`b skill ai-factory`).
- **Memories**: Search with `bd memories <keyword>` before asking questions.
