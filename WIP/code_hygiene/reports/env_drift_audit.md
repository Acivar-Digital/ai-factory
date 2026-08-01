# 🕵️ Environment Variables Drift Audit Report

Scanned `118` files in `src2/`.

## 📂 `.env.example`

### 🛑 Line 1: `OPENROUTER_PIPELINE_MODEL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable OPENROUTER_PIPELINE_MODEL is present in .env.example but not referenced anywhere in the codebase, making it an unused example variable.

### 🛑 Line 1: `OPENROUTER_SUMMARIZER_MODEL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable is defined in .env.example but not referenced anywhere in the provided code context or codebase, making it an unused example variable.

### 🛑 Line 1: `SSL_KEY_PATH` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable SSL_KEY_PATH is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.

### 🛑 Line 1: `AGENT_WEBHOOK_URL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable AGENT_WEBHOOK_URL is defined in .env.example but is not referenced anywhere in the provided code context. Since it is unused in the codebase, it should be removed from the example file to prevent confusion.

### 🛑 Line 1: `OPENROUTER_PIPELINE_CACHE` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable OPENROUTER_PIPELINE_CACHE is defined in .env.example but is not referenced anywhere in the codebase. This is an unused example variable, which can lead to confusion for developers and clutter the environment configuration.

### 🛑 Line 1: `RAG_MODEL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable RAG_MODEL is defined in .env.example but is not referenced anywhere in the codebase. This represents undocumented or unused configuration, which creates confusion for new developers and maintenance overhead.

### 🛑 Line 1: `TELEGRAM_WEBHOOK_URL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable is present in .env.example but not used anywhere in the code, making it an unused example variable.

### 🛑 Line 1: `SSL_CERT_PATH` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable SSL_CERT_PATH is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.

### 🛑 Line 1: `OPENROUTER_SUMMARIZER_CACHE` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.

### 🛑 Line 1: `OLLAMA_API_URL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable OLLAMA_API_URL is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.

### 🛑 Line 1: `EMBEDDING_MODEL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable EMBEDDING_MODEL is present in .env.example but is not referenced anywhere in the codebase. This constitutes an unused example variable, which leads to confusion for new developers and configuration drift.

### 🛑 Line 1: `MCPMART_BASE_URL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable MCPMART_BASE_URL is defined in .env.example but is not used anywhere in the codebase, making it an unused example variable.

### 🛑 Line 1: `NARRATIVE_MODEL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable NARRATIVE_MODEL is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.

### 🛑 Line 1: `INTAKE_MODEL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable INTAKE_MODEL is present in the .env.example file but is not referenced anywhere in the codebase, making it an unused example variable.

### 🛑 Line 1: `WELCOME_MODEL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable WELCOME_MODEL is present in .env.example but not referenced in the code, making it an unused example variable.

### 🛑 Line 1: `MCPMART_API_KEY` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable MCPMART_API_KEY is defined in .env.example but is not referenced anywhere in the provided code context, indicating it is an unused example variable that should be removed.

### 🛑 Line 1: `NONSIFU_MODEL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable NONSIFU_MODEL is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.

### 🛑 Line 1: `SUMMARIZER_MODEL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable SUMMARIZER_MODEL is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.

### 🛑 Line 1: `PIPELINE_MODEL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable 'PIPELINE_MODEL' is present in .env.example but is not referenced anywhere in the codebase. This constitutes an unused example variable, which leads to configuration drift.

### 🛑 Line 1: `OPENROUTER_INTAKE_MODEL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable is present in .env.example but not referenced in any provided code context, and since it's a specific integration variable (OpenRouter), it is likely unused or obsolete.

### 🛑 Line 1: `MEMORY_MODEL` (unused_example)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable MEMORY_MODEL is defined in .env.example but is not referenced anywhere in the codebase, making it an unused example variable.

---

## 📂 `src2/core/memory/mem0_store.py`

### 🛑 Line 379: `OPENAI_API_KEY` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The code explicitly sets the environment variable OPENAI_API_KEY based on a provided key, which is a critical configuration for OpenAI services. If this is missing from .env.example, it is a true drift violation as it's required for the system's memory store functionality.

### 🛑 Line 381: `OPENAI_BASE_URL` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable OPENAI_BASE_URL is explicitly set in the environment via os.environ, indicating it is a required configuration for the OpenAI API base URL. Its absence from .env.example makes it an undocumented configuration variable.

---

## 📂 `src2/core/rotator.py`

### 🛑 Line 154: `GEMINI_KEYS` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable GEMINI_KEYS is used to initialize a RotatingGoogleProvider, which is critical for the API key rotation logic. Its absence from .env.example makes it undocumented and would prevent new developers or deployment pipelines from knowing it requires a configuration.

### 🛑 Line 218: `LLM_BASE_URL` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable LLM_BASE_URL is explicitly required by the code (raising a ValueError if missing), and it is marked as 'undocumented' (missing from .env.example). This is a critical configuration requirement for the application to function.

### 🛑 Line 219: `LLM_API_KEY` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable LLM_API_KEY is explicitly required by the code (raising a ValueError if missing), and it is not a standard system fallback. Its absence from .env.example would prevent the application from functioning.

---

## 📂 `src2/core/services/storage.py`

### 🛑 Line 9: `S3_ENDPOINT` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable S3_ENDPOINT is used to configure the S3 storage backend. While it has a default value for local development (MinIO), it is a critical configuration for connecting to actual S3-compatible storage in staging or production environments. Its absence from .env.example makes it undocumented and would hinder deployment.

### 🛑 Line 10: `S3_ACCESS_KEY` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable S3_ACCESS_KEY is used to configure S3 storage access, which is critical for production environments. While it has a default value for local development (minioadmin), it must be documented in .env.example to ensure proper configuration in staging and production.

### 🛑 Line 11: `S3_SECRET_KEY` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable S3_SECRET_KEY is used to configure S3 storage credentials. While it has a default value, it is a sensitive secret that must be explicitly defined in .env.example to ensure proper configuration in production and staging environments.

### 🛑 Line 12: `S3_BUCKET` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable S3_BUCKET is used to configure the S3 storage bucket name, which is environment-specific. While a default value is provided, it is a critical configuration for storage connectivity in production/staging environments and should be documented in .env.example.

### 🛑 Line 13: `AWS_REGION` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable AWS_REGION is used to configure the S3 client, but it is missing from the .env.example file. While it has a default value of 'us-east-1', it is a critical configuration for cloud deployment and should be documented in the example environment file to allow developers to change it for different regions.

---

## 📂 `src2/core/valkey.py`

### 🛑 Line 22: `VALKEY_HOST` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable VALKEY_HOST is explicitly required by the code (raising a KeyError if missing), and its absence from .env.example makes it an undocumented dependency that would break deployment.

### 🛑 Line 23: `VALKEY_PORT` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The code explicitly raises a KeyError if VALKEY_PORT is missing, indicating it is a mandatory configuration requirement for the application to function. Since it is undocumented in .env.example, this is a true drift violation.

---

## 📂 `src2/engine/monthly_generator.py`

### 🛑 Line 24: `CHRONO_URL` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable CHRONO_URL is used to configure the base URL and API key for the OpenAIProvider, which is critical for the engine's functionality. Its absence from .env.example makes it a true drift violation.

### 🛑 Line 25: `CHRONO_URL` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable CHRONO_URL is used to configure the base URL and API key for the OpenAIProvider, which is critical for the engine's functionality. Its absence from .env.example makes it unable to be deployed or configured correctly in new environments.

### 🛑 Line 26: `CHRONO_URL` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable CHRONO_URL is used to configure the critical API endpoint and authentication key for the OpenAIProvider, and it is missing from the .env.example file. This is a true drift violation as it is a required configuration for the engine to function.

---

## 📂 `src2/engine/narrative_simplifier.py`

### 🛑 Line 223: `SIMPLIFIER_CONCURRENCY` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable SIMPLIFIER_CONCURRENCY is used to control the concurrency level of the narrative simplifier, but it is missing from the .env.example file. This is a configuration setting that should be documented for deployment and tuning.

---

## 📂 `src2/engine/prompt_engine.py`

### 🛑 Line 58: `BAZI_ENGINE_CONCURRENCY` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable is explicitly required by the code (raises ValueError if missing), meaning the application will crash if it is not documented in .env.example.

---

## 📂 `src2/engine/rag_client.py`

### 🛑 Line 18: `QDRANT_API_KEY` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable QDRANT_API_KEY is used in the code but is missing from the .env.example file. While it is not explicitly checked in the startup validation block (lines 23-27), it is a critical configuration for authenticating with a Qdrant vector database, and its absence would likely cause authentication failures during runtime.

---

## 📂 `src2/interfaces/telegram/app.py`

### 🛑 Line 198: `VALKEY_HOST` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable VALKEY_HOST is used to configure the Redis/Valkey backend host. While it has a default value of '127.0.0.1', it is a custom application-specific configuration for infrastructure connectivity that should be documented in .env.example to ensure consistent deployment across different environments.

### 🛑 Line 199: `VALKEY_PORT` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable VALKEY_PORT is used to configure the Redis/Valkey backend connection. While it has a default value of 6379, it is a service-specific configuration that should be documented in .env.example to allow deployment in different environments (e.g., Docker, Kubernetes) where the port might differ.

### 🛑 Line 328: `PROMO_MONTHLY` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable PROMO_MONTHLY is used to retrieve a promo code for report unlocking, which is a business-logic specific configuration. Since it is missing from the .env.example file, it is a true environment drift violation.

### 🛑 Line 527: `PROMO_MONTHLY` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable PROMO_MONTHLY is used to define a promo code for monthly reports, which is a business-logic specific configuration. Since it is missing from .env.example, it is a required configuration for this feature to function as intended.

### 🛑 Line 528: `PROMO_FEATURE` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable PROMO_FEATURE is used to control a promotional feature toggle/code in the application logic, but it is missing from the .env.example file. This is a custom application-specific configuration that should be documented.

### 🛑 Line 903: `PROMO_MONTHLY` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable PROMO_MONTHLY is used to handle promo code logic for report generation, which is a business-specific configuration. Since it is missing from .env.example, it is a true drift violation.

### 🛑 Line 1171: `ADMIN_ID` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable ADMIN_ID is used to control access to a debug endpoint and is not documented in .env.example. Its absence would prevent administrators from accessing the debug functionality.

---

## 📂 `src2/interfaces/telegram/bgem3_bridge.py`

### 🛑 Line 9: `BGEM3_MCP_URL` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable BGEM3_MCP_URL is explicitly required by the application (it raises a ValueError if missing), but it is not documented in the .env.example file. This is a critical configuration missing from the example.

---

## 📂 `src2/interfaces/telegram/db.py`

### 🛑 Line 36: `DATABASE_URL` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable DATABASE_URL is used to configure the database connection, and while it has a fallback to an in-memory SQLite database, it is a critical configuration parameter that should be documented in .env.example for deployment and production environments.

### 🛑 Line 124: `ADMIN_ID` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable ADMIN_ID (and TELEGRAM_ADMIN_ID) is used to identify administrative users for test runs and ID generation logic, which is a critical configuration for the application's logic. Its absence from .env.example makes it undocumented.

### 🛑 Line 155: `BOT_DB_PATH` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable BOT_DB_PATH is used to configure the database path for the Telegram bot, but it is missing from the .env.example file. This is a critical configuration for persistence in production/staging environments.

### 🛑 Line 292: `ADMIN_ID` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable ADMIN_ID (and TELEGRAM_ADMIN_ID) is used to determine administrative privileges in the code, but is missing from the .env.example file. This is a critical configuration for access control.

### 🛑 Line 327: `ADMIN_ID` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable ADMIN_ID is used as a fallback for TELEGRAM_ADMIN_ID to determine administrative privileges. Since it is not documented in .env.example, new developers or deployment environments will lack the necessary configuration to grant admin access, which is a critical functional requirement.

### 🛑 Line 1083: `DATABASE_URL` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable DATABASE_URL is used to initialize the database engine and session factory. If missing from .env.example, it is a critical configuration required for the application's database connectivity, representing a true drift violation.

---

## 📂 `src2/interfaces/telegram/logging_utils.py`

### ✅ Line 38: `BOT_STDOUT_LOG_PATH` (undocumented)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The variable has a hardcoded default value ('bot_stdout.log'), making it optional for the environment configuration. It does not break the application if missing from .env.example.

### 🛑 Line 45: `BOT_STDERR_LOG_PATH` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `LOW`
- **Reasoning**: The variable BOT_STDERR_LOG_PATH is used to define the log file path. While it has a fallback value ("bot_stderr.log"), it is a custom application-specific configuration that should be documented in .env.example to allow operators to specify the log location.

---

## 📂 `src2/interfaces/telegram/preflight.py`

### 🛑 Line 34: `TELEGRAM_API_BASE` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable TELEGRAM_API_BASE is accessed via os.environ without a default value, meaning the application will crash with a KeyError if it is missing from the environment. Since it is not documented in .env.example, this is a critical drift violation.

### 🛑 Line 57: `TELEGRAM_API_BASE` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable TELEGRAM_API_BASE is accessed via os.environ["TELEGRAM_API_BASE"], which will raise a KeyError if missing. Since it is undocumented in .env.example, it is a critical missing configuration required for the Telegram interface to function.

### 🛑 Line 111: `CLOUDFLARE_TUNNEL_TOKEN` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable CLOUDFLARE_TUNNEL_TOKEN is used to authenticate and run a Cloudflare Tunnel, and the code explicitly checks for its presence and returns False (failing the preflight check) if it is missing. This is a critical configuration requirement for the tunnel to function.

### 🛑 Line 111: `CLOUDFLARE_TOKEN` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable CLOUDFLARE_TOKEN is used as a fallback for CLOUDFLARE_TUNNEL_TOKEN to authenticate the Cloudflare tunnel. Since it is not documented in .env.example, new developers or deployment scripts cannot know which variable to provide, leading to potential deployment failure.

### ✅ Line 142: `OPENROUTER_AUTH_URL` (undocumented)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The variable has a hardcoded default value providing the same functionality as the official API endpoint, making it optional for the environment configuration.

### 🛑 Line 277: `TELEGRAM_API_BASE` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable TELEGRAM_API_BASE is accessed via os.environ without a default value, meaning the application will raise a KeyError if it is missing from the environment. Since it is not documented in .env.example, it is a critical missing configuration for the Telegram notification system.

---

## 📂 `src2/interfaces/telegram/reliability.py`

### 🛑 Line 43: `TELEGRAM_API_BASE` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable TELEGRAM_API_BASE is accessed via os.environ without a default value, meaning the application will crash if it is not defined in the environment. This is a critical configuration requirement for the Telegram interface to function.

### 🛑 Line 74: `REPORT_PROGRESS_CHANNEL_ID` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable REPORT_PROGRESS_CHANNEL_ID is used to define a target for telegram notifications, and it is not documented in the .env.example file. This is a required configuration for the feature to function as intended.

---

## 📂 `src2/interfaces/telegram/utils.py`

### 🛑 Line 149: `TELEGRAM_API_BASE` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable TELEGRAM_API_BASE is accessed via os.environ["TELEGRAM_API_BASE"], which will raise a KeyError if the variable is not defined in the environment. This is a critical configuration requirement for the Telegram interface to function, and its absence from .env.example would break deployments.

### 🛑 Line 194: `TELEGRAM_API_BASE` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable TELEGRAM_API_BASE is accessed via os.environ[...], which will raise a KeyError if missing, causing the application to crash. It is not a standard library fallback and is required for constructing the Telegram API URL.

### 🛑 Line 217: `REPORT_PROGRESS_CHANNEL_ID` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable REPORT_PROGRESS_CHANNEL_ID is used to configure a Telegram channel ID for progress reporting, and it is not present in the .env.example file. This is a required configuration for the feature to function as intended in different environments.

---

## 📂 `src2/worker/celery_app.py`

### 🛑 Line 10: `VALKEY_HOST` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable VALKEY_HOST is used to construct the connection URL for the Celery broker/backend. While there are fallbacks to VALKEY_URL, REDIS_URL, or localhost, the presence of specific host/port variables suggests they are intended for configuration in production/staging environments. Missing from .env.example makes it undocumented.

### 🛑 Line 11: `VALKEY_PORT` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable VALKEY_PORT is used to construct the Valkey/Redis connection URL. While there is a fallback to VALKEY_URL or REDIS_URL, the specific logic on line 12 requires both VALKEY_HOST and VALKEY_PORT to be present to use that specific construction path. Missing this from .env.example prevents new developers from knowing they can configure the host and port separately.

### 🛑 Line 15: `VALKEY_URL` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable VALKEY_URL is used as a primary configuration option for the Celery broker and backend, and it lacks a fallback to a standard system default like PORT. While it has a fallback to REDIS_URL, it is a custom application-specific configuration that should be documented in .env.example to ensure consistent deployment across environments.

### 🛑 Line 15: `REDIS_URL` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: REDIS_URL is used as a fallback for VALKEY_URL, and both are used to configure the Celery broker/backend. Since neither is documented in the example file, this is a missing configuration variable that would break deployment in a non-local environment.

### 🛑 Line 18: `CELERY_BROKER_URL` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable CELERY_BROKER_URL is used to configure the Celery broker, but it is missing from the .env.example file. While there is a fallback to valkey_url, this is a primary configuration point for the rest of the infrastructure.

### 🛑 Line 20: `CELERY_RESULT_BACKEND` (undocumented)
- **Verdict**: `DRIFT_VIOLATION`
- **Severity**: `HIGH`
- **Reasoning**: The variable CELERY_RESULT_BACKEND is used to configure the Celery result backend, which is critical for task tracking. While there is a fallback to a derived valkey_url, the ability to override this via environment variables is a standard deployment requirement for production environments. Its absence from .env.example makes it undocumented.

---

