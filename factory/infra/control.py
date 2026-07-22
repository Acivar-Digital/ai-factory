import json
import os
from pathlib import Path

import httpx
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_settings import BaseSettings, SettingsConfigDict

from factory.infra.http_client import create_resilient_http_client


# =====================================================================
# RUNTIME PATH CONFIGURATION (single source of truth)
# =====================================================================
# The orch/ runtime tree (logs, reports, context, prompt, temp) is rooted at
#     ORCH_ROOT = REPO_ROOT / SANDBOX_DIR / "orch"
# where REPO_ROOT and SANDBOX_DIR are loaded from factory/infra/.env
# so the sandbox location is REUSABLE WITHOUT code changes:
#     CWD     = "/abs/path/to/repo"      # repo root
#     SandBox = "factory"     # subdir under CWD that hosts runtime
# Edit .env to relocate the runtime tree. Safe defaults fall back to the
# current working directory + "factory".
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
# Untrained / free-tier models (e.g. hy3_free) are NOT fine-tuned on the
# pydantic-ai output convention, so they emit prose / `tool_calls` with null
# content / reasoning instead of a valid `final_result` call. We spell the
# convention out and prepend it to EVERY structured-output agent's system
# prompt (see tools.load_skill / tools.build_worker_spec). pydantic-ai's
# output tool is always named `final_result` (pydantic_ai/result.py).
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


# =====================================================================
# 1. STRONGLY-TYPED SYSTEM SETTINGS
# =====================================================================
class SystemSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MCPMart Gateway (Port 18000) -- secrets supplied via env / .env only.
    # NEVER commit a real key; None forces env resolution and fails loudly at
    # request time if unset (SA1-F1 remediation).
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

    # Application & Infrastructure -- DB credentials come from env (DATABASE_URL).
    database_url: str = Field(default="")
    valkey_host: str = Field(default="10.32.34.243")
    valkey_port: int = Field(default=6379)

    # Telegram Bot -- token supplied via env (TELEGRAM_BOT_TOKEN), never committed.
    telegram_bot_token: str = Field(default="")
    telegram_admin_id: int = Field(default=0)
    telegram_api_base: str = Field(default="http://127.0.0.1:9999")


# Instantiate settings
settings = SystemSettings()

# =====================================================================
# 2. PROVIDERS REGISTRY
# =====================================================================
# All providers are instantiated once using the validated settings
#
# Shared transport client WITH EXPLICIT TIMEOUTS. pydantic-ai's default
# `create_async_http_client()` ships with NO timeout, so a dead/unreachable
# endpoint hangs the event loop forever (the observed "run just hangs at
# calling model"). connect=15s fails fast on unreachable hosts; read=300s
# still permits long generations; the outer run_with_loopguard wait_for is
# the final backstop. The client itself (pool/HTTP2/TLS/timeout config) is
# built in `http_client.create_resilient_http_client`; RETRYABLE_STATUS and
# MAX_MODEL_RETRIES are re-exported from that module for `runner._run_agent_retry`.

# =====================================================================
# 2a. RETRY STRATEGY (agent layer, NOT transport layer)
# =====================================================================
# Transient HTTP blips (429 rate-limits, 5xx gateway hiccups) are retried at the
# AGENT layer by `runner._run_agent_retry` via tenacity `wait_exponential` — NOT
# by a custom httpx transport. A transport-level replay would discard the
# accumulated agent conversation, so retries stay above the provider boundary:
# the same single model call is simply re-issued with jittered exponential
# backoff, no context loss. On exhaustion `_run_agent_retry` writes a structured
# FAIL report and exits with SystemExit(1) (graceful abort, no traceback crash).

# Hard wall-clock ceiling for every CLI subprocess the orchestrator spawns
# (tool wrappers + coder sub-script). Without this, a hung CLI (e.g. a stuck
# investigate.py or .git/hooks/pre-push) blocks the asyncio loop forever —
# the per-turn AGENT_RUN_TIMEOUT wait_for cannot interrupt a synchronous
# subprocess.run (see review.md R6).
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
    """Drop query string so tokens passed as URL params never hit disk."""
    text = str(url)
    return text.split("?", 1)[0] + ("?***REDACTED_QUERY***" if "?" in text else "")


def _redact_payload(payload: str) -> str:
    """Recursively mask credential-shaped keys in JSON request/response bodies.

    Also redacts whole-value secrets: any string that looks like a bearer /
    API key / sk-... token is masked in place so auth material is never written
    to the traffic log on disk (SA1-F5).
    """
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
        # Non-JSON body: blanket-mask obvious secret strings before writing.
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


ORCH_HTTP_CLIENT = create_resilient_http_client(
    event_hooks={"request": [_orch_log_request], "response": [_orch_log_response]},
)

PROVIDERS: dict[str, OpenAIProvider] = {
    "mcpmart": OpenAIProvider(
        base_url=settings.mcpmart_base_url,
        api_key=settings.mcpmart_api_key,
        http_client=ORCH_HTTP_CLIENT,
    ),
    "antigravity_manager": OpenAIProvider(
        base_url=settings.antigravity_manager_url,
        api_key=settings.antigravity_manager_key,
        http_client=ORCH_HTTP_CLIENT,
    ),
    "literouter": OpenAIProvider(
        base_url=settings.literouter_url,
        api_key=settings.literouter_auth_key,
        http_client=ORCH_HTTP_CLIENT,
    ),
}

# =====================================================================
# 2b. STARTUP GATEWAY REACHABILITY PROBE (fail-loud on dead gateways)
# =====================================================================
# The orchestrator only "works" if the model-gateway services are up. A dead
# gateway previously surfaced as a cryptic httpx.ConnectError mid-run. This
# probe runs ONCE at startup and names exactly which gateway(s) are down so
# the operator can start the service (or fix .env URLs) instead of guessing.
class GatewayProbeURLs(BaseModel):
    """Typed map of model-gateway name -> base URL, probed at startup."""

    mcpmart: str
    antigravity: str
    literouter: str


GATEWAY_PROBE = GatewayProbeURLs(
    mcpmart=settings.mcpmart_base_url,
    antigravity=settings.antigravity_manager_url,
    literouter=settings.literouter_url,
)


async def verify_gateways_reachable() -> None:
    """Raise RuntimeError listing any unreachable model gateways.

    A 2xx/3xx/4xx response means the host is reachable; only connection
    failures / timeouts / bad URLs count as down. Run once at startup so a
    dead gateway fails loudly with a clear message instead of a mid-run hang.
    """
    unreachable: list[str] = []
    async with create_resilient_http_client() as client:
        for name, url in GATEWAY_PROBE.model_dump().items():
            try:
                await client.get(url)
            except (httpx.ConnectError, httpx.TimeoutException):
                unreachable.append(name)
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

hy3_free = OpenAIChatModel(
    "openrouter/tencent/hy3:free",
    provider=PROVIDERS["literouter"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None,
    )
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

gemini_3_5_flash_extra_low = OpenAIChatModel(
    "gemini-3.5-flash-extra-low",
    provider=PROVIDERS["antigravity_manager"],
    profile=OpenAIModelProfile(openai_supports_tool_choice_required=None, context_window=200000,
    )
)

gemini_3_5_flash_low = OpenAIChatModel(
    "gemini-3.5-flash-low",
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
# 4. CONTROL SHEET (Role-to-Model Object Mapping) — Pydantic model (D06-C)
# =====================================================================
# Harness model split (runner.py is the deterministic conductor; no LLM orchestrator).
# Coder/planner = deepseek_flash (cheap); supervisors = deepseek_flash;
# red_team = deepseek_flash; ops = laguna_xs. Swap freely by editing
# load_control_sheet() — models are sourced from the instantiated OpenAIChatModel
# objects above, NEVER hard-coded as raw "provider:model" strings.
class ControlSheet(BaseModel):
    """Typed model-key -> instantiated OpenAIChatModel registry (no plain dict)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    models: dict[str, OpenAIChatModel]

    def model(self, key: str) -> OpenAIChatModel:
        if key not in self.models:
            raise KeyError(f"[HALT] model_key {key!r} not in CONTROL_SHEET")
        return self.models[key]


def load_control_sheet() -> ControlSheet:
    """Build the CONTROL_SHEET Pydantic model from the instantiated orchestrator models."""
    return ControlSheet(
        models={
            "planner_model": gemini_3_5_flash_low,
            "supervisor_plan_model" : gemini_3_1_pro_low,
            "supervisor_review_model": gemini_3_1_pro_low,
            "coder_model": gemini_3_5_flash_low,
            "red_team_model": gemini_3_1_pro_low,
            "ops_model": laguna_xs,
            "compact_model": gemini_3_5_flash_extra_low,
            # codebase_model: the sandboxed discovery/analysis model for /search
            # and /investigate CLIs. Sourced from the antigravity_manager gateway
            # (same family as the legacy gemini_3_5_flash_extra_low) so the
            # tools stay INSIDE the orchestrator sandbox instead of reaching
            # out to the external admin/deepseek_flash/controls.py CONTROL_SHEET.
            "codebase_model": gemini_3_5_flash_extra_low,
            "healer_mode" : gemini_3_5_flash_extra_low,
        }
    )


CONTROL_SHEET = load_control_sheet()


# =====================================================================
# 5. COMPACTION CONFIG (token-budget Context Compaction Gate, build.md §8.5)
# =====================================================================


class PerRoleConfig(BaseModel):
    compact_at_fraction: float | None = None
    hard_max_tokens: int | None = None


class CompactionConfig(BaseModel):
    """Pydantic model for compaction gate parameters — no plain dict access.

    summarizer_model: key into CONTROL_SHEET (runner does CONTROL_SHEET[key]);
        compact_model = laguna_xs (cheapest) is the recommended small summariser.
    compact_at_fraction: trigger when history >= this fraction of the RUNNING agent's
        context window (token-based, not message-count).
    hard_max_tokens: absolute ceiling regardless of model window.
    keep_recent_messages: tail always retained untouched.
    token_estimate: "char_div_4" (cheap) or "tiktoken" (if available).
    """

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
# 6. ORCHESTRATOR CONTROL KNOBS
# =====================================================================
# WIP semaphore cap (Q11-A): bounds concurrent subagents -> no rate-limit crashes.
MAX_AGENTS = 20

# Read-Bucket Protocol (RBP) budgets — central config, imported by tools.GuardToolset.
# batch_read attempts are uniform for ALL agents (kills the 15-call research loop).
READ_BUDGET = 15
# Raw read_file is coder-only (pre-edit targeted reads); non-coders get 0.
CODER_READ_FILE_BUDGET = 10
# When True, OPS phase BLOCKS on a human approval sentinel before pushing.
REQUIRE_HUMAN_GATE = False

# =====================================================================
# 7. SKILL_MAP (M2) — role -> template + ROLE model key + output_type + tools
# =====================================================================
# D4 slim: the SkillSpec carries NO model/output_type. Those BIND AT SPAWN
# from this map (M3 `load_skill`). `tool_bucket` indexes TOOL_REGISTRY in
# tools.py; "" means the role gets no tools (broadcast-only phases).
# `output_type` is a string key resolved by M3; harmless here for M2.
# Replaced the former plain dict with Pydantic models (D06-C).
class SkillEntry(BaseModel):
    """One role's spawn binding (template + model key + output type + tool bucket)."""

    template: str
    model_key: str
    output_type: str
    tool_bucket: str = ""
    hard_rules: list[str] = Field(default_factory=list)


class SkillMap(BaseModel):
    """Typed role -> SkillEntry registry (no plain dict)."""

    roles: dict[str, SkillEntry]


def load_skill_map() -> SkillMap:
    """Build the SKILL_MAP Pydantic model from the frozen role config."""
    return SkillMap(
        roles={
            "planner": SkillEntry(
                template="planner.yaml",
                model_key="planner_model",
                output_type="DraftPlan",
                tool_bucket="read-only",
                hard_rules=[
                    "never author global_alignment; it is pre-injected",
                    "Research max 5 batch_read rounds, then output the plan. Do NOT loop.",
                    "grep and read_file are forbidden; use batch_read for all discovery.",
                ],
            ),
            "supervisor_plan": SkillEntry(
                template="supervisor_plan.yaml",
                model_key="supervisor_plan_model",
                output_type="ApprovedPlan",
                tool_bucket="read-only",
                hard_rules=[
                    "Research max 5 batch_read rounds before approving.",
                    "grep and read_file are unavailable; use batch_read.",
                ],
            ),
            "coder": SkillEntry(
                template="coder.yaml",
                model_key="coder_model",
                output_type="TaskResult",
                tool_bucket="AST-edit",
                hard_rules=[
                    "never edit src/ or src2/; only write under factory/",
                    "read_file allowed for targeted reads; grep forbidden \u2014 use batch_read.",
                    "Run batch_read BEFORE any edit.",
                ],
            ),
            "supervisor_review": SkillEntry(
                template="supervisor_review.yaml",
                model_key="supervisor_review_model",
                output_type="ReviewResult",
                tool_bucket="read-only",
                hard_rules=["grep and read_file are forbidden; use batch_read."],
            ),
            "red_team": SkillEntry(
                template="red_team.yaml",
                model_key="red_team_model",
                output_type="AuditResult",
                tool_bucket="read-only",
                hard_rules=[
                    "audit only; never modify code",
                    "grep and read_file are forbidden; use batch_read.",
                ],
            ),
            "ops": SkillEntry(
                template="ops.yaml",
                model_key="ops_model",
                output_type="GitResult",
                tool_bucket="",
                hard_rules=["push is the sole src/ exception; final diff only"],
            ),
        }
    )


SKILL_MAP = load_skill_map()


# The 6 orchestrator roles (D8 eager forge order).
SKILL_ROLES: list[str] = list(SKILL_MAP.roles.keys())


# Per-role AGENT-LEVEL model settings. These OVERRIDE the model-level defaults
# carried by each OpenAIChatModel in CONTROL_SHEET for the matching key
# (pydantic-ai: agent.model_settings wins over model.settings). Single source
# of truth for agent behaviour -- look up by role; fall back to DEFAULT.
DEFAULT_AGENT_SETTINGS = ModelSettings(parallel_tool_calls=False)

ROLE_AGENT_SETTINGS: dict[str, ModelSettings] = {
    role: DEFAULT_AGENT_SETTINGS for role in SKILL_ROLES
}


# (Section 8 deleted per grill-me B1 — no fallback; raw crash on failure)
