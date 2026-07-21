# Project Instructions for AI-Factory Framework

This file provides instructions and context for AI coding agents working on the AI-Factory project.

## 🚨 MANDATORY WORKFLOW ENFORCEMENT 🚨

**CRITICAL: Before writing any code or answering any request, you MUST initialize the beads workflow.**

### Session Start Protocol
1. **Run**: `bd prime` (or `bd ready` if prime is unavailable) immediately upon session start.
2. **Verify**: Ensure you have the latest issue context.
3. **Ticket**: If the user's request is not already an issue, create it: `bd create "..." -t task -p 2`.
4. **Claim**: `bd update <id> --claim`.

> **DO NOT PROCEED** without tracking the task in beads. Markdown TODOs and mental notes are PROHIBITED.

### Self-Review (Critic Role)
Before marking a task as complete, you MUST act as a Critic:
1. Run linters: `uv run ruff check factory/ tests/`
2. Run tests: `PYTHONPATH=. uv run pytest tests/`
3. Verify the implementation matches the original request exactly.

<!-- BEGIN BEADS INTEGRATION -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files
<!-- END BEADS INTEGRATION -->

## Build & Test

```bash
# Linting
uv run ruff check factory/ tests/

# Testing
PYTHONPATH=. uv run pytest tests/
```

## Architecture Overview

Autonomous, multi-agent AI coding factory and deterministic orchestrator framework built on Pydantic-AI.

- `factory/infra/`: Core orchestrator engine (runner, control, state, loopguard, ledger)
- `factory/common/`: Shared utilities (subprocess, md_bridge, registry)
- `factory/templates/`: Role YAML specifications (planner, supervisor, coder, reviewer)
- `factory/tools/`: Standalone shadow CLI tooling
- `tests/`: Unit and contract test suite
