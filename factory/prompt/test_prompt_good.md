---
Resume: false
bd: test-prompt-good
write_mode: staged
language: python
start_phase: planner
stop_phase: supervisor_review
scope:
  - src2/engine/module11_probability.py
---

# EPIC (TEST)
Verify valence-gated clash scoring works with real workspace files only.

## CONTEXT
`src2/engine/module11_probability.py` exists. `src2/engine/module3_interaction.py` does NOT exist in workspace.
Implement valence-gated clash (`clash_beneficial` / `clash_harmful`) directly inside `module11_probability.py` without phantom imports.

## PRE-CHECK (planner must verify before coding)
Run: `ls src2/engine/module3_interaction.py` — if MISSING, implement `get_clash_valence` locally (do NOT import missing module).

## DELIVERABLES
1. In `module11_probability.py`: add `clash_beneficial` and `clash_harmful` to `LOG_ODDS_WEIGHTS`
2. Implement `get_clash_valence(dm: str, branch1: str, branch2: str) -> bool | str` locally in same file
3. Add `get_valence_gated_clash` that calls local `get_clash_valence` and returns `(str, dict[str, float])`

## REQUIREMENTS & CONSTRAINTS
- Read `LOG_ODDS_WEIGHTS` and `tai_sui_beneficial`/`harmful` pattern first
- No `except: pass`
- Fail loudly: broken imports must crash visibly

## ACCEPTANCE (must pass at supervisor_review phase)
1. `python -c "from src2.engine.module11_probability import get_valence_gated_clash; print(get_valence_gated_clash('甲','子','午'))"` succeeds
2. Function returns key `clash_beneficial` or `clash_harmful` + weights dict
3. `uv run ruff check src2/engine/module11_probability.py` passes
4. `python -c "import src2.engine.module11_probability"` passes (no phantom import error)
