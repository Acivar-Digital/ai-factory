# 00_fix: Audit-discovered bugfixes (2026-07-22)

Fixes applied in response to a third-party code review of `pipeline.py`,
`execution.py`, and `control.py`. All 7 real findings fixed.

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `pipeline.py:469` | `run_gated` returned `False` on PASS (caller can't distinguish pass from fail) | `return True` |
| 2 | `pipeline.py:275-301` | `do_role` had dead `if/else` branches — both executed identical code | Merged into shared helper |
| 3 | `pipeline.py:349-386` | `record_coder` copy-pasted `do_role`'s `UnexpectedModelBehavior` recovery | Both now call `_recover_from_unexpected_behavior()` |
| 4 | `execution.py:620` | `[] if prior else ...` treats empty `prior={}` (falsy) as "fresh run" | **Deferred** — original `prior={}` is intentionally passed by `run_red_team_gate` when `batch` is empty; treating `{}` as falsy is correct here |
| 5 | `execution.py:307-442` | HALT fired at `_pass=2` (3rd check) before the Nth re-spawn — got 2 re-spawns instead of `CODER_VALIDATION_PASSES` | Loop range `+1`, condition `>`, message says "re-spawn attempts" |
| 6 | `control.py:203-204` | Dead `if any(...): pass` in `_redact_payload` | Removed |
| 7 | `control.py:108` | `pydantic_url` defaulted to `:7766` (same as `literouter_url`) | `:7768` |
| 8 | `control.py:397` | `gemma_4_26b_a4b_it`: `context_window=16000 == max_completion_tokens=16000` → zero input budget | `max_completion_tokens=12000, context_window=32000` |

The reviewer's "double semaphore acquire" claim was incorrect — the first `async with sem:` in `execute_task` exits before the validation re-spawn loop.
