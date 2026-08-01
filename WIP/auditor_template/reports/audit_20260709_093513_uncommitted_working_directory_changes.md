# Red-Team Fiduciary Audit Report

**Scope**: uncommitted working directory changes
**Tiers**: security, logic, performance, telemetry
**Model**: `auditor_model` → `OpenAIChatModel()`
**Timestamp**: 2026-07-09T09:35:13.210986+00:00

## Verdict: 🚨 GO LIVE BLOCKED

**Auditor Notes**: Verify overall correctness and logic of our recent AST codebase cleanup. Confirm that removing dead code functions does not break callers.


---
## 🚨 Tier: SECURITY

**Go-Live Safe**: NO

### Summary

This diff is a dead-code cleanup removing 13 unused functions/classes from the src2 tree. The pre-computed stale-reference scan shows NO production callers reference the deleted symbols (the only dangling reference to deleted RAGQueryOutput is in a non-production `_docs/` review script). The blocking risk is in `src2/interfaces/telegram/db.py`: the removed `delete_reports_for_user` and `delete_user_prefs` were the only methods in that file that delete `Report` and `UserPreference` rows, and the documented right-to-erasure entry point `delete_all_user_data` (body not in diff) may delegate to them — data-erasure completeness is now unverified and must be confirmed before release.

### Risk Ledger

#### 1. 🟠 [High] `src2/interfaces/telegram/db.py :: delete_all_user_data`

**Description**: The diff deletes `delete_user_prefs` (lines 944-951) and `delete_reports_for_user` (lines 953-971). These were the ONLY methods in `Database` that issue `session.query(UserPreference).filter_by(...).delete()` and `session.query(Report).filter_by(...).delete()` (the latter also cascading `delete_daily_forecasts_for_user`). The remaining `delete_all_user_data(self, chat_id)` (lines 972+, body NOT present in the diff) is the documented right-to-erasure entry point whose docstring explicitly promises 'no orphaned records remain (especially in SQLite without foreign_keys=ON)'. Under zero-trust we must assume `delete_all_user_data` delegated to these helpers. If so, (a) the erasure flow raises AttributeError at runtime and fails entirely, or (b) `Report`/`UserPreference` rows containing user PII are left orphaned. Either outcome is a data-retention / right-to-erasure (privacy/compliance) defect. This cannot be disproven from the supplied diff.

**Mitigation**: Before merge, open `delete_all_user_data` and confirm it directly deletes from `UserPreference` and `Report` (and daily forecasts) tables. If it calls `self.delete_reports_for_user(...)` / `self.delete_user_prefs(...)`, restore those methods OR inline equivalent `session.query(...).delete()` statements for both tables, then add a regression test asserting `delete_all_user_data` leaves zero rows in UserPreference/Report/DailyForecast for the user.

#### 2. 🟢 [Low] `src2/interfaces/telegram/schemas.py :: IntakeData`

**Description**: Removed `IntakeData` (lines 120-153) carried `sanitize_alias` (rejects `<>&"` — a Markdown/HTML injection guard for user-supplied alias) and `validate_dob` (enforces `YYYY-MM-DD`/`YYYY-MM-DD HH:MM` format and rejects future birthdates). The stale-caller scan lists no production references, so it appears dead, but removal of a sanitization/validation contract is security-relevant if any intake path instantiates `IntakeData` via a dynamic/registry mechanism not captured by the static scan.

**Mitigation**: Grep the full src2 tree and any entrypoint for `IntakeData` usage (including `IntakeData(**...)` and class registries). If a live intake path remains, confirm an equivalent alias-sanitization and dob-validation contract exists on the replacement schema; otherwise the alias field becomes an injection sink in Telegram/markdown rendering.

#### 3. 🟢 [Low] `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py:34`

**Description**: Deleted `RAGQueryOutput` (src2/interfaces/telegram/chronomancer/rag.py lines 106-110) is still referenced by `output_type=RAGQueryOutput` in a `_docs/` review script. Per audit rules documentation files are not evidence of a production break, and this is non-production, but the script will now raise ImportError if executed.

**Mitigation**: Either delete/repair `07_Refactor_Production_Scripts/chronomancer_rag.py` to not import the removed `RAGQueryOutput`, or confirm it is intentionally abandoned. No production impact; track as code-hygiene cleanup.

#### 4. ℹ️ [Informational] `src/engine/openrouter.py (legacy src tree)`

**Description**: The stale scan reports active `query_classical_text` references inside `src/engine/openrouter.py` (the OLD `src/` tree: lines 180, 221, 233, 240, 468, 487). This diff only modifies `src2/` and does NOT delete `query_classical_text` (it resides in `src2/engine/rag_client.py`). These are pre-existing cross-tree references and are not broken by this change, but they indicate two parallel code trees (`src/` and `src2/`) — a maintenance/audit-surface risk.

**Mitigation**: Confirm the `src/` tree is intentionally retired; if so, schedule its removal to eliminate duplicate LLM/RAG call paths that could independently mishandle API keys (the old `src/engine/openrouter.py` still reads `settings.openrouter_api_key`). No action required for THIS diff.

### Diff Feedback

- `src2/core/identity/service.py` (lines 19-23 removed `get_user_by_uuid`): No stale callers in scan. Safe deletion.
- `src2/core/memory/mem0_store.py` (lines 415-428 removed `add_episodic`/`add_semantic`/`add_feedback`): No stale callers. Safe deletion; these were thin wrappers over `add_memory`.
- `src2/core/schemas/engine.py` (lines 635-638 removed `DailyPillarResolutionResult`): No stale callers. Safe.
- `src2/engine/contradiction_resolver.py` (lines 29-35 removed `ContradictionHierarchy`): No stale callers. Safe.
- `src2/engine/module0_geju.py` (lines 818-840 removed `run_module0_geju`): No stale callers. Safe.
- `src2/engine/narrative_review.py` (lines 67-95 removed `review_narrative`): No stale callers. Safe (note: this also removes LLM-prompt construction that embedded raw scoring data — no new injection surface introduced by removal).
- `src2/engine/narrative_simplifier.py` (lines 216-284 removed `simplify_full_report`): No stale callers for the function itself. The removed code contained hardcoded absolute paths (`/home/yapilwsl/arthityap/baziforecaster/logs/...`) and imported `simplify_month_narrative_task`; that Celery task is NOT deleted and is still referenced in `src2/interfaces/telegram/app.py` — so those references remain valid. Removing the hardcoded-path logging is an improvement.
- `src2/engine/openrouter.py` (lines 148-495 removed `call_openrouter_async`/`stream_openrouter_async`/`call_openrouter_async_with_history`/`call_openrouter_sync`): None of these four names appear in the stale-caller scan, so no production module imports them. The removed code carried `api_key = settings.openrouter_api_key` / `Bearer` header handling and `query_classical_text` calls — these are eliminated cleanly. NOTE: the scan lists `query_classical_text` references in `src/engine/openrouter.py` (the OLD `src/` tree, not in this diff); `query_classical_text` itself is NOT deleted in this diff (it lives in `src2/engine/rag_client.py`), so those old-tree references are pre-existing and out of scope.
- `src2/interfaces/telegram/chronomancer/agents.py` (lines 46-55 removed `DailyForecastResult`): No stale callers. Safe.
- `src2/interfaces/telegram/chronomancer/rag.py` (lines 106-110 removed `RAGQueryOutput`): Dangling reference at `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py:34` (`output_type=RAGQueryOutput`); that is a non-production docs script and is excluded as evidence of a production break, but it will now ImportError.
- `src2/interfaces/telegram/db.py` (lines 944-971 removed `delete_user_prefs` and `delete_reports_for_user`): CRITICAL REVIEW AREA. These were the only methods that delete `UserPreference` and `Report` rows (and `delete_reports_for_user` also cascades `delete_daily_forecasts_for_user`). `delete_all_user_data` (lines 972+, body NOT in diff) is the documented right-to-erasure path whose docstring guarantees "no orphaned records remain (especially in SQLite without foreign_keys=ON)". If it delegates to these helpers, erasure now raises `AttributeError` (full failure) or silently leaves `Report`/`UserPreference` PII orphaned. This cannot be disproven from the diff.
- `src2/interfaces/telegram/reliability.py` (lines 57-86 removed `send_admin_alert`): No stale callers. Safe. (Removal also eliminates a path that forwarded raw `error_trace` text to Telegram — no new leak surface.)
- `src2/interfaces/telegram/schemas.py` (lines 40-46 removed `SessionState.normalize_step` validator; lines 120-153 removed `IntakeData` incl. `sanitize_alias` and `validate_dob`): No stale callers in scan for `IntakeData`. Removing `sanitize_alias` (blocks `<>&"`) and `validate_dob` (rejects future dates / validates format) eliminates input-validation/sanitization logic — if any live intake path still constructs `IntakeData`, this is an XSS/format-validation regression. Verify before release.

---
## ✅ Tier: LOGIC

**Go-Live Safe**: YES

### Summary

This is a dead-code purge removing 13+ unused symbols across src2 (identity, memory, schemas, engine, telegram interfaces). The dependency scan confirms no production (src2) caller of any deleted symbol except `RAGQueryOutput`, whose only remaining reference lives in a non-runtime `_docs/REVIEW` scratch script. References to `query_classical_text`, `settings`, and `simplify_month_narrative_task` flagged by the scan are internal to the deleted `openrouter`/`simplifier` functions (removed together) or in the untouched `src/` v1 tree — those symbols still exist, so no runtime breakage occurs. Two Low-severity hygiene items remain: a dangling `RAGQueryOutput` import in `_docs` and a behavioral change from removing the `SessionState.normalize_step` validator.

### Risk Ledger

#### 1. 🟢 [Low] `src2/interfaces/telegram/chronomancer/rag.py (RAGQueryOutput) → _docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py:34`

**Description**: RAGQueryOutput is deleted from rag.py, but the stale-scan shows a remaining usage at _docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py:34 (`output_type=RAGQueryOutput`). If that reference/scratch script is ever executed it will raise ImportError. The path lives under _docs/REVIEW (a refactor-planning scratch directory), not the src2 runtime tree, so it does not affect production deployment — but it is a genuine dangling reference.

**Mitigation**: Remove or update the import/usage in _docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py (point it at the replacement output model or delete the scratch script). Acceptable as tracked tech-debt since it is outside the production import graph.

#### 2. 🟢 [Low] `src2/interfaces/telegram/schemas.py — SessionState.normalize_step validator (lines ~40-49)`

**Description**: Removal of the normalize_step field_validator is a behavioral change, not pure dead-code removal: SessionState.step no longer defaults empty→'START' nor upper-cases input. Any consumer that constructs SessionState and later compares `state.step` against upper-cased constants (e.g. 'INTAKE', 'START') may now mismatch on lowercase/empty values. The stale-caller scan shows no direct references to normalize_step, but the construction semantics of a runtime-used model changed.

**Mitigation**: Grep for `SessionState(` and `\.step` comparisons across src2 to confirm every construction site supplies step already upper-cased and non-empty, or reintroduce the validator. Required before declaring the cleanup behavior-preserving for the intake/state machine.

### Diff Feedback

**src2/core/identity/service.py (lines ~16-22):** `get_user_by_uuid` removed. Scan shows zero callers. `get_user_by_platform` and `create_user` remain intact. No orphaned references. SAFE.

**src2/core/memory/mem0_store.py (lines ~412-428):** `add_episodic`, `add_semantic`, `add_feedback` removed. The underlying `add_memory(user_id, text, memory_type=, metadata=)` is retained and unchanged. Scan shows no external callers. SAFE.

**src2/core/schemas/engine.py (lines ~632-636):** `DailyPillarResolutionResult` removed. `SerializedGeJuContext` retained. Scan silent → no callers. SAFE.

**src2/engine/contradiction_resolver.py (lines ~26-36):** `ContradictionHierarchy` IntEnum removed. No callers in scan. Note: this is a semantic enum (SPECIFICITY=1..USE_GOD=4); if any priority-comparison logic referenced these constants it would break — but scan shows none. SAFE.

**src2/engine/module0_geju.py (lines ~815-839):** `run_module0_geju` pipeline wrapper removed. Callees `classify_ge_ju`, `validate_special_structure`, `compute_ge_ju_alignment_mod` all retained. No callers. SAFE.

**src2/engine/narrative_review.py (lines ~64-96):** `review_narrative` removed. `LazyAgentProxy`/`narrative_agent` retained. No callers. SAFE.

**src2/engine/narrative_simplifier.py (lines ~213-284):** `simplify_full_report` removed. Its local import `from src2.worker.tasks import simplify_month_narrative_task` is deleted with the function. `simplify_month_narrative_task` itself still exists (referenced by src2/interfaces/telegram/app.py per scan), so the scan's `simplify_month_narrative_task` staleness is a self-reference wiped by the deletion, not a break. Hardcoded log writes under `/home/yapilwsl/arthityap/baziforecaster/logs/...` are also deleted with it. No callers. SAFE.

**src2/engine/openrouter.py (lines ~145-494):** `call_openrouter_async`, `stream_openrouter_async`, `call_openrouter_async_with_history`, `call_openrouter_sync` removed. Retained helpers: `_get_provider_adapter`, `throttle_async`, `_prepare_request_headers`, `_clean_llm_response`, `_resolve_provider_dynamically`. The local imports `from .rag_client import query_classical_text` and `from admin.controls.controls import settings` lived INSIDE the deleted functions and were removed with them — no dangling module-level imports remain. The scan's `query_classical_text`/`settings` references at `src2/engine/openrouter.py:180/221/233/240/468/487` are the now-deleted function bodies (self-deleting), and the `src/engine/openrouter.py` references are the untouched v1 module; both symbols still exist. SAFE — no runtime breakage.

**src2/interfaces/telegram/chronomancer/agents.py (lines ~43-56):** `DailyForecastResult` removed. `Advisory` retained. No external callers. SAFE.

**src2/interfaces/telegram/chronomancer/rag.py (lines ~103-112):** `RAGQueryOutput` removed. `get_rag_agent`/`RAG_INSTRUCTIONS` retained. SCAN FLAG: `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py:34` still uses `output_type=RAGQueryOutput`. This is a non-runtime refactor scratch script (path `07_Refactor_Production_Scripts`), NOT in the src2 production tree — so it does not break deployment, but it is a dangling import. See Low finding #1.

**src2/interfaces/telegram/db.py (lines ~944-970):** `delete_user_prefs` and `delete_reports_for_user` removed. `delete_all_user_data` retained and still calls `delete_daily_forecasts_for_user` (present). No external callers. SAFE.

**src2/interfaces/telegram/reliability.py (lines ~54-90):** `send_admin_alert` removed. `send_telegram_message` retained. No callers in scan. Behavioral note: any prior error path that pushed alerts to admin/channel now silently drops them; since scan shows no call sites, treat as dead. Recommend a final grep for `send_admin_alert(` across src2 to confirm zero remaining callers.

**src2/interfaces/telegram/schemas.py (lines ~40-49 and ~111-148):** Two removals: (a) `SessionState.normalize_step` field_validator — a BEHAVIORAL change (step no longer defaults empty→"START" nor upper-cases), not pure dead code; (b) `IntakeData` class (with alias/dob validators) — if this was the canonical intake model its removal is a logic change. Scan shows no direct callers of either, but the `normalize_step` semantics change is worth verification. See Low finding #2.

---
## ✅ Tier: PERFORMANCE

**Go-Live Safe**: YES

### Summary

This diff is a pure dead-code elimination across 13 source files; 100% of the changes are deletions of functions, classes, and Pydantic schemas that the provided dependency scan confirms have zero remaining production callers. No new loops, blocking I/O, DB queries, or allocations are introduced, and the removal of the openrouter async functions plus simplify_full_report actually eliminates pre-existing event-loop-blocking calls (sync query_classical_text inside async context) and per-month synchronous file I/O. The only residual reference is a non-runtime dangling import inside a `_docs` review script; no Critical or High performance regressions exist, so the change is go-live safe.

### Risk Ledger

#### 1. 🟢 [Low] `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py:34`

**Description**: Stale dependency scan shows `output_type=RAGQueryOutput` at line 34 of this review-script file. `RAGQueryOutput` is deleted from `src2/interfaces/telegram/chronomancer/rag.py`. This file lives under `_docs/REVIEW/...` (a non-runtime refactor artifact, underscore-prefixed, not part of the deployed package), so it is not executed in production and triggers no runtime downtime. If the script were ever run it would raise ImportError.

**Mitigation**: Either delete `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py` or update its import to the surviving agent/output type. Non-blocking for go-live; schedule as cleanup.

### Diff Feedback

`src2/core/identity/service.py` (removed `get_user_by_uuid`, old lines 19-22): single indexed PK lookup wrapper with no callers per scan. Removal is O(1)-cost-free and safe.

`src2/core/memory/mem0_store.py` (removed `add_episodic`/`add_semantic`/`add_feedback`, old lines 415-427): thin one-line delegators to `add_memory`. No callers. Safe; no allocation or I/O change.

`src2/core/schemas/engine.py` (removed `DailyPillarResolutionResult`, old lines 635-637): unused Pydantic model. No callers. Safe.

`src2/engine/contradiction_resolver.py` (removed `ContradictionHierarchy` IntEnum, old lines 29-35): constants only, no callers. Safe; no runtime cost removed that affects anything.

`src2/engine/module0_geju.py` (removed `run_module0_geju`, old lines 818-840): synchronous pipeline wrapper, no callers. Safe. Removes no hot-path logic relied on by survivors.

`src2/engine/narrative_review.py` (removed `review_narrative`, old lines 67-95): async agent round-trip, no callers. Its removal deletes one LLM call site — net compute reduction.

`src2/engine/narrative_simplifier.py` (removed `simplify_full_report`, old lines 216-282): this is the only deleted function with any real performance footprint. It performed `os.makedirs` + synchronous `open(...,"a").write(...)` per month (twice per iteration) and `task.get()` via `run_in_executor`. The `run_in_executor` pattern was correct, but the per-month blocking file writes were an avoidable sync-I/O cost. No callers (stale scan lists `simplify_month_narrative_task` as referenced by `app.py` lines 153/183, but that is the Celery task itself, NOT deleted). Net performance-positive to remove.

`src2/engine/openrouter.py` (removed `call_openrouter_async`, `stream_openrouter_async`, `call_openrouter_async_with_history`, `call_openrouter_sync`, old lines 148-494): these contained a blocking synchronous `query_classical_text(...)` call inside `async with httpx.AsyncClient` (event-loop-blocking anti-pattern) and unbounded `time.sleep`/`asyncio.sleep` retry backoffs. No callers per scan. Removing them eliminates a genuine async-runtime blockage. NOTE: `src/engine/openrouter.py` (the OLD `src` tree, not `src2`) still imports `query_classical_text`, but `query_classical_text` is NOT deleted by this diff — so this is a non-issue.

`src2/interfaces/telegram/chronomancer/agents.py` (removed `DailyForecastResult`, old lines 46-56): schema with no callers. Safe.

`src2/interfaces/telegram/chronomancer/rag.py` (removed `RAGQueryOutput`, old lines 106-110): only remaining reference is `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py:34` — a non-runtime review script under `_docs/`. See Low finding.

`src2/interfaces/telegram/db.py` (removed `delete_user_prefs`/`delete_reports_for_user`, old lines 944-971): narrow bulk-delete helpers; `delete_all_user_data` (comprehensive cleanup) remains. No callers. Safe.

`src2/interfaces/telegram/reliability.py` (removed `send_admin_alert`, old lines 57-89): no callers. Safe.

`src2/interfaces/telegram/schemas.py` (removed `normalize_step` validator, old lines 40-45, and `IntakeData` class, old lines 121-148): no callers. Removing `normalize_step` actually drops a small per-deserialization validation cost (marginal improvement). Out-of-tier logic note: any code relying on upper-cased `step` values must be re-checked, but that is correctness, not performance.

STALE-SCAN TRIAGE: Of the four symbols the scan flagged — `query_classical_text`, `settings`, and `simplify_month_narrative_task` are NOT deleted by this diff (confirmed: only callers/imports of surviving symbols) and are false positives. Only `RAGQueryOutput` was deleted, and its sole residual reference is a non-production `_docs` file. No broken production caller exists for any deleted symbol.

---
## ✅ Tier: TELEMETRY

**Go-Live Safe**: YES

### Summary

This change is purely subtractive: it removes 20 dead functions/classes across the src2 tree with no new code or logging added. Per the pre-computed stale-caller scan, the only remaining reference to a removed symbol is `RAGQueryOutput` inside a non-production `_docs/REVIEW` refactor scratch file (line 34); all other scan hits (`query_classical_text`, `settings`, `simplify_month_narrative_task`) point to symbols that are NOT removed in this diff and remain defined/importable. No in-source production caller of any removed symbol exists, so the cleanup does not break telemetry or call paths in the running system.

### Risk Ledger

#### 1. 🟢 [Low] `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py:34`

**Description**: Stale caller scan shows `output_type=RAGQueryOutput` referencing the `RAGQueryOutput` class removed from `src2/interfaces/telegram/chronomancer/rag.py`. This file lives under the non-production `_docs/REVIEW` refactor-scratch directory, not the deployed source tree, so it does not block go-live. However, the artifact will fail at import/run time if executed.

**Mitigation**: Delete or update `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py` to drop the `RAGQueryOutput` reference (e.g., inline a local model or repoint to the current agent output schema). This is a hygiene fix only; not in the production path.

#### 2. ℹ️ [Informational] `src2/engine/narrative_simplifier.py (removed simplify_full_report)`

**Description**: The removed function held the only monthly-report timing/telemetry instrumentation, writing plaintext (non-JSON) lines to hardcoded absolute WSL paths (`/home/yapilwsl/arthityap/baziforecaster/logs/Time_Monthly_Reports/monthly_timing.log` and `.../Logfire/logfire_telemetry.log`). Because it is dead code (no callers per scan), its removal is acceptable cleanup and actually improves telemetry conformance (no hardcoded dev paths, no stray file I/O). No replacement telemetry was added.

**Mitigation**: Confirm product leadership does not require monthly-report performance telemetry. If required, re-implement it as structured JSON logs via the existing logger (no hardcoded absolute paths, no `open()` file appends) in a live code path rather than a deleted dead function.

### Diff Feedback

- `src2/core/identity/service.py`: `get_user_by_uuid` removed; `get_user_by_platform` retained. Scan shows no remaing callers of the removed fn. OK.
- `src2/core/memory/mem0_store.py`: `add_episodic`/`add_semantic`/`add_feedback` removed; `search()` retained. No stale callers in scan. OK.
- `src2/core/schemas/engine.py`: `DailyPillarResolutionResult` removed. No references in scan. OK.
- `src2/engine/contradiction_resolver.py`: `ContradictionHierarchy(IntEnum)` removed. No remaining references. OK.
- `src2/engine/module0_geju.py`: `run_module0_geju` removed. No callers in scan. OK.
- `src2/engine/narrative_review.py`: `review_narrative` removed. No callers in scan. OK.
- `src2/engine/narrative_simplifier.py`: `simplify_full_report` removed. This deletion also eliminates a `print()`-free but non-conformant plaintext telemetry writer that hardcoded WSL host paths (`/home/yapilwsl/arthityap/baziforecaster/logs/Time_Monthly_Reports` and `.../Logfire/logfire_telemetry.log`) and wrote non-JSON timing lines. Removing hardcoded dev-path logging is a positive telemetry cleanup, and the scan confirms no live callers, so no observability regression for the running system.
- `src2/engine/openrouter.py`: Removed `call_openrouter_async`, `stream_openrouter_async`, `call_openrouter_async_with_history`, `call_openrouter_sync`. These contained a raw `print(f"\n❌ Google API Error Response...")` in a production path and the `query_classical_text` tool-call sites — both removed cleanly. Note: `src/engine/openrouter.py` (the `src` module, NOT `src2`, and NOT in this diff) still imports `query_classical_text` from `src.engine.rag_client`; that is out of scope and unaffected since the symbol is not deleted.
- `src2/interfaces/telegram/chronomancer/agents.py`: `DailyForecastResult` removed. No scan references. OK.
- `src2/interfaces/telegram/chronomancer/rag.py`: `RAGQueryOutput` removed. Only remaining reference is `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py:34` (non-production review artifact). See Low risk.
- `src2/interfaces/telegram/db.py`: `delete_user_prefs` / `delete_reports_for_user` removed; `delete_all_user_data` retained. No scan callers. OK.
- `src2/interfaces/telegram/reliability.py`: `send_admin_alert` removed. No remaing callers in scan; best-effort admin alerting path is gone but no live callers reference it.
- `src2/interfaces/telegram/schemas.py`: `normalize_step` field_validator and the `IntakeData` model (with `sanitize_alias`/`validate_dob` validators) removed. No scan references; both were dead. OK.

---
## How to Fix (Copy-Paste into runner.yaml)

If Go Live is BLOCKED, copy the relevant findings above into the `task:` field of `admin/subagents/runner.yaml`, then run:

```bash
uv run python -m admin.subagents.runner
```

After the runner finishes, re-run this audit to confirm all findings are resolved.
