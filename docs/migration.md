# Migration Plan: Extracting `admin/orchestrator` into Standalone Community Repo `factory` (`ai-factory`)

## Executive Summary
This document outlines the complete migration strategy for extracting the Orchestrator harness from `/home/yapilwsl/arthityap/baziforecaster/admin/orchestrator` into an autonomous, open-source, community-ready standalone repository at `/home/yapilwsl/arthityap/ai-factory`, linked to remote origin `https://github.com/Acivar-Digital/ai-factory.git` under the MIT License ("Freely received, freely given").

---

## 🚨 GUARANTEED OUTCOME CONTRACT

1. **`baziforecaster` (Target Cleanliness)**:
   - **ZERO TRACES**: No LLM working inside `baziforecaster` will have any visibility or awareness that `orchestrator` or `factory` ever existed.
   - All `admin/orchestrator/` code, documentation, prompt specs, and skills are purged.
   - All orchestrator/harness memories are scrubbed from `baziforecaster`'s `bd` memories store AND `remember_fact` persistence.
   - All references to `orchestrator` in `AGENTS.md`, `README.md`, and config files are cleaned up.

2. **`factory` (Full Context Awareness)**:
   - **100% HISTORICAL CONTINUITY**: Any LLM working inside `factory` is fully aware of all historical architecture decisions, fixes, and design evolution.
   - `CHANGELOG.md` in `factory` retains the complete history of orchestrator development.
   - Both **`bd` memories** (18+ harness keys) AND **`remember_fact` notes** (`artefacts/history/`, `facts/`) are exported and seeded into `factory`.
   - All architectural documentation (`docs/`, `facts/`, `SKILL.md`) is preserved and re-anchored under `factory`.

---

## 1. Core Architecture & Principles

1. **100% Standalone Open-Source Framework (`ai-factory`)**:
   - Local directory: `/home/yapilwsl/arthityap/ai-factory`
   - Remote repository: `https://github.com/Acivar-Digital/ai-factory.git`
   - License: MIT License ("Freely received, freely given")
   - `baziforecaster` holds NO symlink or any references to Orchestrator. `admin/orchestrator` is completely removed from `baziforecaster`.
   - `factory` operates on ANY target repository specified by `CWD` in `factory/infra/.env` or passing a `--target /path/to/repo` CLI flag.
2. **Security & Open-Source Readiness**:
   - Zero hardcoded API keys, tokens, or internal IP credentials committed in source code.
   - All model gateway URLs (`mcpmart`, `antigravity`, `literouter`, `pydantic`) configured via `.env` defaults.
   - Clean `.env.example`, `LICENSE` (MIT), and comprehensive community `README.md`.
3. **Control Module Restoration (`control_orchestrator.py` -> `control.py`)**:
   - Restore original clean module name: rename `infra/control_orchestrator.py` back to `factory/infra/control.py`.
   - Update all import references across the engine, tools, common utilities, and test suites from `control_orchestrator` to `control`.
4. **Simplified Execution Scripts**:
   - Entrypoints simplified to `./start.sh` (initial run) and `./continue.sh` (resuming state/coder execution).
5. **Standalone Factory Shadow Tools**:
   - Bundle all shadow tooling (`admin/tools/*.py` -> `factory/tools/`) inside `factory`.
   - `common/subprocess.py` runs tools via `uv run --no-sync python factory/tools/<tool>.py` with `cwd=TARGET_ROOT`.
   - Connect directly to environment services (embedding service, Qdrant vector database, model gateways).

---

## 2. Directory & File Mapping

| Source (`baziforecaster`) | Destination (`factory`) | Purpose |
| :--- | :--- | :--- |
| `admin/orchestrator/infra/control_orchestrator.py` | `factory/infra/control.py` | **Renamed**: Single source of truth for runtime paths, gateways, CONTROL_SHEET |
| `admin/orchestrator/infra/` | `factory/infra/` | Core orchestrator engine (runner, state, gates, ledger, loopguard) |
| `admin/orchestrator/common/` | `factory/common/` | Shared utilities (subprocess, md_bridge, registry, operator) |
| `admin/orchestrator/templates/` | `factory/templates/` | Agent YAML role prompt specs |
| `admin/orchestrator/prompt/` | `factory/prompt/` | Committed task specifications (`user_prompt.md`) |
| `admin/orchestrator/docs/` | `docs/` | Architectural documentation and migration records |
| `admin/orchestrator/facts/` | `facts/` | Epistemic facts & memory persistence (`remember_fact` store) |
| `admin/orchestrator/artefacts/` | `artefacts/` | Role history, transcript logs, and `remember_note` store |
| `admin/orchestrator/test/` | `tests/` | Unit and contract test suite |
| `admin/tools/*.py` | `factory/tools/` | Standalone shadow CLI tools (search, investigate, replace, AST) |
| `admin/orchestrator/CHANGELOG.md` | `CHANGELOG.md` | **Full History**: Preserved orchestrator development history |
| `admin/orchestrator/run_orchestrator.sh` | `./start.sh` | Main CLI entrypoint script |
| `admin/orchestrator/run_orchestrator_continue.sh` | `./continue.sh` | Continuation CLI entrypoint script |

---

## 3. Detailed Step-by-Step Execution Plan

### Phase 1: Repository Setup (`/home/yapilwsl/arthityap/ai-factory`) [COMPLETED]
1. Created directory: `/home/yapilwsl/arthityap/ai-factory`.
2. Initialized Git repo in `factory`: `git init`.
3. Set remote origin: `git remote add origin https://github.com/Acivar-Digital/ai-factory.git`.
4. Scaffolded `pyproject.toml` with `uv` dependencies (`pydantic>=2.0`, `pydantic-ai`, `pydantic-settings`, `httpx`, `pytest`, `ruff`, `pyyaml`).
5. Created `.gitignore` ignoring `.env`, `orch/logs/`, `temp/`, `__pycache__`, `.pytest_cache`, `.checkpoints/`.
6. Created clean `.env.example`.
7. Added `LICENSE` (MIT License).

### Phase 2: Code Extraction, Secret Audit, Module Rename & Tools Wiring [COMPLETED]
1. Extracted `admin/orchestrator/*` and `admin/tools/*.py` to `factory/`.
2. Reorganized internal package layout: `factory/infra/`, `factory/common/`, `factory/tools/`.
3. Renamed `control_orchestrator.py` -> `factory/infra/control.py`.
4. Refactored imports across all python files from `admin.orchestrator` / `control_orchestrator` to `factory.infra.control`.
5. Created entrypoint scripts `./start.sh` and `./continue.sh`.
6. Sanitized secret defaults and configured gateway URLs.

### Phase 3: Complete Memory & History Migration (`factory`) [COMPLETED]
1. Migrated `CHANGELOG.md` to `factory/CHANGELOG.md`.
2. Initialized `bd` in `factory` (`bd init factory`).
3. Seeded all 18+ harness `bd memories` into `factory` (`harness-fail-loudly-resume`, `harness-tier-a-permanent`, `orchestrator-workplan-is-DAG`, etc.).
4. Exported persistent facts snapshot to `factory/facts/memories.json`.

### Phase 4: `baziforecaster` Complete Scrubbing & Sanitization [COMPLETED]
1. Deleted `admin/orchestrator/` completely from `baziforecaster` (`git rm -rf`).
2. Purged all orchestrator/harness memory keys from `baziforecaster` via `bd forget`.
3. Removed `orchestrator` and `wip-harness` skills from `.agents/skills/` and `AGENTS.md`.
4. Committed cleanup to `baziforecaster` git repository (`rollout-pydantic`).

### Phase 5: Next Steps for `factory` In-Repo Agent (User-Directed Testing Protocol)
1. **In-Repo Test Execution**:
   - Run linter check: `uv run ruff check factory/ tests/`.
   - Run test suite: `PYTHONPATH=. uv run pytest tests/`.
   - Run end-to-end dry-run harness execution: `./start.sh`.
2. **Push to Remote**:
   - Stage, commit, and push to origin main:
     `git add . && git commit -m "feat: initial release of ai-factory standalone framework" && git push -u origin main`.
