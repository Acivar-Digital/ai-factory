# 🔍 Pydantic Model Dict-Access Scanner (Verified)

Scanned `116` files in `src2/`.

## 📂 `src2/core/tools/user_profile_input.py`

- **L32** `da_yun_data` (DaYunData): `da_yun_data.pillar`
  - Reason: da_yun_data is a Pydantic model, so accessing its fields should use attribute access (.pillar and .start_year) instead of dictionary subscripting, which will raise a TypeError at runtime.
---

## 📂 `src2/engine/contradiction_resolver.py`

- **L713** `res` (unknown): `res.strength`
  - Reason: The variable `res` holds a Pydantic model representing the combination/interaction strength, but is accessed using dictionary semantics (`.get()`). It should be accessed via attribute access (`.strength`).
---

## 📂 `src2/engine/module8_scoring.py`

- **L125** `month_data` (Pillar): `month_data.branch`
  - Reason: During the Pydantic migration, month_data was converted to a Pydantic model (likely representing a Pillar), but this legacy dictionary-style .get() access was not updated to attribute access.
- **L265** `module_6` (Module6Output): `module_6.ten_god_emphasis`
  - Reason: module_6 is a Pydantic model representing the output of Module 6. Accessing it using dictionary lookup (.get() or []) will raise an AttributeError or TypeError. It should use attribute access instead.
- **L277** `module_6` (Module6Output): `module_6.ten_god_absence`
  - Reason: module_6 is a Pydantic model representing the output of Module 6. Accessing it using dictionary subscripting or .get() will raise an AttributeError/TypeError at runtime.
- **L389** `gate_result` (GateResult): `gate_result.g_dy`
  - Reason: gate_result is a Pydantic model representing the scoring gate output, so accessing its fields using subscript notation will raise a TypeError at runtime. It should use attribute access instead.
---

## 📂 `src2/engine/orchestrator.py`

- **L389** `ge_ju_results` (GeJuResult): `ge_ju_results.pattern_name`
  - Reason: ge_ju_results is a Pydantic model returned by classify_ge_ju, so accessing its fields via subscript notation (['pattern_name']) will raise a TypeError at runtime. It should be accessed via attribute notation (.pattern_name).
- **L418** `strength_profile` (StrengthProfile): `strength_profile.spectrum_tier`
  - Reason: strength_profile is a Pydantic model representing the Day Master's strength profile, so its fields must be accessed via attribute access rather than dictionary subscripting.
- **L465** `macro_results` (MacroResults): `macro_results.macro_environmental_scan.void_audit.is_void_active`
  - Reason: The variable macro_results is a Pydantic model, but it is accessed using dictionary subscripting which will raise a TypeError at runtime. It should be accessed using attribute notation.
- **L593** `scoring_results_pre` (ScoringResults): `scoring_results_pre.composite_score`
  - Reason: scoring_results_pre is a Pydantic model instance, and accessing its fields using dictionary subscripting will raise a TypeError at runtime. It should use attribute access instead.
- **L609** `medicine_results` (MedicineResults): `medicine_results.module_4_results`
  - Reason: medicine_results is a Pydantic model, so accessing it with dictionary subscripting will raise a TypeError at runtime. It should use attribute access instead.
---

## 📂 `src2/engine/prompt_engine.py`

- **L66** `solar_months` (SolarMonth): `solar_months[i].month_name`
  - Reason: solar_months is a list of Pydantic models, so accessing its elements with dictionary subscripting will raise a TypeError. It should be accessed using attribute notation.
---

## 📂 `src2/engine/pydantic_prompt_engine.py`

- **L646** `scored` (unknown): `scored.activities`
  - Reason: scored is a Pydantic model returned by score_day, so accessing its fields requires attribute access (.activities) instead of dictionary access (.get()).
- **L647** `acts` (Activities): `acts.job_interview`
  - Reason: The variable `acts` is a Pydantic model representing activities returned from a Pydantic-based prompt engine, so using `.get()` on it will raise an AttributeError at runtime.
- **L649** `acts` (Acts): `acts.job_interview.score if acts.job_interview else 0`
  - Reason: acts is a Pydantic model returned by the prompt engine, but it is accessed using dictionary .get() syntax which will raise an AttributeError at runtime.
- **L650** `acts` (BaseModel): `acts.love.score if acts.love else 0`
  - Reason: acts is a Pydantic model instance representing daily activities, but it is accessed using dictionary .get() syntax which will raise an AttributeError. It should be accessed using attribute notation.
- **L674** `m` (unknown): `m.month_name`
  - Reason: The variable `m` is a Pydantic model instance, but it is accessed using dictionary subscripting (`m['month_name']`), which is not supported by Pydantic models and will raise a TypeError. It should be accessed via attribute access (`m.month_name`).
- **L675** `m` (unknown): `m.stem`
  - Reason: The variable `m` is an instance of a Pydantic model representing a month. Accessing its fields using dictionary subscripting (e.g., `m['stem']`) will raise a TypeError, and should be replaced with attribute access.
- **L676** `m` (Month): `m.branch`
  - Reason: The variable 'm' is a Pydantic model representing month information, but it is accessed using dictionary subscripting (e.g., m['branch']). It should use attribute access instead.
---

## 📂 `src2/interfaces/telegram/chronomancer/agents.py`

- **L528** `scored` (unknown): `scored.activities`
  - Reason: The variable `scored` is a Pydantic BaseModel, which does not support dictionary-like `.get()` access. It should be accessed directly as an attribute: `scored.activities`.
---

## 📂 `src2/interfaces/telegram/chronomancer/coordinator.py`

- **L387** `s` (Stakeholder): `s.name`
  - Reason: The variable 's' is an instance of a Pydantic model (likely 'Stakeholder') representing a stakeholder, which does not support dict-like '.get()' access. It should use attribute access '.name' instead.
- **L396** `target_s` (TargetSchema): `target_s.name`
  - Reason: The variable target_s is a Pydantic model (likely TargetSchema), so accessing its fields using dictionary .get() syntax will cause an AttributeError. It should be accessed using attribute notation.
- **L404** `target_s` (Strength): `target_s.day_master_strength`
  - Reason: target_s is a Pydantic model representing the strength analysis, so dictionary-like .get() access will raise an AttributeError. It should use attribute access instead.
---

## 📂 `src2/interfaces/telegram/intake/calendar_node.py`

- **L117** `ge_ju_res` (GeJuResult): `ge_ju_res.pattern_name or "Other"`
  - Reason: The function classify_ge_ju returns a Pydantic model, which does not support dict-like .get() access. The attribute pattern_name should be accessed directly.
---


**Total CONFIRMED findings: 24**

_False positives filtered: 71_

_Uncertain after smart pass: 33_
