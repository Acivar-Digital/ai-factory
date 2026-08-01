# 🕵️ Circular Dependency Audit Report

Scanned `118` files in `src2/`.

## 📂 `src2/engine/openrouter.py`

### ✅ Line 191: `src2.engine.rag_client -> src2.engine.openrouter -> src2.engine.rag_client`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The import of `query_classical_text` from `.rag_client` is performed inside a function body (lazy import), which prevents a circular dependency at module-level initialization time.

### ✅ Line 452: `src2.engine.rag_client -> src2.engine.openrouter -> src2.engine.rag_client`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The import of `query_classical_text` from `.rag_client` is performed inside a function body (local import), which defers the import until the function is called at runtime. This prevents a circular dependency at the module level during initial load, avoiding runtime ImportErrors.

---

## 📂 `src2/interfaces/telegram/chronomancer/coordinator.py`

### ✅ Line 35: `src2.interfaces.telegram.chronomancer.agents -> src2.interfaces.telegram.chronomancer.forecast_store -> src2.interfaces.telegram.chronomancer.coordinator -> src2.interfaces.telegram.chronomancer.agents`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The import of 'src2.interfaces.telegram.chronomancer.agents' inside the functions '_get_sifu_agent' and '_get_simplifier_agent' is a lazy import. This prevents the circular dependency from being triggered at module-level initialization, resolving the import loop at runtime only when these functions are called.

### ✅ Line 41: `src2.interfaces.telegram.chronomancer.agents -> src2.interfaces.telegram.chronomancer.forecast_store -> src2.interfaces.telegram.chronomancer.coordinator -> src2.interfaces.telegram.chronomancer.agents`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The import of 'get_simplifier_agent' from '.agents' is performed inside the function '_get_simplifier_agent', which is a lazy import. This prevents the circular dependency from causing a runtime ImportError at module load time.

### ✅ Line 212: `src2.interfaces.telegram.chronomancer.agents -> src2.interfaces.telegram.chronomancer.forecast_store -> src2.interfaces.telegram.chronomancer.coordinator -> src2.interfaces.telegram.chronomancer.agents`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The import of 'DailyDeps' and 'get_daily_orchestrator' from '.agents' is performed inside the 'handle_daily' function. This is a lazy import, which defers the resolution of the agents module until the function is called at runtime, effectively breaking the circular dependency chain at the module level.

### ✅ Line 213: `src2.interfaces.telegram.chronomancer.forecast_store -> src2.interfaces.telegram.chronomancer.coordinator -> src2.interfaces.telegram.chronomancer.forecast_store`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The import of 'forecast_store' is performed inside the 'handle_daily' function, making it a lazy import. This prevents the circular dependency from causing a runtime ImportError at module load time.

### ✅ Line 317: `src2.interfaces.telegram.chronomancer.forecast_store -> src2.interfaces.telegram.chronomancer.coordinator -> src2.interfaces.telegram.chronomancer.forecast_store`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The import of 'forecast_store' is performed inside the 'handle_forecast' function, making it a lazy import. This prevents the circular dependency from causing a runtime ImportError during module initialization.

### ✅ Line 331: `src2.interfaces.telegram.chronomancer.forecast_store -> src2.interfaces.telegram.chronomancer.coordinator -> src2.interfaces.telegram.chronomancer.forecast_store`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The import of `forecast_store` is performed inside the `handle_forecast_category` function, making it a lazy import. This prevents the circular dependency from causing a runtime ImportError during module initialization.

### ✅ Line 389: `src2.interfaces.telegram.chronomancer.agents -> src2.interfaces.telegram.chronomancer.forecast_store -> src2.interfaces.telegram.chronomancer.coordinator -> src2.interfaces.telegram.chronomancer.agents`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The import of 'DailyDeps' from '.agents' is performed inside the 'handle_ask' function, making it a lazy import. This prevents the circular dependency from causing a runtime ImportError at module load time.

### ✅ Line 390: `src2.interfaces.telegram.chronomancer.forecast_store -> src2.interfaces.telegram.chronomancer.coordinator -> src2.interfaces.telegram.chronomancer.forecast_store`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The import of 'get_daily_forecast' from '.forecast_store' is performed inside the 'handle_ask' function, making it a lazy import. This prevents the circular dependency from causing a runtime ImportError during module initialization.

### ✅ Line 523: `src2.interfaces.telegram.chronomancer.forecast_store -> src2.interfaces.telegram.chronomancer.coordinator -> src2.interfaces.telegram.chronomancer.forecast_store`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The import of 'get_rolling_30' from '.forecast_store' is performed inside the 'prebuild_annual_calendar' function, making it a lazy import. This prevents a circular dependency at module load time, avoiding runtime ImportErrors.

---

## 📂 `src2/worker/tasks.py`

### ✅ Line 18: `src2.engine.narrative_simplifier -> src2.worker.tasks -> src2.engine.narrative_simplifier`
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The import of 'simplify_month_narrative' is performed inside a function body, which is a lazy import. This prevents the circular dependency from being triggered at module load time, effectively resolving the loop.

---

