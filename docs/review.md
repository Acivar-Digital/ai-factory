After reading the full post-fix state of all three files, here are the **new logic flaws** found in the current code:

---

## `execution.py` — New Issues

**`process_group` logic inversion still present** — this was flagged before and is **still NOT fixed**. The comment says "Fresh run when no prior exists" but the code is inverted:

```python
to_run = [] if prior else list(g.tasks)  # ← backwards
```

When `prior={}` (empty dict, falsy), this triggers a fresh run when it should adopt the prior verbatim. A `prior={}` is a valid truthy-empty batch — the correct guard is `if prior is None`.

**Validation re-spawn loop iterates `CODER_VALIDATION_PASSES + 1` times** — the loop is `for _pass in range(CODER_VALIDATION_PASSES + 1)` (i.e. 0–3 = **4 iterations**), but the HALT fires at `_pass + 1 > CODER_VALIDATION_PASSES` (i.e. `_pass > 2`, triggering at `_pass=3`). This means the coder gets **4 passes** not 3. The `+1` is leftover from the previous off-by-one fix and overshot.

**`subprocess` imported inside the hot loop** — `import subprocess` appears inside `execute_task` twice (inside the CQRS blocks). This is a module-level import being repeated per task invocation — harmless but indicative of copy-paste drift; the outer-scope `subprocess` import at top of file is sufficient.

---

## `pipeline.py` — New Issues

**`run_red_team_gate` double-appends `red_team` to exchange** — `append_exchange_turn(..., "red_team", rev_out, bd)` is called once after the reviewer runs, then again with `audit.model_dump_json()` inside the FORCED PASS block at `MAX_RETRIES`. On a forced-pass path, this appends the red-team turn **twice**, which corrupts the exchange history used by downstream roles.

**`_run_subprocess_with_timeout` discards stdout** — it only captures `stderr` (`stdout` defaults to inherited/terminal). But the caller in `run_ops_phase` constructs an error message using `stderr_text` — if the pre-push hook writes its failure reason to stdout (common), it's silently lost. Fix: add `stdout=asyncio.subprocess.PIPE` and include both in the error message.

**`passed()` treats a non-string, non-bool, falsy `approved` (e.g. `0`, `None`, `[]`) as FAIL** — the final `else: if not app: return False` branch catches these but the outer `return True` at the end of the evaluations loop will still return `True` if the falsy-non-bool item is not the last one. Any `approved: null` in a mid-list evaluation is silently skipped.

---

## `control.py` — New Issues

**`verify_gateways_reachable` catches all `httpx.HTTPError`** — this includes `httpx.HTTPStatusError` (4xx/5xx responses), which the docstring explicitly says should count as _reachable_. A 401 Unauthorized from a live gateway would incorrectly be reported as unreachable. Fix: only catch `httpx.ConnectError` and `httpx.TimeoutException`.

**`COMPACTION_CONFIG` is a plain `dict[str, object]`** — while `ControlSheet` and `SkillMap` were correctly Pydantic-ified (per the D06-C pattern), `COMPACTION_CONFIG` remains an untyped dict. Accessing keys like `COMPACTION_CONFIG["CONTEXT_COMPACT_CEILING"]` has no IDE/runtime validation and will silently return `None` on a typo.

---

## Summary

| File           | New Issue                                              | Severity  |
| -------------- | ------------------------------------------------------ | --------- |
| `execution.py` | `prior={}` falsy inversion still present               | 🔴 High   |
| `execution.py` | Re-spawn loop runs 4 passes, not 3                     | 🟡 Medium |
| `pipeline.py`  | Double exchange append on red-team forced pass         | 🟡 Medium |
| `pipeline.py`  | `_run_subprocess_with_timeout` drops stdout            | 🟡 Medium |
| `pipeline.py`  | `passed()` silently skips falsy non-bool `approved`    | 🟡 Medium |
| `control.py`   | `verify_gateways_reachable` catches 4xx as unreachable | 🟠 High   |
| `control.py`   | `COMPACTION_CONFIG` untyped plain dict                 | 🟢 Low    |
