import json
import os
import threading
from pathlib import Path

import httpx
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_settings import BaseSettings, SettingsConfigDict

from factory.infra.http_client import get_orch_http_client


# =====================================================================
# RUNTIME PATH CONFIGURATION (single source of truth)
# =====================================================================
def _load_runtime_env() -> dict[str, str]:
    env: dict[str, str] = {}
    p = Path(__file__).resolve().parent / ".env"
    if not p.exists():
        p = Path(__file__).resolve().parent.parent.parent / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


_RUNTIME_ENV = _load_runtime_env()

_CWD = os.environ.get("CWD") or _RUNTIME_ENV.get("CWD") or str(Path.cwd().resolve())
REPO_ROOT = Path(_CWD)
os.environ.setdefault("CWD", str(REPO_ROOT))
PKG_DIR = Path(__file__).resolve().parent.parent  # factory root package
ORCH_ROOT = PKG_DIR / "orch"  # runtime home

LOGS_DIR = ORCH_ROOT / "logs"
RUNTIME_DIR = LOGS_DIR / "runtime"
REPORTS_DIR = ORCH_ROOT / "reports"
CONTEXT_DIR = ORCH_ROOT / "context"
PROMPT_DIR = ORCH_ROOT / "prompt"
TEMP_DIR = PKG_DIR / "temp"
STATUS_MD = PKG_DIR / "STATUS.md"
USER_PROMPT_PATH = PKG_DIR / "prompt" / "user_prompt.md"  # committed task spec

# =====================================================================
# 0. DEFAULT PYDANTIC-AI STRUCTURED-OUTPUT CONVENTION (injected for ALL models)
# =====================================================================
PYDANTIC_AI_INSTRUCTIONS = (
    "You run inside the pydantic-ai agent framework and MUST return structured output. "
    "Provide your final answer by calling the `final_result` tool EXACTLY ONCE, with "
    "arguments that are valid JSON strictly matching the output schema you are given. "
    "Do NOT return your answer as plain text, markdown, or fenced code blocks. "
    "For every field supply the exact type requested: objects and arrays MUST be nested "
    "JSON (never a JSON string), and every required field MUST be present. "
    "If a validation error is returned, fix ONLY the indicated field and call `final_result` again. "
    "Do NOT loop on tools. Once you have sufficient information, call final_result immediately. "
    "Excessive tool calls waste budget."
)


def _load_pydantic_ai_coding_skill() -> str:
    """Load the pydantic-ai-coding skill SKILL.md content for injection into role prompts."""
    skill_path = Path(__file__).resolve().parent.parent.parent.parent / ".agents" / "skills" / "pydantic-ai-coding" / "SKILL.md"
    if skill_path.exists():
        return skill_path.read_text(encoding="utf-8")
    return ""


# =====================================================================
# 1. STRONGLY-TYPED SYSTEM SETTINGS
# =====================================================================
class SystemSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MCPMart Gateway (Port 18000)
    mcpmart_base_url: str = Field(default="http://10.32.34.243:18000/v1/openai")
    mcpmart_api_key: str | None = Field(default='localfreegemini')

    # Antigravity Manager (Port 8045)
    antigravity_manager_url: str = Field(default="http://10.32.34.243:8045/v1")
    antigravity_manager_key: str | None = Field(default='sk-antigravity')

    # OpenRouter Backup (Emergency Failover)
    openrouter_api_key: str | None = Field(default=None)

    # LiteRouter (Port 7766)
    literouter_url: str = Field(default="http://localhost:7766/v1")
    literouter_auth_key: str | None = Field(default='sk-lr-8f2a9e3b1c4d7e5f')

    # Application & Infrastructure
    database_url: str = Field(default="")
    valkey_host: str = Field(default="10.32.34.243")
    valkey_port: int = Field(default=6379)

    # Telegram Bot
    telegram_bot_token: str = Field(default="")
    telegram_admin_id: int = Field(default=0)
    telegram_api_base: str = Field(default="http://127.0.0.1:9999")


settings = SystemSettings()

# =====================================================================
# 2. PROVIDERS REGISTRY
# =====================================================================
TOOL_SUBPROCESS_TIMEOUT = 300.0


def _orch_traffic_log() -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_DIR / "http_traffic.log"


_CRED_KEYS = (
    "authorization",
    "api_key",
    "api-key",
    "x-api-key",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "passwd",
    "cookie",
    "bearer",
    "auth",
    "key",
    "credential",
)


def _redact_headers(headers) -> dict:
    return {
        k: ("***REDACTED***" if k.lower() in ("authorization", "api-key", "x-api-key") else v)
        for k, v in headers.items()
    }


def _redact_url(url: object) -> str:
    text = str(url)
    return text.split("?", 1)[0] + ("?***REDACTED_QUERY***" if "?" in text else "")


def _redact_payload(payload: str) -> str:
    lowered = payload.lower()

    def _mask(value):
        if isinstance(value, dict):
            return {
                k: ("***REDACTED***" if str(k).lower() in _CRED_KEYS else _mask(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [_mask(v) for v in value]
        if isinstance(value, str):
            v = value.strip()
            if v.lower().startswith("bearer ") or v.startswith("sk-") or v.startswith("sk_"):
                return "***REDACTED***"
        return value

    try:
        return json.dumps(_mask(json.loads(payload)), ensure_ascii=False, indent=2)
    except Exception:
        if any(s in lowered for s in ("bearer ", "sk-", "sk_", "api_key", "apikey", "password", "secret")):
            return "***REDACTED_BODY***"
        return payload[:20000]


async def _orch_log_request(request: httpx.Request) -> None:
    try:
        body = request.content
        try:
            payload = _redact_payload(body.decode("utf-8", "replace"))
        except Exception:
            payload = "***REDACTED_BODY***"
        line = (
            f"\n=== REQUEST {request.method} {_redact_url(request.url)} ===\n"
            f"HEADERS: {json.dumps(_redact_headers(request.headers), ensure_ascii=False)}\n"
            f"BODY:\n{payload}\n"
        )
        with open(_orch_traffic_log(), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        with open(_orch_traffic_log(), "a", encoding="utf-8") as f:
            f.write(f"[http-log error] {exc!r}\n")


async def _orch_log_response(response: httpx.Response) -> None:
    try:
        try:
            await response.aread()
            snippet = _redact_payload(response.text)
        except Exception as exc:
            snippet = f"<unreadable body: {exc!r}>"
        line = (
            f"\n=== RESPONSE {response.status_code} {response.http_version} {response.request.method} {_redact_url(response.request.url)} ===\n"
            f"HEADERS: {json.dumps(_redact_headers(response.headers), ensure_ascii=False)}\n"
            f"BODY:\n{snippet}\n"
        )
        with open(_orch_traffic_log(), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        with open(_orch_traffic_log(), "a", encoding="utf-8") as f:
            f.write(f"[http-log error] {exc!r}\n")


_PROVIDERS_CACHE: dict[str, OpenAIProvider] | None = None
_PROVIDERS_LOCK = threading.Lock()


def _make_providers() -> dict[str, OpenAIProvider]:
    return {
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
    }


def _get_providers() -> dict[str, OpenAIProvider]:
    global _PROVIDERS_CACHE
    if _PROVIDERS_CACHE is None:
        with _PROVIDERS_LOCK:
            if _PROVIDERS_CACHE is None:
                _PROVIDERS_CACHE = _make_providers()
    return _PROVIDERS_CACHE


class _LazyProviders(dict[str, OpenAIProvider]):
    """Lazy provider dict that creates providers on first access."""

    def __missing__(self, key: str) -> OpenAIProvider:
        providers = _get_providers()
        value = providers[key]
        self[key] = value
        return value


PROVIDERS = _LazyProviders()

# =====================================================================
# 2b. STARTUP GATEWAY REACHABILITY PROBE
# =====================================================================
class GatewayProbeURLs(BaseModel):
    mcpmart: str
    antigravity: str
    literouter: str


GATEWAY_PROBE = GatewayProbeURLs(
    mcpmart=settings.mcpmart_base_url,
    antigravity=settings.antigravity_manager_url,
    literouter=settings.literouter_url,
)


async def verify_gateways_reachable() -> None:
    unreachable: list[str] = []
    client = get_orch_http_client()
    try:
        for name, url in GATEWAY_PROBE.model_dump().items():
            try:
                await client.get(url)
            except (httpx.ConnectError, httpx.TimeoutException):
                unreachable.append(name)
    finally:
        await client.aclose()
    if unreachable:
        raise RuntimeError(
            "Orchestrator model gateways unreachable: "
            + ", ".join(unreachable)
            + ". Start the gateway service(s) or set their URLs in .env "
            + "(see control.SystemSettings)."
        )


# =====================================================================
# 3. MODELS INSTANTIATION
# =====================================================================

small_model = OpenAIChatModel(
    "gemma-4-31b-it",
    provider=PROVIDERS["mcpmart"],
    settings=ModelSettings(
        max_completion_tokens=1024,
        extra_body={
            "google": {
                "thinking_config": {
                    "thinking_level": "minimal",
                    "include_thoughts": False,
                }
            }
        },
    ),
)

gemma_4_31b_it = OpenAIChatModel(
    "gemma-4-31b-it",
    provider=PROVIDERS["mcpmart"],
    settings=ModelSettings(
        max_completion_tokens=16000,
        extra_body={
            "google": {
                "thinking_config": {
                    "thinking_level": "minimal",
                    "include_thoughts": False,
                }
            }
        },
    ),
)

gemini_3_1_flash_lite = OpenAIChatModel(
    "gemini-3.1-flash-lite",
    provider=PROVIDERS["mcpmart"],
    settings=ModelSettings(
        max_completion_tokens=65535, context_window=200000,
        extra_body={
            "google": {
                "thinking_config": {
                    "thinking_level": "low",
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
        max_completion_tokens=12000, context_window=32000,
        extra_body={
            "google": {
                "thinking_config": {
                    "thinking_level": "minimal",
                    "include_thoughts": False,
                }
            }
        },
    ),
)

deepseek_v4_pro = OpenAIChatModel(
    "nvidia/deepseek-ai/deepseek-v4-pro",
    provider=PROVIDERS["literouter"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None, context_window=200000,
    )
)

qwen3_next = OpenAIChatModel(
    "nvidia/qwen/qwen3-next-80b-a3b-instruct",
    provider=PROVIDERS["literouter"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None,
    )
)

inkling = OpenAIChatModel(
    "nvidia/thinkingmachines/inkling",
    provider=PROVIDERS["literouter"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None,
    )
)

deepseek_flash = OpenAIChatModel(
    "zen/deepseek-v4-flash-free",
    provider=PROVIDERS["literouter"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None, context_window=256000,
    )
)

nemotron_nano = OpenAIChatModel(
    "openrouter/nvidia/nemotron-3-nano-30b-a3b:free",
    provider=PROVIDERS["literouter"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None),
)

nemotron = OpenAIChatModel(
    "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
    provider=PROVIDERS["literouter"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None),
)

ling_flash = OpenAIChatModel(
    "openrouter/inclusionai/ling-3.0-flash:free",
    provider=PROVIDERS["literouter"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None),
    settings=ModelSettings(
        extra_body={
            "reasoning": {
                "effort": "high",
                "exclude": True,
            }
        }
    ),
)

laguna_xs = OpenAIChatModel(
    "openrouter/poolside/laguna-xs-2.1:free",
    provider=PROVIDERS["literouter"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None,
    )
)

freegem31 = OpenAIChatModel(
    "freetier/gemma-4-31b-it",
    provider=PROVIDERS["literouter"],
    settings=ModelSettings(
        max_completion_tokens=8192,
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
        max_completion_tokens=8192,
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
    provider=PROVIDERS["literouter"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None,
    )
)

pydantic_nvidia = OpenAIChatModel(
    "pydantic/nvidia",
    provider=PROVIDERS["literouter"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None,
    )
)

gemini_3_1_pro_low = OpenAIChatModel(
    "gemini-3.1-pro-low",
    provider=PROVIDERS["antigravity_manager"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None, context_window=200000,
    )
)

gemini_3_1_pro_high = OpenAIChatModel(
    "gemini-pro-agent",
    provider=PROVIDERS["antigravity_manager"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None, context_window=200000,
    )
)

gemini_3_5_flash_extra_low = OpenAIChatModel(
    "gemini-3.5-flash-extra-low",
    provider=PROVIDERS["antigravity_manager"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None, context_window=200000,
    )
)

gemini_3_6_flash_low = OpenAIChatModel(
    "gemini-3.6-flash-low",
    provider=PROVIDERS["antigravity_manager"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None, context_window=200000,
    )
)

gemini_3_6_flash_high = OpenAIChatModel(
    "gemini-3.6-flash-high",
    provider=PROVIDERS["antigravity_manager"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None, context_window=200000,
    )
)

gemini_2_5_pro = OpenAIChatModel(
    "gemini-2.5-pro",
    provider=PROVIDERS["antigravity_manager"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None, context_window=200000,
    )
)

# =====================================================================
# 4. CONTROL SHEET (Role-to-Model Object Mapping)
# =====================================================================
class ControlSheet(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    models: dict[str, OpenAIChatModel]

    def model(self, key: str) -> OpenAIChatModel:
        if key not in self.models:
            raise KeyError(f"[HALT] model_key {key!r} not in CONTROL_SHEET")
        return self.models[key]


def load_control_sheet() -> ControlSheet:
    return ControlSheet(
        models={
            "planner_model": gemini_3_1_pro_low,
            "supervisor_plan_model" : gemini_3_1_pro_low,
            "supervisor_review_model": gemini_3_1_pro_low,
            "coder_model": gemini_3_1_pro_low,
            "red_team_model": gemini_3_1_pro_low,
            "ops_model": laguna_xs,
            "compact_model": gemini_3_5_flash_extra_low,
            "codebase_model": gemini_3_5_flash_extra_low,
            "healer_model" : gemini_3_5_flash_extra_low,
            "intern_model" : ling_flash,
            "engineer_model" : ling_flash,
            "senior_model" : ling_flash,
              
              

        }
    )


CONTROL_SHEET = load_control_sheet()


# =====================================================================
# 5. COMPACTION CONFIG (token-budget Context Compaction Gate)
# =====================================================================


class PerRoleConfig(BaseModel):
    compact_at_fraction: float | None = None
    hard_max_tokens: int | None = None


class CompactionConfig(BaseModel):
    summarizer_model: str = "compact_model"
    compact_at_fraction: float = 0.6
    hard_max_tokens: int = 70000
    keep_recent_messages: int = 12
    token_estimate: Literal["char_div_4", "tiktoken"] = "char_div_4"
    CONTEXT_COMPACT_CEILING: int = 200_000
    CONTEXT_COMPACT_FLOOR: int = 60_000
    EMPTY_EXT_RETRIES: int = 3
    per_role: dict[str, PerRoleConfig] = Field(
        default_factory=lambda: {
            "orchestrator": PerRoleConfig(compact_at_fraction=0.6, hard_max_tokens=140000),
        }
    )


COMPACTION_CONFIG = CompactionConfig()


# =====================================================================
# 8. TIER HANDOVER MODELS (Pydantic v2 structured output)
# =====================================================================
class InternResult(BaseModel):
    modified_files: list[str] = []
    refactored_functions: list[str] = []
    remaining_violations: list[str] = []
    notes: str = ""


class EngineerResult(BaseModel):
    modified_files: list[str] = []
    refactored_functions: list[str] = []
    verification_passed: bool = False
    remaining_violations: list[str] = []
    notes: str = ""


class SeniorVerdict(BaseModel):
    passed: bool = False
    approved_files: list[str] = []
    architectural_quality_score: int = 5
    comments: str = ""


class TierState(BaseModel):
    task: str
    scope: list[str] = []
    target_functions: list[str] = []
    current_role: str
    staged_paths: list[str] = []
    last_diagnostics: dict[str, str] = {}


class TodoItem(BaseModel):
    file_path: str
    function_name: str
    target_cc: int = 5
    current_cc: int = 0
    passed: bool = False


class TodoList(BaseModel):
    items: list[TodoItem] = []

    def render_markdown(self) -> str:
        lines = ["### 📋 Active Refactoring Checklist"]
        for item in self.items:
            box = "[x]" if item.passed else "[ ]"
            status = (
                f"CC={item.current_cc} (PASSED)"
                if item.passed
                else f"Target CC <= {item.target_cc} (Current CC={item.current_cc})"
            )
            lines.append(
                f"- {box} `{item.file_path} :: {item.function_name}` ({status})"
            )
        return "\n".join(lines)


# =====================================================================
# 6. ORCHESTRATOR CONTROL KNOBS
# =====================================================================
MAX_AGENTS = 20

READ_BUDGET = 15
CODER_READ_FILE_BUDGET = 10
REQUIRE_HUMAN_GATE = False

# =====================================================================
# 7. SKILL_MAP (M2) — role -> template + ROLE model key + output_type + tools
# =====================================================================
class SkillEntry(BaseModel):
    template: str
    model_key: str
    output_type: str
    tool_bucket: str = ""
    hard_rules: list[str] = Field(default_factory=list)


class SkillMap(BaseModel):
    roles: dict[str, SkillEntry]


def load_skill_map() -> SkillMap:
    return SkillMap(
        roles={
             "intern": SkillEntry(
                 template="intern.yaml",
                 model_key="intern_model",
                 output_type="TaskResult",
                 tool_bucket="AST-edit",
                 hard_rules=[
                     "never edit src/ or src2/; only write under factory/",
                     "read_file allowed for targeted reads; grep forbidden — use batch_read.",
                     "Run batch_read BEFORE any edit.",
                     "Follow strict Pydantic v2 conventions (model_dump, model_validate, no legacy v1 .dict()/parse_obj()/class Config:) and Pydantic AI v2 agent design patterns.",
                 ],
             ),
             "engineer": SkillEntry(
                 template="engineer.yaml",
                 model_key="engineer_model",
                 output_type="TaskResult",
                 tool_bucket="AST-edit",
                 hard_rules=[
                     "never edit src/ or src2/; only write under factory/",
                     "read_file allowed for targeted reads; grep forbidden — use batch_read.",
                     "Run batch_read BEFORE any edit.",
                     "Follow strict Pydantic v2 conventions (model_dump, model_validate, no legacy v1 .dict()/parse_obj()/class Config:) and Pydantic AI v2 agent design patterns.",
                     "Verify all AST and lint checks pass before emitting final_result.",
                 ],
             ),
             "senior": SkillEntry(
                 template="senior.yaml",
                 model_key="senior_model",
                 output_type="TaskResult",
                 tool_bucket="AST-edit",
                 hard_rules=[
                     "never edit src/ or src2/; only write under factory/",
                     "read_file allowed for targeted reads; grep forbidden — use batch_read.",
                     "Run batch_read BEFORE any edit.",
                     "Follow strict Pydantic v2 conventions (model_dump, model_validate, no legacy v1 .dict()/parse_obj()/class Config:) and Pydantic AI v2 agent design patterns.",
                     "Perform final audit and gate verification. Emit final_result for production deployment.",
                 ],
             ),
        }
    )


SKILL_MAP = load_skill_map()


SKILL_ROLES: list[str] = list(SKILL_MAP.roles.keys())


DEFAULT_AGENT_SETTINGS = ModelSettings(parallel_tool_calls=False)

ROLE_AGENT_SETTINGS: dict[str, ModelSettings] = {
    role: DEFAULT_AGENT_SETTINGS for role in SKILL_ROLES
}
