# Red-Team Fiduciary Audit Report

**Scope**: uncommitted working directory changes
**Tiers**: security, logic, performance, telemetry
**Model**: `auditor_model` → `OpenAIChatModel()`
**Timestamp**: 2026-07-09T09:14:37.375453+00:00

## Verdict: 🚨 GO LIVE BLOCKED

**Auditor Notes**: Verify overall correctness and logic of our recent AST codebase cleanup. Confirm that removing dead code functions does not break callers.


---
## 🚨 Tier: SECURITY

**Go-Live Safe**: NO

### Summary

This is NOT a safe dead-code cleanup. The pre-computed stale-dependency scan proves that nearly every function deleted in this diff is still referenced by live `src2` callers across the LLM provider layer, the monthly-forecast engine, the Telegram adapter, and the entire `db.py` persistence layer. The removals convert into ImportErrors at module load (providers, context_template, pydantic_prompt_engine) and AttributeErrors at runtime in every handler (app.py, security.py, pipeline.py, session.py, queue_worker.py, chronomancer/*, intake/*, bridge.py). Critically, this also deletes the right-to-erasure (`delete_all_user_data`) and tier-authorization (`get_user_tier`/`set_user_tier`) paths, creating a privacy/compliance and authorization regression. go_live_safe = False.

### Risk Ledger

#### 1. 🔴 [Critical] `src2/core/schemas/engine.py (LLMRequestPayload, LLMResponsePayload)`

**Description**: Deleted Pydantic schemas are still imported/constructed by `src2/engine/providers/openai.py:26,61` and `src2/engine/providers/gemini.py:24,66`. Removal causes ImportError in the provider modules, which are required for every LLM call. This breaks the entire LLM subsystem at import time.

**Mitigation**: Revert deletion of `LLMRequestPayload` and `LLMResponsePayload` (or migrate provider adapters to the new schema first and update both openai.py and gemini.py imports before deleting).

#### 2. 🔴 [Critical] `src2/core/schemas/engine.py (SerializedProfileContext, SerializedGeJuContext)`

**Description**: Deleted schemas are still constructed by `src2/engine/context_template.py:147,312,329`. Removal causes ImportError in context_template, which is on the path for building forecast context. App module graph fails to load.

**Mitigation**: Revert deletion of `SerializedProfileContext` and `SerializedGeJuContext`, or update context_template.py to use a replacement schema before removing.

#### 3. 🔴 [Critical] `src2/interfaces/telegram/chronomancer/agents.py (MonthlyForecastDeps)`

**Description**: Deleted dataclass is referenced by `src2/engine/pydantic_prompt_engine.py:342-349,353,513` (deps_type=MonthlyForecastDeps and `deps = MonthlyForecastDeps(...)`). Removal causes ImportError in the monthly-forecast engine. `DailyForecastResult` removal is safe (no callers).

**Mitigation**: Revert deletion of `MonthlyForecastDeps`, or move/relocate the class and update pydantic_prompt_engine.py imports prior to deletion.

#### 4. 🔴 [Critical] `src2/core/platforms/telegram.py (TelegramAdapter.close)`

**Description**: Deleted classmethod is called by `src2/interfaces/telegram/app.py:73` (`await TelegramAdapter.close()`). Removal raises AttributeError at application startup/boot path, preventing the src2 Telegram app from starting.

**Mitigation**: Revert deletion of `close`, or update app.py:73 to the replacement shutdown hook (e.g., a shared client lifecycle manager) before removing.

#### 5. 🔴 [Critical] `src2/interfaces/telegram/db.py (mass method removal)`

**Description**: Removed ~25 data-access methods are live-called throughout `src2/interfaces/telegram/*`: app.py (get_all_reports_for_user:572/589, get_user_prefs:597/760/829/842, set_user_prefs:301/303/773/778/781/832, delete_stakeholder:484, log_chat:366+), session.py:69 (delete_session), pipeline.py:47/88 (get_all_reports_for_user, add_report_metadata), queue_worker.py:137/159 (fail_job, mark_job_pending), stakeholder_intake.py:96 (upsert_stakeholder), chronomancer/coordinator.py:109/241/351/477/401/551/673 (get_all_reports_for_user, get_user_prefs, get_stakeholder_aliases, get_reports_for_alias), chronomancer/agents.py:287/457/581 (get_all_reports_for_user, get_user_prefs), intake/calendar_node.py:84/200 (get_semantic_id), bridge.py:250 (get_user_prefs). Every handler now raises AttributeError. This is the core persistence layer.

**Mitigation**: Do NOT delete these methods. Revert the db.py hunk entirely; the cleanup premise is false for this file. If a migration to a different DB layer is intended, it must land atomically with all callers updated in the same change.

#### 6. 🟠 [High] `src2/interfaces/telegram/db.py (delete_all_user_data) -> security.py:84`

**Description**: Right-to-erasure / data-deletion function is removed while `src2/interfaces/telegram/security.py:84` still calls `db.delete_all_user_data(user_id)`. This kills the user-data purge path (ChatLog, DailyForecast, JobQueue, Report, Stakeholder, UserPreference, DbSession, ConsentRecord, UserPromoUsage, PlatformAccount, User). Users can no longer erase their PII — a privacy/compliance (GDPR-style) regression.

**Mitigation**: Restore `delete_all_user_data` in db.py; it is actively wired to the erasure command in security.py. Verify ConsentRecord/UserPromoUsage cascade still executes.

#### 7. 🟠 [High] `src2/interfaces/telegram/db.py (get_user_tier, set_user_tier) -> security.py:48,155`

**Description**: Tier authorization/billing functions removed while `src2/interfaces/telegram/security.py:48` (`tier = db.get_user_tier(user_id)`) and `:155` (`db.set_user_tier(target_user_id, tier)`) still call them. This breaks tier lookups and admin tier assignment, removing the authorization boundary used for feature/tier gating (BAC).

**Mitigation**: Restore both methods in db.py; they enforce the tier-based access control referenced by security.py.

#### 8. 🟡 [Medium] `src2/core/memory/mem0_store.py (delete_user_memories) -> memory_manager.py:108`

**Description**: Removed `delete_user_memories` is still called by `src2/core/memory/memory_manager.py:108` (`self.mem_store.delete_user_memories(resolved_id)`). Memory-erasure path is dead, leaving user memory orphaned on erasure requests.

**Mitigation**: Restore `delete_user_memories` in Mem0Store, or update memory_manager.py:108 to the replacement erasure API before deletion.

#### 9. 🟡 [Medium] `src2/core/memory/memory_manager.py (get_reports_dir, get_profile_path)`

**Description**: Removed helpers are still called by `src2/interfaces/telegram/pipeline.py:65` (`memory_manager.get_reports_dir`), `bridge.py:274` (`memory_manager.get_profile_path`), and `chronomancer/coordinator.py:99` (`memory_manager.get_profile_path`). Report and profile path resolution now raises AttributeError.

**Mitigation**: Restore both methods, or relocate them to the module that the callers now import from before deleting.

#### 10. 🟡 [Medium] `src2/core/services/storage.py (delete_file) -> compliance.py:94`

**Description**: Removed `delete_file` is still called by `src2/core/services/compliance.py:94` (`storage.delete_file(path)`). Compliance-driven file deletion (e.g., on consent withdrawal) now raises AttributeError.

**Mitigation**: Restore `delete_file`, or update compliance.py:94 to the replacement file-deletion API.

#### 11. 🟡 [Medium] `src2/core/tools/bd_config.py (ConfigManager.save) -> bd_cli.py:40`

**Description**: Removed `ConfigManager.save` is still called by `src2/core/tools/bd_cli.py:40` (`ConfigManager.save(config)`). CLI config persistence now raises AttributeError.

**Mitigation**: Restore `save`, or update bd_cli.py:40 to the replacement persistence call before deletion.

#### 12. 🟢 [Low] `src2/interfaces/telegram/evaluation.py (get_tone_advice) -> intake/intake.py:196,354`

**Description**: Removed `get_tone_advice` is still called by `src2/interfaces/telegram/intake/intake.py:196` and `:354` (`evaluator.get_tone_advice()`). Intake feedback rendering now raises AttributeError (UX regression; not a data/security exposure).

**Mitigation**: Restore `get_tone_advice` or update intake.py to the replacement helper.

#### 13. 🟢 [Low] `src2/core/platforms/telegram.py (capabilities); TEST/e2e/test_telegram_adapter.py:60`

**Description**: Removed `capabilities` property is read by `TEST/e2e/test_telegram_adapter.py:60` (`caps = adapter.capabilities`). Test will fail with AttributeError. If `capabilities` is an abstract member of `ChannelAdapter`, concrete implementations must still provide it.

**Mitigation**: Restore the property or update the ABC/test contract. Low impact (test-only).

#### 14. 🟢 [Low] `src2/core/services/storage.py (upload_string, download_string); TEST/unit/test_day9_storage.py:40,51`

**Description**: Removed `upload_string`/`download_string` are still exercised by `TEST/unit/test_day9_storage.py:40,51`. Unit test will fail. No production src2 caller in stale scan.

**Mitigation**: Restore the methods or delete/adjust the corresponding unit tests together with the change.

#### 15. ℹ️ [Informational] `src2/engine/narrative_simplifier.py (simplify_full_report)`

**Description**: Deletion is beneficial: the removed function embedded hardcoded absolute paths (`/home/yapilwsl/arthityap/baziforecaster/logs/Time_Monthly_Reports`, `.../logs/Logfire`). No live callers. This reduces host-specific path leakage. No action required.

**Mitigation**: None — keep removed.

### Diff Feedback

- `src2/core/schemas/engine.py` (LLMRequestPayload/LLMResponsePayload/SerializedProfileContext/SerializedGeJuContext/DailyPillarResolutionResult removed): These are NOT dead. `src2/engine/providers/openai.py:26,61` and `gemini.py:24,66` import/construct `LLMRequestPayload`/`LLMResponsePayload`; `src2/engine/context_template.py:147,312,329` construct `SerializedProfileContext`/`SerializedGeJuContext`. Deleting them raises ImportError in the provider and context-template modules, which are on the hot path for every LLM call.
- `src2/interfaces/telegram/chronomancer/agents.py` (MonthlyForecastDeps removed): `src2/engine/pydantic_prompt_engine.py:342-349,353,513` reference `MonthlyForecastDeps` (deps_type + construction). Removal => ImportError in the monthly-forecast engine. Keep the class or refactor pydantic_prompt_engine.py first.
- `src2/core/platforms/telegram.py` (TelegramAdapter.capabilities + close removed): `src2/interfaces/telegram/app.py:73` calls `await TelegramAdapter.close()` at boot; `TEST/e2e/test_telegram_adapter.py:60` reads `adapter.capabilities`. Removal => AttributeError at startup (app.py:73) and broken test.
- `src2/interfaces/telegram/db.py` (mass removal of ~25 methods): `get_user_prefs`, `set_user_prefs`, `get_all_reports_for_user`, `add_report_metadata`, `delete_session`, `upsert_stakeholder`, `delete_stakeholder`, `get_stakeholder_aliases`, `get_reports_for_alias`, `get_semantic_id`, `get_user_tier`, `set_user_tier`, `fail_job`, `mark_job_pending`, `log_chat`, `delete_all_user_data` are ALL live-called from app.py, security.py, pipeline.py, session.py, queue_worker.py, stakeholder_intake.py, chronomancer/coordinator.py, chronomancer/agents.py, intake/calendar_node.py, and bridge.py (per stale scan). This is the core persistence layer; every handler now raises AttributeError.
- `src2/core/memory/mem0_store.py` (delete_user_memories removed): `src2/core/memory/memory_manager.py:108` calls `self.mem_store.delete_user_memories(resolved_id)`. Broken → memory-erasure path dead.
- `src2/core/memory/memory_manager.py` (get_reports_dir/get_profile_path removed): `src2/interfaces/telegram/pipeline.py:65`, `bridge.py:274`, `chronomancer/coordinator.py:99` call these. Broken → report/profile path resolution fails.
- `src2/core/services/storage.py` (upload_string/download_string/delete_file removed): `src2/core/services/compliance.py:94` calls `storage.delete_file(path)`. Broken → compliance file deletion dead.
- `src2/core/tools/bd_config.py` (ConfigManager.save removed): `src2/core/tools/bd_cli.py:40` calls `ConfigManager.save(config)`. Broken.
- `src2/interfaces/telegram/evaluation.py` (get_tone_advice removed): `src2/interfaces/telegram/intake/intake.py:196,354` call it. Broken.
- `src2/engine/narrative_simplifier.py` (simplify_full_report removed): No live callers (no stale refs). Note: it contained hardcoded absolute paths `/home/yapilwsl/arthityap/baziforecaster/logs/...` — removal is genuinely beneficial.
- `src2/engine/openrouter.py` (call_openrouter_* removed): No `src2` callers in stale scan; safe. Side-effect: bearer-token header construction referencing `settings.openrouter_api_key` is also removed, which is fine since unused.

---
## 🚨 Tier: LOGIC

**Go-Live Safe**: NO

### Summary

This change is mislabeled as "dead-code removal." The pre-computed dependency scan proves the opposite for the `src2` tree: nearly every symbol deleted from `src2/` is still actively invoked by live in-tree callers. The removals will cause hard import-time failures (schema/provider modules, pydantic_prompt_engine, bd_cli) and runtime AttributeErrors across the entire telegram app, DB layer, memory manager, storage compliance path, and intake evaluation. go_live_safe = False; the diff must be reverted or the callers migrated before merge.

### Risk Ledger

#### 1. 🔴 [Critical] `src2/core/schemas/engine.py`

**Description**: Removed LLMRequestPayload, LLMResponsePayload, SerializedProfileContext, SerializedGeJuContext. Stale scan proves live in-tree callers: src2/engine/providers/openai.py:26 (request: LLMRequestPayload), src2/engine/providers/openai.py:61 (return LLMResponsePayload(...)), src2/engine/providers/gemini.py:24,66, src2/engine/context_template.py:147 (SerializedProfileContext(...)), src2/engine/context_template.py:312,329 (SerializedGeJuContext(...)). These are top-level imports/annotations → ImportError at app startup.

**Mitigation**: Re-add all five classes to src2/core/schemas/engine.py (or keep a backward-compat re-export). Do NOT remove until providers/openai.py, providers/gemini.py, and context_template.py are migrated to the new payload types.

#### 2. 🔴 [Critical] `src2/interfaces/telegram/chronomancer/agents.py`

**Description**: Removed MonthlyForecastDeps. Stale scan proves live in-tree caller: src2/engine/pydantic_prompt_engine.py:342-349,353 (deps_type=MonthlyForecastDeps, ctx: RunContext[MonthlyForecastDeps]) and :513 (deps = MonthlyForecastDeps(...)). Module import and runtime instantiation will fail.

**Mitigation**: Re-add MonthlyForecastDeps (or duplicate it into pydantic_prompt_engine.py / a shared schema module). Deletion is unsafe until pydantic_prompt_engine.py is migrated.

#### 3. 🔴 [Critical] `src2/interfaces/telegram/db.py`

**Description**: Removed ~20 Database methods still called by live src2 code: get_semantic_id (intake/calendar_node.py:84,200; core/memory/memory_manager.py:42), get_user_tier (security.py:48), set_user_tier (security.py:155), delete_session (session.py:69; app.py:790,792,865,867; pipeline.py:26,105,109), fail_job (queue_worker.py:137), mark_job_pending (queue_worker.py:159), get_reports_for_alias (chronomancer/coordinator.py:551), get_all_reports_for_user (app.py:572,589; pipeline.py:47; chronomancer/coordinator.py:109,553; chronomancer/agents.py:287,581), add_report_metadata (pipeline.py:88), log_chat (app.py:366,409,524,618,669,754,897,927,936,941), upsert_stakeholder (stakeholder_intake.py:96), get_stakeholder_aliases (chronomancer/coordinator.py:401), delete_stakeholder (app.py:484), delete_all_user_data (security.py:84), get_user_prefs (app.py:597,760,829,842; bridge.py:250; chronomancer/coordinator.py:241,351,477,673; chronomancer/agents.py:457), set_user_prefs (app.py:301,303,773,778,781,832). Every call site raises AttributeError at runtime.

**Mitigation**: Revert ALL deletions in src2/interfaces/telegram/db.py. These are core persistence/telegram handlers — none are dead. If consolidation to another store is intended, migrate every listed caller first and verify with an import smoke test + the test suite.

#### 4. 🔴 [Critical] `src2/core/memory/memory_manager.py`

**Description**: Removed MemoryManager.get_reports_dir and get_profile_path. Stale scan proves live callers: src2/interfaces/telegram/pipeline.py:65 (memory_manager.get_reports_dir(chat_id)), src2/interfaces/telegram/bridge.py:274 (memory_manager.get_profile_path(chat_id)), src2/interfaces/telegram/chronomancer/coordinator.py:99 (memory_manager.get_profile_path(user_id)). AttributeError at runtime.

**Mitigation**: Re-add get_reports_dir and get_profile_path to MemoryManager, or migrate the three call sites to a shared path helper. Do not delete until callers are updated.

#### 5. 🔴 [Critical] `src2/core/memory/mem0_store.py`

**Description**: Removed Mem0Store.delete_user_memories. Stale scan proves caller src2/core/memory/memory_manager.py:108 (self.mem_store.delete_user_memories(resolved_id)). AttributeError during erasure flow.

**Mitigation**: Re-add delete_user_memories to Mem0Store (guarded by `if not self.enabled: return` + self.memory.delete_all(str(user_id))), or change memory_manager.py:108 to call the replacement API.

#### 6. 🔴 [Critical] `src2/core/services/storage.py`

**Description**: Removed StorageService.delete_file. Stale scan proves caller src2/core/services/compliance.py:94 (storage.delete_file(path)). AttributeError during consent/file-destruction compliance flow.

**Mitigation**: Re-add delete_file (self.client.delete_object(Bucket=self.bucket, Key=key)) or migrate compliance.py:94 to the replacement deletion API.

#### 7. 🔴 [Critical] `src2/core/tools/bd_config.py`

**Description**: Removed ConfigManager.save. Stale scan proves caller src2/core/tools/bd_cli.py:40 (ConfigManager.save(config)). AttributeError / lost persistence at config write time.

**Mitigation**: Re-add ConfigManager.save classmethod (atomic tmp+os.replace with timestamp), or migrate bd_cli.py:40 to the new persistence path.

#### 8. 🔴 [Critical] `src2/core/platforms/telegram.py`

**Description**: Removed TelegramAdapter.close classmethod. Stale scan proves caller src2/interfaces/telegram/app.py:73 (await TelegramAdapter.close()). Unless a base ChannelAdapter.close exists (unproven; zero-trust = no), this raises AttributeError at app teardown/startup.

**Mitigation**: Re-add the TelegramAdapter.close classmethod that closes the shared _http_client, or migrate app.py:73 to the base-class shutdown hook. Verify a base-class close() actually exists before deletion.

#### 9. 🔴 [Critical] `src2/interfaces/telegram/evaluation.py`

**Description**: Removed InputEvaluator.get_tone_advice. Stale scan proves callers src2/interfaces/telegram/intake/intake.py:196 (return evaluator.get_tone_advice()) and :354 (feedback_msg += f"\n\n{evaluator.get_tone_advice()}"). AttributeError in intake feedback path.

**Mitigation**: Re-add get_tone_advice to InputEvaluator, or migrate both intake.py call sites to the replacement helper.

#### 10. 🟡 [Medium] `TEST/e2e/test_telegram_adapter.py`

**Description**: Removed TelegramAdapter.capabilities property. Stale scan shows TEST/e2e/test_telegram_adapter.py:60 (caps = adapter.capabilities) exercises it. If the test imports src2.core.platforms.telegram.TelegramAdapter, it now fails with AttributeError.

**Mitigation**: Restore the capabilities property on the adapter, or update the test to read ChannelCapabilities directly. Confirm which adapter the test imports before merge.

#### 11. 🟡 [Medium] `TEST/unit/test_day9_storage.py`

**Description**: Removed StorageService.upload_string and download_string. Stale scan shows TEST/unit/test_day9_storage.py:40 (svc.upload_string(...)) and :51 (svc.download_string(...)). These unit tests will fail with AttributeError against src2 StorageService.

**Mitigation**: Restore upload_string/download_string on StorageService, or rewrite the unit tests against the replacement API.

### Diff Feedback

- `src2/core/schemas/engine.py` (delete LLMRequestPayload/LLMResponsePayload/SerializedProfileContext/SerializedGeJuContext/DailyPillarResolutionResult): NOT dead. `src2/engine/providers/openai.py:26,61` and `src2/engine/providers/gemini.py:24,66` import/construct these at module top-level, and `src2/engine/context_template.py:147,312,329` construct SerializedProfileContext/SerializedGeJuContext. Removing them breaks import of the provider chain → app cannot start.
- `src2/interfaces/telegram/chronomancer/agents.py` (delete MonthlyForecastDeps/DailyForecastResult): MonthlyForecastDeps is NOT dead. `src2/engine/pydantic_prompt_engine.py:342-349,353,513` references and instantiates it. Import + runtime break.
- `src2/interfaces/telegram/db.py` (delete ~20 Database methods): Catastrophic. The scan lists live `src2` callers for get_semantic_id (intake/calendar_node.py:84,200; core/memory/memory_manager.py:42), get_user_tier (security.py:48), set_user_tier (security.py:155), delete_session (session.py:69; app.py:790,792,865,867; pipeline.py:26,105,109), fail_job (queue_worker.py:137), mark_job_pending (queue_worker.py:159), get_reports_for_alias (chronomancer/coordinator.py:551), get_all_reports_for_user (app.py:572,589; pipeline.py:47; chronomancer/coordinator.py:109,553; chronomancer/agents.py:287,581), add_report_metadata (pipeline.py:88), log_chat (app.py:366,409,524,618,669,754,897,927,936,941), upsert_stakeholder (stakeholder_intake.py:96), get_stakeholder_aliases (chronomancer/coordinator.py:401), delete_stakeholder (app.py:484), delete_all_user_data (security.py:84), get_user_prefs (app.py:597,760,829,842; bridge.py:250; chronomancer/coordinator.py:241,351,477,673; chronomancer/agents.py:457), set_user_prefs (app.py:301,303,773,778,781,832). All become AttributeError at runtime.
- `src2/core/memory/memory_manager.py` (delete get_reports_dir/get_profile_path): NOT dead. `src2/interfaces/telegram/pipeline.py:65` calls get_reports_dir; `src2/interfaces/telegram/bridge.py:274` and `src2/interfaces/telegram/chronomancer/coordinator.py:99` call get_profile_path.
- `src2/core/memory/mem0_store.py` (delete delete_user_memories/add_episodic/add_semantic/add_feedback): delete_user_memories NOT dead — `src2/core/memory/memory_manager.py:108` calls self.mem_store.delete_user_memories(resolved_id).
- `src2/core/services/storage.py` (delete upload_string/download_string/delete_file): delete_file NOT dead — `src2/core/services/compliance.py:94` calls storage.delete_file(path).
- `src2/core/tools/bd_config.py` (delete ConfigManager.save): NOT dead — `src2/core/tools/bd_cli.py:40` calls ConfigManager.save(config).
- `src2/core/platforms/telegram.py` (delete TelegramAdapter.capabilities property and TelegramAdapter.close classmethod): close NOT dead — `src2/interfaces/telegram/app.py:73` calls await TelegramAdapter.close(). capabilities only referenced by TEST/e2e/test_telegram_adapter.py:60.
- `src2/interfaces/telegram/evaluation.py` (delete InputEvaluator.get_tone_advice): NOT dead — `src2/interfaces/telegram/intake/intake.py:196,354` call evaluator.get_tone_advice().
- Genuinely dead (verified safe by scan): get_hour_stem (src2) only used by src/, get_user_by_uuid, ContradictionHierarchy, get_sg_now (src2 only called by src/), run_module0_geju, review_narrative, simplify_full_report, call_openrouter_*, DailyForecastResult, DailyPillarResolutionResult, RAGQueryOutput (docs only), rank_days_aggregate (src2 only called by src/), delete_user_prefs, delete_reports_for_user, get_users_with_push_enabled (no src2 caller), send_admin_alert, normalize_step/IntakeData, PipelineMetrics.close (no caller). These removals are correct.


---
## 🚨 Tier: PERFORMANCE

**Go-Live Safe**: NO

### Summary

This "AST cleanup" deletes functions that are still referenced by live production modules, not dead code. The removals cause import-time ImportError in the LLM provider layer, the pydantic prompt engine, and the context-template builder (service will not start), plus runtime AttributeError in hot async paths (DB accessors invoked by request handlers, the job worker, security/tier enforcement, and the push scheduler). Removing TelegramAdapter.close() also leaks the shared async HTTP connection pool. Because Critical import-time breaks and High resource/runtime breaks exist, go_live_safe = False.

### Risk Ledger

#### 1. 🔴 [Critical] `src2/core/schemas/engine.py (LLMRequestPayload, LLMResponsePayload, SerializedProfileContext, SerializedGeJuContext)`

**Description**: These schemas are deleted but still imported/used by live modules: src2/engine/providers/openai.py:26,61 and src2/engine/providers/gemini.py:24,66 (type hints + return value construction) and src2/engine/context_template.py:147,312,329. Removing them raises ImportError at module import time, which propagates up and prevents the engine/provider/context layers from loading. The application cannot start.

**Mitigation**: Do NOT delete these classes, or migrate the references in providers/openai.py, providers/gemini.py, and engine/context_template.py to the new location first. Restore LLMRequestPayload/LLMResponsePayload/SerializedProfileContext/SerializedGeJuContext in engine.py until all live importers are updated.

#### 2. 🔴 [Critical] `src2/interfaces/telegram/chronomancer/agents.py (MonthlyForecastDeps) -> src2/engine/pydantic_prompt_engine.py`

**Description**: MonthlyForecastDeps is deleted, but src2/engine/pydantic_prompt_engine.py:342-353 annotate five Agents with deps_type=MonthlyForecastDeps and :513 constructs MonthlyForecastDeps(...). ImportError at engine load prevents the monthly forecast pipeline from starting.

**Mitigation**: Restore MonthlyForecastDeps in agents.py or relocate it to pydantic_prompt_engine.py and update the import there before deleting.

#### 3. 🟠 [High] `src2/core/platforms/telegram.py (TelegramAdapter.close) -> src2/interfaces/telegram/app.py:73`

**Description**: close() was the only code that did `await _http_client.aclose()` for the global shared async HTTP client. Removing it means the shared connection pool is never closed. app.py:73 still calls `await TelegramAdapter.close()`, so the shutdown path now raises AttributeError and skips cleanup entirely, leaking connections/File descriptors for the process lifetime.

**Mitigation**: Restore the close() classmethod (or replace the app.py:73 call site with a direct `_http_client.aclose()` wired into the FastAPI shutdown event). Ensure _http_client is actually closed on shutdown.

#### 4. 🟠 [High] `src2/interfaces/telegram/db.py (Database) — get_user_tier, set_user_tier, get_user_prefs, set_user_prefs, get_semantic_id, get_all_reports_for_user, get_reports_for_alias, add_report_metadata, log_chat, upsert_stakeholder, get_stakeholder_aliases, delete_stakeholder, delete_all_user_data, delete_session, fail_job, mark_job_pending, get_users_with_push_enabled`

**Description**: All these methods are deleted, yet live callers remain: src2/interfaces/telegram/app.py (572,589,792,867), security.py (48,84,155), pipeline.py (47,105,109), session.py:69, queue_worker.py (137,159), bridge.py:250, chronomancer/coordinator.py (109,241,351,477,551,673), chronomancer/agents.py (287,581), intake/calendar_node.py (84,200), and src/bot/* equivalents. Every call raises AttributeError at runtime in hot async paths — /daily and monthly report handlers, the job worker (fail_job/mark_job_pending), tier/privilege enforcement (get_user_tier/set_user_tier), and the push scheduler (get_users_with_push_enabled). This causes failed requests, worker churn, and retry/error-path overhead.

**Mitigation**: These are NOT dead code. Restore the deleted Database methods, or migrate each caller in the files above to the new persistence layer before removal. At minimum, restore get_user_tier/set_user_tier/get_user_prefs/set_user_prefs/delete_session/fail_job/mark_job_pending/get_all_reports_for_user to unblock core paths.

#### 5. 🟠 [High] `src2/core/memory/mem0_store.py & src2/core/memory/memory_manager.py (delete_user_memories, get_reports_dir, get_profile_path)`

**Description**: delete_user_memories is deleted but called at src2/core/memory/memory_manager.py:108 (`self.mem_store.delete_user_memories(resolved_id)`) and src/memory/memory_manager.py:152. get_reports_dir/get_profile_path are deleted but called at src2/interfaces/telegram/pipeline.py:65, bridge.py:274, chronomancer/coordinator.py:99, chronomancer/agents.py:294,588, and src/bot/pipeline.py:65, src/bot/bridge.py:232. These throw AttributeError when erasure/report-generation paths run.

**Mitigation**: Restore delete_user_memories on Mem0Store, and get_reports_dir/get_profile_path on MemoryManager, or update the callers to new helpers before deletion.

#### 6. 🟠 [High] `src2/interfaces/telegram/evaluation.py (get_tone_advice) & src2/interfaces/telegram/chronomancer/ranking.py (rank_days_aggregate)`

**Description**: get_tone_advice deleted but still called at src2/interfaces/telegram/intake/intake.py:196,354. rank_days_aggregate deleted but referenced at src/bot/chronomancer_handler.py:938 and src2/.../chronomancer/coordinator.py via the 'best' ranking map. Both raise AttributeError in user-facing intake and monthly ranking flows.

**Mitigation**: Restore both functions, or migrate intake.py and chronomancer_handler.py/coordinator.py to the replacement API before deleting.

#### 7. 🟡 [Medium] `src2/interfaces/telegram/metrics.py (PipelineMetrics.close)`

**Description**: close() (which flushed the in-memory metrics buffer) is removed. Any buffered telemetry is never flushed on shutdown, leaking queued metrics and losing observability data.

**Mitigation**: Restore PipelineMetrics.close() and call it from the shutdown hook, or flush the buffer inline in __del__/atexit.

#### 8. 🟢 [Low] `src2/core/calendar/populate_calendar.py (get_hour_stem) & src2/engine/daily_pillar.py (get_sg_now)`

**Description**: get_hour_stem (src2) is deleted while src/calendar/populate_calendar.py:103 still references get_hour_stem; get_sg_now (src2) is deleted while src/bot/chronomancer_handler.py:41,103 still imports/uses it. Because these are src-vs-src2 cross-paths, the break depends on import source, but the stale scan flags them as active references and they must be verified before removal.

**Mitigation**: Confirm the import source for get_hour_stem in src/calendar/populate_calendar.py and get_sg_now in src/bot/chronomancer_handler.py; if they target the deleted src2 symbols, restore or repoint the imports.

#### 9. 🟢 [Low] `src2/core/platforms/telegram.py (TelegramAdapter.capabilities) -> TEST/e2e/test_telegram_adapter.py:60`

**Description**: The capabilities property is removed; the e2e test reads `adapter.capabilities`, which will raise AttributeError. Lower impact (test-only) but still a regression in CI.

**Mitigation**: Restore the capabilities property or update the test to use TelegramAdapter.CAPABILITIES directly.

### Diff Feedback

- src2/core/schemas/engine.py (@@ -602,36 +602,3 @@): Deleting LLMRequestPayload, LLMResponsePayload, SerializedProfileContext, SerializedGeJuContext is UNSAFE. Stale scan proves live importers: src2/engine/providers/openai.py:26,61 and src2/engine/providers/gemini.py:24,66 (type hints + return construction) and src2/engine/context_template.py:147,312,329. Module import fails at startup → entire engine/provider chain dead (Critical availability regression).
- src2/interfaces/telegram/chronomancer/agents.py (class MonthlyForecastDeps removed): Stale scan shows src2/engine/pydantic_prompt_engine.py:342-353 and :513 construct/annotate Agents and deps with this type. ImportError at engine load (Critical).
- src2/interfaces/telegram/db.py (mass deletion of Database methods): get_user_tier, set_user_tier, get_user_prefs, set_user_prefs, get_semantic_id, get_all_reports_for_user, get_reports_for_alias, add_report_metadata, log_chat, upsert_stakeholder, get_stakeholder_aliases, delete_stakeholder, delete_all_user_data, delete_session, fail_job, mark_job_pending, get_users_with_push_enabled are all still called by live files (src2/interfaces/telegram/app.py, security.py, pipeline.py, session.py, queue_worker.py, bridge.py, chronomancer/coordinator.py, chronomancer/agents.py, intake/calendar_node.py, src2/core/memory/memory_manager.py; and src/bot/*). These become AttributeError at request/worker time (High).
- src2/core/platforms/telegram.py (@@ -123,9 +119,3 @@): Removing the close() classmethod deletes the only code path that did `await _http_client.aclose()`. Stale scan shows src2/interfaces/telegram/app.py:73 still calls `await TelegramAdapter.close()`, which will now raise AttributeError and skip cleanup → the global shared async HTTP client / connection pool is leaked (High resource leak).
- src2/core/memory/mem0_store.py & memory_manager.py: delete_user_memories (src2/core/memory/memory_manager.py:108 caller), get_reports_dir (pipeline.py:65, chronomancer/agents.py:294,588, src/memory/memory_manager.py:123), get_profile_path (bridge.py:274, chronomancer/coordinator.py:99, src/bot/bridge.py:232) are live callers → AttributeError (High).
- src2/interfaces/telegram/evaluation.py (get_tone_advice removed): src2/interfaces/telegram/intake/intake.py:196,354 still call it (High). src2/interfaces/telegram/chronomancer/ranking.py (rank_days_aggregate removed): src/bot/chronomancer_handler.py:938 and src2/.../coordinator.py:? still reference it (High).
- src2/interfaces/telegram/metrics.py (@@ -79,6 +79,3 @@): Removing PipelineMetrics.close() drops the shutdown flush() of the buffered metrics → unflushed telemetry buffer leak (Medium).
- src2/core/calendar/populate_calendar.py (get_hour_stem removed) and src2/engine/daily_pillar.py (get_sg_now removed): stale scan flags src/calendar/populate_calendar.py:103 and src/bot/chronomancer_handler.py:41,103 as live references; module cross-path break risk (Low/verify).

---
## 🚨 Tier: TELEMETRY

**Go-Live Safe**: NO

### Summary

This change set does NOT remove dead code — it deletes 40+ live, actively-invoked methods and Pydantic schemas across the src2 persistence, engine, and memory layers. The stale-caller scan confirms live callers in app.py, security.py, pipeline.py, queue_worker.py, coordinator.py, agents.py, intake/, and the engine providers. Multiple deletions cause import-time ImportError (engine cannot start) and the rest cause runtime AttributeError on the main message-handling path. The codebase is non-functional after this diff. go_live_safe = False. Telemetry-wise, the cleanup incidentally removed dev artifacts (hardcoded /home/yapilwsl paths, print()), but also removed the only structured telemetry hooks without replacement.

### Risk Ledger

#### 1. 🔴 [Critical] `src2/interfaces/telegram/db.py (Database class) + src2/interfaces/telegram/* callers`

**Description**: 20+ core persistence methods were deleted from Database while live callers remain across the src2 runtime. Verified stale-caller references: log_chat (app.py:366,409,524,618,669,754,897,927,936,941), get_user_prefs (app.py:597/760/829/842, bridge.py:250, coordinator.py:241/351/477/673, agents.py:457), set_user_prefs (app.py:301/303/773/778/781/832), get_all_reports_for_user (app.py:572/589, pipeline.py:47, coordinator.py:109/553, agents.py:287/581), add_report_metadata (pipeline.py:88), upsert_stakeholder (stakeholder_intake.py:96), delete_stakeholder (app.py:484), get_stakeholder_aliases (coordinator.py:401), get_reports_for_alias (coordinator.py:551), get_user_tier (security.py:48), set_user_tier (security.py:155), delete_session (session.py:69, app.py:790/865, pipeline.py:105/109), fail_job (queue_worker.py:137), mark_job_pending (queue_worker.py:159), get_semantic_id (intake/calendar_node.py:84/200, memory_manager.py:42), delete_all_user_data (security.py:84). Every call resolves to AttributeError at runtime; the bot cannot log chats, store prefs, retrieve reports, manage sessions, or run the job queue.

**Mitigation**: DO NOT delete these methods. Revert the db.py hunk entirely, or restore each method from git history (git show HEAD:src2/interfaces/telegram/db.py) and re-add the full block that was removed. Validate with `python -c 'import src2.interfaces.telegram.db'` and `python -c 'import src2.interfaces.telegram.app'` after restore.

#### 2. 🔴 [Critical] `src2/core/schemas/engine.py + src2/engine/providers/* + src2/engine/context_template.py + src2/engine/pydantic_prompt_engine.py`

**Description**: LLMRequestPayload, LLMResponsePayload, SerializedProfileContext, SerializedGeJuContext (engine.py) and MonthlyForecastDeps (agents.py) were deleted, but active importers remain: src2/engine/providers/openai.py:26,61 and gemini.py:24,66 (LLMRequestPayload/LLMResponsePayload), src2/engine/context_template.py:147,312,329 (Serialized*Context), and src2/engine/pydantic_prompt_engine.py:342-349,353,513 (MonthlyForecastDeps, used as deps_type, RunContext param, and constructor). With no remaining definition, these modules raise ImportError on import, so the engine package and everything that imports it (app startup) fails before any request is served.

**Mitigation**: Revert the engine.py schema deletion and the agents.py MonthlyForecastDeps deletion, OR relocate the classes to a still-imported module and update the importers. Verify: `python -c 'import src2.engine.providers.openai, src2.engine.pydantic_prompt_engine, src2.engine.context_template'` must succeed after fix.

#### 3. 🔴 [Critical] `src2/interfaces/telegram/security.py:84 (db.delete_all_user_data)`

**Description**: delete_all_user_data was deleted from Database, but security.py:84 still calls db.delete_all_user_data(user_id) to honor right-to-erasure / account deletion. This is a hard compliance/GDPR control; after the change it raises AttributeError, so user data deletion is silently broken (the exception will propagate up and the /delete flow crashes, leaving all PII intact).

**Mitigation**: Restore delete_all_user_data in db.py from git history. Add a regression test asserting deletion cascades all 10 tables (ChatLog, DailyForecast, JobQueue, Report, Stakeholder, UserPreference, DbSession, ConsentRecord, UserPromoUsage, PlatformAccount, User).

#### 4. 🟠 [High] `src2/core/memory/memory_manager.py + src2/core/memory/mem0_store.py`

**Description**: MemoryManager.get_reports_dir (called pipeline.py:65) and get_profile_path (called bridge.py:274) were deleted; Mem0Store.delete_user_memories (called memory_manager.py:108) was deleted. All three call sites now raise AttributeError. The memory-manager erasure path (delete_user_memories) is also a compliance gap for vector-store data deletion.

**Mitigation**: Restore get_reports_dir, get_profile_path in memory_manager.py and delete_user_memories in mem0_store.py from git history. Confirm bridge.py:274 and pipeline.py:65 resolve.

#### 5. 🟠 [High] `src2/core/platforms/telegram.py (TelegramAdapter)`

**Description**: TelegramAdapter.close() classmethod and the capabilities property were deleted. app.py:73 calls `await TelegramAdapter.close()` during shutdown/lifecycle; capabilities is part of the ChannelAdapter contract consumed by tests and adapters. Both now raise AttributeError.

**Mitigation**: Restore close() (re-open the shared _http_client guard) and the capabilities property, or update app.py:73 to the new shutdown API. Add an import/smoke test for the adapter.

#### 6. 🟠 [High] `src2/core/tools/bd_config.py (ConfigManager.save) + src2/core/tools/bd_cli.py:40`

**Description**: ConfigManager.save was deleted but bd_cli.py:40 calls ConfigManager.save(config). CLI config writes now raise AttributeError; the bd CLI tool is broken.

**Mitigation**: Restore ConfigManager.save (atomic write with .tmp + os.replace and UTC timestamp) from git history; keep it since bd_cli.py depends on it.

#### 7. 🟠 [High] `src2/core/services/storage.py (StorageService.delete_file) + src2/core/services/compliance.py:94`

**Description**: delete_file (and upload_string/download_string) were removed from StorageService, but compliance.py:94 calls storage.delete_file(path) to remove offloaded compliance artifacts. This raises AttributeError and breaks the compliance data-retention/deletion path.

**Mitigation**: Restore delete_file (and upload_string/download_string if used elsewhere) in StorageService from git history, or rewrite compliance.py:94 to use a different client method.

#### 8. 🟡 [Medium] `src2/interfaces/telegram/evaluation.py (InputEvaluator.get_tone_advice) + intake/intake.py:196,354`

**Description**: get_tone_advice was deleted but intake.py:196 and :354 call evaluator.get_tone_advice(); both now raise AttributeError, breaking intake feedback generation.

**Mitigation**: Restore get_tone_advice in evaluation.py from git history, or remove its calls in intake.py.

#### 9. 🟡 [Medium] `src2/core/platforms/telegram.py (capabilities) + TEST/e2e/test_telegram_adapter.py:60`

**Description**: The capabilities property removal violates the ChannelAdapter ABC contract; the e2e test at test_telegram_adapter.py:60 reads adapter.capabilities and will fail. More broadly, deleting observable capability metadata reduces runtime introspection needed for telemetry/routing.

**Mitigation**: Restore the capabilities property or update the ABC/test contract. Do not delete contract-required members during 'cleanup'.

#### 10. ℹ️ [Informational] `src2/engine/narrative_simplifier.py + src2/engine/openrouter.py (removed code)`

**Description**: From a strict telemetry gate view the diff did one good thing: it removed dev artifacts — simplify_full_report wrote to hardcoded absolute paths (/home/yapilwsl/arthityap/baziforecaster/logs/Time_Monthly_Reports, logs/Logfire) and openrouter.py contained print() and emoji logger.error calls. However, those were the ONLY structured telemetry hooks for LLM calls and monthly-report timing; their removal regresses observability with no replacement. No new TODO/FIXME/HACK/print() statements were introduced in the diff (verified from the diff text; grep not available in this audit session).

**Mitigation**: After restoring the correctly-live functions above, reintroduce structured (JSON) telemetry via the existing logging/metrics layer (e.g., PipelineMetrics) rather than hardcoded file paths, and gate any debug logging behind env vars.

### Diff Feedback

- src2/interfaces/telegram/db.py: DELETED get_semantic_id, get_user_tier, set_user_tier, delete_session, fail_job, mark_job_pending, get_reports_for_alias, get_all_reports_for_user, add_report_metadata, log_chat, upsert_stakeholder, get_stakeholder_aliases, delete_stakeholder, delete_user_prefs, delete_reports_for_user, delete_all_user_data, get_user_prefs, set_user_prefs, get_users_with_push_enabled. The stale scan proves every one of these is still called by live src2 modules (app.py:366/409/524/572/589/597/760/829/842/484/301/303/773/778/781/832; security.py:48/84/155; pipeline.py:47/65/88/105/109; session.py:69; queue_worker.py:137/159; stakeholder_intake.py:96; coordinator.py:109/241/351/401/477/551/553/673; agents.py:287/457/581; bridge.py:250; intake/calendar_node.py:84/200). Each call now raises AttributeError. This single file deletion breaks the entire bot runtime.
- src2/core/schemas/engine.py: DELETED LLMRequestPayload, LLMResponsePayload, SerializedProfileContext, SerializedGeJuContext, DailyPillarResolutionResult. Stale scan shows src2/engine/providers/openai.py:26,61, gemini.py:24,66, and src2/engine/context_template.py:147,312,329 still import/use them. With no remaining definition, these modules fail at import time → the engine package cannot be imported → app startup fails.
- src2/interfaces/telegram/chronomancer/agents.py: DELETED MonthlyForecastDeps. Stale scan shows src2/engine/pydantic_prompt_engine.py:342-349,353,513 references it (deps_type=, ctx: RunContext[...], deps=MonthlyForecastDeps(...)). ImportError at engine import.
- src2/core/memory/memory_manager.py: DELETED get_reports_dir, get_profile_path; stale scan shows pipeline.py:65 (memory_manager.get_reports_dir) and bridge.py:274 (memory_manager.get_profile_path) call them → AttributeError.
- src2/core/memory/mem0_store.py: DELETED delete_user_memories; stale scan shows memory_manager.py:108 calls self.mem_store.delete_user_memories → AttributeError + broken erasure.
- src2/core/platforms/telegram.py: DELETED TelegramAdapter.close() classmethod and capabilities property; app.py:73 calls await TelegramAdapter.close() → AttributeError; capabilities referenced by ChannelAdapter consumers.
- src2/core/tools/bd_config.py: DELETED ConfigManager.save; bd_cli.py:40 calls ConfigManager.save(config) → AttributeError.
- src2/core/services/storage.py: DELETED delete_file (also upload_string, download_string); compliance.py:94 calls storage.delete_file(path) → AttributeError.
- src2/interfaces/telegram/evaluation.py: DELETED get_tone_advice; intake/intake.py:196,354 call it → AttributeError.
- src2/engine/narrative_simplifier.py: DELETED simplify_full_report (good riddance — it wrote to hardcoded /home/yapilwsl/arthityap/... paths and Logfire files), but no replacement structured telemetry was added.
- src2/engine/openrouter.py: DELETED call_openrouter_async/stream/with_history (contained print() and emoji logger calls) — these were the only places LLM call telemetry existed; their removal regresses observability (informational).

---
## How to Fix (Copy-Paste into runner.yaml)

If Go Live is BLOCKED, copy the relevant findings above into the `task:` field of `admin/subagents/runner.yaml`, then run:

```bash
uv run python -m admin.subagents.runner
```

After the runner finishes, re-run this audit to confirm all findings are resolved.
