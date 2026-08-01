# 🧹 Codebase Hygiene: Summary & Next Steps

**Date generated:** 2026-07-07T22:19:03+08:00
**Total files scanned:** `118` in `src2/`
**Total active anomalies/violations detected:** `252`

## ⚠️ Concentration Risk Analysis
The following files contain the highest density of active issues. Cleaning these files first yields the highest impact.

| File Path | Violations Count | High Severity Count | Category Breakdown |
| --- | --- | --- | --- |
| [`src2/interfaces/telegram/db.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/db.py) | `36` | `6` | Dead Code (30), Environment Drift (6) |
| [`.env.example`](file:////home/yapilwsl/arthityap/baziforecaster/.env.example) | `21` | `0` | Environment Drift (21) |
| [`src2/engine/contradiction_resolver.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/contradiction_resolver.py) | `14` | `0` | Dead Code (10), Schema Hazard (4) |
| [`src2/core/services/storage.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/services/storage.py) | `9` | `4` | Dead Code (4), Environment Drift (5) |
| [`src2/interfaces/telegram/app.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/app.py) | `8` | `5` | Async Hazard (1), Environment Drift (7) |
| [`src2/engine/pydantic_prompt_engine.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/pydantic_prompt_engine.py) | `8` | `3` | Async Hazard (4), Schema Hazard (4) |
| [`src2/core/memory/mem0_store.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/memory/mem0_store.py) | `8` | `2` | Dead Code (6), Environment Drift (2) |
| [`src2/engine/module0_geju.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/module0_geju.py) | `8` | `1` | Dead Code (1), Schema Hazard (7) |
| [`src2/interfaces/telegram/chronomancer/coordinator.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/chronomancer/coordinator.py) | `8` | `1` | Async Hazard (1), Dead Code (6), Silent Killer (1) |
| [`src2/engine/module6_ten_gods.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/module6_ten_gods.py) | `7` | `6` | Dead Code (1), Schema Hazard (6) |
| [`src2/engine/monthly_generator.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/monthly_generator.py) | `7` | `5` | Code Duplication (2), Dead Code (1), Environment Drift (3), Silent Killer (1) |
| [`src2/interfaces/telegram/preflight.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/preflight.py) | `7` | `5` | Async Hazard (1), Dead Code (1), Environment Drift (5) |
| [`src2/interfaces/telegram/chronomancer/agents.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/chronomancer/agents.py) | `7` | `3` | Async Hazard (2), Code Duplication (2), Dead Code (2), Silent Killer (1) |
| [`src2/worker/celery_app.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/worker/celery_app.py) | `6` | `6` | Environment Drift (6) |
| [`src2/engine/prompt_engine.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/prompt_engine.py) | `6` | `5` | Async Hazard (4), Dead Code (1), Environment Drift (1) |
| [`src2/core/rotator.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/rotator.py) | `5` | `3` | Dead Code (2), Environment Drift (3) |
| [`src2/engine/openrouter.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/openrouter.py) | `5` | `1` | Dead Code (4), Schema Hazard (1) |
| [`src2/core/schemas/engine.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/schemas/engine.py) | `5` | `0` | Dead Code (5) |
| [`src2/engine/narrative_simplifier.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/narrative_simplifier.py) | `4` | `2` | Async Hazard (2), Dead Code (1), Environment Drift (1) |
| [`src2/engine/providers/openai.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/providers/openai.py) | `4` | `2` | Dead Code (2), Schema Hazard (2) |
| [`src2/core/platforms/telegram.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/platforms/telegram.py) | `4` | `1` | Async Hazard (1), Dead Code (3) |
| [`src2/engine/module3_interaction.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/module3_interaction.py) | `4` | `0` | Schema Hazard (4) |
| [`src2/interfaces/telegram/schemas.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/schemas.py) | `4` | `0` | Dead Code (4) |
| [`src2/interfaces/telegram/utils.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/utils.py) | `3` | `3` | Environment Drift (3) |
| [`src2/engine/module2_root.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/module2_root.py) | `3` | `2` | Dead Code (1), Schema Hazard (2) |
| [`src2/interfaces/telegram/reliability.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/reliability.py) | `3` | `2` | Dead Code (1), Environment Drift (2) |
| [`src2/engine/providers/gemini.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/providers/gemini.py) | `3` | `1` | Dead Code (2), Schema Hazard (1) |
| [`src2/core/memory/memory_manager.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/memory/memory_manager.py) | `3` | `0` | Dead Code (3) |
| [`src2/core/valkey.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/valkey.py) | `2` | `2` | Environment Drift (2) |
| [`src2/interfaces/telegram/report_utils.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/report_utils.py) | `2` | `2` | Async Hazard (2) |
| [`src2/core/services/intake.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/services/intake.py) | `2` | `1` | Async Hazard (1), Dead Code (1) |
| [`src2/engine/module12_compatibility.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/module12_compatibility.py) | `2` | `1` | Code Duplication (1), Dead Code (1) |
| [`src2/core/calendar/populate_calendar.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/calendar/populate_calendar.py) | `2` | `0` | Code Duplication (1), Dead Code (1) |
| [`src2/core/tools/user_profile_input.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/tools/user_profile_input.py) | `2` | `0` | Dead Code (2) |
| [`src2/engine/daily_pillar.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/daily_pillar.py) | `2` | `0` | Code Duplication (1), Dead Code (1) |
| [`src2/interfaces/telegram/chronomancer/rag.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/chronomancer/rag.py) | `2` | `0` | Dead Code (2) |
| [`src2/interfaces/telegram/chronomancer/ranking.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/chronomancer/ranking.py) | `2` | `0` | Dead Code (2) |
| [`src2/interfaces/telegram/evaluation.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/evaluation.py) | `2` | `0` | Dead Code (2) |
| [`src2/engine/rag_client.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/rag_client.py) | `1` | `1` | Environment Drift (1) |
| [`src2/engine/session.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/session.py) | `1` | `1` | Schema Hazard (1) |
| [`src2/engine/solar_calendar.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/solar_calendar.py) | `1` | `1` | Schema Hazard (1) |
| [`src2/interfaces/telegram/bgem3_bridge.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/bgem3_bridge.py) | `1` | `1` | Environment Drift (1) |
| [`src2/interfaces/telegram/validators.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/validators.py) | `1` | `1` | Silent Killer (1) |
| [`src2/core/identity/service.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/identity/service.py) | `1` | `0` | Dead Code (1) |
| [`src2/core/platforms/base.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/platforms/base.py) | `1` | `0` | Dead Code (1) |
| [`src2/core/tools/bd_config.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/tools/bd_config.py) | `1` | `0` | Dead Code (1) |
| [`src2/core/tools/formatter.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/core/tools/formatter.py) | `1` | `0` | Dead Code (1) |
| [`src2/engine/bazi_calculator.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/bazi_calculator.py) | `1` | `0` | Dead Code (1) |
| [`src2/engine/context_template.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/context_template.py) | `1` | `0` | Dead Code (1) |
| [`src2/engine/module11_probability.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/module11_probability.py) | `1` | `0` | Schema Hazard (1) |
| [`src2/engine/module13_spectrum.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/module13_spectrum.py) | `1` | `0` | Schema Hazard (1) |
| [`src2/engine/module1_macro.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/module1_macro.py) | `1` | `0` | Schema Hazard (1) |
| [`src2/engine/narrative_review.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/narrative_review.py) | `1` | `0` | Dead Code (1) |
| [`src2/engine/orchestrator.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/orchestrator.py) | `1` | `0` | Schema Hazard (1) |
| [`src2/engine/prompt_maker.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/engine/prompt_maker.py) | `1` | `0` | Schema Hazard (1) |
| [`src2/interfaces/telegram/intake/intake.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/intake/intake.py) | `1` | `0` | Dead Code (1) |
| [`src2/interfaces/telegram/logging_utils.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/logging_utils.py) | `1` | `0` | Environment Drift (1) |
| [`src2/interfaces/telegram/metrics.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/metrics.py) | `1` | `0` | Dead Code (1) |
| [`src2/interfaces/telegram/queue_worker.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/queue_worker.py) | `1` | `0` | Dead Code (1) |
| [`src2/interfaces/telegram/tailoring.py`](file:////home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/tailoring.py) | `1` | `0` | Dead Code (1) |

---

## 📂 Detailed Actions Required by File

### 📄 `src2/interfaces/telegram/db.py`
Total issues: **36**

#### [Environment Drift] Line 36: `DATABASE_URL`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable DATABASE_URL is used to configure the database connection, and while it has a fallback to an in-memory SQLite database, it is a critical configuration parameter that should be documented in .env.example for deployment and production environments.
- **Last Updated**: `2026-07-07T22:10:48.284647+08:00`

#### [Environment Drift] Line 124: `ADMIN_ID`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable ADMIN_ID (and TELEGRAM_ADMIN_ID) is used to identify administrative users for test runs and ID generation logic, which is a critical configuration for the application's logic. Its absence from .env.example makes it undocumented.
- **Last Updated**: `2026-07-07T22:10:12.823623+08:00`

#### [Environment Drift] Line 155: `BOT_DB_PATH`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable BOT_DB_PATH is used to configure the database path for the Telegram bot, but it is missing from the .env.example file. This is a critical configuration for persistence in production/staging environments.
- **Last Updated**: `2026-07-07T22:11:05.252982+08:00`

#### [Environment Drift] Line 292: `ADMIN_ID`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable ADMIN_ID (and TELEGRAM_ADMIN_ID) is used to determine administrative privileges in the code, but is missing from the .env.example file. This is a critical configuration for access control.
- **Last Updated**: `2026-07-07T22:10:21.603987+08:00`

#### [Environment Drift] Line 327: `ADMIN_ID`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable ADMIN_ID is used as a fallback for TELEGRAM_ADMIN_ID to determine administrative privileges. Since it is not documented in .env.example, new developers or deployment environments will lack the necessary configuration to grant admin access, which is a critical functional requirement.
- **Last Updated**: `2026-07-07T22:10:30.916000+08:00`

#### [Environment Drift] Line 1083: `DATABASE_URL`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable DATABASE_URL is used to initialize the database engine and session factory. If missing from .env.example, it is a critical configuration required for the application's database connectivity, representing a true drift violation.
- **Last Updated**: `2026-07-07T22:10:56.654026+08:00`

#### [Dead Code] Line 98: `generate_and_link_semantic_id`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is explicitly mentioned in the manual (CHAPTER_04_COMBINATION.md), indicating it is part of the core logic intended for the system but not currently integrated into the active execution path.

#### [Dead Code] Line 144: `get_semantic_id`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a method of a database handler class that does not appear to be called dynamically via reflection or as an API entry point.

#### [Dead Code] Line 256: `get_user_tier`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function performs a standard database query for user tiers which is not typically called dynamically via reflection or as a webhook entry point.

#### [Dead Code] Line 265: `set_user_tier`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function performs a specific database update for user tiers which is not typically called dynamically via generic handlers.

#### [Dead Code] Line 362: `set_monthly_code`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: No static references found in the codebase, but it is explicitly referenced in the manual documentation (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is part of the intended core logic but currently disconnected from the active execution path.

#### [Dead Code] Line 394: `set_feature_code`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the codebase but is mentioned in the manual documentation (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is disconnected core logic.

#### [Dead Code] Line 466: `delete_session`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function performs a standard database operation (deleting a session) that is not typically called dynamically via generic frameworks or as a webhook entry point.

#### [Dead Code] Line 522: `get_active_jobs`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the codebase but is mentioned in the manual documentation (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is disconnected core logic.

#### [Dead Code] Line 554: `get_global_job_count_today`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is mentioned in the manual (CHAPTER_10_SPECIAL_STRUCTURES.md), indicating it is disconnected core logic.

#### [Dead Code] Line 583: `fail_job`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function performs a simple database update that is not typically called dynamically via generic frameworks or as an entry point.

#### [Dead Code] Line 604: `mark_job_pending`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function's logic (marking a job as pending with a retry count) is a standard database operation that is unlikely to be called dynamically via reflection or as an external entry point.

#### [Dead Code] Line 626: `clear_user_jobs`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISKCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is mentioned in the manual documentation (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is disconnected core logic.

#### [Dead Code] Line 640: `get_reports_for_alias`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a helper method within a database interface class that does not appear to be called dynamically.

#### [Dead Code] Line 663: `get_all_reports_for_user`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a helper method within a database interface class that does not appear to be called dynamically or used as an entry point.

#### [Dead Code] Line 684: `add_report_metadata`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function's logic (adding report metadata to a database) is a standard database operation that is unlikely to be called dynamically via generic reflection or as a webhook entry point.

#### [Dead Code] Line 714: `log_chat`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function's purpose (logging chat messages to a database) is a typical utility function that would be called explicitly by a bot's message handler. There is no evidence of dynamic dispatch or entry-point usage.

#### [Dead Code] Line 727: `upsert_stakeholder`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a database operation method within a class, which is typically not called dynamically via entry points or webhooks.

#### [Dead Code] Line 783: `get_stakeholder_aliases`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function performs a simple data retrieval operation that is not typically called dynamically via generic frameworks or entry points.

#### [Dead Code] Line 787: `get_stakeholder_count`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the codebase but is mentioned in the manual (CHAPTER_10_SPECIAL_STRUCTURES.md), indicating it is disconnected core logic.

#### [Dead Code] Line 795: `delete_stakeholder`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function performs a standard database deletion operation without any dynamic dispatch patterns that would suggest it is used as a callback or entry point.

#### [Dead Code] Line 813: `save_daily_forecast`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is mentioned in the manual documentation (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is part of the core logic intended for a specific feature set described in the manual.

#### [Dead Code] Line 862: `get_daily_forecast`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the codebase but is mentioned in the manual documentation (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is disconnected core logic.

#### [Dead Code] Line 884: `get_daily_forecast_range`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISKCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is mentioned in the manual (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is disconnected core logic.

#### [Dead Code] Line 929: `delete_daily_forecast_for_user_date`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is mentioned in the manual documentation (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is disconnected core logic.

#### [Dead Code] Line 944: `delete_user_prefs`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function performs a standard database deletion of user preferences which is not typically called dynamically.

#### [Dead Code] Line 956: `delete_reports_for_user`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The function is not referenced anywhere in the codebase, and its functionality is entirely superseded by `delete_all_user_data` which performs the same deletion of reports (and other user data) in a more comprehensive manner.

#### [Dead Code] Line 969: `delete_all_user_data`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function's purpose (deleting all user data for GDPR/privacy compliance) is not typically called via dynamic dispatch or as a webhook entry point.

#### [Dead Code] Line 997: `get_user_prefs`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a helper method within a database interface class that does not appear to be called dynamically or used as an entry point.

#### [Dead Code] Line 1024: `set_user_prefs`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function's logic (updating user preferences like push notifications and sifu_mode) does not suggest it is a called dynamically via a common pattern or an entry point.

#### [Dead Code] Line 1054: `get_users_with_push_enabled`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function's logic (fetching users with push notifications enabled for Telegram) is a specific utility function that is not called dynamically via reflection or as an entry point.

---

### 📄 `.env.example`
Total issues: **21**

#### [Environment Drift] Line 1: `OPENROUTER_PIPELINE_MODEL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable OPENROUTER_PIPELINE_MODEL is present in .env.example but not referenced anywhere in the codebase, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:12.254503+08:00`

#### [Environment Drift] Line 1: `OPENROUTER_SUMMARIZER_MODEL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable is defined in .env.example but not referenced anywhere in the provided code context or codebase, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:12.254557+08:00`

#### [Environment Drift] Line 1: `SSL_KEY_PATH`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable SSL_KEY_PATH is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:12.254569+08:00`

#### [Environment Drift] Line 1: `AGENT_WEBHOOK_URL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable AGENT_WEBHOOK_URL is defined in .env.example but is not referenced anywhere in the provided code context. Since it is unused in the codebase, it should be removed from the example file to prevent confusion.
- **Last Updated**: `2026-07-07T22:15:12.254578+08:00`

#### [Environment Drift] Line 1: `OPENROUTER_PIPELINE_CACHE`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable OPENROUTER_PIPELINE_CACHE is defined in .env.example but is not referenced anywhere in the codebase. This is an unused example variable, which can lead to confusion for developers and clutter the environment configuration.
- **Last Updated**: `2026-07-07T22:15:12.254586+08:00`

#### [Environment Drift] Line 1: `RAG_MODEL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable RAG_MODEL is defined in .env.example but is not referenced anywhere in the codebase. This represents undocumented or unused configuration, which creates confusion for new developers and maintenance overhead.
- **Last Updated**: `2026-07-07T22:15:12.254594+08:00`

#### [Environment Drift] Line 1: `TELEGRAM_WEBHOOK_URL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable is present in .env.example but not used anywhere in the code, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:12.254601+08:00`

#### [Environment Drift] Line 1: `SSL_CERT_PATH`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable SSL_CERT_PATH is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:12.254608+08:00`

#### [Environment Drift] Line 1: `OPENROUTER_SUMMARIZER_CACHE`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:20.311116+08:00`

#### [Environment Drift] Line 1: `OLLAMA_API_URL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable OLLAMA_API_URL is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:20.311823+08:00`

#### [Environment Drift] Line 1: `EMBEDDING_MODEL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable EMBEDDING_MODEL is present in .env.example but is not referenced anywhere in the codebase. This constitutes an unused example variable, which leads to confusion for new developers and configuration drift.
- **Last Updated**: `2026-07-07T22:15:20.311849+08:00`

#### [Environment Drift] Line 1: `MCPMART_BASE_URL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable MCPMART_BASE_URL is defined in .env.example but is not used anywhere in the codebase, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:20.311857+08:00`

#### [Environment Drift] Line 1: `NARRATIVE_MODEL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable NARRATIVE_MODEL is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:28.248334+08:00`

#### [Environment Drift] Line 1: `INTAKE_MODEL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable INTAKE_MODEL is present in the .env.example file but is not referenced anywhere in the codebase, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:28.249282+08:00`

#### [Environment Drift] Line 1: `WELCOME_MODEL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable WELCOME_MODEL is present in .env.example but not referenced in the code, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:28.249316+08:00`

#### [Environment Drift] Line 1: `MCPMART_API_KEY`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable MCPMART_API_KEY is defined in .env.example but is not referenced anywhere in the provided code context, indicating it is an unused example variable that should be removed.
- **Last Updated**: `2026-07-07T22:15:28.249328+08:00`

#### [Environment Drift] Line 1: `NONSIFU_MODEL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable NONSIFU_MODEL is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:28.249336+08:00`

#### [Environment Drift] Line 1: `SUMMARIZER_MODEL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable SUMMARIZER_MODEL is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:36.359996+08:00`

#### [Environment Drift] Line 1: `PIPELINE_MODEL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable 'PIPELINE_MODEL' is present in .env.example but is not referenced anywhere in the codebase. This constitutes an unused example variable, which leads to configuration drift.
- **Last Updated**: `2026-07-07T22:15:36.360771+08:00`

#### [Environment Drift] Line 1: `OPENROUTER_INTAKE_MODEL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable is present in .env.example but not referenced in any provided code context, and since it's a specific integration variable (OpenRouter), it is likely unused or obsolete.
- **Last Updated**: `2026-07-07T22:15:36.360800+08:00`

#### [Environment Drift] Line 1: `MEMORY_MODEL`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable MEMORY_MODEL is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.
- **Last Updated**: `2026-07-07T22:15:44.486012+08:00`

---

### 📄 `src2/engine/contradiction_resolver.py`
Total issues: **14**

#### [Dead Code] Line 29: `ContradictionHierarchy`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The class is an IntEnum defining priority levels for contradiction resolution. It has no static references in the other files of the codebase, and given its nature as a a configuration-style enum, it is unlikely to be called dynamically.

#### [Dead Code] Line 41: `_safe_get_pillar_attr`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is a private helper utility used for safe attribute access on pillar objects. It has no static references in thep codebase, and is mentioned in the manual, suggesting it is disconnected core logic.

#### [Dead Code] Line 84: `apply_specificity_rule`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is explicitly mentioned in the manual (CHAPTER_10_SPECIAL_STRUCTURES.md), indicating it is part of the core logic intended for the system's theoretical framework but not yet integrated into the active execution pipeline.

#### [Dead Code] Line 172: `calculate_combo_clash_net`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is explicitly mentioned in the manual (CHAPTER_10_SPECIAL_STRUCTURES.md), indicating it is part of the core logic intended for the engine but not yet integrated into the active execution pipeline.

#### [Dead Code] Line 238: `resolve_dm_strength_paradox`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the codebase but is explicitly mentioned in the manual (CHAPTER_11_SYNTHESIS.md), indicating it is part of the core logic intended for the system's synthesis phase but not yet integrated into the active execution pipeline.

#### [Dead Code] Line 293: `resolve_wealth_vs_control`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the rest of the codebase, but is explicitly mentioned in the manual (CHAPTER_11_SYNTHESIS.md), indicating it implements a specific protocol described in the documentation.

#### [Dead Code] Line 353: `resolve_resource_vs_output`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is explicitly mentioned in the manual (CHAPTER_11_SYNTHESIS.md), indicating it is part of the core theoretical framework but not currently integrated into the active execution pipeline.

#### [Dead Code] Line 394: `resolve_combination_override`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is explicitly mentioned in the manual (CHAPTER_11_SYNTHESIS.md), indicating it is part of the core logic described in the documentation but not currently integrated into the active execution pipeline.

#### [Dead Code] Line 435: `resolve_paradox_four_step`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in any other Python files, but it is explicitly mentioned in the verified manual (CHAPTER_11_SYNTHESIS.md), indicating it implements a specific theoretical framework described in the documentation.

#### [Dead Code] Line 467: `calculate_temporal_weight_enhanced`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the codebase but is explicitly mentioned in the manual (CHAPTER_10_SPECIAL_STRUCTURES.md), indicating it is part of the core logic intended for the system's theoretical framework or future implementation.

#### [Schema Hazard] Line 571: `_match_pattern`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function accepts a 'contradiction' argument typed as a raw 'dict', which is used to access complex nested data (signal_a, signal_b), indicating a lack of Pydantic model validation for a complex input payload.
- **Last Updated**: `2026-07-07T19:40:02.491440+08:00`

#### [Schema Hazard] Line 611: `_determine_dominant_theme`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses a list of raw dictionaries (`list[dict]`) to handle complex data structures (contradictions) instead of a Pydantic model, which is a schema hazard.
- **Last Updated**: `2026-07-07T19:40:07.611448+08:00`

#### [Schema Hazard] Line 632: `_synthesize`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function accepts 'list[dict]' as an input for 'contradictions', which is a complex data structure containing weights, signals, and classifications, but fails to use a Pydantic model for this input.
- **Last Updated**: `2026-07-07T19:40:12.887915+08:00`

#### [Schema Hazard] Line 712: `_get_combo_strength`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses a raw 'dict' as the input type for 'combo', which is a complex data structure representing a combination, instead of a Pydantic model.
- **Last Updated**: `2026-07-07T19:40:23.815450+08:00`

---

### 📄 `src2/core/services/storage.py`
Total issues: **9**

#### [Environment Drift] Line 9: `S3_ENDPOINT`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable S3_ENDPOINT is used to configure the S3 storage backend. While it has a default value for local development (MinIO), it is a critical configuration for connecting to actual S3-compatible storage in staging or production environments. Its absence from .env.example makes it undocumented and would hinder deployment.
- **Last Updated**: `2026-07-07T22:03:15.636924+08:00`

#### [Environment Drift] Line 10: `S3_ACCESS_KEY`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable S3_ACCESS_KEY is used to configure S3 storage access, which is critical for production environments. While it has a default value for local development (minioadmin), it must be documented in .env.example to ensure proper configuration in staging and production.
- **Last Updated**: `2026-07-07T22:03:24.612953+08:00`

#### [Environment Drift] Line 11: `S3_SECRET_KEY`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable S3_SECRET_KEY is used to configure S3 storage credentials. While it has a default value, it is a sensitive secret that must be explicitly defined in .env.example to ensure proper configuration in production and staging environments.
- **Last Updated**: `2026-07-07T22:03:34.084288+08:00`

#### [Environment Drift] Line 12: `S3_BUCKET`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable S3_BUCKET is used to configure the S3 storage bucket name, which is environment-specific. While a default value is provided, it is a critical configuration for storage connectivity in production/staging environments and should be documented in .env.example.
- **Last Updated**: `2026-07-07T22:03:42.804145+08:00`

#### [Environment Drift] Line 13: `AWS_REGION`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable AWS_REGION is used to configure the S3 client, but it is missing from the .env.example file. While it has a default value of 'us-east-1', it is a critical configuration for cloud deployment and should be documented in the example environment file to allow developers to change it for different regions.
- **Last Updated**: `2026-07-07T22:03:51.933318+08:00`

#### [Dead Code] Line 27: `upload_string`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function provides a simple wrapper around S3 put_object for string content. There are no dynamic calls or entry points that would utilize this specific method.

#### [Dead Code] Line 33: `download_string`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function provides a basic utility for reading a string from S3, which is not typically called dynamically in this architecture.

#### [Dead Code] Line 37: `delete_file`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a standard utility method in a storage service class that is not called dynamically or used as an entry point.

#### [Dead Code] Line 40: `file_exists`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: No static references found in the codebase, but it is explicitly referenced in the verified manual chapter CHAPTER_12_MASTER_CASES.md, indicating it is intended core logic that is currently disconnected from the active implementation.

---

### 📄 `src2/interfaces/telegram/app.py`
Total issues: **8**

#### [Async Hazard] Line 167: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The `open` call is used to read a log file from the disk. Since this is inside an async function `get_celery_stats` which is likely part of a Telegram bot interface, it blocks the event loop during I/O operations. This can lead to latency or heartbeat failures in the event loop.
- **Last Updated**: `2026-07-07T22:00:57.323709+08:00`

#### [Environment Drift] Line 328: `PROMO_MONTHLY`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable PROMO_MONTHLY is used to retrieve a promo code for report unlocking, which is a business-logic specific configuration. Since it is missing from the .env.example file, it is a true environment drift violation.
- **Last Updated**: `2026-07-07T22:09:29.787691+08:00`

#### [Environment Drift] Line 527: `PROMO_MONTHLY`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable PROMO_MONTHLY is used to define a promo code for monthly reports, which is a business-logic specific configuration. Since it is missing from .env.example, it is a required configuration for this feature to function as intended.
- **Last Updated**: `2026-07-07T22:09:38.703779+08:00`

#### [Environment Drift] Line 903: `PROMO_MONTHLY`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable PROMO_MONTHLY is used to handle promo code logic for report generation, which is a business-specific configuration. Since it is missing from .env.example, it is a true drift violation.
- **Last Updated**: `2026-07-07T22:09:47.228393+08:00`

#### [Environment Drift] Line 1171: `ADMIN_ID`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable ADMIN_ID is used to control access to a debug endpoint and is not documented in .env.example. Its absence would prevent administrators from accessing the debug functionality.
- **Last Updated**: `2026-07-07T22:10:04.220862+08:00`

#### [Environment Drift] Line 198: `VALKEY_HOST`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable VALKEY_HOST is used to configure the Redis/Valkey backend host. While it has a default value of '127.0.0.1', it is a custom application-specific configuration for infrastructure connectivity that should be documented in .env.example to ensure consistent deployment across different environments.
- **Last Updated**: `2026-07-07T22:04:09.059901+08:00`

#### [Environment Drift] Line 199: `VALKEY_PORT`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable VALKEY_PORT is used to configure the Redis/Valkey backend connection. While it has a default value of 6379, it is a service-specific configuration that should be documented in .env.example to allow deployment in different environments (e.g., Docker, Kubernetes) where the port might differ.
- **Last Updated**: `2026-07-07T22:04:35.781830+08:00`

#### [Environment Drift] Line 528: `PROMO_FEATURE`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable PROMO_FEATURE is used to control a promotional feature toggle/code in the application logic, but it is missing from the .env.example file. This is a custom application-specific configuration that should be documented.
- **Last Updated**: `2026-07-07T22:09:55.974520+08:00`

---

### 📄 `src2/engine/pydantic_prompt_engine.py`
Total issues: **8**

#### [Async Hazard] Line 413: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The synchronous `open` and `json.load` calls are performed directly within the async function `run_pydantic_engine`, blocking the event loop during I/O operations.
- **Last Updated**: `2026-07-07T22:00:13.718895+08:00`

#### [Async Hazard] Line 737: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The synchronous `open` and `yaml.dump` calls are performed inside an async function `process_month` on a path that appears to be part of a regular processing loop. This blocks the event loop during I/O operations, which is a hazard in high-concurrency async applications.
- **Last Updated**: `2026-07-07T22:00:22.604772+08:00`

#### [Async Hazard] Line 785: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The synchronous 'open' and 'json.dump' calls are performed within an async function 'run_pydantic_engine', blocking the event loop during I/O operations. This is a hazard on active paths.
- **Last Updated**: `2026-07-07T22:00:48.578073+08:00`

#### [Schema Hazard] Line 40: `load_prompt_template`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function returns a raw dictionary from a YAML file, which is a complex data structure. In a Pydantic-driven engine, this should be validated against a schema model to ensure the prompt template structure is correct.
- **Last Updated**: `2026-07-07T20:14:19.769074+08:00`

#### [Schema Hazard] Line 49: `get_active_clashes`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses 'Any' for the input parameter 'm3', which is then accessed as an object with an 'active_disruptors' attribute. This indicates a lack of a Pydantic model or a specific type hint for a complex object, representing a schema hazard.
- **Last Updated**: `2026-07-07T20:14:25.566031+08:00`

#### [Schema Hazard] Line 78: `get_active_combinations`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses 'Any' for the input parameter 'm3', which is then accessed as an object with an 'active_alliances' attribute. This indicates a lack of a Pydantic model or a specific type hint for a complex object, representing a schema hazard.
- **Last Updated**: `2026-07-07T20:14:31.108874+08:00`

#### [Schema Hazard] Line 554: `format_user_prompt`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function takes a raw 'dict' as 'template_dict' for a structured prompt template, which should be ideally represented by a Pydantic model to ensure the structure of the template is validated.
- **Last Updated**: `2026-07-07T20:19:47.222653+08:00`

#### [Async Hazard] Line 756: `open`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The synchronous 'open' call is located within an exception handler in an async function. While it blocks the event loop, it is only executed during an error state, which is not a hot path. Therefore, it is a low-severity hazard.
- **Last Updated**: `2026-07-07T22:00:40.214067+08:00`

---

### 📄 `src2/core/memory/mem0_store.py`
Total issues: **8**

#### [Environment Drift] Line 379: `OPENAI_API_KEY`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The code explicitly sets the environment variable OPENAI_API_KEY based on a provided key, which is a critical configuration for OpenAI services. If this is missing from .env.example, it is a true drift violation as it's required for the system's memory store functionality.
- **Last Updated**: `2026-07-07T22:02:32.252681+08:00`

#### [Environment Drift] Line 381: `OPENAI_BASE_URL`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable OPENAI_BASE_URL is explicitly set in the environment via os.environ, indicating it is a required configuration for the OpenAI API base URL. Its absence from .env.example makes it an undocumented configuration variable.
- **Last Updated**: `2026-07-07T22:02:40.998363+08:00`

#### [Dead Code] Line 139: `generate_response`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the rest of the codebase, but it is explicitly mentioned in the manual (CHAPTER_04_COMBINATION.md), indicating it is part of the intended core logic but not currently integrated into the active execution pipeline.
- **Last Updated**: `2026-07-07T21:01:44.012755+08:00`

#### [Dead Code] Line 415: `add_episodic`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a helper method within a class that provides a specific memory type wrapper around a generic 'add_memory' method. It does not appear to be part of any dynamic dispatch or public API entry point.
- **Last Updated**: `2026-07-07T21:01:44.012769+08:00`

#### [Dead Code] Line 418: `add_semantic`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a helper method within a Mem0Store class that doesn't appear to be called dynamically or as an entry point.
- **Last Updated**: `2026-07-07T21:01:44.012775+08:00`

#### [Dead Code] Line 421: `add_feedback`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a helper method within a Mem0Store class that doesn't appear to be called dynamically or as an API entry point.
- **Last Updated**: `2026-07-07T21:01:44.012781+08:00`

#### [Dead Code] Line 459: `delete_user_memories`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function performs a specific administrative action (deleting user memories) that is not called by any other part of the system. It is not used as a dynamic entry point or webhook.
- **Last Updated**: `2026-07-07T21:01:44.012787+08:00`

#### [Dead Code] Line 464: `build_context`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is explicitly mentioned in the manual (CHAPTER_12_MASTER_CASES.md), indicating it is part of the core logic intended for use or documented as a feature, but not currently integrated into the active execution pipeline.
- **Last Updated**: `2026-07-07T21:01:44.012794+08:00`

---

### 📄 `src2/engine/module0_geju.py`
Total issues: **8**

#### [Schema Hazard] Line 334: `classify_ge_ju`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses Pydantic models for the primary input (ChartProfile) and output (GeJuClassificationResult), but it accepts raw dictionaries for 'root_results' and 'transformed_branches'. Since these are complex data payloads used for calculation logic, they should be defined as Pydantic models to ensure type safety and validation.
- **Last Updated**: `2026-07-07T19:46:21.295835+08:00`

#### [Schema Hazard] Line 32: `_has_meaningful_root`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses a raw 'dict | None' for 'transformed_branches', which is a complex data structure representing branch transformations. This should be represented by a Pydantic model or a more specific type for consistency and validation.
- **Last Updated**: `2026-07-07T19:45:46.905637+08:00`

#### [Schema Hazard] Line 63: `_count_ten_god_category`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses a raw 'dict | None' for 'transformed_branches', which is a complex data structure representing branch transformations. This should be ideally represented by a Pydantic model or a specific type alias for better validation and validation.
- **Last Updated**: `2026-07-07T19:45:52.656627+08:00`

#### [Schema Hazard] Line 111: `_calculate_dominance_pct`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses a raw dict for 'transformed_branches' input and returns a tuple containing a raw dict. For a core calculation logic involving element distribution, this should be represented by a Pydantic model to ensure type safety and validation of the element keys.
- **Last Updated**: `2026-07-07T19:45:58.408940+08:00`

#### [Schema Hazard] Line 169: `_check_counter_elements`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses a raw 'dict | None' for 'transformed_branches', which is a complex data structure mapping branches to elements. This should be part of a Pydantic model or a more specific type.
- **Last Updated**: `2026-07-07T19:46:03.820755+08:00`

#### [Schema Hazard] Line 234: `_check_vibrant_structure`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses a raw 'dict | None' for 'transformed_branches', which is a complex data structure representing branch transformations. This should be ideally represented by a Pydantic model or a specific type alias for better validation and schema enforcement.
- **Last Updated**: `2026-07-07T19:46:15.208376+08:00`

#### [Schema Hazard] Line 699: `compute_ge_ju_alignment_mod`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses a raw `dict[str, Any]` for the `strength_profile` parameter, which is a complex data structure containing critical scoring information (like 'spectrum_tier'), instead of a Pydantic model.
- **Last Updated**: `2026-07-07T19:46:27.130680+08:00`

#### [Dead Code] Line 818: `run_module0_geju`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function serves as a pipeline wrapper for Module 0. Given the lack of any call sites or dynamic dispatch mechanisms in the engine's main execution flow, it is confirmed dead.

---

### 📄 `src2/interfaces/telegram/chronomancer/coordinator.py`
Total issues: **8**

#### [Silent Killer] Line 51: `NotImplementedError`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SILENT_KILLER`
- **Reasoning**: The code catches a NotImplementedError from get_solar_months and falls back to a hardcoded year (2026). This is a silent failure that masks a missing implementation for the specific target year, potentially providing incorrect astronomical/calendar data for the user without warning.

#### [Dead Code] Line 211: `handle_daily`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: No static references found in the codebase, but it is explicitly referenced in the manual (CHAPTER_11_SYNTHESIS.md), indicating it is part of the core logic intended for the user interface but not currently wired up to a command handler.

#### [Dead Code] Line 316: `handle_forecast`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: No static references found in the codebase, but it is explicitly mentioned in the manual (CHAPTER_11_SYNTHESIS.md), indicating it is intended core logic that is currently disconnected from the active Telegram bot pipeline.

#### [Dead Code] Line 330: `handle_forecast_category`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is mentioned in the documentation (CHAPTER_11_SYNTHESIS.md), indicating it is disconnected core logic.

#### [Dead Code] Line 374: `handle_forecast_menu`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not statically referenced in the codebase, but it is explicitly mentioned in the verified manual (CHAPTER_11_SYNTHESIS.md), indicating it is part of the intended core logic but currently disconnected from the active implementation.

#### [Dead Code] Line 388: `handle_ask`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not statically referenced in the codebase, but it is explicitly mentioned in the manual (CHAPTER_11_SYNTHESIS.md), indicating it is part of the core logic intended for the user interface but currently disconnected from the active execution path.

#### [Dead Code] Line 522: `prebuild_annual_calendar`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: No static references found in the codebase, but it is referenced in the manual documentation (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is disconnected core logic.

#### [Async Hazard] Line 576: `open`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The `open` call is used to read a JSON file from disk. Since this is inside an async function `_get_monthly_context` and is not offloaded to a thread pool, it blocks the event loop. While the file size is likely small, any disk I/O in an async path is a potential hazard.
- **Last Updated**: `2026-07-07T22:01:25.103667+08:00`

---

### 📄 `src2/engine/module6_ten_gods.py`
Total issues: **7**

#### [Schema Hazard] Line 119: `calculate_ten_gods`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function accepts raw dicts for natal_stems and hidden_stems, and in its legacy mode (when input_data is a string), it returns a raw dictionary instead of a Pydantic model. This creates a dual-path API where one path is schema-less, bypassing validation.
- **Last Updated**: `2026-07-07T20:01:58.152282+08:00`

#### [Schema Hazard] Line 307: `calculate_ten_god_dominance`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function accepts a raw 'dict' as 'ten_gods_profile' instead of a Pydantic model, which is a complex data structure representing the chart's Ten Gods profile.
- **Last Updated**: `2026-07-07T20:02:15.503640+08:00`

#### [Schema Hazard] Line 533: `get_day_hour_ten_god_emphasis`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function accepts a raw 'dict' as input ('ten_gods_profile') instead of a Pydantic model, despite returning a structured Pydantic model ('DayHourTenGodEmphasis'). This creates a schema hazard for complex data payloads.
- **Last Updated**: `2025-01-24T10:00:00Z`

#### [Schema Hazard] Line 599: `detect_powerful_ten_god_combos`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function accepts a raw 'dict' as input for 'ten_gods_profile' instead of a Pydantic model, which is a schema hazard for complex data structures.
- **Last Updated**: `2025-01-24T10:30:00Z`

#### [Schema Hazard] Line 624: `detect_ten_god_absence`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function accepts a raw 'dict' as input (ten_gods_profile) for a complex data structure, instead of using a Pydantic model for validation.
- **Last Updated**: `2025-01-24T12:00:00Z`

#### [Schema Hazard] Line 661: `calculate_ten_gods_deep`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses raw dicts for complex inputs (chart_stems, chart_branches) and as the return type, instead of Pydantic models for structured data validation.
- **Last Updated**: `2026-07-07T20:04:40.770392+08:00`

#### [Dead Code] Line 307: `calculate_ten_god_dominance`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the codebase but is explicitly mentioned in the manual (CHAPTER_10_SPECIAL_STRUCTURES.md), indicating it is part of the core logic intended for the engine but not yet integrated into the active pipeline.

---

### 📄 `src2/engine/monthly_generator.py`
Total issues: **7**

#### [Environment Drift] Line 24: `CHRONO_URL`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable CHRONO_URL is used to configure the base URL and API key for the OpenAIProvider, which is critical for the engine's functionality. Its absence from .env.example makes it a true drift violation.
- **Last Updated**: `2026-07-07T22:04:54.054169+08:00`

#### [Environment Drift] Line 25: `CHRONO_URL`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable CHRONO_URL is used to configure the base URL and API key for the OpenAIProvider, which is critical for the engine's functionality. Its absence from .env.example makes it unable to be deployed or configured correctly in new environments.
- **Last Updated**: `2026-07-07T22:05:11.957972+08:00`

#### [Environment Drift] Line 26: `CHRONO_URL`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable CHRONO_URL is used to configure the critical API endpoint and authentication key for the OpenAIProvider, and it is missing from the .env.example file. This is a true drift violation as it is a required configuration for the engine to function.
- **Last Updated**: `2026-07-07T22:05:03.299998+08:00`

#### [Silent Killer] Line 74: `Exception`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SILENT_KILLER`
- **Reasoning**: The code catches all exceptions during the LLM keyword generation step and silently falls back to empty keyword sets. This prevents the LLM failure from crashing the application, but it results in 'all_queries' being empty, which silently skips the entire RAG (Retrieval Augmented Generation) process without any logging or warning. This is a dangerous silent failure because the quality of the final output will be significantly degraded without the user or developer knowing why the LLM failed.

#### [Code Duplication] Line 186: `calculate_end_date_logic`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DUPLICATION`
- **Reasoning**: The code block contains specific business logic for calculating the end date of a month, including a fallback for 2027 solar months and a hardcoded 29-day offset. This logic is repeated across two different engine files and should be refactored into a shared utility.
- **Last Updated**: `2026-07-07T22:18:43.508448+08:00`

#### [Dead Code] Line 50: `generate_12_months_concurrently`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the active codebase but is explicitly mentioned in the manual (CHAPTER_04_COMBINATION.md), indicating it is part of the core logic intended for the system's functionality but currently disconnected from the active execution path.

#### [Code Duplication] Line 113: `RAG context concatenation logic`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DUPLICATION`
- **Reasoning**: The code implements a specific business logic for filtering and joining RAG context strings based on a sentinel value ('No specific references found.'). This logic is repeated across two different engine files and should be refactored into a shared utility function.
- **Last Updated**: `2026-07-07T22:18:34.801645+08:00`

---

### 📄 `src2/interfaces/telegram/preflight.py`
Total issues: **7**

#### [Environment Drift] Line 34: `TELEGRAM_API_BASE`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable TELEGRAM_API_BASE is accessed via os.environ without a default value, meaning the application will crash with a KeyError if it is missing from the environment. Since it is not documented in .env.example, this is a critical drift violation.
- **Last Updated**: `2026-07-07T22:11:31.864448+08:00`

#### [Environment Drift] Line 57: `TELEGRAM_API_BASE`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable TELEGRAM_API_BASE is accessed via os.environ["TELEGRAM_API_BASE"], which will raise a KeyError if missing. Since it is undocumented in .env.example, it is a critical missing configuration required for the Telegram interface to function.
- **Last Updated**: `2026-07-07T22:11:40.781129+08:00`

#### [Environment Drift] Line 111: `CLOUDFLARE_TUNNEL_TOKEN`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable CLOUDFLARE_TUNNEL_TOKEN is used to authenticate and run a Cloudflare Tunnel, and the code explicitly checks for its presence and returns False (failing the preflight check) if it is missing. This is a critical configuration requirement for the tunnel to function.
- **Last Updated**: `2026-07-07T22:14:01.385007+08:00`

#### [Environment Drift] Line 111: `CLOUDFLARE_TOKEN`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable CLOUDFLARE_TOKEN is used as a fallback for CLOUDFLARE_TUNNEL_TOKEN to authenticate the Cloudflare tunnel. Since it is not documented in .env.example, new developers or deployment scripts cannot know which variable to provide, leading to potential deployment failure.
- **Last Updated**: `2026-07-07T22:14:10.600822+08:00`

#### [Environment Drift] Line 277: `TELEGRAM_API_BASE`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable TELEGRAM_API_BASE is accessed via os.environ without a default value, meaning the application will raise a KeyError if it is missing from the environment. Since it is not documented in .env.example, it is a critical missing configuration for the Telegram notification system.
- **Last Updated**: `2026-07-07T22:11:49.597513+08:00`

#### [Async Hazard] Line 124: `subprocess.check_output`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `status: 'ASYNC_HAZARD'`
- **Reasoning**: The call to subprocess.check_output is a synchronous blocking call inside an async function. While this is a preflight check (likely executed during startup), the use of time.sleep(2) on line 120 further exacerbates the blocking of the event loop.
- **Last Updated**: `2026-07-07T22:01:51.574071+08:00`

#### [Dead Code] Line 136: `check_openrouter_api`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is mentioned in the manual (CHAPTER_10_SPECIAL_STRUCTURES.md), indicating it is part of the same project's documentation/core logic but not currently integrated into the active execution path.

---

### 📄 `src2/interfaces/telegram/chronomancer/agents.py`
Total issues: **7**

#### [Silent Killer] Line 116: `NotImplementedError`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SILENT_KILLER`
- **Reasoning**: The code catches a NotImplementedError and falls back to a known working year (2026) to avoid a crash. This is a dangerous silent failure because it returns incorrect calendar data for any year that is not 2026, instead of failing loudly when the solar calendar logic is missing for a specific year.

#### [Code Duplication] Line 119: `find_best_month_logic`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DUPLICATION`
- **Reasoning**: The code implements a specific business logic for finding the latest month entry that is less than or equal to a target date. This logic is repeated across two different files in the the same module, indicating a copy-paste violation that should be refactored into a shared utility function.
- **Last Updated**: `2026-07-07T22:18:52.280694+08:00`

#### [Async Hazard] Line 624: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The synchronous 'open' and 'json.load' calls are performed within an async function 'get_monthly_context' which is likely part of a request-handling path in a Telegram bot. This blocks the event loop during I/O operations, potentially impacting the rest of the bot's responsiveness.
- **Last Updated**: `2026-07-07T22:01:16.186936+08:00`

#### [Dead Code] Line 25: `MonthlyForecastDeps`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The class MonthlyForecastDeps is a Pydantic BaseModel used for dependency injection or structured data passing. No static references were found in the codebase, and there are no dynamic calls or entry points that utilize this schema.

#### [Dead Code] Line 46: `DailyForecastResult`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The class is a Pydantic BaseModel used for structured output from an LLM agent. Such classes are often passed as 'response_format' or 'output_schema' to LLM calls, but since there are no static references to the class name in the codebase, it is not being used to instantiate objects or as a type hint in any active code path.

#### [Code Duplication] Line 142: `Person profile mapping logic`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DUPLICATION`
- **Reasoning**: The code block is a data mapping function that transforms a person object (p) into a dictionary. This logic is repeated across two different files, which is a clear violation of DRY principles and should be refactored into a shared utility or a method on the person model.
- **Last Updated**: `2026-07-07T22:19:00.722119+08:00`

#### [Async Hazard] Line 330: `open`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The `open` call is used to read a small JSON file from disk. While technically synchronous, in the context of a Telegram bot agent, this is a typical pattern for reading configuration or state files. However, since it's inside an async function `get_monthly_context` which is likely called on the hot path of a request handler, it blocks the event loop. Given the typical size of these 'master.json' files and the context of a Telegram bot, this is a low-severity hazard.
- **Last Updated**: `2026-07-07T22:01:07.404435+08:00`

---

### 📄 `src2/worker/celery_app.py`
Total issues: **6**

#### [Environment Drift] Line 10: `VALKEY_HOST`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable VALKEY_HOST is used to construct the connection URL for the Celery broker/backend. While there are fallbacks to VALKEY_URL, REDIS_URL, or localhost, the presence of specific host/port variables suggests they are intended for configuration in production/staging environments. Missing from .env.example makes it undocumented.
- **Last Updated**: `2026-07-07T22:04:18.165717+08:00`

#### [Environment Drift] Line 11: `VALKEY_PORT`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable VALKEY_PORT is used to construct the Valkey/Redis connection URL. While there is a fallback to VALKEY_URL or REDIS_URL, the specific logic on line 12 requires both VALKEY_HOST and VALKEY_PORT to be present to use that specific construction path. Missing this from .env.example prevents new developers from knowing they can configure the host and port separately.
- **Last Updated**: `2026-07-07T22:04:45.455005+08:00`

#### [Environment Drift] Line 15: `VALKEY_URL`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable VALKEY_URL is used as a primary configuration option for the Celery broker and backend, and it lacks a fallback to a standard system default like PORT. While it has a fallback to REDIS_URL, it is a custom application-specific configuration that should be documented in .env.example to ensure consistent deployment across environments.
- **Last Updated**: `2026-07-07T22:14:45.284972+08:00`

#### [Environment Drift] Line 15: `REDIS_URL`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: REDIS_URL is used as a fallback for VALKEY_URL, and both are used to configure the Celery broker/backend. Since neither is documented in the example file, this is a missing configuration variable that would break deployment in a non-local environment.
- **Last Updated**: `2026-07-07T22:14:54.043766+08:00`

#### [Environment Drift] Line 18: `CELERY_BROKER_URL`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable CELERY_BROKER_URL is used to configure the Celery broker, but it is missing from the .env.example file. While there is a fallback to valkey_url, this is a primary configuration point for the rest of the infrastructure.
- **Last Updated**: `2026-07-07T22:15:02.858476+08:00`

#### [Environment Drift] Line 20: `CELERY_RESULT_BACKEND`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable CELERY_RESULT_BACKEND is used to configure the Celery result backend, which is critical for task tracking. While there is a fallback to a derived valkey_url, the ability to override this via environment variables is a standard deployment requirement for production environments. Its absence from .env.example makes it undocumented.
- **Last Updated**: `2026-07-07T22:15:12.253708+08:00`

---

### 📄 `src2/engine/prompt_engine.py`
Total issues: **6**

#### [Async Hazard] Line 52: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The synchronous 'open' and 'json.load' calls are performed directly within the async function 'run_engine', blocking the event loop during I/O operations.
- **Last Updated**: `2026-07-07T21:59:31.829823+08:00`

#### [Environment Drift] Line 58: `BAZI_ENGINE_CONCURRENCY`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable is explicitly required by the code (raises ValueError if missing), meaning the application will crash if it is not documented in .env.example.
- **Last Updated**: `2026-07-07T22:05:28.760705+08:00`

#### [Async Hazard] Line 93: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The `open` call is used for intermediate file saving within an async function `process_month` which is executed concurrently via `asyncio.gather`. This blocks the event loop during I/O operations, potentially delaying other concurrent tasks.
- **Last Updated**: `2026-07-07T21:59:40.364158+08:00`

#### [Async Hazard] Line 138: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The synchronous 'open' and 'json.dump' calls are performed within an async function 'run_engine', blocking the event loop during I/O operations. This is a hazard on active paths.
- **Last Updated**: `2026-07-07T21:59:57.108883+08:00`

#### [Async Hazard] Line 152: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The `open` call is used to write a JSON file to disk. This is a synchronous I/O operation that blocks the event loop. Since this occurs within the `run_engine` function, which is likely a hot path for processing prompts, it is a true async hazard.
- **Last Updated**: `2026-07-07T22:00:05.598558+08:00`

#### [Dead Code] Line 33: `run_engine`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not statically referenced in the code, but it is explicitly mentioned in the manual (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is a core engine entry point that is likely intended for use or used via a dynamic call/API wrapper not captured by static analysis.

---

### 📄 `src2/core/rotator.py`
Total issues: **5**

#### [Environment Drift] Line 154: `GEMINI_KEYS`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable GEMINI_KEYS is used to initialize a RotatingGoogleProvider, which is critical for the API key rotation logic. Its absence from .env.example makes it undocumented and would prevent new developers or deployment pipelines from knowing it requires a configuration.
- **Last Updated**: `2026-07-07T22:02:49.612490+08:00`

#### [Environment Drift] Line 218: `LLM_BASE_URL`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable LLM_BASE_URL is explicitly required by the code (raising a ValueError if missing), and it is marked as 'undocumented' (missing from .env.example). This is a critical configuration requirement for the application to function.
- **Last Updated**: `2026-07-07T22:02:58.417964+08:00`

#### [Environment Drift] Line 219: `LLM_API_KEY`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable LLM_API_KEY is explicitly required by the code (raising a ValueError if missing), and it is not a standard system fallback. Its absence from .env.example would prevent the application from functioning.
- **Last Updated**: `2026-07-07T22:03:06.721120+08:00`

#### [Dead Code] Line 148: `model_profile`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code, but is mentioned in the manual (CHAPTER_02_HIDDEN_RESERVES.md), indicating it is part of the intended but unused or dormant core logic.

#### [Dead Code] Line 152: `get_rotating_google_provider`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is mentioned in the manual (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is disconnected core logic.

---

### 📄 `src2/engine/openrouter.py`
Total issues: **5**

#### [Schema Hazard] Line 410: `call_openrouter_sync`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses a raw list of dictionaries (`list[dict[str, Any]]`) for the `tools` parameter instead of a Pydantic model to define the tool schema, which is a complex data structure.
- **Last Updated**: `2026-07-07T20:08:51.389351+08:00`

#### [Dead Code] Line 148: `call_openrouter_async`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function name suggests it is a utility for calling OpenRouter, which would typically be called by a higher-level engine or orchestrator. Since no other part of the system uses it, it is confirmed dead.

#### [Dead Code] Line 290: `stream_openrouter_async`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function name suggests it is an asynchronous streaming implementation that is likely unused or replaced by a more generic LLM interface.

#### [Dead Code] Line 364: `call_openrouter_async_with_history`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function name suggests it is a utility for calling OpenRouter with history, which is not dynamically called via common patterns in the engine.

#### [Dead Code] Line 410: `call_openrouter_sync`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function name suggests it is a synchronous wrapper for LLM calls, which is typically replaced by asynchronous versions in modern async-first architectures. No dynamic calls or entry points are found.

---

### 📄 `src2/core/schemas/engine.py`
Total issues: **5**

#### [Dead Code] Line 605: `LLMRequestPayload`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The class LLMRequestPayload is a Pydantic model used for defining the request payload structure for LLM calls. No static references were found in the codebase, and there is no evidence of it being used dynamically or as an entry point. It appears to be an unused schema definition.

#### [Dead Code] Line 613: `LLMResponsePayload`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The class LLMResponsePayload is a Pydantic model used for structuring LLM responses. No static references were found in the codebase, and there are no dynamic calls or entry points that utilize this schema. It appears to be an unused definition.

#### [Dead Code] Line 619: `SerializedProfileContext`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and it is a simple Pydantic model used for data serialization/deserialization, which is unlikely to be called dynamically in a way that would hide its usage.

#### [Dead Code] Line 628: `SerializedGeJuContext`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the class is a Pydantic BaseModel used for serialization, which is typically referenced by name in API responses or internal data transfer objects. Since there are no calls or instantiations of this class anywhere in the project, it is confirmed dead.

#### [Dead Code] Line 635: `DailyPillarResolutionResult`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The class is a Pydantic model used for structured data representation. No static references were found in the codebase, and there is no evidence of dynamic calls or use as an API endpoint/webhook. It appears to be an unused schema definition.

---

### 📄 `src2/engine/narrative_simplifier.py`
Total issues: **4**

#### [Async Hazard] Line 258: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The synchronous 'open' and 'write' calls are used for logging performance metrics to a local file. Since this is part of a loop processed via 'asyncio.gather', it blocks the event loop for every processed month, potentially causing latency spikes in a high-throughput system.
- **Last Updated**: `2026-07-07T21:59:23.205849+08:00`

#### [Async Hazard] Line 268: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The synchronous 'open' and 'write' calls are performed inside an async function 'process' which is executed concurrently via 'asyncio.gather'. This blocks the event loop for every processed month, creating a significant performance bottleneck on a hot path.
- **Last Updated**: `2026-07-07T21:59:31.829081+08:00`

#### [Dead Code] Line 216: `simplify_full_report`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is not an entry point or called dynamically. It appears to be unused.

#### [Environment Drift] Line 223: `SIMPLIFIER_CONCURRENCY`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable SIMPLIFIER_CONCURRENCY is used to control the concurrency level of the narrative simplifier, but it is missing from the .env.example file. This is a configuration setting that should be documented for deployment and tuning.
- **Last Updated**: `2026-07-07T22:05:20.532512+08:00`

---

### 📄 `src2/engine/providers/openai.py`
Total issues: **4**

#### [Schema Hazard] Line 25: `build_payload`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses raw dicts for 'tools' input and returns a raw dict as the payload, which is a complex structure intended for an external API call. This bypasses Pydantic validation for the final payload structure.
- **Last Updated**: `2026-07-07T20:14:08.728901+08:00`

#### [Schema Hazard] Line 54: `extract_response`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function accepts a raw dictionary (`dict[str, Any]`) as input for a complex LLM response payload, which bypasses Pydantic validation for the incoming data structure.
- **Last Updated**: `2025-01-24T12:00:00Z`

#### [Dead Code] Line 25: `build_payload`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not statically referenced in the codebase, but it is explicitly mentioned in the manual (CHAPTER_12_MASTER_CASES.md), indicating it is part of the core logic intended for use or documentation purposes.

#### [Dead Code] Line 54: `extract_response`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not statically referenced in the code, but it is explicitly mentioned in the manual (CHAPTER_04_COMBINATION.md), indicating it is part of the core logic intended for use or documentation purposes.

---

### 📄 `src2/core/platforms/telegram.py`
Total issues: **4**

#### [Async Hazard] Line 96: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The synchronous 'open' call is used to read a file from disk within an async function 'send_outgoing' on a hot path for sending messages. This blocks the event loop during I/O operations.
- **Last Updated**: `2026-07-07T21:59:14.545854+08:00`

#### [Dead Code] Line 45: `capabilities`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The `capabilities` property is not referenced anywhere in the codebase, and since it is a property of a platform class, it is likely intended to be part of a generic platform interface that is not currently utilized by the rest of the system.

#### [Dead Code] Line 48: `parse_incoming`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not statically referenced in the codebase, but it is explicitly mentioned in the verified manual chapter CHAPTER_02_HIDDEN_RESERVES.md, indicating it is part of the core logic intended for future use or documented as a reference implementation.

#### [Dead Code] Line 127: `close`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The function is a class method designed to cleanup resources (HTTP client). Cleanup functions like this are often called by a framework's lifecycle own management or dynamically via a loop of cleanup tasks. However, with no static references, it is likely dead or part of a lifecycle management system not visible to static analysis. Given the typical pattern of 'close' methods in platform handlers, it isle likely intended to be called during shutdown. But without a single reference, it's confirmed dead in the current state of the codebase.

---

### 📄 `src2/engine/module3_interaction.py`
Total issues: **4**

#### [Schema Hazard] Line 150: `_compute_stem_combo_modifiers`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses a raw 'dict' for 'month_data', which is a complex data structure containing 'stem' and 'branch' information, instead of a Pydantic model.
- **Last Updated**: `2025-01-24T12:00:00Z`

#### [Schema Hazard] Line 218: `_detect_fu_yin`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses 'Any' for input parameters p1 and p2, and internally uses .get() or getattr() to handle them as either dictionaries or objects, indicating a lack of a strict Pydantic schema for the input data structures.
- **Last Updated**: `2025-01-24T10:30:00Z`

#### [Schema Hazard] Line 236: `_detect_fan_yin`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses 'Any' for input parameters p1 and p2, and then uses generic .get() or getattr() calls to access 'stem' and 'branch' attributes, indicating it accepts raw dictionaries or arbitrary objects instead of a structured Pydantic model for the pillar data.
- **Last Updated**: `2026-07-07T19:58:51.614142+08:00`

#### [Schema Hazard] Line 250: `detect_same_pillar_trigger`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function accepts 'external_pillar' as 'Any' and 'natal_pillars' as a raw 'list', and internally uses .get() or getattr() to handle potentially raw dictionaries or objects, indicating a lack of a strict Pydantic schema for the pillar data structures.
- **Last Updated**: `2026-07-07T19:58:57.358784+08:00`

---

### 📄 `src2/interfaces/telegram/schemas.py`
Total issues: **4**

#### [Dead Code] Line 42: `normalize_step`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The function is a class method used as a Pydantic validator (implied by its placement within a BaseModel subclass, though the missing @field_validator decorator is likely a bug or legacy code). It has no static references and is not used as a validator by Pydantic because it lacks the decorator. Therefore, it is dead code.

#### [Dead Code] Line 86: `validate_strength_value`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is a class method used for validation logic (likely for a Pydantic model in schemas.py), and while it not statically referenced in other files, it is explicitly mentioned in the documentation (CHAPTER_11_SYNTHESIS.md), indicating it is part of thes system's core logic but currently disconnected from the active execution path.

#### [Dead Code] Line 121: `IntakeData`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and it is a Pydantic model used for data validation. Such models are typically used as type hints for request bodies in API endpoints or handler functions. Since no other part of the code imports or uses this class, it is confirmed dead.

#### [Dead Code] Line 130: `sanitize_alias`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The function is defined as a class method within a Pydantic-like schema class, but it is not decorated with @field_validator or @validator, and there is not a reference to it being called manually. It is intended as a validator but lacks the necessary decorator to be triggered by Pydantic.

---

### 📄 `src2/interfaces/telegram/utils.py`
Total issues: **3**

#### [Environment Drift] Line 149: `TELEGRAM_API_BASE`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable TELEGRAM_API_BASE is accessed via os.environ["TELEGRAM_API_BASE"], which will raise a KeyError if the variable is not defined in the environment. This is a critical configuration requirement for the Telegram interface to function, and its absence from .env.example would break deployments.
- **Last Updated**: `2026-07-07T22:12:07.482895+08:00`

#### [Environment Drift] Line 194: `TELEGRAM_API_BASE`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable TELEGRAM_API_BASE is accessed via os.environ[...], which will raise a KeyError if missing, causing the application to crash. It is not a standard library fallback and is required for constructing the Telegram API URL.
- **Last Updated**: `2026-07-07T22:12:16.022792+08:00`

#### [Environment Drift] Line 217: `REPORT_PROGRESS_CHANNEL_ID`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable REPORT_PROGRESS_CHANNEL_ID is used to configure a Telegram channel ID for progress reporting, and it is not present in the .env.example file. This is a required configuration for the feature to function as intended in different environments.
- **Last Updated**: `2026-07-07T22:14:36.058833+08:00`

---

### 📄 `src2/engine/module2_root.py`
Total issues: **3**

#### [Schema Hazard] Line 134: `calculate_root`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses Pydantic models (RootInput, ModuleRootOutput) for its primary input and output, but it accepts raw 'dict | None' for 'transformed_branches' and 'selective_extractions'. While these are optional, they represent complex data structures (branch transformations and extractions) that should be ideally modeled via Pydantic for strict validation in a core engine module.
- **Last Updated**: `2026-07-07T19:56:14.359009+08:00`

#### [Schema Hazard] Line 412: `get_root_sub_score`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses raw dicts (month_data, transformed_branches, selective_extractions) and a raw list (self_punished_branches) for complex input data structures instead of Pydantic models.
- **Last Updated**: `2026-07-07T19:56:20.534728+08:00`

#### [Dead Code] Line 640: `calculate_tier1_simplified_count`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the codebase but is explicitly mentioned in the manual (CHAPTER_10_SPECIAL_STRUCTURES.md), indicating it is pedagogical logic intended for documentation purposes.

---

### 📄 `src2/interfaces/telegram/reliability.py`
Total issues: **3**

#### [Environment Drift] Line 43: `TELEGRAM_API_BASE`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable TELEGRAM_API_BASE is accessed via os.environ without a default value, meaning the application will crash if it is not defined in the environment. This is a critical configuration requirement for the Telegram interface to function.
- **Last Updated**: `2026-07-07T22:11:58.486522+08:00`

#### [Environment Drift] Line 74: `REPORT_PROGRESS_CHANNEL_ID`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable REPORT_PROGRESS_CHANNEL_ID is used to define a target for telegram notifications, and it is not documented in the .env.example file. This is a required configuration for the feature to function as intended.
- **Last Updated**: `2026-07-07T22:14:27.381524+08:00`

#### [Dead Code] Line 57: `send_admin_alert`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function's purpose (sending admin alerts for errors) is a typical candidate for dynamic calls or global error handlers, but without any such mechanism present in the codebase, it is confirmed dead.

---

### 📄 `src2/engine/providers/gemini.py`
Total issues: **3**

#### [Schema Hazard] Line 23: `build_payload`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses raw dicts for 'tools' input and returns a raw dict as the payload, which is a complex structure for an API contract.
- **Last Updated**: `2025-01-24T10:30:00Z`

#### [Dead Code] Line 23: `build_payload`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is mentioned in the manual (CHAPTER_12_MASTER_CASES.md), indicating it is disconnected core logic.

#### [Dead Code] Line 55: `extract_response`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is mentioned in the manual (CHAPTER_04_COMBINATION.md), indicating it is part of the core logic intended for use or documented as an example, but not currently integrated into the active execution path.

---

### 📄 `src2/core/memory/memory_manager.py`
Total issues: **3**

#### [Dead Code] Line 91: `get_reports_dir`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function's purpose (managing reports directories) is not typically called dynamically via generic memory management interfaces.
- **Last Updated**: `2026-07-07T21:01:44.012807+08:00`

#### [Dead Code] Line 97: `get_profile_path`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a simple helper for constructing a path to 'profile.json'. It is not an entry point, not called dynamically, and not referenced in any configuration or documentation.

#### [Dead Code] Line 105: `clear_all_user_data`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not statically referenced in the codebase, but it is explicitly mentioned in the verified manual chapter CHAPTER_06_HARM_PUNISHMENT.md, indicating it is intended core logic for user data erasure (likely for compliance or administrative purposes) that is not currently integrated into the active execution pipeline.

---

### 📄 `src2/core/valkey.py`
Total issues: **2**

#### [Environment Drift] Line 22: `VALKEY_HOST`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable VALKEY_HOST is explicitly required by the code (raising a KeyError if missing), and its absence from .env.example makes it an undocumented dependency that would break deployment.
- **Last Updated**: `2026-07-07T22:04:00.026588+08:00`

#### [Environment Drift] Line 23: `VALKEY_PORT`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The code explicitly raises a KeyError if VALKEY_PORT is missing, indicating it is a mandatory configuration requirement for the application to function. Since it is undocumented in .env.example, this is a true drift violation.
- **Last Updated**: `2026-07-07T22:04:26.485863+08:00`

---

### 📄 `src2/interfaces/telegram/report_utils.py`
Total issues: **2**

#### [Async Hazard] Line 99: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The `open` call is used to read a JSON file from disk. Since this is part of a `get_month_narrative` function (likely called by a Telegram bot handler), it blocks the event loop during I/O operations, which can lead to latency for other users.
- **Last Updated**: `2026-07-07T22:02:00.352854+08:00`

#### [Async Hazard] Line 175: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The `open` call and subsequent `json.dump` are synchronous file I/O operations performed directly within an async function, blocking the event loop. This occurs on a path that involves network calls (simplify_month_narrative), suggesting it is part of an active request-handling path.
- **Last Updated**: `2026-07-07T22:02:09.062906+08:00`

---

### 📄 `src2/core/services/intake.py`
Total issues: **2**

#### [Async Hazard] Line 68: `open`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `ASYNC_HAZARD`
- **Reasoning**: The `open()` call is used to write a JSON export of user data to a temporary file. This is a synchronous I/O operation performed directly within the async `handle_message` function, which blocks the event loop for the duration of the file write.
- **Last Updated**: `2026-07-07T21:59:14.545894+08:00`

#### [Dead Code] Line 9: `handle_message`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not statically referenced in the codebase, but it is explicitly mentioned in the manual (CHAPTER_11_SYNTHESIS.md), indicating it is part of the core logic intended for the system's message handling pipeline, but currently disconnected from the active execution path.

---

### 📄 `src2/engine/module12_compatibility.py`
Total issues: **2**

#### [Code Duplication] Line 304: `branch_mapping_logic`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DUPLICATION`
- **Reasoning**: The code implements a specific business logic mapping for branches (Yin, Wu, Xu -> Mao, etc.). This identical logic is repeated across two different engine modules, indicating a clear violation of DRY principles and should be refactored into a shared utility function.
- **Last Updated**: `2026-07-07T22:18:26.623363+08:00`

#### [Dead Code] Line 688: `analyze_compatibility_with_transits`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the codebase but is explicitly mentioned in the manual (CHAPTER_09_TAI_SUI.md), indicating it is part of the core logic intended for use or documented as a feature, but not currently integrated into the active execution pipeline.

---

### 📄 `src2/core/calendar/populate_calendar.py`
Total issues: **2**

#### [Code Duplication] Line 9: `STEM_MAP and BRANCH_MAP constants`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DUPLICATION`
- **Reasoning**: These are static mapping constants used for Bazi/Calendar translations. Having them duplicated across core and engine modules suggests they should be moved to a shared constants or utility file to ensure consistency.
- **Last Updated**: `2026-07-07T22:18:09.936186+08:00`

#### [Dead Code] Line 53: `get_hour_stem`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function's logic (calculating a stem based on day and hour branches) is highly specific to a calendar population logic that is not invoked anywhere else in the current active pipeline.
- **Last Updated**: `2026-07-07T21:01:44.012669+08:00`

---

### 📄 `src2/core/tools/user_profile_input.py`
Total issues: **2**

#### [Dead Code] Line 38: `apply_override`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the codebase but is explicitly mentioned in the manual (CHAPTER_10_SPECIAL_STRUCTURES.md), indicating it is part of the core logic intended for user overrides but not currently integrated into the active execution pipeline.

#### [Dead Code] Line 66: `get_effective_profile`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the rest of the codebase, but it is explicitly mentioned in the manual documentation (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is part of the core logic intended for use or described in the documentation, but not currently integrated into the active execution path.

---

### 📄 `src2/engine/daily_pillar.py`
Total issues: **2**

#### [Dead Code] Line 26: `get_sg_now`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a simple utility for getting the current time in Singapore time, which does not appear to be used by any other part of the system.

#### [Code Duplication] Line 33: `Heavenly Stems list`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DUPLICATION`
- **Reasoning**: This is a static list of the Ten Heavenly Stems used in Chinese astrology/calendar calculations. Since it is a fundamental constant used across multiple engine modules, it should be defined once in a shared constants file.
- **Last Updated**: `2026-07-07T22:18:17.956451+08:00`

---

### 📄 `src2/interfaces/telegram/chronomancer/rag.py`
Total issues: **2**

#### [Dead Code] Line 106: `RAGQueryOutput`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The class RAGQueryOutput is defined but not referenced anywhere in the same file or other files in the codebase. It is a Pydantic model used for structured output, but the function generate_rag_queries (which logically would use it) does not reference it.

#### [Dead Code] Line 127: `generate_rag_queries`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is explicitly mentioned in the manual (CHAPTER_04_COMBINATION.md), indicating it is part of the intended core logic but currently disconnected from the active execution pipeline.

---

### 📄 `src2/interfaces/telegram/chronomancer/ranking.py`
Total issues: **2**

#### [Dead Code] Line 86: `rank_days_aggregate`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function's logic is specific to a ranking algorithm for 'scored_days' which is not utilized by any other part of the system.

#### [Dead Code] Line 111: `rank_days_by_health`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: No static references found in the codebase, but it is explicitly mentioned in the manual (CHAPTER_06_HARM_PUNISHMENT.md), indicating it is part of the intended core logic but currently disconnected from the active execution pipeline.

---

### 📄 `src2/interfaces/telegram/evaluation.py`
Total issues: **2**

#### [Dead Code] Line 16: `evaluate_profile`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not statically referenced in the code, but it is explicitly mentioned in the verified manual chapter CHAPTER_01_COMMANDING_QI.md, indicating it is part of the intended core logic but currently disconnected from the active execution pipeline.

#### [Dead Code] Line 73: `get_tone_advice`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The function is a helper method within a Telegram interface class, providing a static string of advice. It has no static references in the rest of the codebase and no dynamic calls (like getattr or dispatchers) are evident in the    the Telegram interface's logic.

---

### 📄 `src2/engine/rag_client.py`
Total issues: **1**

#### [Environment Drift] Line 18: `QDRANT_API_KEY`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable QDRANT_API_KEY is used in the code but is missing from the .env.example file. While it is not explicitly checked in the startup validation block (lines 23-27), it is a critical configuration for authenticating with a Qdrant vector database, and its absence would likely cause authentication failures during runtime.
- **Last Updated**: `2026-07-07T22:09:21.091217+08:00`

---

### 📄 `src2/engine/session.py`
Total issues: **1**

#### [Schema Hazard] Line 49: `build_lifestate`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses 'Any' for its input parameters and returns a raw 'dict', despite handling a complex data structure (life-state) that should be validated by a Pydantic model.
- **Last Updated**: `2026-07-07T20:20:04.110075+08:00`

---

### 📄 `src2/engine/solar_calendar.py`
Total issues: **1**

#### [Schema Hazard] Line 51: `get_annual_pillar`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function returns a raw dictionary `dict[str, str]` to represent a pillar (stem and branch), which is a core domain entity in BaZi. This should be represented by a Pydantic model for consistent validation and type safety across the engine.
- **Last Updated**: `2026-07-07T20:20:20.109352+08:00`

---

### 📄 `src2/interfaces/telegram/bgem3_bridge.py`
Total issues: **1**

#### [Environment Drift] Line 9: `BGEM3_MCP_URL`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable BGEM3_MCP_URL is explicitly required by the application (it raises a ValueError if missing), but it is not documented in the .env.example file. This is a critical configuration missing from the example.
- **Last Updated**: `2026-07-07T22:10:39.642105+08:00`

---

### 📄 `src2/interfaces/telegram/validators.py`
Total issues: **1**

#### [Silent Killer] Line 190: `Exception`
- **Severity**: 🔴 **HIGH**
- **Status/Verdict**: `SILENT_KILLER`
- **Reasoning**: The try-except block swallows ValueError and TypeError during a float conversion of a score. If the score is invalid (e.g., None or a non-numeric string), the range check is skipped entirely without adding a violation, allowing invalid data to pass through the validator.

---

### 📄 `src2/core/identity/service.py`
Total issues: **1**

#### [Dead Code] Line 19: `get_user_by_uuid`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a simple database query helper that is not likely to be called dynamically via reflection or as a generic entry point.
- **Last Updated**: `2026-07-07T21:01:44.012735+08:00`

---

### 📄 `src2/core/platforms/base.py`
Total issues: **1**

#### [Dead Code] Line 31: `parse_incoming`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: Abstract method defined in a base class for platform integrations. While no static references are found, it is referenced in the documentation (CHAPTER_02_HIDDEN_RESERVES.md), indicating it is part of the core architectural design for handling incoming messages across platforms.

---

### 📄 `src2/core/tools/bd_config.py`
Total issues: **1**

#### [Dead Code] Line 10: `save`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is a class method designed for saving configuration data to a file. It does not appear to be an entry point or dynamically called.

---

### 📄 `src2/core/tools/formatter.py`
Total issues: **1**

#### [Dead Code] Line 66: `generate_pdf_report`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is explicitly mentioned in the manual (CHAPTER_04_COMBINATION.md), indicating it is part of the intended core logic but currently disconnected from the active execution pipeline.

---

### 📄 `src2/engine/bazi_calculator.py`
Total issues: **1**

#### [Dead Code] Line 7: `calculate_bazi`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: No static references found in the codebase, but it is explicitly referenced in the verified manual documentation (CHAPTER_10_SPECIAL_STRUCTURES.md), indicating it is core logic that is currently disconnected from the active execution pipeline.

---

### 📄 `src2/engine/context_template.py`
Total issues: **1**

#### [Dead Code] Line 459: `build_context`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the codebase but is explicitly mentioned in the manual (CHAPTER_12_MASTER_CASES.md), indicating it is part of the core logic intended for use or documentation purposes.
- **Last Updated**: `2026-07-07T21:01:44.012801+08:00`

---

### 📄 `src2/engine/module11_probability.py`
Total issues: **1**

#### [Schema Hazard] Line 135: `_map_triggers`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function accepts 'Any' as input and uses extensive 'hasattr' and 'isinstance(..., dict)' checks to handle potentially raw dictionaries or objects, indicating a lack of a formal Pydantic schema for the 'triggers' payload.
- **Last Updated**: `2026-07-07T19:49:00.082985+08:00`

---

### 📄 `src2/engine/module13_spectrum.py`
Total issues: **1**

#### [Schema Hazard] Line 21: `_dm_concentration_from_pillars`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses a raw 'dict | None' for 'transformed_branches', which is a complex data structure representing branch transformations. This should be mapped to a Pydantic model for validation and consistency across the engine.
- **Last Updated**: `2026-07-07T19:50:24.549211+08:00`

---

### 📄 `src2/engine/module1_macro.py`
Total issues: **1**

#### [Schema Hazard] Line 526: `_filter_tai_sui_by_shen`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function signature explicitly allows 'dict' as a type for 'shen_profile', and the implementation handles it as a raw dictionary, bypassing Pydantic validation for a complex data structure.
- **Last Updated**: `2026-07-07T19:55:33.671587+08:00`

---

### 📄 `src2/engine/narrative_review.py`
Total issues: **1**

#### [Dead Code] Line 67: `review_narrative`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: No static references found in the codebase, and the function is not used as a dynamic entry point or webhook. It appears to be a part of an unused reviewer agent implementation.

---

### 📄 `src2/engine/orchestrator.py`
Total issues: **1**

#### [Schema Hazard] Line 121: `handle_clash_activation`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses raw 'list' types for its input parameters 'clashed_branches' and 'chart_branches' instead of a structured Pydantic model or a more specific type hint (e.g., list[str]), and it returns a dictionary of Pydantic models. While it processes complex logic, the input side lacks schema validation for the lists.
- **Last Updated**: `2026-07-07T20:09:16.108213+08:00`

---

### 📄 `src2/engine/prompt_maker.py`
Total issues: **1**

#### [Schema Hazard] Line 75: `_serialise_engine_outputs`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `SCHEMA_HAZARD`
- **Reasoning**: The function uses 'Any' for the input 'engine_result', which bypasses type safety and schema validation for a complex object that is clearly accessed as a Pydantic-like model (e.g., engine_result.engine_outputs). This is a schema hazard as it lacks a concrete Pydantic model type hint for a complex data structure.
- **Last Updated**: `2026-07-07T20:10:02.367903+08:00`

---

### 📄 `src2/interfaces/telegram/intake/intake.py`
Total issues: **1**

#### [Dead Code] Line 52: `_compute_age_display`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced by any other function in the same file or other files in the codebase, but it is mentioned in the documentation (CHAPTER_03_PRODUCTION_CONTROL.md), indicating it is part of the intended core logic but currently disconnected from the active execution path.

---

### 📄 `src2/interfaces/telegram/logging_utils.py`
Total issues: **1**

#### [Environment Drift] Line 45: `BOT_STDERR_LOG_PATH`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DRIFT_VIOLATION`
- **Reasoning**: The variable BOT_STDERR_LOG_PATH is used to define the log file path. While it has a fallback value ("bot_stderr.log"), it is a custom application-specific configuration that should be documented in .env.example to allow operators to specify the log location.
- **Last Updated**: `2026-07-07T22:11:22.871465+08:00`

---

### 📄 `src2/interfaces/telegram/metrics.py`
Total issues: **1**

#### [Dead Code] Line 82: `close`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `CONFIRMED_DEAD`
- **Reasoning**: The function is a cleanup method typically used in context managers or by the rest of the application to ensure buffers are flushed. Since there are no static references and it is part of a class that likely manages a resource, it is a candidate for dead code, but often these are called via base class interfaces or generic cleanup routines. However, based on thes provided context, it is no longer used.

---

### 📄 `src2/interfaces/telegram/queue_worker.py`
Total issues: **1**

#### [Dead Code] Line 86: `start_worker`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not statically referenced in the codebase, but it is mentioned in the manual documentation (CHAPTER_00_THE_DETERMINISTIC_BAZI_TOC.md), indicating it is part of the core logic intended for the system's operation but not currently integrated into the active execution pipeline.

---

### 📄 `src2/interfaces/telegram/tailoring.py`
Total issues: **1**

#### [Dead Code] Line 342: `build_reviewer_flags_note`
- **Severity**: 🟡 **LOW**
- **Status/Verdict**: `DISCONNECTED_CORE_LOGIC`
- **Reasoning**: The function is not referenced in the code but is mentioned in the manual (CHAPTER_12_MASTER_CASES.md), indicating it is part of the intended core logic but currently disconnected from the active execution pipeline.

---

