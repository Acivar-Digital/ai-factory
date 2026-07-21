---
Resume: false
bd: baziforecaster-m99d
scope:
  - src2/engine/module3_interaction.py
  - src2/engine/contradiction_resolver.py
  - src2/engine/module1_macro.py
  - src2/engine/module11_probability.py
  - src2/engine/module9_triggers.py
  - src2/engine/shen_classifier.py
  - src2/engine/module8_scoring.py
  - src2/engine/module4_medicine.py
  - src2/engine/module2_root.py
  - src2/engine/activity_oracle.py
  - src2/engine/session.py
---

# EPIC
Complete all 5 P1 engine calculation bugs: canonical interaction priority, 合能解冲, 贪合忘克/忘生, clash valence-awareness, and 用神 direction framework (化/制/扛/通关 + 有根 + strength-as-value elimination).

## CONTEXT
The P1 bugs (`baziforecaster-m99d`, `-hca1`, `-9ab5`, `-rgmv`, `-c047`) were filed during the V31 audit (2026-07-11/12). Core math functions for all 5 bugs were implemented in `src2/engine/` in subsequent commits, but the tickets were never closed. This run:

1. **Verifies** that all core math is correct and canonical
2. **Wires** functions that exist but are orphaned (not called from the scoring pipeline)
3. **Fixes** remaining blanket-negative holdouts in `module11_probability.py`
4. **Validates** that 用神-direction framework is complete and connected

### Pre-audit findings (2026-07-21):
- `INTERACTION_PRIORITY` in `module3_interaction.py:122` is canon-correct ✓
- `get_clash_mediation_factor` (m3:360) correctly handles 三会→0.0, 三合→conditional, 六合/半合→1.0 ✓
- `get_suspended_stems` (m3:1223) implements 贪合忘克; called from `module2_root.py:363` ✓
- `get_clash_valence` (m3:1240) returns +/-1 per 用/忌 polarity but **never called** from scoring pipeline ✗
- `_resolve_mechanism` (shen_classifier.py:59) implements 化/制/扛/通关 chooser; 有根 gate at sc:108 ✓
- `dayun_clash` in `module11_probability.py:129` uses blanket-negative log-odds (no valence check) ✗
- `module10_classification.py` already handles `positive_friction` / `negative_friction` for clash ✓

## DELIVERABLES

### Batch 1: Interaction Priority Verification + Hardening
1. Verify `INTERACTION_PRIORITY` dict matches 三会(8) > 三合(7) > 冲(6) > 六合(5) > 半合(4) > 刑(3) > 害(2) > 破(1)
2. Verify `get_clash_mediation_factor` (m3:360-392) returns correct mediation:
   - 三会 → 0.0 (always resolves clash)
   - 三合 → 0.0 if non-peak branch, 1.0 if 旺支 (peak) is clashed (旺支逢冲以冲论)
   - 六合/半合 → 1.0 (never resolve clash)
3. Verify `_combo_overridden_by_clash` in `contradiction_resolver.py` is consistent
4. Check `module1_macro.py` for any residual `冲 > 合` hardcoding (the old bug)

### Batch 2: Clash Valence Wiring (rgmv)
1. Add valence-aware clash log-odds keys to `LOG_ODDS_WEIGHTS` in `module11_probability.py:87-133`:
   - `clash_beneficial` — 忌神被冲 = relief (career_collapse↓, health_disruption↓)
   - `clash_harmful` — 用神被冲 = drain (career_collapse↑, health_disruption↑)
2. Replace blanket `dayun_clash` key usage with valence-gated dispatch in `_map_triggers` (m11:203-259)
3. Wire `compute_clash_valence_map` (m3:1255) into the trigger/scoring pipeline
4. Ensure module9 `triggers.py` surfaces clash polarity tokens (mirror pattern: tai_sui_beneficial/harmful)
5. Verify `module1_macro.py` `冲太岁` uses valence scoring, not flat -30 penalty

### Batch 3: 用神 Direction Framework Verification (c047)
1. Verify `_resolve_mechanism` (shen_classifier.py:59-71) is called from the canonical classification path
2. Verify 有根 gate (sc:108-113) `_is_element_rooted` correctly filters medicine candidates
3. Audit `module8_scoring.py` for strength-as-value patterns — replace with element-level polarity (yong/xi/xian/chou/ji)
4. Audit `module4_medicine.py` — verify it uses yong/ji polarity, not flat +/- scores
5. Audit `activity_oracle.py` and `session.py` — verify typed polarity access, no raw dict/dynamic
6. Verify `module2_root.py` correctly propagates occupied/suspended stems for 贪合忘克

### Batch 4: Validation Gate
1. `uv run ruff check src2/engine/` → clean
2. Verify all 5 bd tickets are verifiably fixed → update and close

## STATE
must_be_pydantic: true
must_be_canonical: true

## REQUIREMENTS & CONSTRAINTS
- **ALL work saved in `admin/orchestrator/temp/`.** That is the ONLY writable folder.
- **DO NOT edit anything outside `admin/orchestrator/temp/`.** Every other path is READ-ONLY.
- **Edit ONLY staging copies under `admin/orchestrator/temp/src2/...`.**
- **Reuse existing patterns.** Mirror `tai_sui_beneficial`/`harmful` for clash valence. Do not invent new conventions.
- **Fail loudly.** No `except: pass`. Raise on unexpected shapes.
- **Never commit or push** — harness/operator handles that.

## ANTI-PATTERNS (CRITICAL)
- **Do NOT rewrite core math** — the interaction priority, 贪合忘克, clash mediation, and 用神-direction functions are already correctly implemented. The gap is wiring them into the scoring pipeline, not re-implementing them.
- **Do NOT change the `INTERACTION_PRIORITY` dict** (m3:122-131) or `get_clash_mediation_factor` (m3:360-392) — they are canon-correct.
- **Do NOT touch `src2/core/schemas/unified.py` model definitions** unless a field change is required for valence propagation.
- **Do NOT add blanket +/- clash scoring** — all clash scoring must be valence-gated.
- **Do NOT leave orphaned functions** — if a function (e.g. `compute_clash_valence_map`) is defined but unused, wire it OR verify it's a public utility.

## ACCEPTANCE
1. All clash scoring in module11 uses valence-gated log-odds (clash_beneficial / clash_harmful)
2. `compute_clash_valence_map` is called from the scoring pipeline, not orphaned
3. 用神-direction framework: 化/制/扛/通关 chooser + 有根 gate produce correct medicine/taboo
4. No blanket-negative clash penalties remain in any engine module
5. `uv run ruff check src2/engine/` → clean
6. All 5 P1 tickets verified → status updated
