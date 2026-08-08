# CC Reduction Plan — 136 Functions / 55 Files / Two Rounds

## Scope
- **Target**: All functions with CC > 5 in `TARGET_REPO/`
- **Scanner**: `admin/code_hygiene/scanners/find_cc_nested.py` (min-cc=6)
- **Hard Limit**: CC ≤ 5 per function (per pyproject.toml max-complexity=5)
- **Total Tickets**: 136 (1 per violating function)
- **Max Concurrency**: 20 subagents
- **Strategy**: Guard clauses + early returns + extract private helpers + match/case for enums
- **Forbidden**: Dict dispatch, `kill_tries.py`, new imports beyond what's already imported, hallucinated symbols

## Round 1: Refactor + Test (Batches of 20)

Each subagent:
1. Takes 1 ticket (1 function)
2. Reads the full source file
3. Refactors the function to CC ≤ 5 using guard clauses, early return, helper extraction
4. Runs `uv run ruff check .` to verify no new C901/CC violations
5. Runs any existing tests for the target file
6. Commits the diff only (no push)
7. Closes the ticket

### Batch 1 (20 functions) — Tickets 01–20
1. `TARGET_REPO/core/tools/bazi_engine.py` — `get_day_master_strength` CC=20
2. `TARGET_REPO/core/tools/bazi_engine.py` — `score_elements` CC=8
3. `TARGET_REPO/interfaces/telegram/chronomancer/rag.py` — `GemmaRAGModel` CC=19
4. `TARGET_REPO/interfaces/telegram/chronomancer/rag.py` — `request` CC=18
5. `TARGET_REPO/interfaces/telegram/chronomancer/oracle_gatherer.py` — `_gather_transits` CC=19
6. `TARGET_REPO/interfaces/telegram/chronomancer/oracle_gatherer.py` — `format_transit_pillar` CC=13
7. `TARGET_REPO/core/memory/mem0_store.py` — `build_context` CC=19
8. `TARGET_REPO/core/memory/mem0_store.py` — `__init__` CC=14
9. `TARGET_REPO/core/memory/mem0_store.py` — `Mem0Store` CC=10
10. `TARGET_REPO/core/memory/mem0_store.py` — `search` CC=9
11. `TARGET_REPO/core/memory/mem0_store.py` — `get_user_mem0` CC=8
12. `TARGET_REPO/engine/module12_compatibility.py` — `_get_branch_score` CC=19
13. `TARGET_REPO/engine/module12_compatibility.py` — `_get_void_emptiness_score` CC=18
14. `TARGET_REPO/engine/module12_compatibility.py` — `analyze_compatibility` CC=15
15. `TARGET_REPO/engine/module12_compatibility.py` — `_get_day_master_score` CC=13
16. `TARGET_REPO/engine/module12_compatibility.py` — `_get_peach_blossom_score` CC=13
17. `TARGET_REPO/engine/module12_compatibility.py` — `_get_ge_ju_score` CC=6
18. `TARGET_REPO/engine/daily_pillar.py` — `resolve_daily_pillar_range` CC=19
19. `TARGET_REPO/engine/daily_pillar.py` — `get_pillar_from_string` CC=7
20. `TARGET_REPO/interfaces/telegram/evaluation.py` — `evaluate_profile` CC=18

### Batch 2 (20 functions) — Tickets 21–40
21. `TARGET_REPO/interfaces/telegram/evaluation.py` — `InputEvaluator` CC=8
22. `TARGET_REPO/engine/da_yun.py` — `calculate_da_yun` CC=18
23. `TARGET_REPO/engine/da_yun.py` — `_get_days_to_solar_term` CC=11
24. `TARGET_REPO/engine/module8_scoring.py` — `calculate_composite_score_adapter` CC=18
25. `TARGET_REPO/engine/module8_scoring.py` — `_compute_occupation_suspend_mod` CC=6
26. `TARGET_REPO/interfaces/telegram/chronomancer/oracle_narrator.py` — `resolve_liu_nian` CC=17
27. `TARGET_REPO/interfaces/telegram/ui_components.py` — `send_stakeholders_list` CC=16
28. `TARGET_REPO/interfaces/telegram/gatekeeper.py` — `Gatekeeper` CC=16
29. `TARGET_REPO/interfaces/telegram/gatekeeper.py` — `validate` CC=15
30. `TARGET_REPO/engine/module14_palaces.py` — `analyze_palaces` CC=16
31. `TARGET_REPO/interfaces/telegram/chronomancer/ranking.py` — `rank_days_by_health` CC=15
32. `TARGET_REPO/interfaces/telegram/chronomancer/ranking.py` — `format_ranking_output` CC=7
33. `TARGET_REPO/interfaces/telegram/chronomancer/ranking.py` — `rank_days_by_activity` CC=6
34. `TARGET_REPO/engine/transformer.py` — `serialise_egress` CC=15
35. `TARGET_REPO/engine/transformer.py` — `normalize_elements` CC=10
36. `TARGET_REPO/engine/transformer.py` — `extract_text` CC=9
37. `TARGET_REPO/engine/transformer.py` — `normalize_strength` CC=7
38. `TARGET_REPO/engine/transformer.py` — `normalize_element` CC=6
39. `TARGET_REPO/engine/module11_probability.py` — `run_probability_scoring` CC=15
40. `TARGET_REPO/engine/prompt_maker.py` — `get_ge_ju_category` CC=15

### Batch 3 (20 functions) — Tickets 41–60
41. `TARGET_REPO/engine/prompt_maker.py` — `get_chinese_branch` CC=13
42. `TARGET_REPO/engine/prompt_maker.py` — `make_month` CC=12
43. `TARGET_REPO/engine/prompt_maker.py` — `get_chinese_stem` CC=11
44. `TARGET_REPO/engine/rag_client.py` — `query_classical_text` CC=15
45. `TARGET_REPO/engine/rag_client.py` — `query_classical_text_async` CC=15
46. `TARGET_REPO/engine/module13_spectrum.py` — `calculate_strength_profile` CC=14
47. `TARGET_REPO/engine/module13_spectrum.py` — `_get_root_sub_score` CC=8
48. `TARGET_REPO/engine/module13_spectrum.py` — `_get_spectrum_tier` CC=7
49. `TARGET_REPO/interfaces/telegram/chronomancer/oracle_coordinator.py` — `handle_oracle` CC=13
50. `TARGET_REPO/interfaces/telegram/chronomancer/forecast_store.py` — `get_daily_forecast` CC=13
51. `TARGET_REPO/interfaces/telegram/chronomancer/forecast_store.py` — `get_rolling_30` CC=12
52. `TARGET_REPO/engine/prompt_stitcher.py` — `stitch_report` CC=12
53. `TARGET_REPO/engine/bazi_cache.py` — `get_or_fetch_classical_text` CC=12
54. `TARGET_REPO/engine/bazi_cache.py` — `_load_cache` CC=9
55. `TARGET_REPO/interfaces/telegram/ier_parser.py` — `parse_question` CC=11
56. `TARGET_REPO/engine/module6_ten_gods.py` — `check_tomb_clash_trigger` CC=11
57. `TARGET_REPO/engine/module6_ten_gods.py` — `detect_ten_god_absence` CC=9
58. `TARGET_REPO/engine/module6_ten_gods.py` — `get_day_hour_ten_god_emphasis` CC=8
59. `TARGET_REPO/engine/module6_ten_gods.py` — `check_san_he_resolution_trigger` CC=8
60. `TARGET_REPO/engine/module6_ten_gods.py` — `get_ten_god_category` CC=6

### Batch 4 (20 functions) — Tickets 61–80
61. `TARGET_REPO/engine/module6_ten_gods.py` — `calculate_ten_gods` CC=6
62. `TARGET_REPO/interfaces/telegram/intake/intake.py` — `_handle_intake_extract_obj_profile` CC=10
63. `TARGET_REPO/interfaces/telegram/intake/intake.py` — `__format_playback_format_auto` CC=7
64. `TARGET_REPO/interfaces/telegram/intake/intake.py` — `_handle_intake_obj_pillars` CC=7
65. `TARGET_REPO/core/schemas/unified.py` — `derive_ten_god` CC=10
66. `TARGET_REPO/core/schemas/unified.py` — `SelectiveExtractions` CC=6
67. `TARGET_REPO/core/schemas/unified.py` — `ClashActivations` CC=6
68. `TARGET_REPO/core/services/compliance.py` — `forget_user` CC=10
69. `TARGET_REPO/core/services/compliance.py` — `export_user_data` CC=6
70. `TARGET_REPO/engine/module1_macro.py` — `get_priority_type` CC=10
71. `TARGET_REPO/engine/module1_macro.py` — `get_legacy_impact` CC=10
72. `TARGET_REPO/engine/activity_oracle.py` — `_detect_transit_triggers` CC=10
73. `TARGET_REPO/engine/activity_oracle.py` — `_get_activity_forecast_domain_elements` CC=7
74. `TARGET_REPO/engine/activity_oracle.py` — `get_hour_pillar` CC=6
75. `TARGET_REPO/engine/activity_oracle.py` — `_score_job_interview` CC=6
76. `TARGET_REPO/engine/activity_oracle.py` — `_extract_love_profile` CC=6
77. `TARGET_REPO/engine/activity_oracle.py` — `_eval_wealth_element` CC=6
78. `TARGET_REPO/engine/activity_oracle.py` — `_score_monthly_transit` CC=6
79. `TARGET_REPO/engine/prompt_engine.py` — `run_engine` CC=10
80. `TARGET_REPO/interfaces/telegram/intake/calendar_node.py` — `_run_input_engine` CC=9

### Batch 5 (20 functions) — Tickets 81–100
81. `TARGET_REPO/core/tools/user_profile_input.py` — `apply_override` CC=9
82. `TARGET_REPO/core/platforms/telegram.py` — `_parse_message` CC=9
83. `TARGET_REPO/core/platforms/telegram.py` — `send_outgoing` CC=8
84. `TARGET_REPO/core/platforms/telegram.py` — `_parse_callback_query` CC=6
85. `TARGET_REPO/core/platforms/telegram.py` — `_validate_message_content` CC=6
86. `TARGET_REPO/engine/module2_root.py` — `_calc_positive_root_impact` CC=9
87. `TARGET_REPO/engine/module2_root.py` — `_get_elemental_adjustment` CC=9
88. `TARGET_REPO/engine/module2_root.py` — `_eval_branch_clash_adj` CC=8
89. `TARGET_REPO/engine/module2_root.py` — `_is_branch_dm_root` CC=7
90. `TARGET_REPO/engine/module2_root.py` — `calculate_root` CC=7
91. `TARGET_REPO/engine/module2_root.py` — `_eval_branch_tier1` CC=7
92. `TARGET_REPO/engine/module2_root.py` — `_eval_stem_clash_adj` CC=7
93. `TARGET_REPO/engine/module2_root.py` — `_eval_stem_tier1` CC=6
94. `TARGET_REPO/engine/module2_root.py` — `get_stem_for_element_simple` CC=6
95. `TARGET_REPO/interfaces/telegram/app.py` — `_check_valkey_status` CC=8
96. `TARGET_REPO/interfaces/telegram/app.py` — `_redact_and_log_webhook` CC=7
97. `TARGET_REPO/interfaces/telegram/app.py` — `_try_apply_promo_codes` CC=7
98. `TARGET_REPO/interfaces/telegram/app.py` — `_parse_log_line` CC=6
99. `TARGET_REPO/interfaces/telegram/app.py` — `_handle_subscribe_command` CC=6
100. `TARGET_REPO/interfaces/telegram/app.py` — `_handle_step_fallback` CC=6

### Batch 6 (20 functions) — Tickets 101–120
101. `TARGET_REPO/interfaces/telegram/app.py` — `_handle_authorized_commands_and_steps` CC=6
102. `TARGET_REPO/engine/stealth_damage.py` — `calculate_accumulated_damage` CC=8
103. `TARGET_REPO/engine/module5_causal.py` — `_get_clashed_elements` CC=8
104. `TARGET_REPO/engine/module_activation.py` — `score_period_activation` CC=8
105. `TARGET_REPO/engine/module_activation.py` — `event_for` CC=7
106. `TARGET_REPO/engine/module_activation.py` — `get_xi_cycle_support` CC=6
107. `TARGET_REPO/core/rotator.py` — `ModelFactory` CC=7
108. `TARGET_REPO/core/rotator.py` — `get_model` CC=6
109. `TARGET_REPO/core/rotator.py` — `create` CC=6
110. `TARGET_REPO/engine/classical_rules.py` — `get_hai_damage_type` CC=7
111. `TARGET_REPO/engine/classical_rules.py` — `get_chong_base_severity` CC=6
112. `TARGET_REPO/engine/module0_geju_detection.py` — `_detect_fei_tian_lu_ma` CC=7
113. `TARGET_REPO/engine/module0_geju_detection.py` — `_detect_vibrant_structure` CC=7
114. `TARGET_REPO/engine/module0_geju_detection.py` — `_detect_ten_god_pattern` CC=7
115. `TARGET_REPO/engine/module3_interaction.py` — `_calc_from_args_dict` CC=7
116. `TARGET_REPO/engine/module3_interaction.py` — `calculate_interactions` CC=6
117. `TARGET_REPO/engine/module3_interaction.py` — `_detect_san_he` CC=6
118. `TARGET_REPO/engine/module3_interaction.py` — `_detect_ban_he` CC=6
119. `TARGET_REPO/engine/module3_interaction.py` — `_calc_xing_type` CC=6
120. `TARGET_REPO/engine/module3_interaction.py` — `_xing_match` CC=6

### Batch 7 (16 functions) — Tickets 121–136
121. `TARGET_REPO/engine/module3_interaction.py` — `_calc_voids` CC=6
122. `TARGET_REPO/interfaces/telegram/preflight.py` — `check_bgem3` CC=6
123. `TARGET_REPO/interfaces/telegram/preflight.py` — `_classify_webhook` CC=6
124. `TARGET_REPO/interfaces/telegram/session.py` — `save_session` CC=6
125. `TARGET_REPO/interfaces/telegram/utils.py` — `send_telegram_message` CC=6
126. `TARGET_REPO/interfaces/telegram/conductor.py` — `_run_conductor_filter_missing` CC=6
127. `TARGET_REPO/interfaces/telegram/conductor.py` — `_run_conductor_build_system_prompt` CC=6
128. `TARGET_REPO/interfaces/telegram/chronomancer/parser.py` — `parse_pillar_string` CC=6
129. `TARGET_REPO/core/memory/memory_manager.py` — `_resolve_id` CC=6
130. `TARGET_REPO/core/memory/memory_manager.py` — `clear_all_user_data` CC=6
131. `TARGET_REPO/core/services/session.py` — `save_session` CC=6
132. `TARGET_REPO/engine/pydantic_prompt_engine.py` — `MonthlyForecastResult` CC=6
133. `TARGET_REPO/engine/module10_classification.py` — `_classify_events_dedup_insert` CC=6
134. `TARGET_REPO/engine/stars.py` — `detect_yang_ren` CC=6
135. `TARGET_REPO/engine/monthly_generator.py` — `_determine_is_void` CC=6
136. `TARGET_REPO/engine/module0_geju_utils.py` — `_is_branch_counter` CC=6

## Round 2: Verify Against Git Diff (Batches of 20)

After Round 1 completes, each subagent:
1. Takes 1 ticket
2. Checks `git diff HEAD~1` for the target file
3. Validates the refactored function has CC ≤ 5 (using `find_cc_nested.py`)
4. Validates no new CC violations were introduced in the file
5. Validates all tests still pass
6. Marks the ticket as verified
7. Closes the ticket

Batch 1 (20) → Verify tickets 01–20
Batch 2 (20) → Verify tickets 21–40
...
Batch 7 (16) → Verify tickets 121–136

## Resilience / Network Interruption
- Each ticket represents 1 function — if a subagent fails, the ticket stays `in_progress` and can be picked up by any agent in the next batch
- Batches are independent — no cross-batch dependencies
- `bd list --status in_progress` shows exactly which functions need retrying
- `bd show <id>` shows the function path and current state

## Progress Update

- **2026-07-31 Batch 1**: 8 functions refactored across 5 files (136→128 violations)
- Commits: build_context, search, get_user_mem0 (mem0_store.py), resolve_daily_pillar_range, get_pillar_from_string (daily_pillar.py), _gather_transits (oracle_gatherer.py), request (rag.py), _get_day_master_score (module12_compatibility.py)
- **Remaining**: 128 violations across ~50 files
