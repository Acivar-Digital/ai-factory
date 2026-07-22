---
Resume: false
bd: factory-src2-build
write_mode: staged
language: python
start_phase: planner
stop_phase: supervisor_review
scope:
  - src2/engine/module11_probability.py
---

# EPIC
Add valence-gated clash (`clash_beneficial` / `clash_harmful`) to the scoring pipeline.

## CONTEXT
`module11_probability.py` uses a flat `dayun_clash` key instead of valence-gated pairs.
`get_clash_valence` logic is not yet available — implement it locally or as a minimal helper.

## DELIVERABLES
1. In `module11_probability.py`, add `clash_beneficial` and `clash_harmful` keys to `LOG_ODDS_WEIGHTS`
2. Implement `get_clash_valence(dm, branch1, branch2)` locally (or import from `src2/engine/module3_interaction.py` ONLY if that file exists in workspace)
3. Add `get_valence_gated_clash` that uses the valence result and returns the matching log-odds key/weight

## REQUIREMENTS & CONSTRAINTS
- Read existing `LOG_ODDS_WEIGHTS` and scoring pattern first — match style
- Fail loudly: no `except: pass`
- If `module3_interaction.py` is missing from workspace, implement valence logic directly (do not import phantom module)

## ANTI-PATTERNS
- Do not modify any file not listed in scope

## ACCEPTANCE
1. `from src2.engine.module11_probability import get_valence_gated_clash` succeeds
2. Function returns correct keys matching `tai_sui_beneficial`/`harmful` pattern
3. `uv run ruff check src2/engine/module11_probability.py` passes
4. No broken imports (`ModuleNotFoundError`) at runtime
