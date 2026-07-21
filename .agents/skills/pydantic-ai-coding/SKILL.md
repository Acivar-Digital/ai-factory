---
name: pydantic-ai-coding
description: Build AI agents with Pydantic AI — tools, capabilities (including on-demand loading), structured output, streaming, testing, and multi-agent patterns. This file is a LAZY-LOAD INDEX: BaziForecaster-specific rules are inline; all generic patterns (agents core, capabilities, tools, testing, orchestration) are deferred to references/*.md, loaded on demand. Use when the user mentions Pydantic AI, imports pydantic_ai, or asks to build an AI agent.
license: MIT
compatibility: Requires Python 3.10+
metadata:
  version: "1.2.0"
  author: pydantic
---

# Building AI Agents with Pydantic AI — Lazy-Load Index

Pydantic AI is a Python agent framework for production-grade Generative AI apps. This skill is
**thin by design**: the BaziForecaster-specific rules are inline below; every generic pattern is
in `references/*.md` and loaded only when needed.

## 🚨 BaziForecaster Specific Rules (inline, always relevant)

### CRITICAL RULE: Pydantic V2 Syntax Only
- NO legacy V1 syntax (`.dict()`, `.parse_obj()`, `class Config:`).
- Use V2: `.model_dump()`, `.model_validate()`, `model_config = {}`.

### Custom OpenAI-Compatible Endpoints (Breaking API Change)
`OpenAIModel` is deprecated; `base_url`/`api_key` can no longer be passed to the constructor.
Use `OpenAIChatModel` + `OpenAIProvider`:
```python
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
provider = OpenAIProvider(base_url="https://api.deepseek.com/v1", api_key="YOUR_KEY")
model = OpenAIChatModel(model_name="deepseek-chat", provider=provider)
```

### BaziForecaster agent conventions
- Agents use `pydantic_ai` v2.0+ (or Instructor) ONLY — no other framework (AGENTS.md hard rule).
- Model selection is centralized via `admin/controls/controls.py` — never `os.getenv` for models.
- Prompts live in YAML under `infrastructure/prompt/` — never inline in code.
- Structured `output_type` is the standard hand-off contract (the orchestrator uses
  Pydantic models for every role: DraftPlan/ApprovedPlan/TaskResult/AuditResult/...).
- The orchestrator (`admin/orchestrator`) is a **pure-Python deterministic state machine**, NOT
  an LLM. "Skills" = Python-built subagents (`Agent` per phase) carrying their own toolset +
  prompt. Same principle as lazy-loaded subagents: the conductor never carries execution tools.
- **Loopguard 400 retry** (`_loopguard.py`): `ModelHTTPError(status_code=400)` retries up to
  3x with exponential backoff inside `run_with_loopguard`'s `while True` loop. Other status
  codes (401/403/5xx after transport retries) propagate to the terminal `except Exception`
  for loud failure. This is universal: coder, planner, supervisor, all roles benefit.

---

## Lazy-Load Index — read only what you need

| I want to... | Reference file |
|---|---|
| Create/configure agents, output types, deps, specs, run methods | `references/AGENTS-CORE.md` |
| Bundle reusable behavior / intercept lifecycle (Capabilities, Hooks) | `references/CAPABILITIES-AND-HOOKS.md` |
| Eager vs on-demand loading, `load_capability`, progressive disclosure | `references/ON-DEMAND-CAPABILITIES.md` |
| Add function tools, toolsets, MCP servers, search tools | `references/TOOLS-CORE.md` |
| Approvals, retries, validators, timeouts, tool search | `references/TOOLS-ADVANCED.md` |
| Provider-native web search / fetch / code execution | `references/NATIVE-TOOLS.md` |
| Multimodal input, message history, history processors | `references/INPUT-AND-HISTORY.md` |
| Test / debug agent behavior (TestModel, overrides) | `references/TESTING-AND-DEBUGGING.md` |
| Multi-agent graphs, direct API, A2A, durable exec, evals | `references/ORCHESTRATION-AND-INTEGRATIONS.md` |
| Common task recipes | `references/COMMON-TASKS.md` |
| Full architecture / mental model | `references/ARCHITECTURE.md` |

---

## When to Use This Skill
Invoke when: user builds an AI agent / LLM app, mentions Pydantic AI, adds tools/capabilities/
structured output, defines agents from YAML specs, streams events, delegates between agents, or
tests agent behavior. Code imports `pydantic_ai` or references `Agent`/`RunContext`/`Tool`.

Do **not** use for: the `pydantic` validation library alone, other AI frameworks
(LangChain/LlamaIndex/CrewAI/AutoGen), or general Python unrelated to agents.

## Quick-Start (kept inline — most common path)
```python
from pydantic_ai import Agent
agent = Agent('anthropic:claude-sonnet-4-6', instructions='Be concise, reply with one sentence.')
print(agent.run_sync('Where does "hello world" come from?').output)
```
Structured output + tools + testing patterns: see the index above (do not load all references at
once — pick the one matching your task).
