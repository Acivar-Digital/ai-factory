# AI-Factory Multi-Agent Pipeline Workflow Architecture

## 1. Executive Summary & Core Discipline

AI-Factory is a **deterministic Python state machine conductor** (`factory/infra/runner.py`, `factory/infra/pipeline.py`). It is **not** an LLM orchestrator — the conductor never delegates orchestration decisions to an LLM. All phase transitions, gate checks, and state mutations are driven by deterministic Python code.

The pipeline enforces a **3-tier linear review flow**: `intern` → `engineer` → `senior`. Three mandatory passes with **zero backward bouncing**. Each tier must succeed before the next begins.

**Fail Loudly & Resumable**: All state updates are atomic. A circuit breaker tier cascade ensures that if the `senior` tier trips, a `RuntimeError` is raised immediately — no silent degradation, no retry loops.

**Strict Sandboxing**: All modifications target staging copies under `factory/temp/`. A baseline `.orig` snapshot is captured at staging time for `diff_vs_orig` comparison. **Zero direct edits** to `TARGET_REPO`.

## 2. Strategic Design Principles (The 7 Signposts)

### 2.1 Model Assignment Lock

Centralized in `factory/infra/control.py`. The `ling_flash` model is assigned across **all tiers** (`intern_model`, `engineer_model`, `senior_model`). No model switching occurs without explicit user instruction. This ensures deterministic, reproducible output quality across the entire pipeline.

### 2.2 System Prompt Hardening

System prompts (`intern.yaml`, `engineer.yaml`, `senior.yaml`) enforce strict conventions:

- **Pydantic v2 syntax**: `model_dump()`, `model_validate()` — no legacy v1 `.dict()` calls.
- **Flat guard clauses**: Cyclomatic Complexity (CC) ≤ 5 per function.
- **Underscore helper naming**: Private helpers follow `_is_promo_expired` convention.
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

### 2.9 Job Ledger Logging Ritual (`docs/20_Factory_Workflow_jobids.json`)

Before every delegated runner execution, the runner sub-agent assigns a sequential `job_id` (starting at `"001"`, zero-padded to 3 digits) and records the following entry into `docs/20_Factory_Workflow_jobids.json`:

| Field | Value |
|-------|-------|
| `job_id` | Sequential string, e.g. `"001"`, `"002"` |
| `timestamp_start` | ISO-8601 timestamp when the runner sub-agent begins execution |
| `harness_changes_applied` | List of harness modifications (prompt patches, AST verifier updates, tool limit changes) made in this run |
| `pipeline_config` | Snapshot of the pipeline configuration (`start_phase`, `stop_phase`, `TARGET_REPO`, `scope`, `target_functions`) |

Upon run completion, the sub-agent appends the following fields to the same entry:

| Field | Value |
|-------|-------|
| `timestamp_end` | ISO-8601 timestamp when the runner sub-agent finishes execution |
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

### Detailed Flow

1. **Frontmatter Parser**: Reads `user_prompt.md`, extracts `scope`, `target_functions`, `start_phase`, `stop_phase`, and `TARGET_REPO` configuration.
2. **Staging**: Copies target files into `factory/temp/` with `.orig` baseline snapshots via `context.py:_stage_copies`.
3. **Intern Tier**: The `intern` agent makes initial modifications. Every edit is verified instantly via `verify_edit()`. If CC > 5 or syntax fails, `ModelRetry` forces same-turn self-correction.
4. **Verify Gate**: `_run_verify_edit` runs a full AST verification pass on the intern's staged files. Results are stored in `state_dict` under `last_tier_diagnostic_<path>`.
5. **Engineer Tier**: Receives the diagnostic block from the verify gate as upfront context. Makes refinement edits with the same `ModelRetry` self-correction mechanism.
6. **Verify Gate**: Same `_run_verify_edit` gate runs again on engineer's edits.
7. **Senior Tier**: Final quality and architecture audit gate. Reviews all staged files for CC ≤ 5, AST safety, and architectural correctness. On success, emits `final_result`.
8. **Definition of Done**: Staged files in `factory/temp/` are validated and ready for the next pipeline phase or final delivery.

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

### Runtime Logs

- **Raw response artifacts**: `factory/orch/logs/runtime/response_raw_<role>_<timestamp>.json` — full model interaction JSON for every tier.
- **Execution log**: `factory/orch/logs/runtime/run.log` — continuous stdout capture of all pipeline activity.

### Execution Reports

- **Report directories**: `factory/orch/reports/run_<timestamp>/` — structured execution reports per pipeline run, including tier results, diagnostics, and artifact snapshots.

### Persistent Memory

- **`bd remember` / `bd memories`**: Cross-session memory persistence for architectural decisions, AST diagnostics, and handover contracts. These survive across turns, sessions, and LLM role switches.

### Failure Logging

- **Failure artifacts**: `factory/orch/logs/runtime/fail_<tier>_<tier>.json` — structured failure diagnostics when a tier is blocked or trips the circuit breaker.
- **Main failure log**: `factory/orch/logs/runtime/fail_main.log` — uncaught exception tracebacks for pipeline-level failures.

## Changelog

### 2026-08-02 (Pre-Restart Harness Hardening & Resilience)
- **Per-Function Atomic Checkpointing**: Implemented `_persist_checkpoint()` in `pipeline.py` to write locked function progress atomically to `factory/orch/reports/checkpoint_state.json`, preserving completed work across restarts/interruptions.
- **Automated Monolith AST Decomposition Hints**: Added `generate_ast_decomposition_hint()` in `pipeline.py` to analyze CC > 8 functions and inject concrete helper function extraction suggestions into Layer 3 of the Surgical Context Sandwich.
- **Symbol-Enriched ModelRetry Guidance**: Updated `replace_function` and `replace_text` in `tools_shell.py` to include module symbol outlines (`imported_modules` + `top_level_symbols`) in `ModelRetry` diagnostics when in-tool AST verification fails.

### 2026-08-02 (Function-by-Function Micro-Loops & Surgical Context Sandwich)
- **Function-by-Function Micro-Loops**: Pipeline in `pipeline.py` executes refactoring sequentially function-by-function. Once a function reaches CC <= 5, it is locked in immediately and skipped in subsequent passes.
- **Surgical Context Sandwich Pattern**: Constructed 3-layer prompt context block (`extract_file_skeleton_and_imports` + `extract_function_node_source` + function-specific refactoring directive), preserving global imports and symbol outlines while keeping prompt sizes under 3k tokens.
- **Attempt Generosity**: Increased tier attempt allowance from 3 to 5 attempts per tier (`MAX_ATTEMPTS = 5`).

### 2026-08-02 (Function-Node Slicing & Enterprise AST Upgrade)
- **Function-Node Slicing**: Implemented `extract_function_node_source()` and `stitch_function_node_source()` in `virtual_ast_buffer.py` using standard library `ast.parse`. Extracts isolated 15-line target function AST nodes and stitches refactored nodes back deterministically.
- **Turn 1 Prompt AST Node Injection**: Added `_build_isolated_ast_block()` in `pipeline.py` to automatically inject target function AST source into Turn 1 prompt context, eliminating the 15-read death spiral.
- **Read Budget Nudge Enforcement**: Enforced `READ_BUDGET=3` cap and `_READ_REDUNDANT` / `_READ_FATAL` nudging inside `GuardToolset`.

### 2026-08-02 (Pydantic-AI 2.0 & Harness Alignment Upgrade)
- **Workflow Spec Initialized**: Created `docs/20_Factory_Workflow.md` incorporating the 5 strategic signposts (later expanded to 7).
- **Pydantic-AI 2.0 Hooks Capability**: Integrated native `@hooks.on.before_model_request` lifecycle hook in `agent.py` for context scrubbing.
- **Strongly-Typed Dependency Injection**: Added `TierState` dependency model (`deps_type=TierState`) in `control.py` and `agent.py`.
- **Structured Output Handover Models**: Added Pydantic v2 handoff models (`InternResult`, `EngineerResult`, `SeniorVerdict`) in `control.py`.
- **Audit-Only Tool Scoping**: Implemented Senior role tool filter in `tools_guard.py` restricting Senior tier to read/audit tools (`verify_edit`, `read_file`, `grep_codebase`) and blocking code modifications.
- **Pydantic AI 2.0 ModelRetry**: Integrated native tool-level retries inside `tools_file.py` and `tools_shell.py` for instant AST self-correction.
- **System Prompt Hardening**: Injected Pydantic v2 rules, flat guard clause constraints (CC <= 5), and underscore helper naming (`_is_promo_expired`) into `intern.yaml`, `engineer.yaml`, `senior.yaml`.
- **Memory Isolation Discipline**: Recorded strict isolation boundary between local factory runtime traces (`state_dict`, `factory/orch/`) and global Orchestrator `bd remember` database.

### 2026-08-02 (Harness Resilience & TODO Checklist Upgrade)
- **Harness-Generated TODO Checklist**: Implemented `TodoItem` and `TodoList` Pydantic v2 models in `control.py` and `build_todo_checklist()` in `pipeline.py`. Live AST checklist (`[ ]` vs `[x]`) reinjects into prompt context per turn.
- **API Transport Resilience**: Expanded `ModelAPIError` retry budget in `agent.py` from 3 to 7 attempts with exponential backoff (`2s -> 4s -> 8s -> 16s -> 32s -> 64s`) + jitter to withstand OpenRouter 429 rate limit bursts and 502/503 micro-outages.
- **Compound Condition Rule**: Injected explicit Compound Condition Rule into `intern.yaml` and `engineer.yaml` forcing decomposition of `if A and B:` into flat single-condition guard clauses to prevent AST CC inflation.
- **Section 2 Expanded**: Added Principle 6 (Harness-Generated Live TODO Checklist) and Principle 7 (API Transport Resilience) to Strategic Design Principles.

### 2026-08-02 (Job Ledger Ritual & Structured Experimentation Logging)
- **Principle 9 (Job Ledger Logging Ritual)**: Added `docs/20_Factory_Workflow_jobids.json` as an append-only JSON ledger. Before every delegated runner execution, the runner sub-agent assigns a sequential `job_id` (zero-padded to 3 digits) and logs `timestamp_start`, `harness_changes_applied`, and `pipeline_config`. Upon completion, `timestamp_end`, `status`, `failing_tier`, `root_cause`, `ast_verification_summary`, and `improvements_needed` are appended to the entry.
- **Structured Experimentation Logging**: The job ledger provides a deterministic audit trail for all delegation runs, enabling cross-run comparison of harness changes and their outcomes.

### 2026-08-02 (Delegated Execution Protocol & Harness Enhancement Workflow)
- **Principle 8 (Delegated Pipeline Execution)**: Added rule requiring Orchestrator to delegate pipeline runs (`runner.py`) to sub-agents via `task` tool, receiving structured diagnostic reports to prevent main context exhaustion while focusing on harness tuning.
### 2026-08-02 (Loud Mandatory Jobids Ledger Inspection at Every Turn)
- **Principle 10 (Mandatory Jobids Inspection at Every Turn)**: Orchestrator MUST read and inspect `/home/yapilwsl/arthityap/ai-factory/docs/20_Factory_Workflow_jobids.json` at EVERY turn to prevent context loss during context compaction.
- **Top-Level Ledger Directives**: Inspect `project_title`, `objective`, `definition_of_done`, `autonomous_execution_rules` (`what_you_must_do` vs `what_you_must_not_do`), and `target_functions_status` table to drive all autonomous harness hardening decisions.

### 2026-08-02 (Unified Sub-Agent Memory Mandate via bd remember)
- **Principle 11 (Unified Intelligence & bd remember Alignment)**: Orchestrator and sub-agents operate as ONE unified system. Always use `bd remember` for persistent architectural decisions and alignment updates. Sub-agents query and write to `bd remember` to maintain context across context compactions and agent invocations.

### 2026-08-03 (Dynamic Budget Matrix & Soft Nudge)
- **Dynamic Budget Matrix**: Replaced static tool budget allocation with a line-count-based dynamic matrix. Write budget = `max(35, line_count // 2)`, where `line_count` is derived from the target function's AST `lineno`/`end_lineno` span. Read budget = 2x write budget, scaling proportional allocation to target function complexity while enforcing a hard cap to prevent infinite read loops. This supersedes the prior `compute_dynamic_retry_budget` formula (`max(5, line_count // 5)`) which was too conservative for multi-function refactors.
- **Soft Nudge at 80%**: A soft warning (`[budget] warning: 80% threshold reached`) is emitted at 80% of budget consumption via stdout in `_loopguard.py`, prompting the agent to wrap up before the fatal exhaustion threshold at 100%. This replaces the silent failure mode and resolves the earlier rejected formulation (max(5, line_count // 5) / max(15, line_count // 2)) that failed the 7-gap critical assessment.
