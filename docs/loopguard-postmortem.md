# Post-Mortem: The Failure Taxonomy of LoopGuard

This document captures the embedded tribal knowledge within `_loopguard.py` and `runner.py`. It explains the *why* behind specific edge-case fixes and loop pathology handlers that were discovered not through documentation or framework guidelines, but by observing real agentic system failures in production over weeks of execution. 

If you are maintaining this codebase, **do not remove these mechanisms** without understanding the exact failure modes they prevent.

## 1. The A-B-A-B Alternation Detector (`alt_prev`, `alt_count`)

**The Failure Mode:**
Standard guardrails detect when an LLM calls the exact same tool with the exact same arguments sequentially (A-A-A). However, models often get stuck in a ping-pong state where they alternate between two distinct tool calls (A-B-A-B-A-B). Because the signature changes every turn, identical-signature guards never trip, leading to an infinite loop that burns tokens and budget.

**The Fix:**
We track `alt_prev` and increment `alt_count` when the model cycles back to a previous state. This breaks the infinite ping-pong loop explicitly by recognizing the alternating pattern, rather than just sequential repetition.

## 2. The No-Op Same-Result Detector (`result_signature`, `result_repeat`)

**The Failure Mode:**
An LLM may call *different* tools (or the same tool with slightly different, valid arguments) but receive the *same empty or non-mutating result* back from the environment every time. Since the tool calls themselves are unique, call-based loop guards fail to catch it. The model will keep trying variations of the call, getting the same useless result, and looping forever.

**The Fix:**
We hash or signature the actual *result* returned by the tools. If the environment returns the identical no-op response across multiple different attempts, `result_repeat` trips and halts the loop. This guards the state machine based on environment feedback, not just model output.

## 3. Shared-Model Monkey-Patch Restore (`finally` block)

**The Failure Mode:**
When multiple agent roles share the same underlying model object instance, monkey-patching the model (e.g., overriding the `request` closure to intercept or log transcripts) causes state leakage. A patched closure from Role A would leak Role A's transcript data into Role B's folder because the patch persisted on the shared object.

**The Fix:**
Implemented `_patched_model_request = agent.model` with a strict `finally` restore block. This ensures that even if an agent crashes or finishes, the model object is returned to its pristine state, physically preventing cross-role transcript contamination.

## 4. The `extract_tool_calls` Final-Response-Only Filter

**The Failure Mode:**
Pydantic-AI's internal turn-loop accumulates all intermediate tool calls. If the guardrail sums ALL intermediate tool calls across the entire loop, the condition meant to detect "the model finally answered the user" never correctly fires, because the aggregate always contains tool calls. This causes infinite re-entry into the agent loop.

**The Fix:**
The filter is heavily restricted to only inspect the *last* `ModelResponse`, explicitly excluding `final_result`. By isolating the very final turn, we accurately determine if the model yielded a conversational answer versus another tool request.

## 5. Non-Fatal `UsageLimitExceeded` Recovery

**The Failure Mode:**
When an agent (like a coder) exhausted its token or request budget, the framework would throw a `UsageLimitExceeded` exception and HALT the entire pipeline, killing unrelated, perfectly valid parallel tasks or subsequent phases.

**The Fix:**
We catch the exhaustion specifically and enforce a surgical recovery path by passing `tools=[]` to the model. This strips the agent of its ability to loop further and forces it to yield a final text response with its current context. This encapsulates the failure, allowing the orchestrator to recover the DAG and continue other work, rather than crashing the whole run. 
