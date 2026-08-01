# 🕵️ Engine Schema Compliance Report

Scanned `43` engine files.

## 📂 `src2/engine/activity_oracle.py`

### ✅ Line 59: `get_verdict` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that maps a float to a string. It does not handle complex data structures, so Pydantic models are not required.

### ✅ Line 90: `_day_element` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes a primitive string input and returns a primitive string output. It does not handle complex data structures.

### ✅ Line 94: `_is_favorable` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses the Pydantic model 'ChartProfile' for its complex input and returns a simple boolean primitive. This is compliant with the schema validation requirements.

### ✅ Line 98: `_is_unfavorable` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (ChartProfile) for its complex input and returns a simple boolean primitive. This is compliant with the schema validation requirements.

### ✅ Line 102: `_branch_clash` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes primitive strings and returns a boolean, which does not require a Pydantic schema.

### ✅ Line 106: `_branch_combines` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes primitive strings and returns a boolean. It does not handle complex data structures that require Pydantic validation.

### ✅ Line 110: `_get_natal_stems` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (ChartProfile) as input and returns a simple list of strings, which is an appropriate type for a basic collection of primitives.

### ✅ Line 118: `_stem_combines_with_natal` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a private helper function that operates on simple primitive types (str and list of str) to perform a basic lookup. It does not handle complex data payloads that require Pydantic schema validation.

### ✅ Line 123: `_void_day_penalty` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (ChartProfile) as an input and returns a simple primitive tuple. For a helper function of this nature, this is compliant.

### ✅ Line 131: `_month_officer_bonus` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a private helper method that takes primitive types (str) and a specific domain object (Pillar) and returns a simple tuple of primitives. It does not handle complex data payloads that require Pydantic schema validation.

### ✅ Line 143: `_month_peach_blossom_bonus` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a private helper method that takes a typed Pillar object and returns a simple primitive tuple. It does not handle complex data payloads that require Pydantic schema validation.

### ✅ Line 150: `_branch_element_favor` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses the Pydantic model 'ChartProfile' for its complex input and returns a simple primitive tuple. This is compliant with the schema validation requirements.

### ✅ Line 162: `_score_travel` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (Pillar, ChartProfile) for its inputs and returns a simple tuple of (int, str). Since it is an internal helper function (indicated by the leading underscore) and handles primitive return types, it is compliant.

### ✅ Line 216: `_score_job_interview` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (Pillar, ChartProfile) for its inputs and returns a simple tuple of (int, str). Since it is an internal helper function (indicated by the leading underscore) and the return type is a simple primitive tuple, it is compliant.

### ✅ Line 271: `_score_love` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (Pillar, ChartProfile) for its inputs and returns a simple tuple of (int, str). Since it is an internal helper function (indicated by the leading underscore) and the return type is a simple primitive tuple, it is compliant.

### ✅ Line 325: `_score_speculation` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (Pillar, ChartProfile) for its inputs and returns a simple tuple of primitive types (int, str), which is appropriate for an internal helper function.

### ✅ Line 388: `_score_study` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (Pillar, ChartProfile) for its inputs and returns a simple tuple of (int, str). Since it is an internal helper function (indicated by the leading underscore) and the return type is a simple primitive tuple, it is compliant.

### ✅ Line 454: `score_day` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (Pillar, ChartProfile, ActivityDayResult) for its input and output types, ensuring structured validation of complex data payloads.

### ✅ Line 542: `score_range` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (Pillar, ChartProfile, ActivityDayResult) for all complex inputs and outputs, ensuring type safety and validation.

### ✅ Line 552: `get_activity_forecast` in `src2/engine/activity_oracle.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ChartProfile, ScoringOutput, ActivityForecast) for both input and output types, ensuring strong schema validation for complex data structures.

---

## 📂 `src2/engine/bazi_data.py`

### ✅ Line 1057: `get_ten_god` in `src2/engine/bazi_data.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (str) for both input and output, acting as a basic lookup helper. It does not handle complex data structures that would require Pydantic models.

### ✅ Line 1223: `get_life_stage` in `src2/engine/bazi_data.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (int and str) for its input and output, making it a simple helper function that does not require a Pydantic schema.

---

## 📂 `src2/engine/bazi_math.py`

### ✅ Line 57: `clamp` in `src2/engine/bazi_math.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple mathematical helper that uses primitive float types for its inputs and outputs. It does not handle complex data structures that would require Pydantic models.

### ✅ Line 101: `gate_dy` in `src2/engine/bazi_math.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple mathematical helper that takes a primitive float and returns a float. It does not handle complex data structures, so Pydantic models are not required.

### ✅ Line 112: `gate_ann` in `src2/engine/bazi_math.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple mathematical helper that takes a float and returns a float, which does not require a Pydantic schema model.

### ✅ Line 133: `calculate_gated_score` in `src2/engine/bazi_math.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses primitive types (float) for inputs and returns a Pydantic model (GatedScoreResult), which is the correct pattern for a mathematical calculation function.

### ✅ Line 234: `get_spectrum_tier` in `src2/engine/bazi_math.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (float input, str output) for a basic mapping operation, which does not require a Pydantic schema.

### ✅ Line 245: `get_dsi_baseline_adj` in `src2/engine/bazi_math.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes a primitive string and returns a primitive float. It does not handle complex data structures, so it is compliant.

### ✅ Line 250: `get_dsi_tier_scalar` in `src2/engine/bazi_math.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes a primitive string and returns a primitive float. It does not handle complex data structures, so it is exempt from Pydantic schema requirements.

---

## 📂 `src2/engine/context_template.py`

### ✅ Line 45: `serialise_reference_tables` in `src2/engine/context_template.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple utility that converts internal reference constants into a formatted string for display/logging. It does not handle complex data payloads or API contracts that require Pydantic validation.

### ✅ Line 50: `fmt_set` in `src2/engine/context_template.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple string formatting helper that takes a dictionary and a label, and it does not handle complex API-level data payloads that require Pydantic validation.

### ✅ Line 90: `_fmt_pillar` in `src2/engine/context_template.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple internal helper that takes a Pydantic model (Pillar) and returns a primitive string. It does not use raw dictionaries for complex data structures.

### ✅ Line 96: `serialise_profile` in `src2/engine/context_template.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ChartProfile and SerializedProfileContext) for both input and output, ensuring type safety and validation for complex data structures.

### ✅ Line 309: `serialise_ge_ju_context` in `src2/engine/context_template.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ChartProfile and SerializedGeJuContext) for both input and output, ensuring strict schema validation.

### ✅ Line 459: `build_context` in `src2/engine/context_template.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function takes no arguments and returns a simple string. It is a simple helper function that does not handle complex data structures, thus it is exempt from Pydantic schema requirements.

---

## 📂 `src2/engine/contradiction_resolver.py`

### ✅ Line 41: `_safe_get_pillar_attr` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a low-level internal helper designed to safely retrieve attributes from either a dictionary or an object, acting as a utility for flexibility. It does not define or handle a complex API payload that should be replaced by a Pydantic model.

### ✅ Line 49: `_extract_profile_branches_and_stems` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (ChartProfile) as input and returns a simple tuple of lists, which is an appropriate representation for internal data extraction. It does not handle complex raw dictionaries.

### ✅ Line 65: `get_classical_source_hierarchy` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns a static configuration dictionary. It acts as a constant provider/helper rather than a data processing API entry point requiring a Pydantic schema for validation.

### ✅ Line 84: `apply_specificity_rule` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ContradictionSignal and SpecificityRuleResult) for both input and output, ensuring type safety and schema validation.

### ✅ Line 96: `get_temporal_context_window` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function correctly uses a Pydantic model (TemporalContextWindow) as the return type, ensuring structured validation of the output.

### ✅ Line 111: `classify_true_vs_apparent` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ContradictionSignal and ContradictionClassification) for both input and output, ensuring strict schema validation for complex data structures.

### ✅ Line 167: `calculate_temporal_weight` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple mathematical helper that takes a float and returns a float, which does not require a Pydantic schema model.

### ✅ Line 172: `calculate_combo_clash_net` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses primitive types for inputs and a Pydantic model (ComboClashNetResult) for the output, which is compliant with the schema validation requirements.

### ✅ Line 183: `classify_contradiction` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ContradictionSignal and ContradictionClassification) for both input and output, ensuring strict schema validation for complex data structures.

### ✅ Line 224: `apply_hierarchy_of_evidence` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses the 'ContradictionSignal' Pydantic model (implied by the type hint) for both input and output, ensuring structured data validation.

### ✅ Line 238: `resolve_dm_strength_paradox` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ContradictionSignal, ChartProfile, ContradictionResolution) for all complex input and output types, ensuring strict schema validation.

### ✅ Line 293: `resolve_wealth_vs_control` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ChartProfile, ContradictionSignal, ContradictionResolution) for its complex input and output types, ensuring strict schema validation.

### ✅ Line 353: `resolve_resource_vs_output` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ContradictionSignal and ContradictionResolution) for its complex input and output types, ensuring strict schema validation.

### ✅ Line 394: `resolve_combination_override` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses primitive float inputs and returns a Pydantic model (ContradictionResolution), which is the correct pattern for structured data output.

### ✅ Line 435: `resolve_paradox_four_step` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ContradictionSignal and ContradictionResolution) for both input and output, ensuring type safety and validation for complex data structures.

### ✅ Line 467: `calculate_temporal_weight_enhanced` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple mathematical helper that takes and returns primitive float types. It does not handle complex data structures, so Pydantic models are not required.

### ✅ Line 475: `_extract_signals` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (EngineOutput, ContradictionSignal) for its primary input and output types, ensuring structured validation of the complex data payloads.

### 🛑 Line 571: `_match_pattern` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function accepts a 'contradiction' argument typed as a raw 'dict', which is used to access complex nested data (signal_a, signal_b), indicating a lack of Pydantic model validation for a complex input payload.

### 🛑 Line 611: `_determine_dominant_theme` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses a list of raw dictionaries (`list[dict]`) to handle complex data structures (contradictions) instead of a Pydantic model, which is a schema hazard.

### 🛑 Line 632: `_synthesize` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function accepts 'list[dict]' as an input for 'contradictions', which is a complex data structure containing weights, signals, and classifications, but fails to use a Pydantic model for this input.

### ✅ Line 679: `resolve_contradictions` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function signature correctly uses Pydantic models (ChartProfile, EngineOutput, ContradictionResult) for its inputs and outputs. While internal logic uses dictionaries for temporary calculations (e.g., the 'contradictions' list), the API contract defined by the signature is fully compliant.

### 🛑 Line 712: `_get_combo_strength` in `src2/engine/contradiction_resolver.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses a raw 'dict' as the input type for 'combo', which is a complex data structure representing a combination, instead of a Pydantic model.

---

## 📂 `src2/engine/da_yun.py`

### ✅ Line 13: `_next_pillar` in `src2/engine/da_yun.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple internal helper that operates on primitive types (strings and booleans) and returns a tuple of strings. It does not handle complex data payloads that would require Pydantic models.

### ✅ Line 26: `_get_days_to_solar_term` in `src2/engine/da_yun.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses primitive types (date, bool, int) for its inputs and outputs, which is appropriate for a simple date calculation helper. It does not handle complex data structures that require Pydantic models.

### ✅ Line 34: `_fetch_term_dates` in `src2/engine/da_yun.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a private helper method that takes a primitive (int) and returns a list of standard library date objects. It does not handle complex data payloads that require Pydantic schema validation.

### ✅ Line 62: `calculate_da_yun` in `src2/engine/da_yun.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ChartProfile as input and DaYunOutput as output) for complex data structures, ensuring type safety and validation.

### ✅ Line 137: `get_current_da_yun` in `src2/engine/da_yun.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (DaYunOutput and DaYunCycleItem) for both input and output, ensuring type safety and validation for complex data structures.

---

## 📂 `src2/engine/daily_pillar.py`

### ✅ Line 18: `get_sg_today` in `src2/engine/daily_pillar.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns a primitive 'date' object and takes no arguments. It is a simple helper function and does not handle complex data structures.

### ✅ Line 26: `get_sg_now` in `src2/engine/daily_pillar.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns a primitive datetime object and does not handle complex data structures, making it a simple helper function.

### ✅ Line 75: `_pillar_index` in `src2/engine/daily_pillar.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (str, int) for its inputs and output, which is appropriate for a low-level helper function. It does not handle complex data structures that would require Pydantic models.

### ✅ Line 83: `get_pillar_for_date` in `src2/engine/daily_pillar.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses primitive types (date, str) for inputs and returns a Pydantic model (Pillar), which is compliant with the schema validation requirements.

### ✅ Line 94: `get_pillar_from_string` in `src2/engine/daily_pillar.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple string parsing helper that takes a primitive string and returns a tuple of strings. It does not handle complex data payloads that would require Pydantic models.

### ✅ Line 110: `get_month_anchor_for_date` in `src2/engine/daily_pillar.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (SolarMonthAnchor) for its return type and handles a list of these models, adhering to schema validation standards.

### ✅ Line 117: `_best_anchor` in `src2/engine/daily_pillar.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (SolarMonthAnchor) for both input and output, ensuring type safety and validation for complex structures.

### ✅ Line 138: `resolve_daily_pillar` in `src2/engine/daily_pillar.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a specific type 'Pillar' for its return value and 'date' for its input, which are well-defined types rather than raw dictionaries or lists for complex data.

### ✅ Line 152: `resolve_daily_pillar_range` in `src2/engine/daily_pillar.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a list of Pydantic models (Pillar) as the return type, and takes standard Python date objects as input. It does not use raw dictionaries for complex data structures.

---

## 📂 `src2/engine/element_phase.py`

### ✅ Line 20: `get_element_phase` in `src2/engine/element_phase.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (str) for both input and output, which is appropriate for a basic lookup helper function. It does not handle complex data structures that would require Pydantic models.

### ✅ Line 51: `get_phase_multiplier` in `src2/engine/element_phase.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (str, float) for its inputs and outputs, which is appropriate for a basic lookup helper function. It does not handle complex data structures that would require Pydantic models.

---

## 📂 `src2/engine/module0_geju.py`

### ✅ Line 23: `_count_branches` in `src2/engine/module0_geju.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses the Pydantic model 'ChartProfile' as input and returns a primitive 'int', which is appropriate for a simple counting helper.

### 🛑 Line 32: `_has_meaningful_root` in `src2/engine/module0_geju.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses a raw 'dict | None' for 'transformed_branches', which is a complex data structure representing branch transformations. This should be represented by a Pydantic model or a more specific type for consistency and validation.

### 🛑 Line 63: `_count_ten_god_category` in `src2/engine/module0_geju.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses a raw 'dict | None' for 'transformed_branches', which is a complex data structure representing branch transformations. This should be ideally represented by a Pydantic model or a specific type alias for better validation and validation.

### 🛑 Line 111: `_calculate_dominance_pct` in `src2/engine/module0_geju.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses a raw dict for 'transformed_branches' input and returns a tuple containing a raw dict. For a core calculation logic involving element distribution, this should be represented by a Pydantic model to ensure type safety and validation of the element keys.

### 🛑 Line 169: `_check_counter_elements` in `src2/engine/module0_geju.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses a raw 'dict | None' for 'transformed_branches', which is a complex data structure mapping branches to elements. This should be part of a Pydantic model or a more specific type.

### ✅ Line 205: `_check_seasonal_support` in `src2/engine/module0_geju.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a private helper method (indicated by the leading underscore) that takes simple primitive types (str, bool) and an optional dictionary for internal state tracking. It does not handle complex API-level data payloads.

### 🛑 Line 234: `_check_vibrant_structure` in `src2/engine/module0_geju.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses a raw 'dict | None' for 'transformed_branches', which is a complex data structure representing branch transformations. This should be ideally represented by a Pydantic model or a specific type alias for better validation and schema enforcement.

### 🛑 Line 334: `classify_ge_ju` in `src2/engine/module0_geju.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models for the primary input (ChartProfile) and output (GeJuClassificationResult), but it accepts raw dictionaries for 'root_results' and 'transformed_branches'. Since these are complex data payloads used for calculation logic, they should be defined as Pydantic models to ensure type safety and validation.

### 🛑 Line 699: `compute_ge_ju_alignment_mod` in `src2/engine/module0_geju.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses a raw `dict[str, Any]` for the `strength_profile` parameter, which is a complex data structure containing critical scoring information (like 'spectrum_tier'), instead of a Pydantic model.

### ✅ Line 747: `validate_special_structure` in `src2/engine/module0_geju.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ChartProfile and GeJuValidation) for its primary input and output. While it accepts an optional 'transformed_branches' dict, this is likely a internal mapping of branch transformations which is acceptable for a helper-like validation function. The core API contract is Pydantic-based.

### ✅ Line 818: `run_module0_geju` in `src2/engine/module0_geju.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (GeJuInput and GeJuOutput) for both input and output, ensuring strict schema validation for complex data structures.

---

## 📂 `src2/engine/module10_classification.py`

### ✅ Line 118: `_get_age_multiplier` in `src2/engine/module10_classification.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple internal helper that operates on primitive types (str, int, float) and does not handle complex data structures requiring Pydantic models.

### ✅ Line 127: `_extract_hidden_ten_gods` in `src2/engine/module10_classification.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (ChartProfile) as input and returns a simple list of strings, which is appropriate for a list of identifiers. It does not use raw dictionaries for complex data structures.

### ✅ Line 145: `_is_active` in `src2/engine/module10_classification.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a private helper function that handles generic data access (dict or object) to check for an 'active' flag. It does not define or enforce a complex API contract via Pydantic models, but rather acts as a utility for internal state checking.

### ✅ Line 154: `classify_events` in `src2/engine/module10_classification.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (EventClassificationInput and EventClassificationOutput) for its input and output signatures, ensuring structured data validation.

### ✅ Line 574: `_create_event` in `src2/engine/module10_classification.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that instantiates a Pydantic model (Event). It takes primitive types as arguments and returns a Pydantic model, which is the correct pattern for creating model instances.

---

## 📂 `src2/engine/module11_probability.py`

### ✅ Line 112: `_sigmoid` in `src2/engine/module11_probability.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple mathematical helper that takes a float and returns a float, which does not require a Pydantic schema.

### ✅ Line 117: `is_event_actively_elevated` in `src2/engine/module11_probability.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a typed 'Event' object as input and returns a primitive 'bool'. It does not handle complex raw dictionaries or lists where a Pydantic model should be used.

### 🛑 Line 135: `_map_triggers` in `src2/engine/module11_probability.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function accepts 'Any' as input and uses extensive 'hasattr' and 'isinstance(..., dict)' checks to handle potentially raw dictionaries or objects, indicating a lack of a formal Pydantic schema for the 'triggers' payload.

### ✅ Line 186: `run_probability_scoring` in `src2/engine/module11_probability.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ProbabilityInput and ProbabilityOutput) for its input and output types, ensuring structured validation of complex data.

---

## 📂 `src2/engine/module12_compatibility.py`

### ✅ Line 166: `_get_ge_ju_score` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a private helper that takes simple primitive types (strings) and returns a simple tuple of primitives. It does not handle complex data structures that require Pydantic validation.

### ✅ Line 181: `_describe_ge_ju_match` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (str, int) for its inputs and output, making it a simple helper function that does not require a Pydantic schema.

### ✅ Line 191: `_get_day_master_score` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a private helper function that takes simple primitive types (strings) and returns a simple tuple of primitives. It does not handle complex data structures that require Pydantic validation.

### ✅ Line 228: `_get_branch_score` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a private helper method that takes primitive types (strings) and returns a simple tuple of (int, str). It does not handle complex data payloads that would require Pydantic models.

### ✅ Line 274: `_get_peach_blossom_score` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ChartProfile) for inputs and returns a simple primitive tuple. This is compliant with the schema design.

### ✅ Line 303: `_calculate_peach_blossom_branch` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes a primitive string input and returns a primitive string or None. It does not handle complex data structures, so Pydantic models are not required.

### ✅ Line 315: `_get_void_emptiness_score` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ChartProfile) for its inputs and returns a simple primitive tuple (int, str), which is appropriate for internal helper functions.

### ✅ Line 366: `_analyze_transit_impact` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ChartProfile, Pillar) for inputs and returns a simple tuple of primitives. Since it is an internal helper (prefixed with _), returning a tuple is acceptable and does not constitute a schema hazard.

### ✅ Line 415: `_analyze_aspect_patterns` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ChartProfile) for inputs and returns a simple tuple of primitives. As an internal helper (indicated by the leading underscore), returning a tuple is acceptable and does not constitute a schema hazard.

### ✅ Line 477: `calculate_exact_ten_god` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function takes simple string primitives as input and returns a string. It is a simple helper function for mapping two stems to a Ten God relationship, and does not handle complex data structures that would require Pydantic models.

### ✅ Line 501: `evaluate_relationship_dynamic` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ChartProfile) for complex input objects and returns a simple primitive tuple (int, str), which is appropriate for a calculation helper.

### ✅ Line 578: `analyze_compatibility` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ChartProfile, CompatibilityResult) for both input and output, ensuring strong typing and validation for complex data structures.

### ✅ Line 688: `analyze_compatibility_with_transits` in `src2/engine/module12_compatibility.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ChartProfile, Pillar, CompatibilityResult) for its complex inputs and outputs, ensuring type safety and validation.

---

## 📂 `src2/engine/module13_spectrum.py`

### 🛑 Line 21: `_dm_concentration_from_pillars` in `src2/engine/module13_spectrum.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses a raw 'dict | None' for 'transformed_branches', which is a complex data structure representing branch transformations. This should be mapped to a Pydantic model for validation and consistency across the engine.

### ✅ Line 73: `_graduated_pattern_score` in `src2/engine/module13_spectrum.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses the Pydantic model 'GeJuOutput' for its input and returns a primitive float, which is compliant with the schema validation requirements.

### ✅ Line 96: `calculate_strength_profile` in `src2/engine/module13_spectrum.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (SpectrumInput and SpectrumOutput) for both input and output, ensuring structured validation of complex data payloads.

---

## 📂 `src2/engine/module14_palaces.py`

### ✅ Line 17: `analyze_palaces` in `src2/engine/module14_palaces.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (PalaceInput and PalaceOutput) for its input and output signatures, ensuring structured validation. Although it uses internal dicts for processing, the API contract is compliant.

---

## 📂 `src2/engine/module1_macro.py`

### ✅ Line 41: `_get_stem_transformation_status` in `src2/engine/module1_macro.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (ChartProfile) for its complex input and returns a simple primitive (str). It is compliant with the schema validation requirements.

### ✅ Line 62: `_is_branch_void` in `src2/engine/module1_macro.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes primitive types (strings) and returns a boolean. It does not handle complex data structures that require Pydantic validation.

### ✅ Line 68: `_calculate_interaction_score` in `src2/engine/module1_macro.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple internal helper that takes primitive strings and returns an integer. It does not handle complex data structures that would require Pydantic models.

### ✅ Line 93: `_get_era_block` in `src2/engine/module1_macro.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ChartProfile and MacroEraBlock) for both input and output, ensuring strict schema validation for complex data structures.

### ✅ Line 151: `calculate_macro` in `src2/engine/module1_macro.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ChartProfile, Pillar, MacroOutput) for its input parameters and return type, ensuring strong typing and validation for complex data structures.

### ✅ Line 423: `check_zhi_tai_sui` in `src2/engine/module1_macro.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (TaiSuiTrigger) for its return type, and the input parameters are simple primitives (str, list of strings). While 'natal_branches' is a list, it is a simple collection of strings, not a complex data payload requiring a schema model.

### ✅ Line 445: `check_chong_tai_sui` in `src2/engine/module1_macro.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (TaiSuiTrigger) for its return type, but accepts a raw list for 'natal_branches'. However, given the context of this is a specific calculation helper for Tai Sui triggers, the use of a list of strings is a standard primitive for this specific logic, and the output is properly schema-validated.

### ✅ Line 459: `check_xing_tai_sui` in `src2/engine/module1_macro.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a raw list for 'natal_branches' instead of a structured Pydantic model or a more specific type, but it is a internal logic helper that returns a Pydantic model (TaiSuiTrigger). Given the context of the function's complexity, the raw list is acceptable for this specific internal utility.

### ✅ Line 474: `check_po_tai_sui` in `src2/engine/module1_macro.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (TaiSuiTrigger) for its return type, and the inputs are simple primitives (str, list of strings). This is compliant with the schema validation requirements for complex data structures.

### ✅ Line 488: `check_hai_tai_sui` in `src2/engine/module1_macro.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a raw list for 'natal_branches' instead of a structured Pydantic model or a more specific type, but it is a internal logic helper that returns a Pydantic model (TaiSuiTrigger). Given the context of the core calculation engine, passing a list of strings is acceptable for this specific helper. However, strictly speaking, it uses a raw list for a complex input. But since it's a simple internal check, it's a a FALSE_POSITIVE.

### ✅ Line 502: `check_he_tai_sui` in `src2/engine/module1_macro.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a raw list for 'natal_branches' instead of a structured Pydantic model or a more specific type, but it is a internal logic helper that returns a Pydantic model (TaiSuiTrigger). Given the context of the core calculation engine, passing a list of strings is acceptable for this specific helper. However, strictly speaking, it uses a raw list for a collection of domain entities. But since it's a a simple internal helper, it's a FALSE_POSITIVE.

### 🛑 Line 526: `_filter_tai_sui_by_shen` in `src2/engine/module1_macro.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function signature explicitly allows 'dict' as a type for 'shen_profile', and the implementation handles it as a raw dictionary, bypassing Pydantic validation for a complex data structure.

### ✅ Line 557: `run_module1_macro` in `src2/engine/module1_macro.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (MacroInput and MacroOutput) for its input and output types, ensuring structured data validation.

---

## 📂 `src2/engine/module2_root.py`

### ✅ Line 57: `_is_hit` in `src2/engine/module2_root.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes primitive strings and returns a boolean. It does not handle complex data structures that would require Pydantic models.

### ✅ Line 73: `_get_earth_type` in `src2/engine/module2_root.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes a primitive string input and returns a primitive string output. It does not handle complex data structures that would require Pydantic models.

### ✅ Line 82: `_is_element_rooted` in `src2/engine/module2_root.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a private helper function that operates on simple primitive types (str, list[str]) and returns a boolean. It does not handle complex data payloads that require Pydantic schema validation.

### ✅ Line 99: `_get_hidden_proportion` in `src2/engine/module2_root.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes primitive types (str, str) and returns a primitive type (float). It does not handle complex data structures that require Pydantic schema validation.

### ✅ Line 123: `_is_branch_controlled` in `src2/engine/module2_root.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple internal helper that takes primitive types (str, Optional[str]) and returns a boolean. It does not handle complex data payloads.

### 🛑 Line 134: `calculate_root` in `src2/engine/module2_root.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (RootInput, ModuleRootOutput) for its primary input and output, but it accepts raw 'dict | None' for 'transformed_branches' and 'selective_extractions'. While these are optional, they represent complex data structures (branch transformations and extractions) that should be ideally modeled via Pydantic for strict validation in a core engine module.

### 🛑 Line 412: `get_root_sub_score` in `src2/engine/module2_root.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function uses raw dicts (month_data, transformed_branches, selective_extractions) and a raw list (self_punished_branches) for complex input data structures instead of Pydantic models.

### ✅ Line 504: `calculate_dm_strength_tier1` in `src2/engine/module2_root.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ChartProfile and DmStrengthTier1) for both input and output, ensuring strict schema validation for complex data structures.

### ✅ Line 574: `calculate_clash_adjusted_dm_score` in `src2/engine/module2_root.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ChartProfile and ClashAdjustedDmScore) for its primary complex input and output. The 'clashed_branches' list is a simple list of strings, which is acceptable for a helper-style calculation function.

### ✅ Line 640: `calculate_tier1_simplified_count` in `src2/engine/module2_root.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ChartProfile and Tier1SimplifiedCount) for both input and output, ensuring strict schema validation for complex data structures.

### ✅ Line 683: `get_seasonal_adjustment_factor` in `src2/engine/module2_root.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (SeasonalAdjustmentFactor) as its return type, and its inputs are simple primitives (strings). It is fully compliant with the schema validation requirements.

---

## 📂 `src2/engine/module3_interaction.py`

### ✅ Line 124: `_get_distance_multiplier` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple internal helper that takes primitive strings and returns a float. It does not handle complex data structures that require Pydantic schema validation.

### ✅ Line 130: `_get_interaction_state` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (float, bool) as inputs and returns a string. It is a simple helper function and does not handle complex data structures.

### ✅ Line 142: `_is_pillar_void` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses the Pydantic model 'ChartProfile' for its complex input and returns a simple boolean primitive. This is compliant with the schema validation requirements.

### 🛑 Line 150: `_compute_stem_combo_modifiers` in `src2/engine/module3_interaction.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses a raw 'dict' for 'month_data', which is a complex data structure containing 'stem' and 'branch' information, instead of a Pydantic model.

### 🛑 Line 218: `_detect_fu_yin` in `src2/engine/module3_interaction.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses 'Any' for input parameters p1 and p2, and internally uses .get() or getattr() to handle them as either dictionaries or objects, indicating a lack of a strict Pydantic schema for the input data structures.

### 🛑 Line 236: `_detect_fan_yin` in `src2/engine/module3_interaction.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses 'Any' for input parameters p1 and p2, and then uses generic .get() or getattr() calls to access 'stem' and 'branch' attributes, indicating it accepts raw dictionaries or arbitrary objects instead of a structured Pydantic model for the pillar data.

### 🛑 Line 250: `detect_same_pillar_trigger` in `src2/engine/module3_interaction.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function accepts 'external_pillar' as 'Any' and 'natal_pillars' as a raw 'list', and internally uses .get() or getattr() to handle potentially raw dictionaries or objects, indicating a lack of a strict Pydantic schema for the pillar data structures.

### ✅ Line 276: `get_si_shen_harmony_stability` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (SiShenHarmonyStability) as the return type, and its inputs are simple primitives (bool, list[str]). This is compliant with the schema validation requirements.

### ✅ Line 297: `_check_alliance_improved` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (AllianceImprovementDetails) for its return type, and its inputs are simple primitives (str, set[str]), which is compliant.

### ✅ Line 322: `get_clash_monthly_qi` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (str, float) for its inputs and outputs, acting as a mathematical/logic helper. It does not handle complex data structures that would require Pydantic models.

### ✅ Line 332: `get_clash_dm_strength_modifier` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes a primitive float and returns a primitive float, which does not require a Pydantic schema model.

### ✅ Line 340: `get_clash_mediation_factor` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses raw 'list' types for 'natal_alliances' and 'chart_branches' instead of Pydantic models or specific typed lists, but it is a low-level internal calculation helper that returns a primitive float. It does not handle a complex API payload or a primary module entry point.

### ✅ Line 385: `get_harm_severity` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes primitive strings and returns a float, which does not require a Pydantic schema model.

### ✅ Line 389: `get_xing_severity` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes a primitive string and returns a primitive float. It does not handle complex data structures, so it is exempt from Pydantic schema requirements.

### ✅ Line 393: `calculate_combination_strength` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (CombinationStrength) as the return type, and its inputs are primitive types or simple collections (str, frozenset, list). It does not handle complex data payloads via raw dicts.

### ✅ Line 444: `calculate_harmony_strength` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (HarmonyStrength) for its return type and takes simple primitive types (str, list) as input. The list of stems is a simple collection of primitives, not a complex data structure requiring a schema model.

### ✅ Line 469: `calculate_interactions` in `src2/engine/module3_interaction.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (InteractionInput and InteractionOutput) for its primary input and output, ensuring structured validation of the complex data payloads.

---

## 📂 `src2/engine/module4_medicine.py`

### ✅ Line 10: `calculate_medicine` in `src2/engine/module4_medicine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (MedicineInput and MedicineOutput) for its input and output signatures, ensuring structured data validation.

---

## 📂 `src2/engine/module5_causal.py`

### ✅ Line 8: `calculate_causal_links` in `src2/engine/module5_causal.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (CausalInput, Pillar, InteractionOutput, CausalOutput) for all complex input and output structures, ensuring strict type validation.

---

## 📂 `src2/engine/module6_ten_gods.py`

### ✅ Line 96: `get_cycle_proximity` in `src2/engine/module6_ten_gods.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (str, float) for its inputs and outputs, acting as a mathematical helper for distance calculation. It does not handle complex data structures that would require Pydantic models.

### 🛑 Line 119: `calculate_ten_gods` in `src2/engine/module6_ten_gods.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function accepts raw dicts for natal_stems and hidden_stems, and in its legacy mode (when input_data is a string), it returns a raw dictionary instead of a Pydantic model. This creates a dual-path API where one path is schema-less, bypassing validation.

### ✅ Line 279: `get_ten_god_magnitude_multiplier` in `src2/engine/module6_ten_gods.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple mathematical helper that takes a float and returns a float, which does not require a Pydantic schema.

### ✅ Line 295: `get_seasonal_ten_god_weight` in `src2/engine/module6_ten_gods.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (str, float) for its inputs and output, acting as a simple weight lookup helper. It does not handle complex data structures that would require Pydantic models.

### 🛑 Line 307: `calculate_ten_god_dominance` in `src2/engine/module6_ten_gods.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function accepts a raw 'dict' as 'ten_gods_profile' instead of a Pydantic model, which is a complex data structure representing the chart's Ten Gods profile.

### ✅ Line 400: `check_tomb_clash_trigger` in `src2/engine/module6_ten_gods.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (TombClashTriggerResult) as its return type, and its inputs are simple primitives (strings). It is compliant with the schema validation requirements.

### ✅ Line 443: `check_fill_void_trigger` in `src2/engine/module6_ten_gods.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (FillVoidTriggerResult) as its return type, and its inputs are simple primitives (strings). It is compliant with the schema validation requirements.

### ✅ Line 493: `check_san_he_resolution_trigger` in `src2/engine/module6_ten_gods.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (SanHeResolutionTriggerResult) for its return type, and the input parameters are simple primitives (str, list). This is compliant with the schema validation requirements.

### 🛑 Line 533: `get_day_hour_ten_god_emphasis` in `src2/engine/module6_ten_gods.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function accepts a raw 'dict' as input ('ten_gods_profile') instead of a Pydantic model, despite returning a structured Pydantic model ('DayHourTenGodEmphasis'). This creates a schema hazard for complex data payloads.

### 🛑 Line 599: `detect_powerful_ten_god_combos` in `src2/engine/module6_ten_gods.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function accepts a raw 'dict' as input for 'ten_gods_profile' instead of a Pydantic model, which is a schema hazard for complex data structures.

### 🛑 Line 624: `detect_ten_god_absence` in `src2/engine/module6_ten_gods.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function accepts a raw 'dict' as input (ten_gods_profile) for a complex data structure, instead of using a Pydantic model for validation.

### 🛑 Line 661: `calculate_ten_gods_deep` in `src2/engine/module6_ten_gods.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function uses raw dicts for complex inputs (chart_stems, chart_branches) and as the return type, instead of Pydantic models for structured data validation.

---

## 📂 `src2/engine/module7_shen_sha.py`

### ✅ Line 21: `classify_star_activation` in `src2/engine/module7_shen_sha.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ShenShaInput and ShenShaOutput) for its input and output signatures, ensuring structured validation of complex data payloads.

---

## 📂 `src2/engine/module8_scoring.py`

### ✅ Line 27: `_sigmoid_cap` in `src2/engine/module8_scoring.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple mathematical helper that uses primitive float types for input and output, which is appropriate and does not require Pydantic models.

### ✅ Line 34: `calculate_composite_score` in `src2/engine/module8_scoring.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ScoringInput and ScoringOutput) for its primary input and output signatures, which is compliant with the schema validation requirements. Although it performs internal dictionary manipulations and dynamic attribute injection on the output object, the API contract itself is defined by Pydantic models.

### ✅ Line 437: `get_dm_luck_interaction` in `src2/engine/module8_scoring.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (DmLuckInteraction) as the return type and correctly instantiates it using the unpacked dictionary from the matrix. This is compliant with the schema validation requirements.

---

## 📂 `src2/engine/module9_triggers.py`

### ✅ Line 38: `detect_clash_triggers` in `src2/engine/module9_triggers.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (InteractionOutput and ClashTriggersOutput) for both input and output, ensuring strict schema validation for complex data structures.

### ✅ Line 70: `_yield_special_star_triggers` in `src2/engine/module9_triggers.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses primitive types (str) for inputs and a Generator yielding a Pydantic model (StarDetectionResult), which is compliant with the schema design.

### ✅ Line 126: `detect_special_star_triggers` in `src2/engine/module9_triggers.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ChartProfile, Pillar, StarDetectionResult) for its inputs and outputs, ensuring type safety and validation for complex data structures.

### ✅ Line 159: `_calculate_peach_blossom_branch` in `src2/engine/module9_triggers.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple internal helper that maps a single string input to a single string output. It does not handle complex data structures, so Pydantic models are not required.

### ✅ Line 173: `detect_da_yun_triggers` in `src2/engine/module9_triggers.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (ChartProfile) for the main profile input and returns a simple list of strings, which is appropriate for a list of trigger labels. The 'Any' type for da_yun_pillar is acceptable as it is treated as an object with stem/branch attributes.

### ✅ Line 221: `_get_dm_element` in `src2/engine/module9_triggers.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes a primitive string and returns a primitive string or None. It does not handle complex data structures that require Pydantic validation.

### ✅ Line 227: `run_trigger_detection` in `src2/engine/module9_triggers.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (TriggersInput and TriggersOutput) for its input and output signatures, ensuring structured validation of complex data payloads.

### ✅ Line 327: `calculate_trigger_potency` in `src2/engine/module9_triggers.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses primitive types for inputs and a Pydantic model (TriggerPotencyResult) for the output, which is compliant with the schema validation requirements.

---

## 📂 `src2/engine/monthly_generator.py`

### ✅ Line 101: `build_domain_rag` in `src2/engine/monthly_generator.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple internal helper that processes a list of strings (queries) and returns a string. It does not handle complex data payloads that require Pydantic schema validation.

---

## 📂 `src2/engine/narrative_review.py`

### ✅ Line 38: `get_narrative_agent` in `src2/engine/narrative_review.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns an Agent object, which is a specialized class instance. It does not handle complex data payloads via raw dictionaries or lists; it is a factory function for a specific object.

### ✅ Line 54: `__init__` in `src2/engine/narrative_review.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple constructor initializing a internal reference to a getter object. It does not handle complex data payloads or API contracts.

### ✅ Line 57: `__getattr__` in `src2/engine/narrative_review.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: This is a magic method for attribute access delegation, not a data processing function that handles complex payloads. It is exempt from schema validation requirements.

---

## 📂 `src2/engine/narrative_simplifier.py`

### ✅ Line 95: `get_month_simplifier_agent` in `src2/engine/narrative_simplifier.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a factory/singleton provider that returns a specific object type (Agent). It does not handle complex data payloads or raw dictionaries for input/output validation.

### ✅ Line 110: `get_advisory_simplifier_agent` in `src2/engine/narrative_simplifier.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a factory method that returns an Agent object. It does not handle complex data payloads or raw dictionaries as inputs or outputs that should be replaced by Pydantic models.

### ✅ Line 126: `__init__` in `src2/engine/narrative_simplifier.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a class constructor taking a single dependency (getter) for internal state management, not handling complex data payloads or API contracts.

### ✅ Line 129: `__getattr__` in `src2/engine/narrative_simplifier.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: This is a magic method for attribute access delegation, not a data processing function that handles complex payloads. It is exempt from schema validation requirements.

---

## 📂 `src2/engine/openrouter.py`

### ✅ Line 45: `_reserve_slot` in `src2/engine/openrouter.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple internal helper that takes and returns primitive float types, not complex data structures.

### ✅ Line 74: `_clean_llm_response` in `src2/engine/openrouter.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple string manipulation helper that takes a string and returns a string. It does not handle complex data structures that would require Pydantic models.

### ✅ Line 86: `throttle_sync` in `src2/engine/openrouter.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple utility helper that takes a primitive string and returns nothing. It does not handle complex data structures, so it is not a schema hazard.

### ✅ Line 95: `_prepare_request_headers` in `src2/engine/openrouter.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a low-level internal helper for HTTP header manipulation using standard dictionary types, which is appropriate for its purpose and does not involve complex BaZi domain models.

### ✅ Line 118: `_resolve_provider_dynamically` in `src2/engine/openrouter.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function takes a simple string input and returns a simple string or None. It does not handle complex data structures, so it is a a simple helper function and is exempt from Pydantic schema requirements.

### ✅ Line 130: `_get_provider_adapter` in `src2/engine/openrouter.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a internal helper that returns a module (Any), taking simple primitive types (str) as input. It does not handle complex data payloads that would require Pydantic schema validation.

### 🛑 Line 410: `call_openrouter_sync` in `src2/engine/openrouter.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function uses a raw list of dictionaries (`list[dict[str, Any]]`) for the `tools` parameter instead of a Pydantic model to define the tool schema, which is a complex data structure.

---

## 📂 `src2/engine/orchestrator.py`

### ✅ Line 72: `_parse_pillar` in `src2/engine/orchestrator.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a normalization helper that explicitly handles various input types (Any) to produce a validated Pydantic model (Pillar). This is a standard pattern for flexible input parsing and does not represent a schema hazard.

### ✅ Line 98: `persist_audit_trace` in `src2/engine/orchestrator.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a typed list of Pydantic models (TraceEntry) as input, ensuring structured validation of the trace data.

### ✅ Line 107: `apply_selective_extraction` in `src2/engine/orchestrator.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (SelectiveExtractionResult and ExtractedStemItem) for its return type and internal data structures, ensuring type safety and validation.

### 🛑 Line 121: `handle_clash_activation` in `src2/engine/orchestrator.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses raw 'list' types for its input parameters 'clashed_branches' and 'chart_branches' instead of a structured Pydantic model or a more specific type hint (e.g., list[str]), and it returns a dictionary of Pydantic models. While it processes complex logic, the input side lacks schema validation for the lists.

### ✅ Line 141: `run_full_engine` in `src2/engine/orchestrator.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function signature correctly uses Pydantic models (ChartProfile and EngineOutput) for its primary input and output, ensuring structural validation for the complex data payloads it orchestrates.

### ✅ Line 148: `log_step` in `src2/engine/orchestrator.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses 'Any' for inputs and outputs, which are then treated as dictionaries. This is a logging helper that handles serialization of Pydantic models into raw dicts for tracing, and is not a primary API entry point for calculation logic.

### ✅ Line 149: `serialise` in `src2/engine/orchestrator.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a generic utility helper designed specifically to convert Pydantic models into raw dictionaries for serialization. It does not define a complex API contract using raw dicts; rather, it is the mechanism used to perform the conversion.

---

## 📂 `src2/engine/prompt_checker.py`

### ✅ Line 15: `get_prompt_checker_agent` in `src2/engine/prompt_checker.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple factory function that returns an Agent object. It does not handle complex data payloads or raw dictionaries as inputs or outputs.

---

## 📂 `src2/engine/prompt_engine.py`

### ✅ Line 16: `_json_serial` in `src2/engine/prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: This is a low-level utility helper function for JSON serialization of date/datetime objects, not a high-level API or data processing function requiring Pydantic schema validation.

---

## 📂 `src2/engine/prompt_maker.py`

### ✅ Line 48: `_get_ge_ju_category` in `src2/engine/prompt_maker.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that takes a string and returns a string, which does not require a complex data structure or Pydantic model.

### ✅ Line 60: `_build_age_ge_ju_framing` in `src2/engine/prompt_maker.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (int, str) for inputs and returns a string. It is a simple helper function for string formatting and does not handle complex data structures that would require Pydantic models.

### 🛑 Line 75: `_serialise_engine_outputs` in `src2/engine/prompt_maker.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses 'Any' for the input 'engine_result', which bypasses type safety and schema validation for a complex object that is clearly accessed as a Pydantic-like model (e.g., engine_result.engine_outputs). This is a schema hazard as it lacks a concrete Pydantic model type hint for a complex data structure.

### ✅ Line 116: `_derive_age` in `src2/engine/prompt_maker.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses the Pydantic model 'ChartProfile' as input and returns a primitive 'int', which is a correct and compliant implementation for this specific logic.

### ✅ Line 130: `_parse_json_response` in `src2/engine/prompt_maker.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns a raw dict, but it is a low-level utility helper for parsing raw LLM text into a dictionary before further validation. It does not define a business-level API contract.

### ✅ Line 211: `get_prompt_maker_agent` in `src2/engine/prompt_maker.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns an Agent object which is a wrapper for an LLM call. The output_type is explicitly set to MonthResponse (a Pydantic model), ensuring structured output validation. It does not use raw dicts for complex data exchange.

---

## 📂 `src2/engine/prompt_stitcher.py`

### ✅ Line 14: `get_report_stitcher_agent` in `src2/engine/prompt_stitcher.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple factory function that returns an Agent object. It does not handle complex data payloads or raw dictionaries where Pydantic models should be used.

### ✅ Line 21: `get_reviewer_agent` in `src2/engine/prompt_stitcher.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns an Agent object, which is a specialized class. It does not handle complex data payloads via raw dictionaries or lists; it is a simple factory function for an Agent instance.

---

## 📂 `src2/engine/providers/gemini.py`

### 🛑 Line 23: `build_payload` in `src2/engine/providers/gemini.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function uses raw dicts for 'tools' input and returns a raw dict as the payload, which is a complex structure for an API contract.

### ✅ Line 55: `extract_response` in `src2/engine/providers/gemini.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function takes a raw `dict[str, Any]` as input to parse an external API response, which is a common pattern for initial extraction. However, it correctly returns a Pydantic model `LLMResponsePayload`, ensuring that the output is validated. Since it acts as a bridge from raw API data to a structured model, it is not a a schema hazard.

---

## 📂 `src2/engine/providers/openai.py`

### 🛑 Line 25: `build_payload` in `src2/engine/providers/openai.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function uses raw dicts for 'tools' input and returns a raw dict as the payload, which is a complex structure intended for an external API call. This bypasses Pydantic validation for the final payload structure.

### 🛑 Line 54: `extract_response` in `src2/engine/providers/openai.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function accepts a raw dictionary (`dict[str, Any]`) as input for a complex LLM response payload, which bypasses Pydantic validation for the incoming data structure.

---

## 📂 `src2/engine/pydantic_prompt_engine.py`

### 🛑 Line 40: `load_prompt_template` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function returns a raw dictionary from a YAML file, which is a complex data structure. In a Pydantic-driven engine, this should be validated against a schema model to ensure the prompt template structure is correct.

### 🛑 Line 49: `get_active_clashes` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses 'Any' for the input parameter 'm3', which is then accessed as an object with an 'active_disruptors' attribute. This indicates a lack of a Pydantic model or a specific type hint for a complex object, representing a schema hazard.

### 🛑 Line 78: `get_active_combinations` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function uses 'Any' for the input parameter 'm3', which is then accessed as an object with an 'active_alliances' attribute. This indicates a lack of a Pydantic model or a specific type hint for a complex object, representing a schema hazard.

### ✅ Line 116: `_json_serial` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: This is a low-level utility helper function used for JSON serialization of specific types. It does not handle complex business logic payloads or API contracts that require Pydantic schema validation.

### ✅ Line 124: `make_serializable` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: This is a general-purpose utility helper function designed to convert non-serializable types to serializable ones. It does not define or handle a specific business logic schema or API contract, making it a FALSE_POSITIVE.

### ✅ Line 136: `check_text_constraints` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple validation helper that operates on primitive types (str) and does not handle complex data structures or API payloads.

### ✅ Line 170: `validate_advisory` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns 'Advisory', which is a Pydantic model (implied by the context of the file name and the return type hint). It performs internal validation on the model's attributes. This is a compliant use of schema models.

### ✅ Line 187: `validate_score_rating` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns 'self' (which is an instance of Module8, a Pydantic model) and performs internal validation. It does not use raw dicts or lists for complex data payloads.

### ✅ Line 204: `validate_result` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns 'MonthlyForecastResult', which is a Pydantic model (implied by the context of the class and the return type hint). It does not use raw dicts or lists for complex data structures.

### ✅ Line 268: `validate_career` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns 'CareerResult', which is a Pydantic model (implied by the context of the prompt engine and the return type hint). It performs internal validation on a field and returns the instance. This is a compliant use of schema models.

### ✅ Line 282: `validate_relationship` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns a Pydantic model (RelationshipResult) and operates on internal state, acting as a validation method within a Pydantic-based engine. It does not use raw dicts for complex data exchange.

### ✅ Line 296: `validate_health` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns 'HealthResult', which is a Pydantic model (implied by the context of the file name and return type hint), and it operates on internal state. It is compliant with schema validation practices.

### ✅ Line 310: `validate_wealth` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns 'WealthResult', which is a Pydantic model (implied by the context of the prompt engine and the return type hint). It performs internal validation on a field and returns self. This is a compliant use of schema-based validation.

### ✅ Line 323: `validate_overview` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns 'OverviewResult', which is a Pydantic model (implied by the context of the class and the return type hint). It does not use raw dicts or lists for complex data structures.

### ✅ Line 352: `build_shared_system_prompt` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a structured dependency object (MonthlyForecastDeps) and returns a simple string. It does not use raw dictionaries for complex data exchange; it relies on the provided context/dependency objects.

### ✅ Line 384: `domain_system_prompt` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function takes a RunContext and returns a simple string. It does not handle complex data payloads via raw dictionaries or lists; it is a simple prompt builder helper.

### ✅ Line 389: `overview_system_prompt` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function takes a RunContext with a specific dependency type and returns a simple string. It does not handle complex data payloads via raw dictionaries or lists; it is a simple prompt builder helper.

### ✅ Line 468: `build_domain_rag` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function takes a list of queries (likely strings) and returns a string. It is a simple string formatting helper function and does not handle complex data payloads that require Pydantic validation.

### 🛑 Line 554: `format_user_prompt` in `src2/engine/pydantic_prompt_engine.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `LOW`
- **Reasoning**: The function takes a raw 'dict' as 'template_dict' for a structured prompt template, which should be ideally represented by a Pydantic model to ensure the structure of the template is validated.

---

## 📂 `src2/engine/rag_client.py`

### ✅ Line 32: `query_classical_text` in `src2/engine/rag_client.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses simple primitive types (str, int) for its input and output, which is appropriate for a standalone tool designed for LLM tool-calling. It does not handle complex data structures that would require Pydantic models.

---

## 📂 `src2/engine/session.py`

### ✅ Line 35: `get_advice_posture` in `src2/engine/session.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is a simple helper that maps a string to an integer using a dictionary. It uses primitive types and does not handle complex data structures, so it is exempt from Pydantic schema requirements.

### 🛑 Line 49: `build_lifestate` in `src2/engine/session.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function uses 'Any' for its input parameters and returns a raw 'dict', despite handling a complex data structure (life-state) that should be validated by a Pydantic model.

---

## 📂 `src2/engine/shen_classifier.py`

### ✅ Line 30: `classify_shen` in `src2/engine/shen_classifier.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses a Pydantic model (ShenClassifierOutput) as the return type, and the input parameters are simple primitives (strings and lists). This is compliant with the schema validation requirements.

### ✅ Line 42: `derive_engine_logic` in `src2/engine/shen_classifier.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function returns a Pydantic model (ShenClassification), and takes no arguments. It is compliant with the schema validation requirements.

---

## 📂 `src2/engine/solar_calendar.py`

### 🛑 Line 51: `get_annual_pillar` in `src2/engine/solar_calendar.py`
- **Verdict**: `SCHEMA_HAZARD`
- **Severity**: `HIGH`
- **Reasoning**: The function returns a raw dictionary `dict[str, str]` to represent a pillar (stem and branch), which is a core domain entity in BaZi. This should be represented by a Pydantic model for consistent validation and type safety across the engine.

### ✅ Line 357: `get_solar_months` in `src2/engine/solar_calendar.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function correctly uses a Pydantic model (SolarMonthAnchor) in its return type hint and explicitly instantiates the model from the raw data, ensuring type safety and validation.

---

## 📂 `src2/engine/stars.py`

### ✅ Line 16: `_yield_stars` in `src2/engine/stars.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function is an internal helper (indicated by the leading underscore) that uses a Pydantic model (StarDetectionResult) for its output (via yield) and accepts primitive types or specific domain models (Pillar) for its inputs. It does not use raw dictionaries for complex data payloads.

### ✅ Line 82: `detect_stars` in `src2/engine/stars.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (ChartProfile, Pillar, StarDetectionResult) for both input and output, ensuring strong typing and schema validation.

### ✅ Line 128: `detect_yang_ren` in `src2/engine/stars.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The function uses Pydantic models (ChartProfile, Pillar, StarDetectionResult) for both input and output, ensuring strong typing and validation for complex data structures.

---

## 📂 `src2/engine/stealth_damage.py`

### ✅ Line 11: `calculate_accumulated_damage` in `src2/engine/stealth_damage.py`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `HIGH`
- **Reasoning**: The function uses Pydantic models (DamageInputItem, AccumulatedDamageResult, DamageBreakdown) for both input and output, ensuring strict schema validation for complex data structures.

---

