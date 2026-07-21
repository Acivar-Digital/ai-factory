---
Resume: false
bd: factory-harness-smoke
write_mode: staged
language: python
start_phase: planner
stop_phase: supervisor_plan
scope:
  - admin/orchestrator/temp/
---

# EPIC
Smoke test: verify the factory pipeline can produce a runnable script.

## DELIVERABLES
- A Python script at `admin/orchestrator/temp/harness_test.py` that prints exactly `This Harness is Working`

## REQUIREMENTS & CONSTRAINTS
- Write via `write_file` tool only — do NOT execute or shell-out.
- No imports needed. No comments.

## ACCEPTANCE
1. `python admin/orchestrator/temp/harness_test.py` prints `This Harness is Working`
