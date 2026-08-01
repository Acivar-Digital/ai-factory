# Stale Callers & Imports Identified in codebase

### Stale References for: `RAGQueryOutput`
  - `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/chronomancer_rag.py:34`: output_type=RAGQueryOutput,

### Stale References for: `query_classical_text`
  - `_docs/DEV/V31/88_scripts/book_audit.py:34`: "name": "query_classical_text",
  - `_docs/DEV/V31/88_scripts/book_audit.py:57`: if name != "query_classical_text":
  - `_docs/DEV/V31/88_scripts/book_audit.py:67`: from src.engine.rag_client import query_classical_text
  - `_docs/DEV/V31/88_scripts/book_audit.py:68`: result = query_classical_text(query=query, top_k=5)
  - `_docs/DEV/V31/88_scripts/book_audit.py:84`: You have `query_classical_text` to search four classical texts: 《渊海子平》《三命通会》《地天师》《穷通宝鉴》.
  - `_docs/DEV/V31/88_scripts/book_audit.py:152`: f"Use query_classical_text (up to {cfg.max_tool_calls_per_chapter} calls) to verify classical citations."
  - `_docs/DEV/V31/88_scripts/test_api.py:34`: "name": "query_classical_text",
  - `_docs/DEV/V31/88_scripts/test_api.py:190`: print("TEST 4: Tool Call Round-Trip (query_classical_text)")
  - `_docs/DEV/V31/88_scripts/test_api.py:201`: "You have access to the query_classical_text tool to search classical texts. "
  - `_docs/DEV/V31/88_scripts/test_api.py:210`: "Use your query_classical_text tool to verify this claim against classical sources. "
  - `_docs/DEV/V31/88_scripts/test_api.py:256`: if fn_name != "query_classical_text":
  - `_docs/DEV/V31/88_scripts/test_api.py:257`: print(f"\n  ❌ TEST 4 FAILED — Expected tool 'query_classical_text', got '{fn_name}'")
  - `_docs/DEV/V31/88_scripts/test_api.py:276`: "name": "query_classical_text",
  - `src/engine/openrouter.py:180`: from src.engine.rag_client import query_classical_text
  - `src/engine/openrouter.py:221`: if tc["function"]["name"] == "query_classical_text":
  - `src/engine/openrouter.py:232`: logger.info(f"    🔧 Tool called (Turn {turn + 1}): query_classical_text(query='{query_val}')")
  - `src/engine/openrouter.py:233`: context = query_classical_text(
  - `src/engine/openrouter.py:240`: "name": "query_classical_text",
  - `src/engine/openrouter.py:468`: from src.engine.rag_client import query_classical_text
  - `src/engine/openrouter.py:487`: if tc["function"]["name"] == "query_classical_text":

### Stale References for: `settings`
  - `update_controls.py:10`: settings=ModelSettings(temperature=0.0, max_tokens=16384),
  - `update_controls.py:16`: settings=ModelSettings(
  - `infrastructure/rag/mcp_bazirag.py:154`: # Load settings and target Gemma 31B on MCPMart
  - `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/app.py:23`: from src.config.settings import settings
  - `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/app.py:31`: pg_url = str(settings.database_url)
  - `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/app.py:107`: if settings.database_url:
  - `_docs/REVIEW/pydantic-ai/07_Refactor_Production_Scripts/app.py:114`: r = await client.get(f"{settings.qdrant_url}/health")
  - `src2/interfaces/telegram/app.py:14`: from src2.core.config.settings import settings
  - `src2/interfaces/telegram/app.py:32`: pg_url = str(settings.database_url)
  - `src2/interfaces/telegram/app.py:114`: if settings.database_url:
  - `src2/interfaces/telegram/app.py:122`: r = await client.get(f"{settings.qdrant_url}/health")
  - `src2/interfaces/telegram/chronomancer/rag.py:7`: from pydantic_ai.settings import ModelSettings
  - `src2/interfaces/telegram/chronomancer/rag.py:19`: Explicitly overrides model settings to disable reasoning and enforce temperature=0.0
  - `src2/core/rotator.py:179`: from pydantic_ai.settings import ModelSettings
  - `src2/core/rotator.py:187`: settings = ModelSettings(**settings_dict) if settings_dict else None
  - `src2/core/rotator.py:190`: return OpenAIChatModel(model_name=model_name, provider=provider, settings=settings)
  - `src2/core/valkey.py:13`: Fails fast if connection settings are missing or client creation fails.
  - `src2/core/config/model_profiles.py:50`: # Merge custom profile or fall back to default settings
  - `src2/core/config/settings.py:22`: settings = Settings()
  - `src2/core/memory/mem0_store.py:198`: settings = {}

### Stale References for: `simplify_month_narrative_task`
  - `src2/interfaces/telegram/app.py:153`: "name": job.get("name", "tasks.simplify_month_narrative_task"),
  - `src2/interfaces/telegram/app.py:183`: "name": "tasks.simplify_month_narrative_task",
