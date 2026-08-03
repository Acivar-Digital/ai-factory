# Factory Upgrade Plan: Production-Grade Harness & AST Verification

## Overview

Enhance the AI-Factory harness with multi-layer AST verification, comment-preserving sandbox editing, automated target repo deployment, and a structured 3-tier review pipeline (Intern → Engineer → Senior Engineer).

The upgrade guarantees fail-fast/fail-loud verification gates, strict Pydantic v2 data contracts, Pydantic AI agent integration, comment preservation, and resource-bounded execution.

---

## 1. New Modules

### 1.1 `factory/infra/ast_verifier.py`
- **7-Layer Verification Sandbox**:
  1. Syntax check (`ast.parse` with recursion depth & 1MB limits)
  2. Cyclomatic complexity (CC > 5), nesting level (> 3), and try-pyramid detection
  3. Attribute hallucination detection (via standard library symbol inspection + pyright)
  4. Call argument signature parity & swap detection
  5. Function signature parity against `.orig` base
  6. Namespace collision detection
  7. Scope & symbol verification (`SymbolScopeVisitor` with native support for `TYPE_CHECKING`, star imports, `visit_NamedExpr`, `visit_Starred`, `visit_Subscript`)
- **`run_lint_regression()`**: Differential `ruff` and `pyright` baseline comparison against `.orig`
- **`ensure_pydantic_imports()`**: Validates Pydantic v2+ import availability (`pydantic.BaseModel`, `Field`, `ConfigDict`)
- **`VerificationCircuitBreaker`**: Opens after 3 consecutive failures per file; half-open retry after 30s. Halts tier cleanly on circuit open with structured error logs.
- **Resource Constraints**: `MAX_FILE_SIZE = 1_000_000` (1MB limit) and max AST depth ceiling (`sys.getrecursionlimit()` safety check).

### 1.2 `factory/infra/virtual_ast_buffer.py`
- **Comment-Preserving AST Buffer**: Uses concrete syntax tree (CST / line-range slicing) for code replacement instead of standard `ast.unparse()` to prevent loss of comments, docstrings, or code formatting.
- **`replace_function`**: Surgical function replacement preserving surrounding module comments and docstrings.
- **`inject_helper`**: AST-guided helper function injection.
- **`get_source`**: Source code retrieval guaranteeing 100% comment and formatting retention.
- **Python 3.11+ Support**: Handles `ast.AsyncGeneratorExp`, `ast.ExceptGroup`, and nested class definitions.

### 1.3 `factory/infra/ast_analyzer.py`
- **`FunctionCandidateScanner`**: AST anti-pattern scanner enforcing quality standards.
- **Anti-Pattern Rules**: Identifies try pyramids, deep block nesting (>3), and high cyclomatic complexity (>5).
- **`scan_file_for_anti_patterns()`**: Pre-flight analysis executed before Coder phase starts.

---

## 2. Integration Points

### 2.1 `factory/infra/tools_shell.py`
- **`verify_edit(relative_path, function_name=None)`**:
  - Reads working copy from `factory/temp/`
  - Runs `run_lint_regression` (`ruff` + `pyright`)
  - Runs `verify_refactored_ast` on targeted function or file
  - Returns strongly-typed Pydantic v2 `VerificationResult` JSON
  - Enforces per-verification timeout (`VERIFY_EDIT_TIMEOUT = 45s`)

### 2.2 `factory/infra/tools_guard.py`
- `verify_edit` registered in `MODIFY_TOOLS` and `TOOL_REGISTRY`
- ACL enforcement, plan gate validation (`remember`), and per-tier budget tracking

### 2.3 `factory/infra/pipeline.py`
- Integrates the Intern → Engineer → Senior tier execution sequence
- Executes `verify_edit` automatically after each tier's edit output
- Injects structured error diagnostics into subsequent tier prompts upon verification failure
- Halts execution loud and clear if verification fails after maximum retries

### 2.4 `factory/infra/deploy.py`
- **Automated Target Repo Sync**: Safely syncs validated temp files (`factory/temp/*.py`) to `TARGET_REPO` paths after Senior approval.
- Includes pre-flight dry-run diff check and file integrity verification prior to disk write.

---

## 3. 3-Tier Review Pipeline

### 3.1 Flow & Roles
1. **Intern**: Receives task prompt → generates initial implementation → `verify_edit` gate.
2. **Engineer**: Receives task prompt + Intern diff + verification logs → applies targeted refactoring & error fixes → `verify_edit` gate.
3. **Senior Engineer**: Receives task prompt + prior diffs + verification logs → conducts strict security, performance, and anti-pattern review → final edit → `verify_edit` gate.

### 3.2 Key Design Principles
- **Always 3 Passes**: Sequential multi-pass refinement (no skip, no bounce-back).
- **Role Differentiation**: Tier-specific system prompts with distinct temperature & sampling strategies (Intern: draft generation; Engineer: surgical fix & linter compliance; Senior: strict minimal-diff audit).
- **Pydantic AI Integration**: All agents configured using Pydantic AI v2.0+ specifications (`factory/infra/agents/*.yaml`).

### 3.3 Agent Configuration YAMLs
- `intern.yaml`: Intern Builder specification
- `engineer.yaml`: Engineer Fixer specification
- `senior.yaml`: Senior Auditor & Finalizer specification

---

## 4. Sandbox & Deployment Model

### 4.1 File Handling & Staging
- `.orig`: Untouched baseline copy of original target file.
- `.py`: Staged working copy in `factory/temp/` where LLM edits land.
- All verification steps (AST checks, linter regressions, diff generation) operate between `.orig` and `factory/temp/*.py`.
- **Automated Deployment**: `factory/infra/deploy.py` handles atomic target repository updates upon full pipeline approval.

### 4.2 Checkpoint & Log Retention
- **Atomic Checkpoints**: JSONL logs per run ID in `factory/orch/logs/` updated via temporary file + `os.replace`.
- **24-Hour TTL**: `CHECKPOINT_TTL_SECONDS = 86400` auto-expires stale session state.
- **Log Rotation Policy**: 7-day TTL log cleaner (`LOG_RETENTION_DAYS = 7`) prevents log folder storage bloat.

---

## 5. Circuit Breaker, Budgets, & Resource Limits

| Setting | Value | Purpose |
|---|---|---|
| `TOOL_BUDGET` | *Dynamic* (see rows below) | Max tool calls per tier — computed from target function line count |
| `WRITE_BUDGET` | `max(35, line_count // 2)` | Write tool budget scaled by target function AST line span |
| `READ_BUDGET` | 2x `WRITE_BUDGET` | Read tool budget = 2x write budget |
| `SOFT_NUDGE_THRESHOLD` | 80% | Soft warning emitted at 80% before fatal exhaustion |
| `MAX_RETRIES` | 10 | Max execution attempts per tier |
| `CIRCUIT_BREAKER_THRESHOLD` | 3 | Consecutive failures before opening circuit breaker |
| `CIRCUIT_BREAKER_HALF_OPEN` | 30s | Cooldown period before half-open attempt |
| `VERIFY_EDIT_TIMEOUT` | 45s | Max timeout for AST + linter regression pass |
| `MAX_FILE_SIZE` | 1,000,000 | 1MB max file size for AST parser |
| `LOG_RETENTION_DAYS` | 7 | Automatic log cleanup threshold |

---

## 6. Testing & Quality Verification

- **`tests/test_ast_verifier.py`**: Unit & integration tests for all AST verifier layers, circuit breakers, and checkpoint TTL logic.
- **Comment Preservation Tests**: Validates that CST syntax buffer edits retain 100% of docstrings and comments.
- **Edge Case Coverage**: Validates `SymbolScopeVisitor` handling of walrus operators (`:=`), starred expressions (`*args`), subscript references (`obj["key"]`), exception groups, and nested classes.
- **Lint & Type Check Pipeline**: Clean compliance via `uv run ruff check factory/ tests/` and `uv run pytest tests/`.
