# Factory Upgrade Plan: Optimize Harness with kill_tries.py Logic

## Overview

Enhance the AI-Factory harness with AST verification, sandbox-based editing, and a 3-tier review pipeline (intern → engineer → senior engineer). The goal is to produce higher-quality code by adding verification gates and a multi-pass review chain.

---

## 1. New Modules

### 1.1 `factory/infra/ast_verifier.py`
- 7-layer AST verification sandbox:
  1. Syntax check
  2. CC/nesting/try-pyramid checks
  3. Attribute hallucination detection
  4. Call argument swap detection
  5. Signature parity
  6. Namespace collision
  7. Unimported symbol detection (via `SymbolScopeVisitor`)
- `run_lint_regression()` — ruff/pyright baseline comparison
- `ensure_pydantic_imports()` — verifies pydantic imports are available
- `SymbolScopeVisitor` — tracks imported symbols and their usage; handles `ast.Name`, `ast.Call`, `ast.AnnAssign`, `ast.NamedExpr` (walrus), `ast.Starred`, `ast.Attribute`, `ast.Subscript`
- `VerificationCircuitBreaker` — opens after 3 consecutive failures per file, half-open after 30s
- All `ast.parse` calls enforce `MAX_FILE_SIZE = 1_000_000` (1MB)
- Structured logging via `logger.info`/`logger.warning` at each stage

### 1.2 `factory/infra/virtual_ast_buffer.py`
- `VirtualASTBuffer` for in-memory AST replacement
- `replace_function` — surgical function replacement without touching disk
- `inject_helper` — inject helper functions into the AST
- `get_source` — retrieve the current source via `ast.unparse()`
- Supports recursive class search (nested classes)
- Handles `ast.AsyncGeneratorExp` and `ast.ExceptGroup` (Python 3.11+)

### 1.3 `factory/infra/ast_analyzer.py`
- `FunctionCandidateScanner` — anti-pattern detection with priority ranking
- Detects: try pyramids, deep nesting >3, cyclomatic complexity >5
- `scan_file_for_anti_patterns()` — pre-flight check before coder starts
- Handles `ast.AsyncGeneratorExp` and `ast.ExceptGroup` (Python 3.11+)

---

## 2. Integration Points

### 2.1 `factory/infra/tools_shell.py`
- `verify_edit(relative_path, function_name=None)` — runs after any edit
  - Reads file from disk
  - Runs `run_lint_regression` (ruff/pyright)
  - Runs `verify_refactored_ast` on the target function or full file
  - Returns JSON result with pass/fail and details
  - 30s timeout when called from pipeline

### 2.2 `factory/infra/tools_guard.py`
- `verify_edit` registered in `MODIFY_TOOLS` and `TOOL_REGISTRY`
- ACL-wrapped and budget-tracked like all other tools

### 2.3 `factory/infra/pipeline.py`
- `verify_edit` wired into the intern→engineer→senior pipeline
- After each tier produces an edit, `verify_edit` runs automatically
- Failed verification errors are injected into the next tier's prompt
- `MAX_FILE_SIZE = 1_000_000` enforced on all `ast.parse` calls
- `VERIFY_EDIT_TIMEOUT = 30` seconds per verification

---

## 3. 3-Tier Review Pipeline

### 3.1 Flow
1. **Intern** receives the user prompt → produces an edit → `verify_edit` gate
2. **Engineer** receives the prompt + intern's diff → produces an edit → `verify_edit` gate
3. **Senior Engineer** receives the prompt + all prior diffs → produces final edit → `verify_edit` gate

### 3.2 Key Design Decisions
- **Always 3 passes** — never skip tiers
- **Each tier can edit directly** — no bouncing back, no pass-back
- **Shared prompt base** — same user prompt for all tiers
- **Tier-specific system prompts** — fixed role definitions, dynamic user content
- **No model diversity** — same LLM for all tiers (cost consideration)

### 3.3 Agent YAMLs
- `intern.yaml` — exists (Intern Builder role)
- `engineer.yaml` — new (Engineer role, hands-on fixer)
- `senior.yaml` — replaces `boss.yaml` (Senior Engineer role, final authority)

---

## 4. Sandbox Model

### 4.1 File Handling
- `.orig` = original file in the real repo (never modified)
- `.py` = working copy in `factory/temp/` that the LLM edits
- All checks (AST verification, lint regression, diff) run between `.orig` and `.py`
- The finished file stays in temp — the user copies it to the desired repo manually
- The harness never writes to the real repo

### 4.2 Checkpoint/Resume
- JSONL per run ID in `factory/orch/logs/`
- Atomic writes (temp file + `os.replace`) to prevent interleaving under concurrency
- 24-hour TTL (`CHECKPOINT_TTL_SECONDS = 86400`); stale checkpoints auto-expire

### 4.3 Pre-flight Anti-pattern Check
- `ast_analyzer.scan_file_for_anti_patterns()` runs before the coder starts
- Gives early feedback on try pyramids, deep nesting, CC > 5

---

## 5. Circuit Breaker & Budget

- **Tool call budget**: 20 tool calls per tier
- **Retry limit**: 10 tries per tier
- **VerificationCircuitBreaker**: Opens after 3 consecutive verification failures for a file
- **Half-open**: After 30s, allows one more attempt before fully opening

---

## 6. Testing

- `tests/test_ast_verifier.py` — 64+ tests covering all 3 new modules, circuit breaker, and checkpoint TTL
- Each sandbox layer tested with both passing and failing inputs
- Edge cases: `SymbolScopeVisitor` with `ast.Subscript`, `ast.NamedExpr`, `ast.Starred`
- `VirtualASTBuffer` with nested classes
- `ast_analyzer` with async generators and exception groups

---

## 7. Logging & Observability

- Structured logging via `logger.info`/`logger.warning` at each stage of `verify_refactored_ast` and `run_lint_regression`
- Logs go to `factory/orch/logs/` (existing folder)
- Verification results logged for operator visibility

---

## 8. SymbolScopeVisitor Enhancements

Added handling for:
- `visit_NamedExpr` — walrus operator (`:=`)
- `visit_Starred` — starred expressions (`*args`)
- `visit_Subscript` — subscript references (`obj["key"]`, `arr[i]`)

---

## 9. Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `MAX_FILE_SIZE` | 1,000,000 | Max file size for `ast.parse` |
| `VERIFY_EDIT_TIMEOUT` | 30 | Seconds per verification |
| `CHECKPOINT_TTL_SECONDS` | 86400 | 24-hour checkpoint expiry |
| `TOOL_BUDGET` | 20 | Tool calls per tier |
| `MAX_RETRIES` | 10 | Retries per tier |
| `CIRCUIT_BREAKER_THRESHOLD` | 3 | Consecutive failures before opening |
| `CIRCUIT_BREAKER_HALF_OPEN` | 30 | Seconds before half-open attempt |