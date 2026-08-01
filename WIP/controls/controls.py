import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_settings import BaseSettings, SettingsConfigDict


# =====================================================================
# 1. STRONGLY-TYPED SYSTEM SETTINGS
# =====================================================================
class SystemSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # NOTE: secret values MUST come from .env (gitignored, loaded by BaseSettings).
    # Never hardcode credentials here — committed defaults are a leak (audit F1).

    # MCPMart Gateway (Port 18000)
    mcpmart_base_url: str = Field(default="http://10.32.34.243:18000/v1/openai")
    mcpmart_api_key: str = Field(default="")

    # Antigravity Manager (Port 8045)
    antigravity_manager_url: str = Field(default="http://10.32.34.243:8045/v1")
    antigravity_manager_key: str = Field(default="")

    # OpenRouter Backup (Emergency Failover)
    openrouter_api_key: str | None = Field(default=None)

    # LiteRouter (Port 7766)
    literouter_url: str = Field(default="http://localhost:7766/v1")
    literouter_auth_key: str = Field(default="")

    # Search APIs
    exa_api_key: str | None = Field(default=None)
    tavily_api_key: str | None = Field(default=None)
    searxng_url: str = Field(default="http://searxng.local")

    # Pydantic Gateway (Port 7768)
    pydantic_url: str = Field(default="http://localhost:7766/v1")
    pydantic_auth_key: str = Field(default="")

    # Application & Infrastructure
    database_url: str = Field(default="")
    valkey_host: str = Field(default="10.32.34.243")
    valkey_port: int = Field(default=6379)

    # Telegram Bot
    telegram_bot_token: str = Field(default="")
    telegram_admin_id: int = Field(default=0)
    telegram_api_base: str = Field(default="http://127.0.0.1:9999")


# Instantiate settings
settings = SystemSettings()

# =====================================================================
# 2. PROVIDERS REGISTRY
# =====================================================================
# All providers are instantiated once using the validated settings
PROVIDERS: dict[str, OpenAIProvider] = {
    "mcpmart": OpenAIProvider(
        base_url=settings.mcpmart_base_url,
        api_key=settings.mcpmart_api_key,
    ),
    "antigravity_manager": OpenAIProvider(
        base_url=settings.antigravity_manager_url,
        api_key=settings.antigravity_manager_key,
    ),
    "literouter": OpenAIProvider(
        base_url=settings.literouter_url,
        api_key=settings.literouter_auth_key,
    ),
    "openrouter": OpenAIProvider(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    ),
    "pydantic": OpenAIProvider(
        base_url=settings.pydantic_url,
        api_key=settings.pydantic_auth_key,
    ),
}

# =====================================================================
# 3. MODELS INSTANTIATION
# =====================================================================

small_model = OpenAIChatModel(
    "gemma-4-31b-it",
    provider=PROVIDERS["mcpmart"],
    settings=ModelSettings(
        temperature=0.1,
        max_tokens=1024,
        extra_body={
            "extra_body": {
                "google": {
                    "thinking_config": {
                        "thinking_level": "minimal",
                        "include_thoughts": False,
                    }
                }
            }
        },
    ),
)

gemma_4_31b_it = OpenAIChatModel(
    "gemma-4-31b-it",
    provider=PROVIDERS["mcpmart"],
    settings=ModelSettings(
        temperature=0.1,
        max_tokens=16000,
        extra_body={
            "extra_body": {
                "google": {
                    "thinking_config": {
                        "thinking_level": "minimal",
                        "include_thoughts": False,
                    }
                }
            }
        },
    ),
)

gemini_3_1_flash_lite = OpenAIChatModel(
    "google/gemini-3.1-flash-lite",
    provider=PROVIDERS["literouter"],
    settings=ModelSettings(
        temperature=0.1,
        max_tokens=65535,
        extra_body={
            "google": {
                "thinking_config": {
                    "thinking_level": "high",
                    "include_thoughts": False,
                }
            }
        },
    ),
)

gemma_4_26b_a4b_it = OpenAIChatModel(
    "gemma-4-26b-a4b-it",
    provider=PROVIDERS["mcpmart"],
    settings=ModelSettings(
        temperature=0.1,
        max_tokens=16000,
        extra_body={
            "extra_body": {
                "google": {
                    "thinking_config": {
                        "thinking_level": "minimal",
                        "include_thoughts": False,
                    }
                }
            }
        },
    ),
)

deepseek_v4_pro = OpenAIChatModel(
    "nvidia/deepseek-ai/deepseek-v4-pro",
    provider=PROVIDERS["literouter"],
    settings=ModelSettings(temperature=0.3, max_tokens=65536),
)

qwen3_next = OpenAIChatModel(
    "nvidia/qwen/qwen3-next-80b-a3b-instruct",
    provider=PROVIDERS["literouter"],
    settings=ModelSettings(temperature=0.1, max_tokens=65536),
)


deepseek_flash = OpenAIChatModel(
    "zen/deepseek-v4-flash-free",
    provider=PROVIDERS["literouter"],
    settings=ModelSettings(max_tokens=65535),
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=False),
)

nemotron_nano = OpenAIChatModel(
    "openrouter/nvidia/nemotron-3-nano-30b-a3b:free",
    provider=PROVIDERS["literouter"],
    settings=ModelSettings(temperature=0.1, max_tokens=65536),
)

nemotron_nano_reasoning = OpenAIChatModel(
    "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    provider=PROVIDERS["literouter"],
    settings=ModelSettings(temperature=0.1, max_tokens=65536),
)

ling_flash = OpenAIChatModel(
    "openrouter/inclusionai/ling-3.0-flash:free",
    provider=PROVIDERS["literouter"],
    settings=ModelSettings(max_tokens=65536),
)

laguna_xs = OpenAIChatModel(
    "openrouter/poolside/laguna-xs-2.1:free",
    provider=PROVIDERS["literouter"],
    settings=ModelSettings(max_tokens=65536),
)

freegem31 = OpenAIChatModel(
    "freetier/gemma-4-31b-it",
    provider=PROVIDERS["literouter"],
    settings=ModelSettings(
        temperature=0.1,
        max_tokens=8192,
        extra_body={
            "thinkingConfig": {
                "thinkingLevel": "minimal",
                "includeThoughts": False,
            }
        },
    ),
)

freegem26 = OpenAIChatModel(
    "freetier/gemma-4-26b-a4b-it",
    provider=PROVIDERS["literouter"],
    settings=ModelSettings(
        temperature=0.1,
        max_tokens=8192,
        extra_body={
            "thinkingConfig": {
                "thinkingLevel": "minimal",
                "includeThoughts": False,
            }
        },
    ),
)


pydantic_google = OpenAIChatModel(
    "pydantic/google",
    provider=PROVIDERS["pydantic"],
    settings=ModelSettings(temperature=0.1, max_tokens=65536),
)

pydantic_nvidia = OpenAIChatModel(
    "pydantic/nvidia",
    provider=PROVIDERS["pydantic"],
    settings=ModelSettings(temperature=0.1, max_tokens=65536),
)

gemini_3_1_pro_low = OpenAIChatModel(
    "gemini-3.1-pro-low",
    provider=PROVIDERS["antigravity_manager"],
    settings=ModelSettings(temperature=0.1, max_tokens=65536),
)

gemini_3_5_flash_extra_low = OpenAIChatModel(
    "gemini-3.5-flash-extra-low",
    provider=PROVIDERS["antigravity_manager"],
    settings=ModelSettings(temperature=0.1, max_tokens=65536),
)

gemini_3_6_flash_high = OpenAIChatModel(
    "gemini-3.6-flash-high",
    provider=PROVIDERS["antigravity_manager"],
    settings=ModelSettings(temperature=0.1, max_tokens=65536),
)

gemini_3_6_flash_low = OpenAIChatModel(
    "gemini-3.6-flash-low",
    provider=PROVIDERS["antigravity_manager"],
    settings=ModelSettings(temperature=0.1, max_tokens=65536),
)

# =====================================================================
# 4. CONTROL SHEET (Role-to-Model Object Mapping)
# =====================================================================
class ControlSheetSchema(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    intake_model: OpenAIChatModel | None = None
    chrono_model: OpenAIChatModel
    rag_model: OpenAIChatModel
    simplifier_model: OpenAIChatModel
    welcome_model: OpenAIChatModel | None = None
    narrative_model: OpenAIChatModel
    subagent_model: OpenAIChatModel
    planner_model: OpenAIChatModel
    git_push_model: OpenAIChatModel
    review_model: OpenAIChatModel
    auditor_model: OpenAIChatModel
    gatherer_model: OpenAIChatModel
    orchestrator_model: OpenAIChatModel
    scanner_model: OpenAIChatModel
    codebase_model: OpenAIChatModel
    baziRAG_model: OpenAIChatModel  # noqa: N815
    rewriter: OpenAIChatModel
    statewriter_model: OpenAIChatModel
    plan_review_model: OpenAIChatModel
    code_review_model: OpenAIChatModel
    web_model: OpenAIChatModel
    oracle_rewriter: OpenAIChatModel
    oracle_narrator: OpenAIChatModel
    oracle_rag: OpenAIChatModel


_CONTROL_SHEET_DICT = {
    "intake_model": small_model,
    "chrono_model": gemini_3_6_flash_low,
    "rag_model": gemini_3_5_flash_extra_low,
    "simplifier_model": gemini_3_6_flash_low,
    "welcome_model": small_model,
    "narrative_model": gemini_3_6_flash_low,
    "subagent_model": gemini_3_6_flash_low,
    "planner_model": gemini_3_6_flash_low,
    "git_push_model": ling_flash,
    "review_model": gemini_3_6_flash_low,
    "auditor_model": gemini_3_6_flash_low,
    "gatherer_model": gemini_3_6_flash_low,
    "orchestrator_model": gemini_3_6_flash_low,
    "scanner_model": gemini_3_6_flash_high,
    "codebase_model": gemini_3_6_flash_low,
    "baziRAG_model": gemini_3_6_flash_low,
    "rewriter": gemini_3_6_flash_low,
    "statewriter_model": gemini_3_6_flash_low,
    # Distinct supervisor models for plan/code review (owner's call; reuse
    # deepseek_flash for now — cross-family avoids same-model blind spots).
    "plan_review_model": gemini_3_6_flash_low,
    "code_review_model": gemini_3_6_flash_low,
    "web_model": gemini_3_5_flash_extra_low,
    # For Orcale Function only
    "oracle_rewriter": gemini_3_6_flash_low,
    "oracle_narrator": gemini_3_6_flash_high,
    "oracle_rag": gemini_3_5_flash_extra_low,

}


CONTROL_SHEET = ControlSheetSchema(**_CONTROL_SHEET_DICT)

# Repo root for sandbox path resolution
REPO_ROOT = Path(__file__).resolve().parents[3]


# =====================================================================
# 5. COMPACTION CONFIG (token-budget Context Compaction Gate, build.md §8.5)
# =====================================================================
# summarizer_model: key into CONTROL_SHEET (runner does getattr(CONTROL_SHEET, key));
#   codebase_model = laguna_xs (cheapest) is the recommended small summariser.
# compact_at_fraction: trigger when history >= this fraction of the RUNNING agent's
#   context window (token-based, not message-count).
# hard_max_tokens: absolute ceiling regardless of model window.
# keep_recent_messages: tail always retained untouched.
# token_estimate: "char_div_4" (cheap) or "tiktoken" (if available).
COMPACTION_CONFIG: dict[str, object] = {
    "summarizer_model": "codebase_model",
    # Global default for WORKERS. Their models expose ~100K windows, so 0.6 ≈ 60K,
    # safely under the ~200K provider latency wall. Per-role ceilings below.
    "compact_at_fraction": 0.6,
    "hard_max_tokens": 70000,
    "keep_recent_messages": 12,
    "token_estimate": "char_div_4",
    # Q3/Q4: orchestrator runs on the higher (~200K) window key; compact conservatively
    # before the wall so it stays zippy. Workers share the global default above.
    "per_role": {
        "orchestrator": {"compact_at_fraction": 0.6, "hard_max_tokens": 140000},
    },
}


# =====================================================================
# 6. ORCHESTRATOR CONTROL KNOBS
# =====================================================================
# WIP semaphore cap (Q11-A): bounds concurrent subagents -> no rate-limit crashes.
MAX_AGENTS = 20

# When True, OPS phase BLOCKS on a human approval sentinel before pushing.
REQUIRE_HUMAN_GATE = False

# Per-role re-execution ceilings (fail loudly, then HALT).
ROLE_MAX_ATTEMPTS: dict[str, int] = {
    "planner": 3,
    "coder": 3,
    "plan_review": 2,
    "code_review": 2,
    "red_team": 2,
    "ops": 2,
}

# Model fallback chains: role CONTROL_SHEET key -> ranked candidates.
FALLBACK_SHEET: dict[str, list[str]] = {
    "planner_model": ["planner_model", "subagent_model", "codebase_model"],
    "plan_review_model": ["plan_review_model", "subagent_model", "codebase_model"],
    "code_review_model": ["code_review_model", "subagent_model", "codebase_model"],
    "subagent_model": ["subagent_model", "codebase_model"],
    "auditor_model": ["auditor_model", "review_model"],
    "git_push_model": ["git_push_model", "codebase_model"],
    "codebase_model": ["codebase_model"],
}
