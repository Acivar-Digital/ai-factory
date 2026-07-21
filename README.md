# AI-Factory Framework 🚀

[![Tests](https://github.com/Acivar-Digital/ai-factory/actions/workflows/test.yml/badge.svg)](https://github.com/Acivar-Digital/ai-factory/actions/workflows/test.yml)

Autonomous, multi-agent AI coding factory and deterministic orchestrator framework built with Pydantic-AI.

## Overview
AI-Factory extracts complex software engineering tasks into parallelizable DAG workplans, orchestrates specialized agent roles (Planner, Supervisor, Coder, Red-Team Reviewer), and enforces strict coding quality gates, AST-level refactoring, and fail-loudly resilience.

## Features
- **Deterministic Orchestrator (`runner.py`)**: Zero LLM orchestrator drift — deterministic DAG conductor enforcing strict contract boundaries.
- **Pydantic-AI & Structured Output**: Built on Pydantic v2.0+ with strongly typed models for all message exchanges and state snapshots.
- **LoopGuard & Sanitization**: Offline JSON repair (`fast-json-repair`) and recovery against model formatting hallucinations.
- **Fail Loudly & Cheaply**: Atomic state transitions (`state.json`), fail-fast assertion gates, and isolated per-agent workspace staging.
- **Standalone Shadow Tools**: Built-in CLI wrappers for semantic search, file investigation, AST function replacement, and import cleaning.

## Directory Structure
```
factory/
├── factory/
│   ├── common/       # Subprocess wrappers, Markdown bridge, registry
│   ├── infra/        # Core orchestrator engine (runner, control, state, loopguard, ledger)
│   ├── prompt/       # Task specifications (user_prompt.md)
│   ├── templates/    # Agent YAML role prompt specs (planner, coder, reviewer, red_team)
│   └── tools/        # Standalone shadow CLI tools (search, investigate, AST tools)
├── docs/             # Architecture guides and migration records
├── facts/            # Epistemic memory snapshot & persistence
├── tests/            # Unit and contract test suite
├── ./start.sh        # Initial run entrypoint script
└── ./continue.sh     # Continuation run entrypoint script
```

## Quick Start
1. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env to set your target CWD and Model Gateway URLs
   ```

2. **Run Factory**:
   ```bash
   ./start.sh
   ```

3. **Continue Interrupted Run**:
   ```bash
   ./continue.sh coder
   ```

## Development & Testing
- **Linter**: `uv run ruff check factory/ tests/`
- **Unit Tests**: `PYTHONPATH=. uv run pytest tests/`

## License
MIT License ("Freely received, freely given").
