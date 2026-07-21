# Refactoring Plan: Runner Split + Agent Modules + Pip-ification

## Goal

Break the monolithic `runner.py` (3558 lines) into a phase-per-file pipeline, colocate each agent with its YAML template, and make all modules proper installable subpackages with clean exports.

**Execution style**: Big bang — all phases refactored in one pass. No incremental PRs or deprecation compat layers. Everything is in scope simultaneously (pipeline split, agent module extraction, pip-ification, test path updates).

## Studio (`studio/`)

A new top-level directory for orchestrator staging, prototyping, and integration work. Located at `studio/`, gitignored, with no initial content. Ready for future use once the refactor stabilises.

---

## Phase 1 — Pipeline Runner (`factory/infra/`)

`runner.py` becomes a **thin CLI entry point** (~150 lines). The pipeline coordination moves to phase-specific files:

| New file | Concern | Extracted from `runner.py` |
|---|---|---|
| `factory/infra/runner.py` | CLI args, `main()` orchestration, module-level helpers | `read_prompt()`, `main()`, `_PHASE_ORDER`, `_SKIPPED_PHASES`, `_RECOVERY_COUNT`, `_COMPACTION_COUNT`, `RAW_OUTPUTS`, `SCOPE_CONTEXT` |
| `factory/infra/pipeline.py` | Pipeline phases: planning gate, code-review gate, red-team gate, ops phase | `do_role()`, `record_coder()`, `run_gated()`, `_assert_plan_gate_ok()`, `_sync_state()`, `_checkpoint()`, `run_code_review_gate()`, `run_red_team_gate()`, `passed()` |
| `factory/infra/agent.py` | Agent lifecycle: build, spawn, recover, log | `build_role_agent()`, `load_skill()`, `_run_agent_retry()`, `_recover_role_output()`, `_SanitizedResult`, `_report_run_failure()`, `append_eval_log()`, `logfire` config |
| `factory/infra/context.py` | Size-aware injection, staging, patching | `estimate_task_tokens()`, `task_context_tier()`, `_stage_copies()`, `_edit_mode_block()`, `_build_tier_b_map()`, `_edit_mode_for()`, `stage_path()`, `stage_paths()`, `stage_workspace_from_draft()`, `_write_harness_patches()`, `staged_zero_diff()`, `_quarantine_coder_artifacts()`, `_dep_pointers_for()`, `TASK_TOKEN_THRESHOLD`, `TIER_B_SLICE_THRESHOLD`, `_TokenEstimate`, `TaskNeedsSplitError` |
| `factory/infra/validation.py` | Harness validation gates (ruff/pyright/smoke) | `_downstream_closure()`, `check_plan_invariants()`, `red_team_passed()`, `_blocker_findings_from_risks()`, `_feedback_from_review_findings()`, `_feedback_from_audit()` |
| `factory/infra/execution.py` | DAG execution (task scheduling) | `run_execute_phase()`, `execute_task()`, `process_group()` |
| `factory/infra/exchange.py` | Exchange turn persistence + status board | `ExchangeTurn`, `exchange_path()`, `load_exchange()`, `format_exchange()`, `save_exchange()`, `append_exchange_turn()`, `update_status_board()`, `TeeLogger`, `_model_to_md()`, `_render_verdict_block()`, `_render_history_md()`, `_detect_and_mark_recovery()` |

### Dependencies between new files

```
runner.py
  └─ pipeline.py
       ├─ agent.py
       │    ├─ context.py
       │    ├─ validation.py
       │    └─ exchange.py
       ├─ execution.py
       │    ├─ agent.py
       │    └─ context.py
       └─ exchange.py
```

### Module-level globals migration

Move module-level `_RECOVERY_COUNT`, `_COMPACTION_COUNT`, `PHASE_SUMMARIES`, `SCOPE_CONTEXT`, `RAW_OUTPUTS`, `_SKIPPED_PHASES` into a **shared state module** or a dedicated `pipeline.py` namespace. Keep them out of `runner.py` to avoid circular imports.

### Sync point: `RAW_OUTPUTS` / `PHASE_SUMMARIES`

`load_skill()` in `agent.py` writes to both. `pipeline.py` reads from both for plan-gate assertions and the L3 food chain. Use a simple mutable dict in a shared module (`factory/infra/_runtime.py`) as the single seam.

---

## Phase 2 — Agent-Specific Modules (`factory/infra/agents/`)

Each agent gets its own `.py` file colocated with its YAML template:

```
factory/infra/agents/
├── __init__.py           # public exports + register in SKILL_MAP
├── planner.py            # DraftPlan logic + planner.yaml
├── planner.yaml
├── coder.py              # TaskResult logic + coder.yaml
├── coder.yaml
├── supervisor.py         # ApprovedPlan + ReviewResult logic
├── supervisor_plan.yaml
├── supervisor_review.yaml
├── red_team.py           # AuditResult logic + red_team.yaml
├── red_team.yaml
├── ops.py                # GitResult logic + ops.yaml
└── ops.yaml
```

Each agent module exports:
- `build_spec(role: str) -> SkillSpec` — overrides/extensions of the base skill spec
- Custom validation or prompt-enrichment functions

The YAML files are loaded via `importlib.resources` (`from factory.infra.agents import planner as _pkg; data = _pkg.read_text('planner.yaml')`) instead of `Path(__file__)` string manipulation.

`control.py`'s `load_skill_map()` is updated to resolve template paths from the agents subpackage.

### Template X `__init__.py`

```python
"""Agent implementations — one module per role, colocated with YAML templates."""
from factory.infra.agents.planner import build_planner_spec
from factory.infra.agents.coder import build_coder_spec
from factory.infra.agents.supervisor import build_supervisor_spec
from factory.infra.agents.red_team import build_red_team_spec
from factory.infra.agents.ops import build_ops_spec
```

---

## Phase 3 — Pip-ification (Clean Subpackages)

### `factory/` → proper namespace package with `__init__.py` re-exports

#### `factory/__init__.py`

```python
"""ai-factory — autonomous multi-agent coding factory."""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("ai-factory")
except PackageNotFoundError:
    __version__ = "0.1.0"
```

#### `factory/common/__init__.py`

Re-export all public symbols from `operator`, `registry`, `md_bridge`, `subprocess`. Already done — just add `__all__` coverage check.

#### `factory/infra/__init__.py`

Become the **public API surface** of the infra package:

```python
"""Orchestrator infra — pipeline, agents, tooling."""
from factory.infra.runner import main
from factory.infra.pipeline import run_pipeline
from factory.infra.agent import load_skill
from factory.infra.execution import run_execute_phase
from factory.infra.context import stage_path, estimate_task_tokens
from factory.infra.validation import check_plan_invariants, red_team_passed
```

No internal modules (`_loopguard`, `_runtime.py`, internal helpers) are re-exported.

#### `factory/tools/__init__.py`

Re-export tool definitions and registry.

### Imports clean-up

Replace intra-package relative imports (`from . import converter`) with explicit absolute imports (`from factory.infra import converter`). This makes the package installable and importable from anywhere.

---

## Phase 4 — `pyproject.toml` Updates

```toml
[project]
name = "ai-factory"
version = "0.1.0"
description = "Autonomous, multi-agent AI coding factory and orchestrator framework"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0.0",
    "pydantic-ai>=0.0.14",
    "pydantic-settings>=2.0.0",
    "httpx>=0.25.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.3.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["factory"]

[tool.hatch.build.targets.wheel.force-include]
# Include YAML templates in the wheel
"factory/infra/agents/*.yaml" = "factory/infra/agents/"
```

---

## Phase 5 — Tests

### Update import paths

46 test files under `tests/` import from `factory.infra.runner`, `factory.infra.control`, `factory.infra.tools`, etc. After the split, many symbols move.

**Big bang approach**: Update ALL test imports in one pass alongside the refactor. `factory/infra/__init__.py` re-exports every public symbol so both old and new import styles work.

### New tests

- `test_pipeline_modules.py` — test each new module loads without import errors
- `test_agents_subpackage.py` — test agent specs build correctly from YAML

---

## Execution Order

```
Step 1:  Create factory/infra/_runtime.py  (shared mutable state)
Step 2:  Extract exchange.py              (status board + ExchangeTurn)
Step 3:  Extract agent.py                 (build_role_agent + load_skill + recovery)
Step 4:  Extract context.py               (staging + patching + token estimation)
Step 5:  Extract validation.py            (plan invariants + gate helpers)
Step 6:  Extract execution.py             (run_execute_phase)
Step 7:  Extract pipeline.py              (do_role + run_gated + gates)
Step 8:  Slim runner.py                   (CLI args + main() + imports)
Step 9:  Create factory/infra/agents/     (one .py per role + YAML + __init__.py)
Step 10: Update pyproject.toml            (include YAML files in wheel)
Step 11: Update factory/infra/__init__.py  (clean public exports)
Step 12: Update ALL test imports           (big bang — all paths in one pass)
Step 13: Run full test suite              (PYTHONPATH=. uv run pytest tests/)
Step 14: Run linting                      (uv run ruff check factory/ tests/)
```
