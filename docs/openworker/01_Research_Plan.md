# OpenWorker Research Plan — LLM Reliability Focus

> **Status:** Plan (refocused)
> **Target:** Fix LLM failures (rubbish + hallucination) in ai-factory harness
> **Source repo:** `/home/yapilwsl/arthityap/github/openworker/openworker/`

## User Directive (recorded via `bd remember`)

> "i am not interested in fancy ui applications. i want to build a long running harness that can help me refactor my repo or build new scripts. now my LLM inside the harness keep failing - always give rubbish and hallucinate. your research must target that."

This refocuses all research on **LLM reliability patterns** in OpenWorker that ai-factory can adopt.

---

## Root Cause (from kimi-cli KC research — confirmed)

ai-factory's LLMs keep hallucinating because:

1. **No output-boundary validation** — `output_sanitizer.py` only repairs broken JSON off-line; nothing validates that the LLM's structured claims (tool calls, file paths, command names) match ground truth *at the model-output boundary*.
2. **Deferred verification** — ruff/verifier runs *after* the LLM finishes. The LLM never sees its own errors in context → can't self-correct.
3. **Config env-guess races** — `os.getenv` applied imperatively after validation → LLM reads stale/guess config.
4. **Silent error swallowing** — provider/transport errors swallowed in retry loops → no error envelope in conversation → blind re-execution.
5. **No deny-by-default gate** — hallucinated destructive tool calls can execute without approval.

## OpenWorker's Anti-Hallucination Patterns (researched)

| Pattern | File | What it does | ai-factory gap |
|---------|------|-------------|----------------|
| **Error feedback into context** | `engine.py:782-787` | `_execute_sync()` catches ALL exceptions, returns `{"error", "error_type"}` as a tool message appended to `self.messages` — LLM sees its own failures and self-corrects *inline* | Verification deferred to post-run ruff/verifier |
| **Deny-by-default permissions** | `permissions.py` + `risk.py` | `RiskClass` (READ/WRITE_LOCAL/EXEC/EXTERNAL) + `Mode` (DISCUSS/PLAN/INTERACTIVE/AUTO); denied/unknown tool calls get `_tool_error_message` in history (no orphans) | No permission gate — tools execute freely |
| **ProviderRouter invalidation** | `router.py:82-88` | `invalidate()` drops cached clients so config changes (new key, new URL) take effect immediately | Models hardcoded in `control.py:ControlSheet` |
| **Friendly error translation** | `errors.py:38-56` | `friendly_model_error()` maps vendor-specific error body markers (`_NO_ACCESS`, `_NO_QUOTA`) to actionable sentences | Raw vendor errors surface to LLM |
| **Tool schema via aisuite Tools** | `tools/registry.py:69-70` | Centralized schema generation: `Tools([func]).tools(format="openai")` from type hints — one source of truth | Manual schema generation risk |
| **Auto-compaction** | `compaction.py` | Token-threshold trigger with retry-once + trim fallback; `context_provider()` injects live directory list into last user message | Context overflow corrupts LLM output |
| **Subagent isolation** | `tools/subagent.py` | `explore` tool spawns child `TurnEngine` in PLAN mode (hard-blocked writes/shell) with fresh context — research without polluting context | `task` tool spawns full intern subagents |
| **Shell safety** | `tools/shell.py` | Persistent shell, `_NONINTERACTIVE_ENV`, timeout bounds (120s default, 600s max) | No timeout enforcement |
| **No orphan tool calls** | `engine.py:651-662` | `_interrupted_tool()` + stop-path: every pending tool_call gets an error result — history never carries orphans | Potential orphan tool calls in history |
| **TestModel evals** | `tests/` | `MockChatProvider` replays scripted responses; 70+ test files including `test_engine.py`, `test_permissions_risk.py` | No eval harness with inline-snapshot |

## 10 KC Cards (Focused on LLM Reliability)

Each card targets a specific ai-factory failure mode and maps an OpenWorker pattern to a concrete `pydantic_ai_2_impl` adoption.

| Card | Title | Focus |
|------|-------|-------|
| **OW-01** | Engine Error Feedback Into Context | `_execute_sync` returns all errors as tool messages — LLM self-corrects inline |
| **OW-02** | Deny-by-Default Permission Engine | `RiskClass` + `Mode` prevents hallucinated destructive actions |
| **OW-03** | Provider Router & Config Invalidation | `ProviderRouter.invalidate()` for fresh config without rebuild |
| **OW-04** | Friendly Error Translation | `friendly_model_error()` maps vendor noise to actionable sentences |
| **OW-05** | Tool Schema Validation & Risk Classification | aisuite `Tools` schema gen + `RiskClass` classification |
| **OW-06** | Auto-Compaction & Context Management | Token-threshold compaction + `context_provider()` for live context |
| **OW-07** | Subagent Isolation for Exploration | `explore` tool (plan mode, hard-blocked writes) |
| **OW-08** | Shell Safety & Timeout Enforcement | Persistent shell + non-interactive env + timeout bounds |
| **OW-09** | No Orphan Tool Calls | Stop-path error messages for every pending call |
| **OW-10** | Testing Strategy & Mock Providers | `MockChatProvider` + scripted responses for deterministic evals |

## Next Steps

1. Generate 10 KC JSON files (`docs/openworker/OW-01.json`–`OW-10.json`).
2. Create `docs/openworker/00_Proposed_Integration.md` (refocused on LLM reliability).
3. Map findings to concrete ai-factory harness fixes (tools_guard.py, output_sanitizer.py, control.py, loopguard).
