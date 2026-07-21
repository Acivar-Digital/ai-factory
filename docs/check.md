# Migration Verification Protocol & Checklist (`check.md`)

This document defines the comprehensive verification protocol to ensure that the extraction and migration of the Orchestrator harness from `baziforecaster` into the standalone `factory` (`ai-factory`) repository is **100% complete, functional, isolated, portable, and verifiable**.

---

## 🎯 Verification Objectives & Outcome Criteria

To declare the migration successful, the codebase must pass six rigorous quality gates:

1. **Packaging & Dependency Integrity**: `uv sync --extra dev` builds cleanly with Hatchling (`[tool.hatch.build.targets.wheel] packages = ["factory"]`) and all runtime dependencies (`pydantic-ai`, `fast-json-repair`, etc.) are declared in `pyproject.toml`.
2. **Test Suite & Linting Readiness**: `uv run ruff check factory/ tests/` and `PYTHONPATH=. uv run pytest tests/` execute with zero errors and 100% pass rate.
3. **Epistemic & Memory Continuity**: All 14 persistent harness memories are loaded and active in `bd memories`, backed up in `facts/memories.json`, and the `bd` task database is functional.
4. **Target Isolation & Zero-Trace Scrubbing**: `baziforecaster` contains zero references, files, skills, or leftover `bd` memories from `orchestrator`.
5. **Runtime Entrypoint & Tooling Verification**: Entrypoints (`./start.sh`, `./continue.sh`) and shadow tools (`factory/tools/*.py`) execute without module import errors or missing symbol failures.
6. **Community Sandboxing & Portability**: Zero hardcoded absolute user paths (e.g. `/home/yapilwsl/...`). Root directories resolved dynamically via `PROJECT_ROOT` / `TARGET_ROOT`. `opencode.json` and `.agents/` workflow configs installed.

---

## 🔍 Detailed Quality Gate Checklist

### Gate 1: Packaging & Dependency Verification
- [x] Add package declaration `[tool.hatch.build.targets.wheel] packages = ["factory"]` to `pyproject.toml`.
- [x] Add missing runtime dependencies (`fast-json-repair`) to `pyproject.toml`.
- [x] Verify `uv sync --extra dev` completes successfully without build errors.

### Gate 2: Code Health & Test Suite Rewiring (100% Pass)
- [x] Run `uv run ruff check factory/ tests/` to confirm zero linting or formatting errors.
- [ ] Fix test suite failures in `tests/` caused by import renames (`control_orchestrator` -> `control`), strict Pydantic model naming (`coderNN`), or test fixture attributes.
- [ ] Verify `PYTHONPATH=. uv run pytest tests/` passes all tests (220+ tests passing, 0 failures).

### Gate 3: Memory & State Continuity
- [x] Run `bd memories` to confirm all 14 persistent memories are restored and readable.
- [x] Verify `facts/memories.json` matches the `bd memories` snapshot.
- [x] Confirm `bd stats` shows all 105 issues intact.

### Gate 4: Zero-Trace Scrubbing of `baziforecaster`
- [x] Verify `/home/yapilwsl/arthityap/baziforecaster/admin/orchestrator` does not exist.
- [x] Confirm `orchestrator` memories scrubbed from `baziforecaster`.
- [x] Confirm `orchestrator` skills purged from `baziforecaster`.

### Gate 5: CLI & Shadow Tooling Execution
- [ ] Verify `./start.sh` initializes correctly and parses task briefs without import failures.
- [ ] Verify `./continue.sh` rehydrates state from `.checkpoints/`.
- [ ] Audit shadow tools in `factory/tools/` to ensure clean import execution.

### Gate 6: Community Sandboxing & Portability
- [x] Copy `opencode.json` settings from `baziforecaster` into `factory/opencode.json`.
- [x] Copy workflows and framework skills (`pydantic-ai-coding`, `pydantic-coding`, `pydantic-evals`, `script-hygiene`, `mcp-playbook`) into `factory/.agents/`.
- [ ] Audit and remove hardcoded developer paths across `factory/` to guarantee 100% portability.

---

## 🚀 Execution & Verification Command Reference

```bash
# 1. Package & Environment Verification
uv sync --extra dev

# 2. Code Quality & Test Suite Verification
uv run ruff check factory/ tests/
PYTHONPATH=. uv run pytest tests/

# 3. Memory & Database Check
bd memories
bd stats

# 4. OpenCode Configuration & Agents Check
cat opencode.json
ls -la .agents/skills/ .agents/workflows/
```
