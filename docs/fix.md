# Engine Calculation Fix — P1 Bug Sweep

> **Parent ticket:** `baziforecaster-m99d`
> **Date:** 2026-07-21
> **Scope:** 5 P1 engine bugs, one orchestrator run

---

## Current State

**Critical discovery:** ~70% of these fixes were already deployed in `src2/engine/` but the `bd` tickets were never closed. What remains is wiring valence-aware functions into the scoring pipeline and fixing holdouts in `module11_probability.py`.

| Bug | Core math | Wired in pipeline |
|---|---|---|
| `m99d` — Canonical interaction priority | ✅ `INTERACTION_PRIORITY` (m3:122) | ✅  Used at m3:1367, mediation at m3:662/871 |
| `hca1` — 合能解冲 | ✅ `get_clash_mediation_factor` (m3:360) | ✅ Correct 三会/三合/六合/半合 logic |
| `9ab5` — 贪合忘克/忘生 | ✅ `get_suspended_stems` (m3:1223) | ✅ Called from m2:363, m4:81-150 |
| `rgmv` — Clash valence-blind | ✅ `get_clash_valence` (m3:1240) | ⚠️ Function exists but `compute_clash_valence_map` has ZERO callers |
| `c047` — 用神 direction | ✅ `_resolve_mechanism` (shen_classifier:59), 有根 gate (sc:108) | ⚠️ Chooser returns mechanism but scoring pipeline may not consume |

---

## Batch Plan (4 batches, file-disjoint)

### B1 — Interaction Priority Verification & Hardening
**Tickets:** `m99d` + `hca1`
**Files:** `src2/engine/module3_interaction.py`, `src2/engine/contradiction_resolver.py`
**Acceptance:**
1. `INTERACTION_PRIORITY` dict matches canon (§1.5)
2. `get_clash_mediation_factor` returns correct mediation for all combo types
3. `_combo_overridden_by_clash` in `contradiction_resolver.py` is consistent
4. No blanket `冲 > 合` residual logic (verify `src2/engine/module1_macro.py`)
5. `uv run ruff check src2/engine/module3_interaction.py` → clean

### B2 — Clash Valence Wiring (rgmv)
**Tickets:** `rgmv`
**Files:** `src2/engine/module11_probability.py`, `src2/engine/module3_interaction.py`, `src2/engine/module9_triggers.py`, `src2/engine/module1_macro.py`
**Acceptance:**
1. Add valence-aware clash log-odds to `LOG_ODDS_WEIGHTS`:
   - `clash_beneficial` (忌神被冲 = relief: career_collapse↓, health_disruption↓)
   - `clash_harmful` (用神被冲 = drain: career_collapse↑, health_disruption↑)
2. `_map_triggers` in module11 consumes valence tokens from clash triggers
3. Replace blanket-`dayun_clash` with valence-gated keys
4. `get_clash_valence`/`compute_clash_valence_map` called from scoring pipeline, not orphaned
5. Module9 triggers surface clash polarity tokens (like it does for void/Tai Sui)

### B3 — 用神 Direction Framework Verification (c047)
**Tickets:** `c047`
**Files:** `src2/engine/shen_classifier.py`, `src2/engine/module8_scoring.py`, `src2/engine/module4_medicine.py`, `src2/engine/activity_oracle.py`, `src2/engine/session.py`, `src2/engine/module2_root.py`
**Acceptance:**
1. 化/制/扛/通关 chooser (`_resolve_mechanism`) called from the canonical yong-shen derivation path
2. 有根 gate (`_is_element_rooted`) correctly filters medicine candidates
3. `module8_scoring.py` uses element-level polarity (yong/xi/xian/chou/ji), not strength-as-value
4. `module4_medicine.py` uses yong/ji polarity, not flat +/- scoring
5. `activity_oracle.py` and `session.py` use typed polarity, not raw dict/dynamic access
6. All residual `strength-as-value` patterns eliminated

### B4 — Validation Gate
**No tickets (verification step)**
**Files:** All touched files
**Acceptance:**
1. `uv run ruff check src2/engine/` → clean
2. All bd tickets verified → closed
3. No regressions in existing tests (`python -m pytest TEST/ -x`)

---

## Dependency Order

```
B1 (interaction priority) ──┐
                            ├── B4 (validation)
B2 (clash valence) ────────┘
B3 (用神 direction) ─────────┘
```

B1 has no code deps; B2 and B3 are independent of each other and of B1. B4 is the final gate.

---

## Key Files Scope

| File | B1 | B2 | B3 |
|---|---|---|---|
| `src2/engine/module3_interaction.py` | ✓ | ✓ | |
| `src2/engine/contradiction_resolver.py` | ✓ | | |
| `src2/engine/module1_macro.py` | ✓ | ✓ | |
| `src2/engine/module11_probability.py` | | ✓ | |
| `src2/engine/module9_triggers.py` | | ✓ | |
| `src2/engine/shen_classifier.py` | | | ✓ |
| `src2/engine/module8_scoring.py` | | | ✓ |
| `src2/engine/module4_medicine.py` | | | ✓ |
| `src2/engine/module2_root.py` | | | ✓ |
| `src2/engine/activity_oracle.py` | | | ✓ |
| `src2/engine/session.py` | | | ✓ |

---

## Verification Protocol

1. Each batch commits staged edits to `admin/orchestrator/temp/`
2. Harness diffs against captured baseline to produce patches
3. Final B4 runs `ruff check` + unit test gate
4. Harness `ops` phase commits + closes tickets
