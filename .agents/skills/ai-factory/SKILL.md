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
    _runtime.py    # Module globals (phase order, raw outputs, summaries)
    exchange.py    # Exchange-turn / status-board / JSONL persistence
    agent.py       # Agent builder & per-role agent construction
    context.py     # Staging, tier-B context injection, harness patches
    validation.py  # Invariant checks, gate constants
    execution.py   # EXECUTE phase - per-task timeout, spawn-all, patching
    pipeline.py    # Gate orchestration (plan, code-review, red-team, ops)
    agents/        # 7 role specs: planner, coder, supervisor_plan,
                   #   supervisor_review, red_team, ops, healer
                   #   Each has a .py class + .yaml prompt template
    tools.py       # Shadow tooling wrappers (search, read, write, AST)
  tools/           # CLI wrappers for repo tools
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

## Key Disciplines (LOAD-BEARING)

- **Fail Fast**: Ship smallest MVP. No future-proofing.
- **Fail Loudly**: Full tracebacks. No `except: pass`. Silent failure swallowing (e.g. catching a guardrail crash or `load_schema_gate.py` crash and treating it as a pass) is strictly prohibited.
- **Fail Cheaply**: Cheap assertions before expensive LLM calls.
- **Zero Dicts**: No `dict` access on Pydantic models. All lookups = Pydantic models.
- **Pydantic Only**: All domain data = strict Pydantic v2 models. No standalone Enums.
- **No model-level fallback**: Single model per role — never switch to a backup model on failure. Agent-level recovery (loopguard retry + `_recover_from_unexpected_behavior` with the SAME model) IS allowed and correct.
- **Harness-owned guardrails**: The coder only *declares* done; the harness runs ruff + pyright + smoke gates on staged files, and re-spawns the coder (up to `CODER_VALIDATION_PASSES` times) with guardrail feedback before the review phase. If a guardrail crashes or produces unparseable output, the task MUST fail/block—it is never a silent pass.
- **Red Team Integrity**: The `red_team_passed` gate relies solely on `findings` and `rubric_cells`. If both are empty, the audit is considered incomplete and the gate MUST fail.

## Test Pattern: Monkeypatch Refactoring

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
