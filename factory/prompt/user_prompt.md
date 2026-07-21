---
Resume: false
bd: factory-src2-build
write_mode: staged
language: python
start_phase: planner
stop_phase: supervisor_review
scope:
  - src2/engine/module3_interaction.py
  - src2/engine/module11_probability.py
---

# EPIC
Wire `get_clash_valence` into the scoring pipeline in `module11_probability.py`.

## CONTEXT
`get_clash_valence` exists in `module3_interaction.py` but is never called.
The scoring pipeline in `module11_probability.py` uses a flat `dayun_clash` key
instead of valence-gated `clash_beneficial`/`clash_harmful` keys.

## DELIVERABLES
1. In `module11_probability.py`, add `clash_beneficial` and `clash_harmful` keys to the `LOG_ODDS_WEIGHTS` dict
2. In `module11_probability.py`, add a function `get_valence_gated_clash` that:
   - Takes the same args as the existing trigger-scoring functions
   - Calls `get_clash_valence` from module3_interaction.py
   - Returns the appropriate log-odds key and weight

## REQUIREMENTS & CONSTRAINTS
- Read the existing `LOG_ODDS_WEIGHTS` dict and scoring pattern first — match its style
- Use proper imports from `module3_interaction`
- Fail loudly: no `except: pass`

## ANTI-PATTERNS
- Do not modify `module3_interaction.py` — only add code to `module11_probability.py`

## ACCEPTANCE
1. `from src2.engine.module11_probability import get_valence_gated_clash` succeeds
2. Function returns correct keys matching `tai_sui_beneficial`/`harmful` pattern
3. `uv run ruff check src2/engine/module11_probability.py` passes
