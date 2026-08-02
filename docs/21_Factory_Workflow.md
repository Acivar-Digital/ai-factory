# AI-Factory Multi-Agent Pipeline Workflow Architecture — Self-Refactoring Epic

## 1. Executive Summary & Core Discipline

AI-Factory is a **deterministic Python state machine conductor** (`factory/infra/runner.py`, `factory/infra/pipeline.py`). It is **not** an LLM orchestrator — the conductor never delegates orchestration decisions to an LLM. All phase transitions, gate checks, and state mutations are driven by deterministic Python code.

In this epic, **AI-Factory refactors its own infrastructure code (`factory/infra/`)**:
- `factory/infra/validation.py` (`_feedback_from_audit`, `check_plan_invariants`, `_downstream_closure`)
- `factory/infra/gatekeeper.py` (`_affected_tests`)
- `factory/infra/ledger.py` (`_py_tree`)

The pipeline enforces a **3-tier linear review flow**: `intern` → `engineer` → `senior`. Three mandatory passes with **zero backward bouncing**. Each tier must succeed before the next begins.

**Fail Loudly & Resumable**: All state updates are atomic. A circuit breaker tier cascade ensures that if the `senior` tier trips, a `RuntimeError` is raised immediately — no silent degradation, no retry loops.

**Strict Sandboxing**: All modifications target staging copies under `factory/temp/`. A baseline `.orig` snapshot is captured at staging time for `diff_vs_orig` comparison. **Zero direct edits** to real code outside staging.

## 2. Strategic Design Principles (The 7 Signposts)

### 2.1 Model Assignment Lock

Centralized in `factory/infra/control.py`. The `ling_flash` model is assigned across **all tiers** (`intern_model`, `engineer_model`, `senior_model`). No model switching occurs without explicit user instruction. This ensures deterministic, reproducible output quality across the entire pipeline.

### 2.2 System Prompt Hardening

System prompts (`intern.yaml`, `engineer.yaml`, `senior.yaml`) enforce strict conventions:

- **Pydantic v2 syntax**: `model_dump()`, `model_validate()` — no legacy v1 `.dict()` calls.
- **Flat guard clauses**: Cyclomatic Complexity (CC) ≤ 5 per function.
- **Underscore helper naming**: Private helpers follow `_is_promo_expired` / `_check_task_file` convention.
- **Zero schema mutation**: The core `user_prompt.md` ask is never mutated by any tier.
- **Pydantic AI 2.0 native patterns** throughout all tier prompts.

### 2.3 Pydantic AI 2.0 Native Self-Correction (`ModelRetry`)

Modification tools (`replace_function`, `replace_text`, `write_file`) run `verify_edit` **instantly** on every edit. If the edit violates CC ≤ 5 or introduces syntax errors, the tool raises `pydantic_ai.ModelRetry`, forcing the **same-turn agent self-correction**. The agent must fix the issue within the current turn rather than deferring to a later pass.

### 2.4 Granular Handover & Diagnostic Persistence

`_run_verify_edit` (in `pipeline.py`) parses `target_functions` from the `user_prompt.md` frontmatter and stores per-file failure diagnostics under the key `last_tier_diagnostic_<file_path>` via `state_dict`. This diagnostic block is injected **upfront** into the next tier's prompt, ensuring each tier starts with full visibility into the previous tier's failures.

### 2.5 Cross-Tier Memory Persistence

Mandatory `bd remember` calls persist architectural decisions, AST diagnostics, and handover contracts across turns, sessions, and LLM roles. This ensures that even across separate pipeline runs, the system retains critical context about structural decisions and failure patterns.

### 2.6 Harness-Generated Live TODO Checklist

`TodoList` and `TodoItem` Pydantic v2 models in `control.py`. Harness deterministically parses `target_functions` via `verify_edit` AST checks at phase start to construct a live TODO list (`- [ ]` vs `- [x]`). Item status updates automatically on tool returns and reinjects into prompt context per turn.

### 2.7 API Transport Resilience (7-Attempt Exponential Backoff)

`ModelAPIError` retry budget in `agent.py` expanded to 7 attempts with exponential backoff (`min(64s, (2^attempt) + jitter)`) to withstand OpenRouter 429 rate limit bursts and 502/503 micro-outages.

### 2.8 Delegated Pipeline Execution & Context Preservation

- **Delegated Execution**: The Orchestrator MUST NEVER run long-running multi-agent pipeline executions (`runner.py`) directly in its main context shell window. Pipeline runs MUST be delegated to sub-agents via `task` calls (`subagent_type: "general"`).
- **Diagnostic Reporting Protocol**: The sub-agent executes `uv run python factory/infra/runner.py --prompt-file factory/prompt/user_prompt.md`, captures full stdout/stderr, AST verification failures, and stack tracebacks, and returns a concise, structured error diagnostic report to the Orchestrator.
- **Orchestrator Focus**: Upon receiving the sub-agent's report, the Orchestrator analyzes the failure mode, maintains context continuity, and performs surgical harness enhancements (prompts, AST verifiers, tool limits, guardrails).

### 2.9 Job Ledger Logging Ritual (`docs/21_Factory_Workflow_jobids.json`)

Before every delegated runner execution, the runner sub-agent assigns a sequential `job_id` (starting at `"001"`, zero-padded to 3 digits) and records the following entry into `docs/21_Factory_Workflow_jobids.json`:

| Field | Value |
|-------|-------|
| `job_id` | Sequential string, e.g. `"001"`, `"002"` |
| `timestamp_start` | ISO-8601 timestamp when the runner sub-agent begins execution |
| `timestamp_start_sgt` | Formatted Singapore Time (SGT, UTC+8) timestamp |
| `harness_changes_applied` | List of harness modifications (prompt patches, AST verifier updates, tool limit changes) made in this run |
| `pipeline_config` | Snapshot of the pipeline configuration (`start_phase`, `stop_phase`, `TARGET_REPO`, `scope`, `target_functions`) |

Upon run completion, the sub-agent appends the following fields to the same entry:

| Field | Value |
|-------|-------|
| `timestamp_end` | ISO-8601 timestamp when the runner sub-agent finishes execution |
| `timestamp_end_sgt` | Formatted Singapore Time (SGT, UTC+8) timestamp |
| `status` | `"success"` or `"failed"` |
| `failing_tier` | Tier name where the pipeline blocked (e.g. `"intern"`, `"engineer"`, `"senior"`), or `null` on success |
| `root_cause` | Description of the failure root cause, or `null` on success |
| `ast_verification_summary` | Summary of AST verification results (pass/fail counts per layer) |
| `improvements_needed` | List of harness improvements identified during the run, or empty list if none |

The JSON file is an append-only array. Each entry is a flat object with the fields above. The Orchestrator reads this ledger to audit delegation history and track harness evolution across runs.

## 3. Workflow Execution Lifecycle

```
[User Prompt] -> [Frontmatter Parser] -> [Staged Copies in factory/temp/]
       |
       v
[Intern Tier (ling_flash)]
       |---> Modification Tools (write_file / replace_function / replace_text)
       |        |---> Instant verify_edit() Check
       |        +---> Raise ModelRetry on CC > 5 or syntax error -> Turn Self-Correction
       v
[_run_verify_edit Gate] -> Persist last_tier_diagnostic in state_dict
       |
       v
[Engineer Tier (ling_flash)] -> Receives Upfront Diagnostic Block
       |---> Modification Tools + ModelRetry
       v
[_run_verify_edit Gate]
       |
       v
[Senior Tier (ling_flash)] -> Final Quality & Architecture Audit Gate
       |---> Passes CC <= 5 & AST Safety -> Emit final_result
       v
[Definition of Done Validation] -> Staged Files Ready in factory/temp/
```

## 4. Verification & Quality Gates

### 4.1 7-Layer AST Verification (`ast_verifier.py`)

Every edit passes through a comprehensive 7-layer AST verification pipeline:

| Layer | Check | Threshold |
|-------|-------|-----------|
| 1 | **Syntax Error Checks** | Any syntax error fails immediately |
| 2 | **Cyclomatic Complexity (CC)** | CC ≤ 5 per function |
| 3 | **Nesting Depth** | Depth ≤ 3 per function |
| 4 | **Hallucinated Fields** | Attributes starting with `_` are whitelisted for private helper extractions; other invented attributes are flagged |
| 5 | **Import Safety** | Relative imports (`node.level > 0`) are whitelisted |
| 6 | **Underscore Helper Naming** | Private helpers must follow `_is_promo_expired` naming convention |
| 7 | **Call Signature & Namespace Parity** | Modified functions must preserve their original call signatures and namespace references |

### 4.2 Lint Regression Check

`uv run ruff check` is run on all staged files as a final regression gate. Any lint failures block progression to the next tier or final delivery.

## 5. Telemetry, Observability & Memory Logging

- **Job Ledger**: `docs/21_Factory_Workflow_jobids.json`
- **Runtime Logs**: `factory/orch/logs/runtime/response_raw_<role>_<timestamp>.json`
- **Reports**: `factory/orch/reports/run_<timestamp>/`
- **Memory Persistence**: `bd remember` / `bd memories`

## Changelog

### 2026-08-02 (Initialization of Self-Refactoring Job 21)
- **Created Ledger & Spec**: Created `docs/21_Factory_Workflow_jobids.json` and `docs/21_Factory_Workflow.md` for tracking the self-refactoring epic of `factory/infra/` modules.
- **Scoped Functions**: Selected 5 core infrastructure functions (`_feedback_from_audit`, `check_plan_invariants`, `_downstream_closure`, `_affected_tests`, `_py_tree`).
- **Singapore Time Standard**: Mandatory SGT timestamp formatting (`timestamp_start_sgt`, `timestamp_end_sgt`) in `docs/21_Factory_Workflow_jobids.json`.
