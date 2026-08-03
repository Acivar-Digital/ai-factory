# AI-Factory Architecture & Deterministic Workflow Specification

> **Document Status**: Production Ground Truth  
> **Source Analysis**: Python Codebase (`factory/infra/`, `factory/tools/`, `factory/common/`)  
> **Orchestrator Model**: Deterministic Python Conductor (NO LLM Orchestrator)

---

## 1. System Overview & Core Philosophy

AI-Factory is a **deterministic orchestrator framework** for multi-agent code-generation and refactoring pipelines. Spawning LLM agents across a 3-tier pipeline (Intern → Engineer → Senior), all workflow decisions, routing, AST verification, and phase gating are strictly controlled by Python scripts. **No LLM makes orchestration or routing decisions.**

### Key Design Mandates
1. **Fail Fast**: Ship minimal, surgical MVPs. No speculative future-proofing.
2. **Fail Loudly**: Full tracebacks via `RuntimeError` or `SystemExit(1)`. Zero silent `except: pass` or error swallowing.
3. **Fail Cheaply**: Static AST checks, line-count bounds, and cheap assertion gates execute *before* making expensive LLM calls.
4. **Two-Root Path Model (`context.py`, `_codebase_common.py`)**:
   - **`REPO_ROOT`**: The AI-Factory repository root (`/home/yapilwsl/arthityap/ai-factory/`). Houses harness infra, logs (`orch/`), runtime state, and CLI shadow tools.
   - **`TARGET_REPO`**: The target application repo (e.g. `baziforecaster/`). Configured in `user_prompt.md` frontmatter (`target_repo:`). Agent codebase searches (`search.py`, `grep_codebase.py`, `list_files.py`) resolve against `TARGET_REPO`.
   - **`factory/temp/` Staging Sandbox**: Working copy isolated directory. All agent edits target `factory/temp/<path>`. Baseline copies (`.orig`) are captured alongside working copies (`.py`). The harness never modifies real repo files directly without explicit user deployment (`deploy.py`).

---

## 2. Pipeline Architecture & Execution Flow (`runner.py` & `pipeline.py`)

```
                              user_prompt.md
                                    │
                                    ▼
                         [read_prompt() Parser]
                                    │
                        ┌───────────┴───────────┐
                        │  Scope & Frontmatter   │
                        └───────────┬───────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────┐
                    │     3-Tier Pipeline Loop     │
                    │  (intern → engineer → senior)│
                    └───────────────┬──────────────┘
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    ▼                               ▼                               ▼
 Tier 1: Intern              Tier 2: Engineer               Tier 3: Senior
 (First-pass refactor)       (Hardening & verification)     (Audit-only verdict)
    │                               │                               │
    └───────────────────────────────┴───────────────────────────────┘
                                    │
                                    ▼
                     [Per-Function Micro-Loop]
                                    │
                                    ▼
               [Surgical Context Sandwich Injection]
               (Skeleton + Imports + Target Function AST)
                                    │
                                    ▼
                          [do_role() Execution]
                          (Pydantic-AI Agent)
                                    │
                                    ▼
                         [_run_verify_edit()]
                     ┌──────────────┴──────────────┐
                     │  7-Layer AST Verification    │
                     │  Cyclomatic Complexity <= 5  │
                     │  Ruff & Pyright Regression   │
                     └──────────────┬──────────────┘
                        ┌───────────┴───────────┐
                        │                       │
                     [PASS]                  [FAIL]
                        │                       │
                        ▼                       ▼
            Lock Function in          Cumulative Failure Ledger
         checkpoint_state.json          + Diagnostic Injection
                        │                       │
                        ▼                       ▼
               Advance to Next           Retry Same Tier or
               Target Function           Fail Loudly [HALT]
```

### 2.1 Prompt & Configuration Parsing
Execution begins at `factory/infra/runner.py`. The `read_prompt(user_prompt.md)` function parses YAML frontmatter:
- `Resume: true|false`: Continues prior run state from `state.json` if enabled.
- `scope: [path1, path2, ...]`: Relative target paths, staged into `factory/temp/<path>`.
- `target_functions: [fn1, fn2, ...]`: Functions scheduled for CC reduction. If omitted, `auto_discover_high_cc_functions()` automatically scans staged files for functions with CC > 5.
- `start_phase` & `stop_phase`: Selects pipeline execution window (`intern`, `engineer`, `senior`).
- `target_repo`: Absolute path to target codebase directory.

### 2.2 Strict 3-Tier Linear Pipeline
The pipeline runs in a strict linear cascade without backward bouncing:
1. **Intern Tier (`ling_flash`)**: Performs initial AST refactoring and helper extraction.
2. **Engineer Tier (`laguna_s`)**: Hardens code structure, fixes edge-case violations, and ensures AST compliance.
3. **Senior Tier (`ling_flash`)**: Audit-only gatekeeper. Evaluates output quality against `user_prompt.md` criteria. Modifying tools (`replace_function`, `write_file`) are hard-blocked for Senior tier.

### 2.3 Per-Function Micro-Loop & Surgical Context Sandwich
For each target function in ascending order of initial Cyclomatic Complexity (CC):
1. **Surgical Context Sandwich Generation (`_build_isolated_ast_block`)**:
   - **Layer 1**: File skeleton and top-level module imports (`extract_file_skeleton_and_imports`).
   - **Layer 2**: Target function AST node source (`extract_function_node_source`).
   - **Layer 3**: Explicit refactoring instruction targeting ONLY the single function to achieve CC <= 5. Includes AST decomposition hints if initial CC > 8.
2. **Role Agent Invocation**: Runs `do_role()`, delegating to `load_skill()`.
3. **Post-Edit AST & CC Verification**: Calls `_run_verify_edit()`:
   - Evaluates Cyclomatic Complexity (target CC <= 5).
   - Runs 7-Layer AST safety sandbox checks.
   - Runs Ruff / Pyright lint regression checks.
4. **Checkpoint Lock-In**:
   - If verification passes (CC <= 5, zero AST violations): Function is added to `locked_functions` and atomically saved to `factory/orch/reports/checkpoint_state.json`.
   - If verification fails: Prepends exact diagnostic error details and the **Cumulative Failure Ledger** (`state_dict["failure_history"]`) to the input prompt for the next attempt.
   - If 15 write failures occur across attempts for a single function, the harness halts immediately with `RuntimeError("[HALT] Target function exceeded 15 write retries — Harness/AST verification failure.")`.

---

## 3. Agent Lifecycle & Confinement Engine (`tools_guard.py` & `_loopguard.py`)

### 3.1 Pydantic-AI Integration (`agent.py`)
LLM agents are built using Pydantic-AI (`pydantic_ai.Agent`) with strongly typed models defined in `control.py`:
- **Structured Output**: Agents must emit structured output via the `final_result` tool matching registered Pydantic schemas (e.g. `TaskResult`). Plain text/markdown final responses are rejected by system prompts.
- **Transient Error Retries (`_run_agent_retry`)**: Handles provider rate limits (429) and server errors (502/503) with up to 7 attempts using exponential backoff (2s, 4s, 8s, 16s, 32s, 64s + jitter).

### 3.2 GuardToolset & Security Chokepoint (`tools_guard.py`)
`GuardToolset` wraps Pydantic-AI `FunctionToolset` instances, acting as a central security and behavioral chokepoint:
- **Mandatory Planning Gate**: Agents MUST invoke the `remember` tool to record a concrete step-by-step plan before invoking modification tools (`replace_function`, `replace_text`, `write_file`, `add_constant`, `add_import`, `move_symbol`, `delete_file`, `rename_file`).
  - Modification calls prior to `remember` are blocked with a system warning.
  - Attempting to bypass the planning gate 3 consecutive times triggers a hard `RuntimeError("[HALT] Model attempted to bypass mandatory planning (remember tool) 3 times.")`.
- **ACL Path Boundaries & Secret Denial**: Prevents directory traversal outside `REPO_ROOT` and blocks access to sensitive files (`.env`, `controls.py`, `secrets`).
- **Senior Role Restriction**: Senior tier has all code-modifying tools (`_SENIOR_BLOCKED`) stripped. Senior agent can only execute discovery tools, `read_file`, `verify_edit`, `remember`, and `final_result`.
- **Unknown Tool Absorber**: Intercepts hallucinated tool calls and returns an informative warning listing valid available tools instead of crashing the process.

### 3.3 LoopGuard & Turn Confinement (`_loopguard.py`)
All agent invocations run wrapped inside `run_with_loopguard()`:
- **Hard Execution Limits**:
  - `MAX_TOTAL_TOOL_CALLS = 40`
  - `MAX_LOOPGUARD_TURNS = 20`
  - `UsageLimits(request_limit=60 for intern, 20 for others)`
- **Soft Warning Nudge**: Emits `[budget] warning: 80% threshold reached` to stdout when tool usage hits 80% of the write budget, advising early completion.
- **Context Scrubbing (`_scrub_old_read_returns`, `intercepted_request`)**: Scrubs historical `read_file` and `batch_read` tool return contents from messages prior to the last 2 turns. Prevents token explosion during multi-turn sessions.
- **Token Budget Compaction (`compact_context_if_needed`)**: Evaluates token count before each turn. If prompt tokens exceed `CONTEXT_COMPACT_CEILING` (200,000 tokens), in-place compaction summarizes prior context using `compact_model`.

---

## 4. Dynamic Tool Budget Matrix (`control.py` & `tools_guard.py`)

Tool budgets scale dynamically according to the line count of the target file being refactored:

$$\text{write\_budget} = \max(35, \lfloor \text{line\_count} / 2 \rfloor)$$

$$\text{read\_budget} = \max(62, \text{line\_count})$$

$$\text{remember\_budget} = 999 \quad (\text{unlimited planning calls})$$

### Budget Behavior Summary
- **Static Floors**: Minimum write budget is 35 calls (`DEFAULT_TOOL_BUDGET`), minimum read budget is 62 calls (`READ_BUDGET`).
- **Read-to-Write Ratio**: Maintains a ~2:1 read-to-write ratio, ensuring adequate scanning headroom for large files without starving modification capacity.
- **Redundant Read Protection**: Requesting line ranges that were already read during the same run returns a `REDUNDANT READ` warning, preserving the agent's remaining tool quota.

---

## 5. Verification & AST Safety Engine (`ast_verifier.py`)

Post-edit code verification passes through a 7-layer AST verification engine (`verify_refactored_ast`) before acceptance.

### 5.1 The 7-Layer AST Verification Sandbox

| Layer | Verification Name | Check Description |
| :--- | :--- | :--- |
| **Layer 1** | **Syntax Sandbox** | Validates code parses via `ast.parse()` without `SyntaxError`. |
| **Layer 2** | **Unauthorized Imports & Symbols** | Restricts imports to safe standard libraries & existing baseline imports. Rejects creation of unauthorized `ClassDef` nodes. |
| **Layer 3** | **Namespace & Helper Rules** | Enforces extracted helper functions start with `_helper_*` and do not collide with existing module namespace symbols. |
| **Layer 4** | **Attribute Sandbox** | Compares `ast.Attribute` references against `.orig` baseline attributes and an approved whitelist to catch hallucinated field accesses. |
| **Layer 5** | **Call Signature Sandbox** | Inspects `ast.Call` nodes to prevent argument ordering swaps relative to baseline call signatures. |
| **Layer 6** | **Signature Parity** | Ensures target function parameters (`posonly`, `args`, `vararg`, `kwonly`, `kwarg`, `defaults`) match baseline contracts exactly. |
| **Layer 7** | **Symbol Scope Check** | Runs `SymbolScopeVisitor` across AST to verify all referenced names, function calls, and type annotations exist in imports, top-level symbols, global constants, or builtins. |

### 5.2 Complexity, Nesting & Anti-Pattern Rules
- **Cyclomatic Complexity Gate**: Target function and all generated helper functions must have CC $\le 5$.
- **Nesting Depth Gate**: Maximum statement nesting depth must be $\le 3$.
- **Try Pyramid Ban**: Rejects nested `Try` blocks within `Try` bodies, `Except` handlers, or `Try-Else` clauses.

### 5.3 Lint & Type Regression (`run_lint_regression`)
- Compares refactored code against `.orig` baseline using:
  - `uv run ruff check --select F821,E9,F63,F7`
  - `uv run pyright`
- Any *new* linting errors or type violations relative to baseline trigger verification failure.

### 5.4 Verification Circuit Breaker (`VerificationCircuitBreaker`)
- Tracks consecutive verification failures per file path.
- **Circuit Trip**: Opens after 3 consecutive failures.
- **Half-Open Cooldown**: Remains open for 30 seconds before permitting a half-open retry attempt. A successful verification resets the counter.

---

## 6. Staging, Memory & State Persistence (`context.py`, `state.py`, `exchange.py`)

- **Orchestrator State (`state.json`)**: Persisted atomically via temporary file write and `os.replace()`.
- **Function Checkpointing (`checkpoint_state.json`)**: Locked-in CC $\le 5$ functions are saved to `factory/orch/reports/checkpoint_state.json` to survive script restarts.
- **Cumulative Failure Ledger**: Failed attempt summaries are appended to `state_dict["failure_history"]`. Subsequent tier attempts inject the full `[CUMULATIVE FAILURE LEDGER — DO NOT REPEAT THESE FAILURE PATHS]` block into prompts to eliminate repetitive LLM error loops.
- **TeeLogger**: Duplicates stdout/stderr to `factory/orch/logs/runtime/run.log` for real-time observability.
- **Deployment Control (`deploy.py`)**: Verified staged code in `factory/temp/` is deployed to target locations ONLY when explicitly triggered. Harness pipeline runs NEVER touch target repo source files directly.
