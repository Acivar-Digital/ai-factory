# MALFORMED_FUNCTION_CALL Fix — Loopguard 400 Retry

> **Issue:** beads `factory-2xo` (open)
> **Date:** 2026-07-21
> **Scope:** One file, add one handler

---

## Root Cause

The provider gateway (OpenRouter/LiteLLM) sometimes false-positive flags valid function calls as malformed and returns HTTP 400 with a "malformed function call" error. The model output was actually fine — the gateway hiccuped. A simple retry of the same request succeeds on the next attempt.

### Exception flow

```
Provider 400 → OpenAI SDK APIStatusError → _map_api_errors → ModelHTTPError(400)
  → model_request → agent graph → _loopguard.py except Exception → _dump_failure → raise
  → runner.py except ModelAPIError → _report_run_failure → SystemExit(1) [HALT]
```

`ModelHTTPError` is a subclass of `ModelAPIError`. The 400 is NOT in `RETRYABLE_STATUS_CODES` (`{429, 500, 502, 503, 504}`), so the transport layer does NOT retry it.

---

## Fix Strategy

**Catch `ModelHTTPError` with status_code 400 inside `_loopguard.py`'s `while True` loop** and retry up to 3 times with exponential backoff. No message injection needed — the same request will succeed on retry (the model output was valid, the gateway flapped).

If all 3 attempts fail, let the error propagate to the existing `except Exception` handler for normal failure loudness.

### Why in `_loopguard.py` not `runner.py`

- `_loopguard.py` **owns** the agent interaction loop — every agent call passes through it.
- `runner.py` is the **orchestrator** caller — it should only see clean success or terminal failure.
- Placing recovery here makes it **universal**: coder, planner, supervisor, all roles benefit.

---

## Implementation

### File: `factory/infra/_loopguard.py`

**Step 1 — Add import** (line 20):
```
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
```

**Step 2 — Add handler** between `except UsageLimitExceeded` (line 369) and `except Exception` (line 369):

```python
            except ModelHTTPError as exc:
                if exc.status_code == 400:
                    attempts = getattr(f, '_malformed_retries', 0) + 1
                    f._malformed_retries = attempts
                    if attempts <= 3:
                        delay = 5 * attempts
                        print(
                            f"[{phase or 'RUN'}] turn {turn} got 400 (attempt {attempts}/3); "
                            f"retrying in {delay}s...",
                            flush=True,
                        )
                        await asyncio.sleep(delay)
                        continue
                _dump_failure(fail_dir, phase, role, current_history, limits, exc, agent_id=agent_id)
                raise
```

**Acceptance:**
1. `ModelHTTPError(status_code=400)` → retries up to 3 times with `asyncio.sleep` backoff, then falls through to generic `except Exception` on exhaustion
2. Other `ModelHTTPError` (e.g. 401, 403) → `_dump_failure` + re-raise (existing behaviour preserved)
3. `ruff check` clean

---

## Dependency Order

```
00_fix.md (this plan)
  └── _loopguard.py change (only work item)
        └── verify: run harness with a provider that 400s on function calls
```

## Verification Protocol

1. `uv run ruff check factory/infra/_loopguard.py` → clean
2. Unit test: `uv run pytest tests/ -x -k "malformed"`
3. Integration: run a task with the target model; observe loopguard retries instead of HALT
4. Close beads issue `factory-2xo`
