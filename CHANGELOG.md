# Changelog

All notable changes to the ai-factory orchestrator are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to semantic versioning for the harness itself.

## 2026-07-22 — Session Fixes: Auto-Remember Transparency + Budget Visibility

**Converter fixed to render full `batch_read`/`read_file` content** (no `[N lines]` truncation). **Budget markers `[TOOL CALL N/M]` preserved in `.md`** (converter no longer strips them). **READ_BUDGET raised to 15**. Auto-remember notes (raw line-numbered content) survive in `.jsonl`/`.md` context for next turn.

| # | File | Issue | Fix |
|---|------|-------|------|
| 1 | `factory/infra/converter.py` | Truncated `batch_read`/`read_file` to `[N lines]`; stripped budget markers | Remove summary truncation; remove `_CONTENT_NOISE` regex |
| 2 | `factory/infra/control.py` | `READ_BUDGET = 5` too low | Raised to 15 |
| 3 | `factory/infra/converter.py` | `[TOOL CALL N/M]` budget markers hidden from agent | Keep markers (transparency) |

## 2026-07-22 — Batch 11.1: CWD Fallback Bridges .env to Tool Resolution

**`_resolve_target_root()` now falls back to `CWD` env var (exported by `control.py`
from `.env`) before falling back to `PROJECT_ROOT`.** Previously, if `TARGET_REPO`
was not set (no `target_repo:` in `user_prompt.md` frontmatter), the tools resolved
against `PROJECT_ROOT` (= factory repo) — agents saw factory files instead of
target repo files. The `.env` file's `CWD=baziforecaster` was only read by
`control.py` and never propagated to `_codebase_common.py`.

**Fallback chain:** `TARGET_REPO` → `CWD` (from `.env` via `control.py`) → `PROJECT_ROOT`

| # | File | Issue | Fix |
|---|------|-------|------|
| 1 | `factory/infra/control.py` | `REPO_ROOT` loaded from `.env` but never exported to env | `os.environ.setdefault("CWD", str(REPO_ROOT))` |
| 2 | `factory/tools/_codebase_common.py` | `_resolve_target_root()` only checked `TARGET_REPO`, skipped `CWD` | Added `CWD` env var check between `TARGET_REPO` and `PROJECT_ROOT` |
| 3 | `tests/test_tool_read_file.py` | Test leaked `CWD` into subprocess env; unused `sys` import | Cleared `CWD`/`TARGET_REPO` in subprocess env; removed `sys` |

## 2026-07-22 — Batch 11: TARGET_REPO Separates Target Source from Harness Root

**All read tools now resolve against `TARGET_REPO` (set via `target_repo:` in
`user_prompt.md` frontmatter) instead of the hardcoded factory repo root.**
Previously, `REPO_ROOT` (`CWD`) served double duty as both the harness root AND
the source-file root — but `src2/` lives in the target repo (`baziforecaster/`),
not the factory repo (`ai-factory/`). Agents could never read `src2/...` paths
because `_codebase_common.py:resolve_secure_path` resolved against
`PROJECT_ROOT` (= factory repo).

**New model: two independent roots.**
- `resolve_secure_path()` — checks `TARGET_REPO` env var at call time; ALL
  paths resolve against target repo. Factory files (`.env`, `runner.py`) become
  invisible — agents have no business reading them.
- `resolve_repo_path()` — always resolves against `PROJECT_ROOT` (= factory
  repo). Used by write tools so edits land in `factory/temp/` as before.

| # | File | Issue | Fix |
|---|------|-------|------|
| 1 | `factory/tools/_codebase_common.py` | `resolve_secure_path` hardcoded to `PROJECT_ROOT` — agent could never read `src2/...` | Added `_resolve_target_root()` that checks `TARGET_REPO` env var at call time; added `resolve_repo_path()` for write tools |
| 2 | `factory/infra/pipeline.py` | No way for user to specify which repo has `src2/` | Parse `target_repo:` from YAML frontmatter; set `os.environ["TARGET_REPO"]` |
| 3 | `factory/infra/runner.py` | Same missing parsing in the runner entrypoint | Same parse + env set |
| 4 | `factory/infra/context.py` | `stage_workspace_from_draft` and `_real_source_paths` checked `REPO_ROOT / fp` — wrong when target is separate | Use `TARGET_REPO` env var (fallback `REPO_ROOT`) |
| 5 | `factory/tools/write_file.py` | Write tool used `resolve_secure_path` — would resolve against target repo (wrong for writes) | Switched to `resolve_repo_path` |
| 6 | `factory/tools/replace_text.py` | Same | Same |
| 7 | `factory/tools/replace_function.py` | Same | Same |
| 8 | `factory/tools/add_constant.py` | Same | Same |
| 9 | `factory/tools/add_import.py` | Same | Same |
| 10 | `factory/tools/delete_file.py` | Same | Same |
| 11 | `factory/tools/rename_file.py` | Same | Same |
| 12 | `factory/tools/move_symbol.py` | Same | Same |
| 13 | `factory/tools/get_repo_structure.py` | Imported `PROJECT_ROOT` directly — wrong repo | Uses `resolve_secure_path(".")` instead |

## 2026-07-22 — Batch 10: Auto-Remember on All Tools

**Every tool now auto-`remember_note()` after a successful operation so the LLM sees its own reads/writes in context next turn — no more re-reading files to verify.** The LLM has 1M token context and wants to test whether this eliminates research loops.

| # | File | Issue | Fix |
|---|------|-------|------|
| 1 | `factory/infra/tools_file.py` | `read_file`, `batch_read` returned results wrapped with nudge/steer instructions — remembering the noise | Now remember raw line-numbered content only |
| 2 | `factory/infra/tools_file.py` | `write_file` remembered only a tag `(N lines)` — LLM couldn't see what changed | Now remembers unified diff of old→new with `@@` line numbers |
| 3 | `factory/infra/tools_file.py` | `delete_file`, `rename_file` omitted entirely | Now remember the paths |
| 4 | `factory/infra/tools_shell.py` | `replace_text` remembered only char-count summary | Now remembers `---OLD---`/`---NEW---` sections with actual text |
| 5 | `factory/infra/tools_shell.py` | `replace_function` remembered only scope name | Now remembers full new function body |
| 6 | `factory/infra/tools_shell.py` | `add_constant` truncated to 80 chars | Now remembers full `NAME = value` line |
| 7 | `factory/infra/tools_shell.py` | `add_import` / `move_symbol` omitted | Now remember the import line and move paths |
| 8 | `factory/infra/converter.py` | Converter stripped `batch_read`/`read_file` results to `[N lines]` in `.md` — the auto-remembered content was truncated before reaching the LLM | Removed special-case truncation; full line-numbered content renders in `.md` |

## 2026-07-22 — Batch 9: Fix Bogus Tool Names in Agent YAML Prompts

**`planner.yaml` and `coder.yaml` listed `remember_fact`, `recall_fact`, `list_facts` as tools — none exist in `_TOOL_BY_NAME`.** The LLM trusted its system prompt, called `list_facts`, got a 404, then spiraled into analysis-paralysis trying to reconcile the discrepancy.

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `factory/infra/agents/planner.yaml` | `tools:` listed `remember_fact`, `recall_fact`, `list_facts` — none registered in `_TOOL_BY_NAME` | Renamed `remember_fact`→`remember`, dropped `recall_fact`/`list_facts` from `tools:` list and instruction allow-list text |
| 2 | `factory/infra/agents/coder.yaml` | Same bogus tools in `tools:` and instructions | Same fix |
| 3 | `factory/infra/agents/red_team.yaml` | READ-MEMORY BRIDGE text suggested `remember/remember_fact` tool call — role only has `batch_read` | Replaced with "markdown thought explanation only" |
| 4 | `factory/infra/agents/supervisor_review.yaml` | Same stale text | Same fix |
| 5 | `factory/infra/agents/supervisor_plan.yaml` | Same stale text | Same fix |

## 2026-07-22 — Batch 7: Fix `stop_phase` Checkpoint Not Wired in Runner

**`_checkpoint()` was defined in `pipeline.py` but never called from `runner.py`.** The `stop_phase` frontmatter field was parsed and stored in `args.stop_after` but the pipeline ran through all phases regardless.

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `factory/infra/runner.py` | `stop_phase` parsed from YAML frontmatter but never checked — pipeline always ran to completion | Wired `_checkpoint()` after each gate (supervisor_plan, supervisor_review, red_team) so `stop_phase` halts the pipeline at the right phase |
| 2 | `.agents/skills/ai-factory/SKILL.md` | Missing documentation on REPO_ROOT resolution and two-phase path model | Added full docs: how `CWD`/`.env`/`cwd()` set `REPO_ROOT`, where scope paths resolve, planner vs coder path bases, and diagnostic steps |

## 2026-07-22 — Batch 8: Add Field Descriptions to EvaluationItem Schema

**`EvaluationItem` Pydantic model had bare type annotations with no semantics.** The JSON Schema the model receives only carried types (`str`, `"Yes" | "No"`) — no descriptions or examples. The model had to infer meaning from free-text prose instead of reading it directly in the form it fills.

| # | File | Issue | Fix |
|---|------|-------|------|
| 1 | `factory/infra/models.py` | `EvaluationItem` fields had no `Field(description=...)` — model couldn't see semantics in the structured output schema | Added `description` and `examples` to every field: `item_id` (must match task id), `approved` (Yes=proceed, No=reject+explain), `comments` (required on No, empty on Yes) |

## 2026-07-22 — Batch 6: Shadow Tools Fixes (Line Numbers, Formatting, Whitespace, Edge Cases)

**Comprehensive fixes for codebase investigation and modification shadow tools.** Addressed critical bugs preventing the LLM from accurately referencing line numbers, preserving codebase formatting, and performing reliable string/regex replacements.

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `factory/tools/read_file.py` | Missing line numbers in output, forcing the LLM to manually count lines | Prepended `N:` line numbers to the output, correctly offsetting by the start index |
| 2 | `factory/tools/read_file.py` | The end-line variable `e` shadowed the exception block variable `e` | Renamed exception block variable from `e` to `ex` |
| 3 | `factory/tools/investigate.py` | Context truncation blindly cut characters (e.g. `12000 * 3.8`), slicing through lines and line number prefixes | Truncation now safely slices at the last complete newline before the limit `rfind('\n', 0, limit)` |
| 4 | `factory/tools/investigate.py` | `extract_pattern_context` created disjointed, visually ambiguous blocks for nearby/overlapping grep matches | Refactored to compute overlapping intervals and merge them into larger contiguous blocks with proper `>>> ` match markers |
| 5 | `factory/tools/replace_text.py` | `--ignore-whitespace` doubly-escaped whitespace (`re.escape` then `re.sub`), resulting in a broken regex | Fixed regex compilation by splitting the input on spaces, escaping chunks, and rejoining with `\s+` |
| 6 | `factory/tools/replace_function.py` | Using `ast.unparse()` wiped all comments and reformatted the entire file | Replaced AST rewrite with precision string slicing based on `node.lineno` and `node.end_lineno`, preserving all file formatting |




## 2026-07-22 — Batch 5: Guardrail Fail-Loudly, Schema Gate Logging, and Verdict Logic

**Audit-driven fixes for 5 execution and validation logic bugs.** Addressed silent-pass vulnerabilities in the staging guardrails, schema gating, and red team validation.

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `runner.py:244` | Final verdict hardcoded to `"PASS" if "This Harness is Working" in last_coder else "CHECK"`, causing all real runs to emit `CHECK` | Verdict now evaluates `batch.results` statuses (`"done"` = `PASS`, else `CHECK`), falling back to history if batch is missing |
| 2 | `execution.py:357` | Guardrail crashes (`except Exception as guard_exc`) silently `continue`d the loop, bypassing failure flags and marking the task as passed | Set `ruff_failed = True` and inject a `[GUARDRAIL CRASH]` feedback block to force a re-spawn |
| 3 | `execution.py:368` | Unparseable guardrail output (e.g. tool emitted raw warnings instead of JSON) triggered a silent `continue` pass | Set `ruff_failed = True` and inject a `[UNPARSEABLE GUARDRAIL]` feedback block to force a re-spawn |
| 4 | `execution.py:543` | `load_schema_gate.py` crashes were caught by a bare `except Exception: pass`, silently allowing broken schemas to proceed as `done` | Logged the exception, set `obj["status"] = "blocked"`, and appended the crash to `obj["notes"]` |
| 5 | `validation.py:100` | `red_team_passed` returned `True` if `rubric_cells` was an empty list (LLM bypassed quality check entirely) | Replaced with `has_audit_data = bool(findings) or bool(rubric_cells)`, ensuring empty audits fail |

## 2026-07-22 — Batch 4: coder_fn signature adapter + PHASE_SUMMARIES race guard

**Audit-driven fixes for 2 of 4 reported bugs.** The critical fix: `record_coder` and
`do_role` were passed as bare `coder_fn`/`reviewer_fn` to `run_code_review_gate` and
`run_red_team_gate`, but the call site `coder_fn(brief, task_id=t.id)` only supplies 2
arguments while `record_coder` requires 6. Runner uses `do_role` as the reviewer, but
`do_role` entirely ignores the caller's brief (it reads from `state_dict["brief"]`).

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `runner.py:203-238` | `record_coder` (6 params) and `do_role` (8 params) passed directly as callables to gate functions — called as `cod er_fn(brief, task_id)` / `reviewer_fn(brief)`, crash at runtime | Wrap in closure adapters that capture `bd`, `history`, `prior`, `state_dict`; use `load_skill` wrappers for reviewers instead of `do_role` |
| 2 | `agent.py:537-541` | `PHASE_SUMMARIES[role]` write inside `load_skill` is unguarded — concurrent coders via `asyncio.gather` race on `PHASE_SUMMARIES["coder"]` | Guard with `role != "coder"` — downstream phases use `RAW_OUTPUTS`/`TaskBatch` for coder results |

**Not a bug (verified):** `build_coder_spec()` hardcodes `tool_allow_list=[]`, but
`build_skill_spec()` in `tools.py:1601-1603` fills from `SKILL_MAP.tool_bucket` when
the list is empty — so coders do receive tools.

**Deferred:** Re-spawn coder stale `message_history` (Bug 1) — the MD bridge
intentionally provides continuity and the feedback brief injects corrections.

## 2026-07-22 — Batch 3: DAG executor hardening (concurrent flag, cross-group, deadlock)

**Third wave of DAG executor fixes.** Removed misleading `concurrent` field
from `WorkGroup` model, made cross-group file-disjointness check `depends_on`-aware,
and added secondary timeout to deadlock fallback.

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `models.py:137`, `execution.py:66`, `pipeline.py`, `ledger.py`, `planner.yaml` | `WorkGroup.concurrent` field was ignored by executor for dispatch but exposed to planner, creating a contract mismatch | Removed `concurrent` from `WorkGroup` model; executor always checks intra-group disjointness; depends_on groups count as sequential in topology log |
| 2 | `execution.py:85-95` | Cross-group file overlap check fired on ALL groups including `depends_on` chains where sequential execution makes overlap safe | Added transitive dependency closure; only concurrent groups (no depends_on relationship) trigger the overlap HALT |
| 3 | `execution.py:611` | Deadlock fallback wait was unbounded — hung forever if prerequisite crashed silently | Added secondary timeout (`DAG_DEADLOCK_TIMEOUT * 2`) that raises `RuntimeError` |
| 4 | `tests/test_file_disjoint_filter.py` | True-positive overlap test used `depends_on` groups (sequential, no race) | Updated to genuinely concurrent groups; added new `test_depends_on_chain_allows_file_overlap` |

**Not a bug (re-confirmed):** `to_run = [] if prior else list(g.tasks)` — `bool({})` is
`False`, so `prior={}` runs all tasks correctly per design intent.

## 2026-07-22 — Batch 2: 4 real bugs from second code review

**Second wave of audit-driven fixes** in response to an independent review
(`docs/review.md`). 5/7 claims verified; 4 real bugs fixed; 1 claim
hallucinated; 1 debatable (re-spawn loop intent ambiguous).

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `pipeline.py:853` | Double red_team exchange append on forced pass — appended raw `rev_out` then modified audit in same call | Removed the second append; existing entry updated in-place with modified audit |
| 2 | `pipeline.py:881-900` | `_run_subprocess_with_timeout` dropped stdout (no `stdout=PIPE`) | Added `stdout=asyncio.subprocess.PIPE`; merged stdout+stderr into returned text |
| 3 | `control.py:317` | `verify_gateways_reachable` caught all `httpx.HTTPError` — 4xx counted as unreachable despite docstring | Changed to `except (httpx.ConnectError, httpx.TimeoutException)` |
| 4 | `control.py:576` | `COMPACTION_CONFIG` was untyped `dict[str, object]` with no validation | Migrated to strict `CompactionConfig(BaseModel)` + `PerRoleConfig`; `_loopguard.py` updated to attribute access |

**Hallucinated claim rejected:** "`passed()` silently skips falsy non-bool `approved`"
— the `else: if not app: return False` branch correctly catches `None`/`0`/`[]`
at any position and exits immediately.

**Debatable claim noted:** "re-spawn loop runs 4 passes not 3" —
`CODER_VALIDATION_PASSES=3` with `range(3+1)`=4 iterations is internally consistent
(1 initial + 3 re-spawns), but whether the constant means "total passes" or
"re-spawn attempts" is ambiguous.

**False positive (ex-review):** `prior={}` falsy inversion — tests explicitly pass
`prior_batch={}` to mean "no prior, run fresh"; the original `[] if prior else ...`
is correct for all callers.

**Tests:** 224/224 pass, ruff clean on changed files.

## 2026-07-22 — Audit: 7 bugfixes from third-party code review

**Audit-driven fixes across `pipeline.py`, `execution.py`, and `control.py`**
in response to an external code review. 8/9 claims verified; 7 real bugs fixed.

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `pipeline.py:469` | `run_gated` returned `False` on PASS (caller can't distinguish pass from fail) | `return True` |
| 2 | `pipeline.py:275-301` | `do_role` had dead `if/else` branches — both executed identical code | Merged into shared `_recover_from_unexpected_behavior()` |
| 3 | `pipeline.py:349-386` | `record_coder` copy-pasted `do_role`'s `UnexpectedModelBehavior` recovery | Both now call shared helper |
| 4 | `execution.py:307-442` | HALT fired at `_pass=2` before the Nth re-spawn — got 2 re-spawns instead of `CODER_VALIDATION_PASSES` | Loop range `+1`, condition `>`, message says "re-spawn attempts" |
| 5 | `control.py:203-204` | Dead `if any(...): pass` in `_redact_payload` | Removed |
| 6 | `control.py:108` | `pydantic_url` defaulted to `:7766` (same as `literouter_url`) | `:7768` |
| 7 | `control.py:397` | `gemma_4_26b_a4b_it`: `context_window=16000 == max_completion_tokens=16000` → zero input budget | `max_completion_tokens=12000, context_window=32000` |

**False positive rejected:** "double semaphore acquire" claim (first `async with sem` exits before re-spawn loop — no deadlock).

**`prior={}` edge case deferred** — intentionally passed by `run_red_team_gate` to mean "no prior batch"; original `[] if prior else ...` is correct.

**Discipline memory clarified** — "no fallback chains" means model-level fallback only; agent-level recovery (same model loopguard retry + `_recover_from_unexpected_behavior`) is the correct pattern, not raw crash.

**Documentation:**
- Audit log written
- `.agents/skills/ai-factory/SKILL.md` — updated
- `AGENTS.md` — removed stale fact-tool references (`remember_fact.py`, `recall_fact.py`, `list_facts.py` were purged in memory unification 2026-07-21)
- `bd` discipline memory clarified

**Tests:** 225/225 pass, ruff clean on changed files.

## 2026-07-21 — Monolithic runner.py refactored into modular architecture

**3558-line `runner.py` split into 10 focused modules.** The monolithic orchestrator
was extracted into a package of single-responsibility files:

| Module | Purpose | Lines |
|---|---|---|
| `_runtime.py` | Module globals: `RAW_OUTPUTS`, `PHASE_SUMMARIES`, `_PHASE_ORDER`, `SCOPE_CONTEXT` | 16 |
| `exchange.py` | Exchange-turn / status-board / JSONL persistence | 302 |
| `agent.py` | Agent builder: `build_role_agent`, `load_skill`, `_run_agent_retry`, `_coder_agent_id` | 548 |
| `context.py` | Staging: `stage_workspace_from_draft`, `_stage_copies`, `_write_harness_patches`, tier-B map | 438 |
| `validation.py` | Invariant checks: `check_plan_invariants`, `red_team_passed`, constants | 210 |
| `execution.py` | EXECUTE phase: `run_execute_phase`, task execution, per-task timeout, harness patching | 935 |
| `pipeline.py` | Gate orchestration: `run_code_review_gate`, `run_red_team_gate`, `run_ops_phase`, `run_gated` | 977 |
| `runner.py` | Slim conductor: `main()`, `read_prompt()`, imports gates/agents (221 lines, was 3558) | 221 |
| `agents/` subpkg | 7 Python + 7 YAML role specs (planner, coder, supervisor, red_team, ops, healer) | ~30 files |
| `__init__.py` | Package exports | 29 |

**Tests migrated.** 46 test files updated: `from factory.infra.runner import X` → direct
imports from new modules. Monkeypatch targets converted from `monkeypatch.setattr(runner, X)`
to string-based `monkeypatch.setattr("factory.infra.module.X")` so patches hit the module
where the name is actually resolved (execution.py / context.py / agent.py import their
dependencies with `from ... import` creating private references). All 225 tests pass.

## 2026-07-21 — ModelHTTPError 400 retry in loopguard

**ModelHTTPError 400 retry.** `_loopguard.py` now catches `ModelHTTPError(status_code=400)` inside the `while True` loop and retries up to 3 times with 5/10/15s backoff before propagating. Other status codes (401, 403, etc.) still fail loudly via the existing `except Exception` handler. Added 3 regression tests for the retry path.

## 2026-07-21 — Memory unification, line-number prefix, nudge on search tools, discipline cheat-sheet

**Item 1 — Memory unification.** Deleted `admin/tools/remember_fact.py`, `recall_fact.py`, `list_facts.py` (dead round-trip: write to `facts/memory.jsonl`, read from non-existent `temp/facts.jsonl`). Purged all wrappers in `infra/tools.py` (function defs, `READ_ONLY_TOOLS`, `MODIFY_TOOLS`, `GuardToolset.call_tool` guard, `guard_tools` param, import, `GuardToolset` fields). Deleted orphaned `facts/memory.jsonl` (174 entries, never recallable). Removed `RECALL_BUDGET` from `control_orchestrator.py`. All agents use `remember()` only.

**Item 2 — Line-number prefix.** `runner.py:inline_files` now prefixes every injected file line with `N: ` so "do-not-touch lines 3110/3114/3115" guardrails are verifiable in the coder dump.

**Item 3 — Memory nudge on search tools.** Prepended `_REMEMBER_NUDGE` to all 8 search tool wrappers (`investigate`, `search`, `list_files`, `get_file_symbols`, `get_repo_structure`, `query_knowledge_graph`, `find_related_code`, `get_code_hierarchy`), `batch_read`, and `read_file`. Removed stale `remember_fact` reference from `GuardToolset.call_tool` SYSTEM NOTE (`tools.py:522`). Nudge text unchanged (already says `remember()`).

**Item 5 — Verification scope (scaffold).** Scope defined: ruff + pyright + targeted module import. Loop mechanism remains OPEN (deferred).

**Item 8 — Discipline cheat-sheet.** Injected frozen `discipline_block` into every coder brief summarizing load-bearing rules (zero-dicts, pydantic-only, fail-loudly, fail-cheaply, no src/ edits, ruff passage).

**Tests:** Updated `test_cli_contract.py` (removed fact-store tests), `test_read_memory_bridge.py` (removed — nudge moved to function level), `TEST/test_mcp.py` (removed Memory Lane).

## 2026-07-21 — Fix: SPAWN-ALL HALT defeats supervisor_review recovery

**Incident:** `hbh1` run crashed with
`RuntimeError: [HALT] EXECUTE phase incomplete: coder03, coder07` *before*
any review. Root cause was **not** the coder — both coders had returned
`status:"done"`; the harness flipped them to `blocked` (B3 fake-done on the
placeholder smoke plan) and the SPAWN-ALL HALT then aborted the run.

**Root cause:** `run_execute_phase` raised the SPAWN-ALL HALT
(`runner.py:2224`) *inside* the initial dispatch of BOTH recovery gates
(`run_code_review_gate` `:2246`, `run_red_team_gate` `:2474`). Those gates
own a `supervisor_review`/`red_team` retry + `force-pass` loop
(`MAX_RETRIES=3`) whose entire purpose is to recover `blocked` work — but
the HALT fired first and killed the function, so the retry loop was **dead code**.
The HALT ("no incomplete work reaches review") directly contradicted the
gate's designed recovery. The harness had silently usurped the supervisor's
recovery authority.

**Fix:**
- `run_execute_phase` gains `strict: bool = True`. The SPAWN-ALL HALT
  now fires only when `strict=True` (top-level caller with no recovery owner).
- All four gate call sites (`run_code_review_gate` initial `:2246` + rerun
  `:2302`; `run_red_team_gate` initial `:2474` + rerun `:2609`) pass
  `strict=False`, so incomplete `TaskResult`s are **returned, not raised**, and
  flow into the gate's retry/`force-pass` loop — restoring the supervisor's
  recovery authority.
- `TaskNeedsSplitError` and the inner per-task pyright HARD-HALT (`1967`),
  B3 fake-done (`2079`), and the `force-pass` net all remain unchanged.
- `test_spawn_all_halt.py` still passes (it calls `run_execute_phase` with the
  default `strict=True`, so the HALT still fires for direct callers — guarding
  the original `uqj06` SPAWN-ALL behaviour).

**Tests:** `admin/orchestrator/test/test_spawn_all_halt_recovery.py`
(`strict=False` returns incomplete instead of raising; default `strict=True` still
halts; gate completes without HALT on a blocked task). `test_harness_gates.py`
`test_staging_diff_gate_zero_diff` / `test_runtime_load_gate_fails` updated to assert
the execute-phase gating directly via `run_execute_phase(strict=True)` (they
previously relied on the early-abort HALT and passed a sync reviewer that is now
actually invoked once the gate recovers).

## 2026-07-21 — Fix: Staging Diff Gate spurious zero-diff HALT

**Incident:** `hbh1` EXECUTE phase aborted with
`RuntimeError: [HALT] EXECUTE phase incomplete: coder01..coder05, coder07`.
6 of 7 coder tasks were wrongly `blocked` as "zero-diff hallucination".

**Root cause:** The Staging Diff Gate (`runner.py`, PRE-REVIEW GATES) compared
`REPO_ROOT / fp` against `REPO_ROOT / "admin/orchestrator/temp" / fp` with
`filecmp.cmp`. When a coder reported an ABSOLUTE staging path, the `Path(...)/`
join collapsed BOTH sides to the same physical staging file, so
`filecmp(file, file)` was always identical → spurious block → SPAWN-ALL HALT.
The Load-Schema Gate had the same broken concat and silently skipped relative `fp`.

**Fix (Fix A + B):**
- `stage_path()` is now the SOLE normalization seam: it collapses absolute AND
  relative temp prefixes to `TEMP_DIR/<rel>`, and every gate routes through it.
- Deleted the redundant `filecmp` Staging Diff Gate. Change-detection is unified
  on the harness-captured `.orig` baseline (B1) via a new testable helper
  `staged_zero_diff(fp) -> bool | None`.
- Genuine zero-diff is folded into the `CODER_VALIDATION_PASSES` re-spawn loop
  (Q5 Option B): re-spawn the coder to actually edit, then block via the
  SPAWN-ALL HALT only if it persists. New files / hallucinated paths defer to
  patch-generation's `real_changes` (no spurious block).
- Load-Schema Gate now resolves via `stage_path(fp)` (validates both path forms).
- SPAWN-ALL HALT kept for genuine fake-done failures.

**Tests:** `admin/orchestrator/test/test_staging_gate.py` (5 regression
cases: absolute+relative `stage_path` collapse; real edit not blocked; genuine
zero-diff; new file; hallucinated path).

## [Unreleased] - 2026-07-20

### Fixed
- **hbh1 validation gate root-cause fixes (Defect A + Defect B + Fixes C'/E/F/G/H).**
  - Root cause (two compounding harness defects, NOT "Fix A missing"): **Defect A** — `guardrail_check.py validate` ran pyright/smoke on the ISOLATED STAGING COPY (`admin/orchestrator/temp/src2/...`), so the file inferred as `admin.orchestrator.temp.src2...` and `reportMissingImports` fired on every cross-module import (e.g. `Import ".db" could not be resolved`), and `src2` was excluded from `[tool.pyright] include`. **Defect B** — the checkpoint was taken lazily *after* the coder edit, so `diff_vs_checkpoint` was always empty and the changed-line filter (`_changed_line_set`) never engaged, blocking coders on pre-existing whole-file errors.
  - Architectural principle (Francis): *"other coder's shit is our shit"* — the gate must (1) run where imports resolve and (2) hold a coder accountable only for errors it introduced on the lines it changed.
  - **Fix A' (Defect A):** `validate` now builds a throwaway validation sandbox (`build_validation_sandbox`) mirroring the repo (symlinked `.venv`/`pyproject.toml`/`src`/`src2`), copies the staged file to its TRUE package path, and runs ruff/smoke/pyright in that sandbox so relative imports resolve. Added `_virtual_live_path`, `_realize_symlink`, `_materialize_along`. The live tree is never touched.
  - **Fix B' (Defect B):** replaced the checkpoint-based `_changed_line_set` with `_changed_lines_from_diff(diff_text)` + `diff_staged_vs_original(staged, live)` (baseline = LIVE ORIGINAL on disk, no sidecar `.bak`/checkpoint file). The changed-line filter now engages against the real pre-edit source. `validate` MUST NOT use `checkpoint`.
  - **Fix C':** added `"src2"` to `[tool.pyright] include` so the sandbox `src2` (symlinked) is within the configured context.
  - **Fix E:** `runner.execute_task` now auto-applies `ruff check --fix` + `ruff format` to the staged file on a ruff failure, then re-scores the auto-fixed file (no model re-spawn for trivial I001/UP034). Appends a `RUFF AUTO-FIX APPLIED` note.
  - **Fix F:** `typecheck_union` drops any pyright error whose file basename is NOT in the coder's edited set (dependency errors are non-blocking); remaining errors are scoped to changed lines only.
  - **Fix G:** `runner.execute_task` now emits `log_operator(level="ERROR")` for the validation-exhaustion HALT so the gate reason is visible next to the SPAWN-ALL HALT.
  - **Fix H:** `smoke_test.py` now imports the staged module by its dotted package name (`_module_dotted` → `importlib.import_module`) so relative imports resolve, and treats import-time `OperationalError`/`ConnectionError`/`OSError` (DB/network at import) as a non-blocking SKIP rather than a failure.
  - Added `TEST/unit/test_validation_gates.py` (18 tests, green) covering changed-line parsing, virtual-live-path mapping, diff-vs-original, union dependency-error dropping, validate end-to-end scoping, smoke env-skip, and the BUG-2 heuristic regression.
- **Coder status-string contract (02_fix.md — `RuntimeError: [HALT] EXECUTE phase incomplete: coder03, coder07`).**
  - Root cause: the coder LLM emitted `status:"completed"` (a non-canonical key); `TaskResult.status` was typed `str` with no constraint, so `"completed"` slipped through and the EXECUTE completion scan hard-halted the whole phase (the harness only treats literal `"done"` as success).
  - Constrained `TaskResult.status` to `Literal["done","blocked"]` in `models.py` so the pydantic-ai-injected coder "form" now lists exactly `done | blocked` (Fix 1's crystal-clear form).
  - Added a `mode="before"` `_norm_status` validator that normalizes synonyms (`complete`/`completed`/`completes`/`ok`/`success`/`finished` → `done`; `fail`/`failed`/`error` → `blocked`, case-insensitive) and raises `ValueError("status must be 'done' or 'blocked'")` on anything unknown — so pydantic-ai feeds the error back and HALTs after retries (no silent swallow). The validator runs `mode="before"` so normalization happens *before* the `Literal` check (an after-validator would reject `"completed"` before it could be normalized).
  - Added `Field(description=...)` to `notes` (ERROR / ACTION / EXPECTED / DELIVERABLE structure when blocked) and `diff_summary` so the free-text fields carry required structure, not open prose (Fix 2).
  - Single source of truth: the model-field validator IS the allowlist; no FROZEN allowlist bolted onto `runner.py` and no `output_sanitizer.py` change needed (the coder goes through `json.loads`/`TaskResult`, not `clean_role_output`).
  - Added `admin/orchestrator/test/test_02_fix_status_contract.py` (9 tests, green) guarding normalization, rejection, the schema enum, and the field descriptions.
- **Harness-owned patch generation (01_fix.md)**
  - Moved `.diff` patch generation from the `coder` LLM to the deterministic orchestrator harness (`runner.py`) to prevent corrupt/synthetic patches with fake git hashes or malformed hunks.
  - Modified `_stage_copies` to capture `.orig` baseline files at staging time for all edited files.
  - Added `_write_harness_patches` to diff each staged file against its `.orig` baseline and output valid git-apply compatible `.diff` files.
  - Added `_quarantine_coder_artifacts` to sweep the `temp/` directory for any hand-written patches (`*.diff`, `*_patch.py`) produced by the coder and move them to `temp/quarantine/` to prevent collisions.
  - Hooked the generation and quarantine functions into `execute_task` to run immediately after the validation re-spawn loop completes (and only when `status=="done"`).
  - Hard-fails (`status="blocked"`) any coder that claims `done` but made zero file changes compared to the `.orig` baseline (fake-done detection).
  - Updated `coder.yaml` prompt templates to explicitly instruct the coder NOT to write diffs, but only edit the staging files.
  - Updated `user_prompt.md` to reflect the new PROPOSE-ONLY / PATCH RULE workflow.
- **Validation gate + review prompt hardening (01_fix.md, continued — tzsdl).**
  - `admin/tools/smoke_test.py` (NEW): a deterministic type-construction gate that detects BUG 2 (a `DictMap[str]` rejecting model instances). Flags any `<X>Map` container whose declared value type is wide (`str`/`Any`/`object`) while a same-file `<X>` model exists but the container rejects an `<X>` instance.
  - `TaskResult` (`models.py`) now carries the `ValidationVerdict` fields (`ruff_ok`, `pyright_ok`, `exec_ok`, `verdict_errors`, `verdict_diff`, `dep_pointers`) so the harness fills the *verdict* half after the smoke + ruff + pyright gates run.
  - `guardrail_check.py` broadened to a **bounded union pyright** (≤5000 lines / ≤4 files / ≤20K lines total) and added `discover_dependencies` so per-stage pyright runs against a producer file before its dependent consumers.
  - `runner.execute_task` re-spawn loop now (a) runs the smoke gate, (b) makes `pyright` **blocking**, (c) **HARD-HALTS** on the 3rd validation failure, and (d) populates `verdict_state`.
  - Reviewer/`red_team` briefs now render the staged **diff** + the `ValidationVerdict` block + `dep_pointers` so reviewers see machine verdicts alongside the coder's claims.
  - `planner.yaml` now requires a `depends_on` edge (producer→consumer) when a task's type contract is consumed by another edited file (D8), and the DAG enforces order + HARD-HALTS the EXECUTE phase on a 3rd validation failure.
  - `supervisor_review.yaml` / `red_team.yaml` templates: removed the blanket "trust the TaskBatch" wording, now permit re-reading upstream dependencies to verify type contracts, and raised the research-call hard limit 10→15.
  - `user_prompt.md` CORRECT pattern example now uses `DictMap[ExternalPillarTrigger]` (not `DictMap[str]`).
  - Added `admin/orchestrator/test/test_01_fix_harness.py` guarding all of the above (9 tests, green).
- **EXECUTE-phase HALT regression — over-scoped pyright gate (01_fix.md, run `hbh1`).**
  - Root cause: the `01_fix` validation gate (`guardrail_check.py typecheck_file` / `typecheck_union`) filtered `our_errors` by file name ONLY, not by changed line. Pre-existing pyright errors anywhere in the target file (e.g. coder07 edited only `module3_interaction.py:~978` but was blocked on 34 pre-existing errors at lines 620–1398) blocked the coder, and the SPAWN-ALL HALT then fired before the recovery loop — halting coder03/coder07.
  - Architectural principle enforced (Francis, 2026-07-21): *"other coder's shit is our shit"* — a task-scoped coder must only be held accountable for errors it INTRODUCED on the lines it CHANGED.
  - **Fix A (root):** `typecheck_file` / `typecheck_union` now intersect `our_errors` with the changed-line set parsed from `diff_vs_checkpoint` (`@@ -a,b +c,d @@` hunk headers, `+`-prefixed lines → current-file line numbers). Added `_parse_pyright_error` and `_changed_line_set` helpers. Errors on unchanged lines are filtered out; the whole-file scope is used only when no checkpoint exists (legacy behaviour). New errors on changed lines are still caught and still block. This is the actual root fix; Fix C (recoverable HALT) is complementary and deferred.
  - **Fix B (observability):** added `log_operator(level="WARNING")` on the three previously-silent blocked paths in `runner.execute_task` — (1) initial coder timeout (`asyncio.wait_for` first pass), (2) re-spawn (validation-loop) coder timeout, (3) validation-exhaustion: the harness-owned `RuntimeError("[HALT] task <id> failed validation after N coder passes …")` is now surfaced loudly next to the SPAWN-ALL HALT instead of being swallowed into a generic `blocked` note. No change to HALT semantics.
  - Added `admin/orchestrator/test/test_guardrail_changed_line_scoping.py` (7 tests: changed-line parsing, per-file union scoping, whole-file fallback, clean-edit passes) and `admin/orchestrator/test/test_fix_b_loud_blocked_paths.py` (3 tests: the three blocked paths each emit a WARNING log + blocked `TaskResult`). Both green.

### Changed

- **Test suite consolidation (66szk).**
  - Merged the three scattered test locations (`admin/orchestrator/test/`, `admin/orchestrator/test/tools/`, `admin/orchestrator/tests/`) into a single flat `admin/orchestrator/test/` directory. `bifr/` sub-suite preserved. Removed the now-duplicate `tests/` and `test/tools/` trees.
  - Repointed stale `admin.orchestrator.tests` imports to `admin.orchestrator.test` in `test_harness_gates.py` and the three `bifr/*.py` files.
  - Added `admin/orchestrator/test/run_all.py`: a dependency-free parallel runner that fires every `test_*.py` (and `bifr/`) as its own `pytest` subprocess via a `ThreadPoolExecutor`, then prints a consolidated PASS/FAIL report. Flags `--workers` and `--per-file-timeout` (default 16 / 300s). Returns non-zero if any file fails.
  - Recreated `admin/orchestrator/test/test_cli_contract.py` (lost during the merge: it was untracked) — covers coder budget scaling/clamp, staging path normalization, and the local JSONL fact-store roundtrip.
  - Added `admin/orchestrator/test/README.md`: the FROZEN-SUITE policy (tests may not be dropped/weakened without explicit approval), the go-live feature-preservation objective, a how-to-add-test guide, and a per-script registry.

### Added
- **Dedicated timeout-fire test (66szk).**
  - Added `admin/orchestrator/test/test_timeout_fire.py` with two tests that set `AGENT_RUN_TIMEOUT=1.0` (via monkeypatch, never touching the live `600.0` constant) and assert the harness actually trips (RuntimeError `EXECUTE phase incomplete`) instead of hanging — for both a directly-hung coder and a hung coder in a dependent group.

### Fixed
- **DAG Timeout Crash (hbh1) fixes (s49n0/01_fix.md).**
  - Raised coder tool budget to 75 in `ROLE_TOOL_BUDGET` to support larger tasks and avoid false-block loopguard overrides.
  - Fixed runner status override logic to only set status to `"blocked"` when the task's status was not already `"done"`, avoiding override of successful coder runs.
  - Added constraints/hard rules to `planner.yaml` and `supervisor_plan.yaml` templates limiting tasks to ≤5 files and requiring disjoint file scopes.
  - Added plan invariant validation gate (`check_plan_invariants` / `PLAN_INVARIANT_RETRIES`) and retry loop in `do_role()` for planner and supervisor_plan roles.

- **DAG Liveness Guard + Per-Task Timeout + add_constant Guidance (s49n0).**
  - Replaced the blind 300s DAG dependency wait at `runner.py:1738` with an unbounded wait + liveness guard. The liveness guard only raises if a prerequisite group has already completed (`group_done[d]=True`) but forgot to signal its event. A slow-but-legitimate group (coder re-spawns >5min) is waited on indefinitely, matching the SPAWN-ALL halt semantics. `DAG_DEADLOCK_TIMEOUT = CODER_VALIDATION_PASSES * AGENT_RUN_TIMEOUT = 1800.0s` is the backstop.
  - Added `group_done: dict[str, bool]` alongside `group_events` and set `True` at both normal-exit and empty-to_run sites. Not set at `TaskNeedsSplitError` (deliberately abort).
  - Wrapped **both** `coder_fn` call sites (initial pass at `runner.py:1530` and re-spawn pass at `runner.py:1654`) in `asyncio.wait_for(timeout=AGENT_RUN_TIMEOUT)` so a hung coder times out individually -> marked `blocked` -> caught by SPAWN-ALL halt.
  - Added `add_constant` usage guidance to `templates/coder.yaml` warning it is for simple constants only (not class/function definitions).
  - Added empty-value guard to `admin/tools/add_constant.py`: missing/empty `constant_code` now exits rc=1 with a clear, model-actionable message instead of a cryptic argparse usage dump.
  - Added `PRIOR ATTEMPT REJECTION` block to re-spawn `feedback_brief` at `runner.py:1645` so a fresh re-spawn agent sees why its predecessor was rejected.
  - Imported `AGENT_RUN_TIMEOUT` from `_loopguard` into `runner.py`.
  - Added comprehensive test suite `admin/orchestrator/tests/test_01_fix_liveness.py` (6 tests: 2 for DAG liveness, 1 for constant correctness, 1 for per-task timeout, 2 for add_constant guards). All 6 pass.

- **Red-Team Gate Vocabulary Crash fix (61y93 / 01_fix.md).**
  - Root cause: red_team evaluated by the planner's User-Story ids (`US-1/2/3`) instead of `coder_N`, but the gate could not map `US-3` -> `coder_3` (planner `coder_idents` were empty), so it raised HARD FAIL on attempt 1 and aborted the whole run — even when the cited engine shims were fine.
  - **Fix A (planner.yaml):** added the ONE FILE = ONE CODER planning-method block (understand intent/scope, identify + count files, give per-file instructions) and the standing invariant that each file belongs to exactly one coder.
  - **Fix C (runner.py `run_red_team_gate`):** replaced the empty `coder_idents`-dependent mapping with an authoritative `file_to_coder` resolver built from `plan.workplan` (file_paths -> coder_N), with rubric `coder_idents` + comment-filename backstops (`resolve_item`). Unresolvable items keyed by a planner user-story id (a vocabulary slip, e.g. `US-3`) are force-passed on the final attempt (propose-only, unpushed) instead of aborting; genuine global blockers (e.g. `rubric_global`) still HARD FAIL.
  - **Fix F (runner.py):** on the final attempt, the forced-pass loop prepends a self-describing `[FORCED PASS attempt N — UNVERIFIED, review files: [...]]` marker into `ev.comments` and re-records the coerced `AuditResult` into the exchange JSONL so the operator sees exactly which files to review manually.
  - **Fix D (red_team.yaml + supervisor_review.yaml):** reviewer prompts now require `item_id` to be a `coder_N` task id (or a file path) and forbid reusing the planner's `US-*` scheme.
  - Added regression test suite `admin/orchestrator/test/test_01_fix_red_team_vocab.py` (4 tests: US-* rejection does not hard-fail; forced-pass marker names the resolved file; planner intent block present; reviewer prompts require coder_N + forbid US-*). harness_smoke-free, no `src2/` edits.

- **Coder loop-resilience: no more false-blocks / dumb-LLM hang-abort (6yyif / 01_fix.md).**
  - **CHANGE 1 (done):** Replaced the single global `UsageLimits(request_limit=40)` in `run_with_loopguard` (`_loopguard.py`) with a per-role map (`role_request_cap`). The hard API-call cap now aligns to each role's GuardToolset tool budget × 2 (≈2 requests per tool call): coder 75→150, planner 10→20, others 15→30. Removes the FALSE-BLOCK that killed tool-looping coders before they could emit `final_result` (the `coder_4` `UsageLimitExceeded` crash in `session_crash.md`).
  - **CHANGE 2:** Added early loop detection that the old guard missed:
    - **A-B-A-B alternation detector** (`alt_prev`/`alt_count`): two DISTINCT tool-call signatures ping-ponging (X→Y→X→Y) force RECOVER at `alt_count >= 2`, instead of burning the full request cap.
    - **No-op same-result detector** (`last_result_sig`/`result_repeat` + new `result_signature()` helper): when the SAME tool-return content keeps coming back, force RECOVER at the identical-sig threshold (`max_same`).
    - Both route into the existing RECOVER-not-EXIT block, reusing the `tools=[]` recovery agent. No new behavior, just more ways to trigger the already-correct recovery path.
  - **CHANGE 3:** `UsageLimitExceeded` (from `pydantic_ai.exceptions`) is now caught **specifically** in the `except` at the `agent.run()` site and routed through the SAME `tools=[]` recovery path (built on `current_history`) instead of re-raising as `[HALT]`. A coder that slips past Change 2 no longer aborts the whole EXECUTE phase — it yields a forced best-effort result; the SPAWN-ALL HALT only fires if that result is itself non-compliant.
  - Added regression test suite `admin/orchestrator/test/test_loopguard_recovery.py` (4 tests: T1 A-B-A-B → recovered before cap; T1b no-op same-result → recovered; T2 `UsageLimitExceeded` → recovered, NOT raised; T3 legit agent → returned normally). All 4 pass. No `src2/` edits, no `runner.py` HALT-logic change.

- **EXECUTE Phase Crash & Double-Nested Staging Paths fixes.**
  - Fixed double-nesting staging paths bug in `admin/orchestrator/infra/runner.py`'s `stage_path(real_repo_path)` by stripping any leading `admin/orchestrator/temp/` or `temp/` prefix.
  - Wrapped `coder_fn` invocations in `runner.py` with exception handling to convert uncaught runner subprocess or tool exceptions into clean, blocked `TaskResult`s, preventing EXECUTE phase crashes.
  - Refactored `GuardToolset` in `admin/orchestrator/infra/tools.py` to cache and track reads by `(path, line_range)` pairs instead of path-only, allowing re-reads of distinct line ranges on the same file while still debiting budget normally.

- **Planner Output Type and Recovery Path Hardening.**
  - Corrected planner's output type configuration back to `"DraftPlan"` in `admin/orchestrator/infra/control_orchestrator.py` to ensure structured outputs are requested from the model.
  - Hardened `admin/orchestrator/infra/runner.py`'s `UnexpectedModelBehavior` recovery path to refuse framework error prose for structured output roles (non-`"str"`), raising a clean `[HALT] role '<role>' emitted no final_result call` RuntimeError instead.
  - Added unit test `test_structured_output_recovery_hardening` in `admin/orchestrator/tests/test_validation_hardening.py` to prevent regressions.

- **Staged Read Redirection & Red-Team Gate Classification Fixes.**
  - Modified `admin/orchestrator/infra/tools.py` (`GuardToolset.call_tool`) to normalize file paths using `normalize_read_path(path)` only for tracking, budget, and re-read checks. Left the path arguments inside `tool_args` passed to the underlying CLI wrappers (like `read_file.py`) unchanged. This ensures that the auditor roles evaluate the staged code under `temp/` instead of live code.
  - Refactored `run_red_team_gate` in `admin/orchestrator/infra/runner.py` to map rejected `item_id`s that are User Stories or Rubric cells back to their associated tasks using their `coder_idents` lists, preventing immediate crash on story/rubric rejections.
  - Added unit tests in `admin/orchestrator/tests/test_gates.py` to verify mapping of story and rubric cell failures back to coder tasks.
  - Implemented the Pre-Review Staging Diff Gate in `runner.py` using `filecmp` to prevent zero-diff hallucinations by blocking review if a staged file is identical to its live reference.
  - Implemented the Pre-Review Runtime Load Gate in `runner.py` via `load_schema_gate.py` to dynamically load staged Python files and execute `model_json_schema()` on `BaseModel` models to capture schema failures.
  - Hardened Budget Fatal / Recovery overrides in `runner.py` (`load_skill`) to intercept loopguard-recovered runs and toolset exhaustion, strictly overriding their status to `"blocked"` instead of `"completed"` or `"done"`.
  - Implemented IDE-style self-correction in `tools.py` (`_check_edit_result`) to intercept errors or unchanged edit results from `replace_text`, `replace_function`, `add_constant`, `add_import`, and `delete_file` CLIs and raise `ModelRetry` exceptions, forcing the agent to retry with descriptive tracebacks.
  - Added unit test suite under `admin/orchestrator/tests/test_harness_gates.py` and `admin/orchestrator/test/tools/test_tool_exceptions.py` to verify the gates and exceptions.

### Added
- **Conductor-led Pre-staging for Orchestrator Plan Phase.**
  - Modified the Conductor (`admin/orchestrator/infra/runner.py`) to stage the workspace right after a `DraftPlan` is parsed, but before the `supervisor_plan` or `coder` phases begin.
  - Implemented `stage_workspace_from_draft(draft, bd)` to identify target files, copy existing source files (`src2/...`) to their mirror path in `temp/src2/...`, and touch/initialize empty 0-byte mock files for expected new deliverables (`temp/...` or `.diff`/`.md` files).
  - Added unit test in `admin/orchestrator/tests/test_prestage.py`.

### Fixed
- **Concurrent Coder Model Monkeypatching Collision.**
  - Modified `admin/orchestrator/infra/runner.py` to clone the resolved model object using `copy.copy(model)` when constructing a coder agent in `build_role_agent()`. This isolates model instances per coder, preventing concurrent `loopguard` request overrides from leaking across agents.
  - Added unit and concurrency integration tests in `admin/orchestrator/tests/test_loopguard.py` to verify request isolation on shared model instances and correct cleanup.

- **String Output AttributeError in runner.py.**
  - Made `admin/orchestrator/infra/runner.py` resilient to raw string outputs from agents by checking if output objects implement `model_dump_json()` before trying to serialize them, falling back to string conversion otherwise.
  - Added unit test file `admin/orchestrator/tests/test_string_output.py` to prevent regressions.

- **Planner JSONL Compilation & Healer Mode Recovery.**
  - Implemented `jsonl_compiler.py` under `admin/orchestrator/infra/` for robust line-by-line JSONL parsing and auto-healing of `EvidenceItem` lists.
  - Configured planner output type to `"str"` in `control_orchestrator.py` to allow the LLM to output raw JSONL streams.
  - Integrated `is_jsonl` check and JSONL compilation inside `clean_role_output` (`output_sanitizer.py`).
  - Added synchronous `healer_mode` recovery fallback in `clean_role_output` to repair validation failures offline using `output_type=model` and prevent `[HALT]` crashes.
  - Implemented self-improving normalizer loop telemetry to recursive-scan and suggest key alias mappings to `FROZEN_KEY_ALIASES`.
  - Added targeted test coverage in `admin/orchestrator/tests/test_jsonl_healer.py`.

- **Plan-Gate Resiliency & Alignment Fixes.**
  - Propagated the `is_forced_pass` state from `run_gated` to `_assert_plan_gate_ok` to allow overriding of rejected evaluations when the planning phase hits attempt 3 (FORCED PASS).
  - Modified `run_code_review_gate` and `run_red_team_gate` to gracefully override rejected evaluations and proceed on forced pass (attempt == MAX_RETRIES).
  - Hardened `supervisor_plan.yaml` to explicitly prohibit structural plan corruption (no merging/collapsing of subtasks) and to instruct the agent to evaluate strategies and scope without verifying non-existent code deliverables during the planning phase.
  - Added test cases in `admin/orchestrator/tests/test_gates.py` to assert the forced-pass behavior and evaluation overrides in code review and red-team gates.



## [Unreleased] - 2026-07-19

### Added
- **Implemented Read-Memory Bridge (ticket `2711x`).**
  - Modified `GuardToolset.call_tool` to append a strict `[SYSTEM NOTE: If you found relevant facts or code patterns in this read, you must call remember/remember_fact to register them now.]` suffix to successful `batch_read` and `read_file` tool returns.
  - Hardened all five role templates (`coder.yaml`, `planner.yaml`, `red_team.yaml`, `supervisor_plan.yaml`, `supervisor_review.yaml`) by adding prompt-level `READ-MEMORY BRIDGE` instructions under the coding philosophies block.
  - Added regression unit tests to `tests/test_read_memory_bridge.py`.

### Fixed
- **Implemented Per-Task Validation Envelope for Orchestrator Gates.**
  - Transitioned `supervisor_plan`, `supervisor_review`, and `red_team` phases to the flat `evaluations` list-based validation shape.
  - Implemented case-insensitive status coercion validator `_coerce_approved` in `models.py` to map any string starting with `yes`/`approve` to `"Yes"` and `no`/`block` to `"No"`, and handle boolean inputs.
  - Refactored `passed()` in `runner.py` to evaluate gating verdicts by inspecting the flat `evaluations` array for `supervisor_plan`, `supervisor_review`, and `red_team`.
  - Updated `run_code_review_gate` to use `ReviewResult` and route feedback to coders via evaluations comments.
  - Updated `run_red_team_gate` to clean output using `AuditResult`, check task-specific and global rejections, and raise `RuntimeError` on global failures.
  - Implemented programmatic runner merge in `_assert_plan_gate_ok` to merge evaluations back into the `DraftPlan` JSON, writing `"Approved"` and `"Comments"` directly to `planner.json` and in RAW_OUTPUTS.
  - Updated `converter.py` to format lists of evaluations as clean markdown tables.
- **Resolving Orchestrator Planner Validation Failures (Option B: Schema Simplification via Evidence Lists).**
  - Refactored Pydantic schemas in `admin/orchestrator/infra/models.py`:
    - Converted `SubTaskBrief.evidence` from dynamic dictionary `dict[str, str]` to structured static list `list[EvidenceItem]`.
    - Converted `Strategy.tool_preference` from dynamic dictionary `dict[str, str]` to structured static list `list[ToolPreferenceItem]`.
    - Added `@property` `tool_preference_dict` to `Strategy` for backwards compatibility.
    - Added before-validators `_coerce_evidence` and `_coerce_tool_preference` for backward compatibility with dictionary inputs in existing code and tests.
    - Added robust validators `_require_evidence` and `_validate_tool_preference_tasks` to ensure task list integrity and proper evidence proofing.
  - Updated prompt templates (`planner.yaml`, `supervisor_plan.yaml`) to match the new list-based structures.
  - Updated helper utility `build_worker_spec` in `tools.py` to use `strategy.tool_preference_dict`.
  - Hardened unit tests in `test_validation_hardening.py` to cover new validation and structure changes.


### Added
- **Subagent schema validation hardening (Template Hardening & Retry Enrichment).**
  - Added a recursive `generate_simplified_schema(model)` utility in `output_sanitizer.py` to generate clean, simplified text representation of Pydantic model schemas.
  - Hardened subagent templates (`planner.yaml`, `supervisor_plan.yaml`, `supervisor_review.yaml`, `red_team.yaml`, `coder.yaml`) by adding static JSON outlines of the expected Pydantic model schemas.
  - Dynamically enriched validation retry feedback: intercepted validation errors inside loopguard request interceptor (`_loopguard.py`) and appended the simplified Pydantic schema structure to help subagents correct validation failures in real-time.
  - Added regression unit tests in `admin/orchestrator/tests/test_validation_hardening.py`.

### Fixed
- **Planner read-budget starvation and redundant reads (ticket `ogow8`).** Fixed a bug where absolute staging paths and relative live paths were tracked as different files in read tracking, leading to budget starvation.
  - Implemented `normalize_read_path` helper to normalize all incoming paths in `tools.py` before adding to or checking in `self._read_paths`.
  - Reordered the identical-call deduplication check in `GuardToolset.call_tool` to run *before* the read budget checks (excluding `batch_read` and `read_file` to keep read-budget limits functional) to prevent cached tool hits from consuming budget.
  - Added new regression tests to `tests/test_guard_read_idempotency.py` to assert path normalization and cache-check-order behavior.
- **File-disjointness HALT false-positive on Planner-claimed derived/staging
  paths (ticket `vw4dd`).** Root cause (session-ses_087c.md,
  observed in `hbh1` ~2026-07-19): the cross-group / intra-group
  file-disjointness assertion (added by closed `zu9u`,
  runner.py:1268-1316) ran over the Planner's raw `file_paths` CLAIMS. The
  Planner is reasoning-only and routinely emits non-source paths (e.g.
  `admin/orchestrator/temp/src2/.../unified_patch.py`), which the runner trusted
  and raised `RuntimeError('[DAG] ... is NOT file-disjoint')`, killing the whole
  run — a false positive.
  - New helper `_real_source_paths()` filters each task's `file_paths` to REAL
    repo-relative `src2/` files that actually exist on disk. Staging mirrors,
    derived names, and hallucinations are dropped before the assertion. A
    non-existent path cannot race, and a staging/hallucinated path is never a
    real edit target.
  - Both the intra-group (runner.py:1294) and cross-group (runner.py:1312)
    assertions now run over the filtered set. A task with NO real source files
    (empty filtered set) is skipped in the intra-group check so two such tasks
    don't collide on the empty tuple. Genuine overlap of TWO REAL existing
    `src2/` source files across concurrent groups STILL HALTS (true positive
    preserved).
  - `asyncio.run(main())` entrypoint wrapped in try/except that writes the
    traceback to `RUNTIME_DIR/fail_main.log` + appends to `RUNTIME_DIR/run.log`
    before re-raising (forensic:secondary gap), so future HALTs land on disk.
  - Tests: `admin/orchestrator/tests/test_file_disjoint_filter.py` added
    (3 tests — filter correctness, false-positive no-crash, true-positive HALT;
    all passing).

### Added
- **Forgiving `batch_read` ergonomics (ticket `rj4ie`).**
  Root cause (session-ses_088e.md + forensic-planner-md-2026-07-17-defects): the
  model burned its entire `read_budget` (5 calls) on malformed `batch_read`
  invocations ("no paths provided", "line_ranges REQUIRED") because the tool
  contract was unforgiving and the role templates gave zero illustration of the
  call shape — forcing a blind `final_result` → `[HALT]` on runs without
  pre-injected context. Two halves:
  - **Tool (`admin/orchestrator/infra/tools.py`):** empty/missing `paths` →
    helpful reject that does NOT consume the productive `read_budget` (ticks a
    new separate `READ_FORGIVE_BUDGET=3` counter in `GuardToolset`; exceeding it
    forces `_READ_FATAL`). Missing `line_ranges` → the fetch SUCCEEDS with a
    bounded 250-line head (`_BATCH_READ_DEFAULT_HEAD`) + a steer note, instead
    of a hard error. A malformed (comma-joined) range is still rejected.
  - **Prompts (5 templates `_BASE_`):** a `batch_read` illustration block
    (1-line desc + 2 examples + 2 negatives) added to
    `planner` / `supervisor_plan` / `supervisor_review` / `red_team` / `coder`
    so the model learns the call shape at the point of use.
  - Tests: `admin/orchestrator/tests/test_batch_read_ergonomics.py` added
    (8 tests, all passing); no regression to `test_guard_read_idempotency.py`.

### Added
- **Scope-driven auto-context for planner + supervisor_plan (tickets `86rmw` / `xfqkf`
  / `y1oqi` / `nwem8`).**
  - `user_prompt.md` is now a YAML front-matter block (`---` delimited) carrying
    `Resume:` / `bd:` / `scope:` (list of files/folders). `read_prompt()` (runner.py)
    parses it into `(resume, task_spec, scope)` and fails loudly on malformed/missing
    front-matter (replaces the legacy strict first-line `Resume:` check).
  - `main()` builds the scoped repo-map ONCE via `inject_repo_map(scope)` and caches it
    in the `SCOPE_CONTEXT` module global (sibling of `PHASE_SUMMARIES`).
  - `inject_repo_map()` (ledger.py) now expands folders, lists per-file symbols
    (`get_file_symbols`), and adds a deterministic knowledge-graph lookup
    (`query_knowledge_graph`) keyed off each file's path + top-level symbols. Empty
    scope falls back to a shallow depth-2 whole-repo tree + a "no scope declared" note.
  - `load_skill` injects `SCOPE_CONTEXT` (as `codebase_reference_context`) into BOTH
    `planner` AND `supervisor_plan` briefs — identical context for both. The old
    hand-written hardcoded `DictMap` block (planner-only, task-specific) is deleted.
  - `prompt/user_prompt_template.md` authoring guide added (schema + filled example).
  - `scope` is a context HINT only — never wired to the coder `file_paths` ACL.
  - Tests: `tests/test_scope_auto_context.py` added (12 tests, all passing).

### Changed
- The `run_orchestrator.sh` `bd:` grep still resolves `bd` from inside the front-matter
  block (it remains a `^bd:` line), so auto-ticket selection is unaffected.
- **Coder tool-budget hardening (ticket `0xvqo`).** Root cause of
  `session_crash.md`: coder_1/coder_3 (3 files each) exhausted the flat 15-call budget
  by re-reading their staging files 6× (redundant `batch_read`) then probing blind.
  Two fixes in `admin/orchestrator/infra/tools.py`:
  - **Dynamic coder budget** — `_coder_budget_for(num_files) = clamp(12 + 4*num_files,
    16, 30)`. Scales with the task's file count (3 files → 24 calls, was 15) so
    multi-file refactors aren't starved, but clamped so a lazy coder cannot sprawl.
    Wired into the coder agent builder (`len(task.file_paths)`).
  - **Per-file read idempotency** — `GuardToolset.call_tool` HARD-rejects a re-read of
    any path already fetched this run (`_READ_REDUNDANT`): it does NOT re-execute the
    read and does NOT consume the read bucket, but still ticks the global tool budget
    (via the `[TOOL CALL a/X]` marker) so a chatty model cannot loop on re-reads
    forever. New paths are recorded and counted against `READ_BUDGET`. Partial
    re-reads (mix of new + already-read paths) execute only the new paths.
  - `READ_BUDGET=5` (batch_read) / `CODER_READ_FILE_BUDGET=10` (read_file) unchanged —
    they still cap DISTINCT reads; redundancy is now enforced HARD (was advisory only).
  - Tests: `tests/test_guard_read_idempotency.py` added (7 tests — idempotency, partial
    re-read, global-budget tick on re-read, read-budget exhaustion, dynamic formula).

## [Unreleased] - 2026-07-18

### Added
- **Size-aware context injection for coder agents (epic `gx30p`, tickets
  `l30qe` / `k2owt` / `qkm3p` / `fzqa2` / `vze01`).**
  - `runner.py`: new `estimate_task_tokens(file_paths)` (deterministic tiktoken
    `cl100k_base` sum, cached encoding, char/4 fallback) + `task_context_tier(...)` →
    `"A"` / `"B"`. Module constants `TASK_TOKEN_THRESHOLD = 100_000` and
    `TIER_B_SLICE_THRESHOLD = 100_000`.
  - **Per-task hard gate** inside `run_execute_phase → execute_task`: before any coder
    spawns, the task's `file_paths` token total is computed. Over-budget tasks fall to
    **Tier B**; a single file exceeding the slice budget raises `TaskNeedsSplitError` (a
    `RuntimeError` that propagates out of `run_execute_phase`, forcing a planner re-plan
    with narrower `file_paths` — vze01 split-escalation, last resort).
  - **Tier B auto-shrink (qkm3p)**: over-budget tasks receive a structural map
    (`_build_tier_b_map` via `get_file_symbols`) injected into the coder brief instead
    of the full files, so the agent edits precise slices without the whole file in
    context. Deterministic, no planner involvement.
  - **Temp-copy staging (fzqa2)**: `_stage_copies` mirrors each live `file_paths` into
    `temp/<task>/` as an eviction-exempt baseline; the coder reads real content there
    (the live-tree read would be evicted to `File read: <path>` for large files) while
    the live tree stays read-only / PROPOSE-ONLY.
  - Tests: `tests/test_context_injection.py` added (token calc, tier selection, staging
    copies, Tier-B map injection, and the `TaskNeedsSplitError` halt). ruff clean.

- **Stop/Continue mechanism WIRED (ticket `udylx`).**
  - `runner.py`: new `--stop-after <phase>` (choices = `_PHASE_ORDER`) and `--resume` argparse flags.
    A nested `_checkpoint(phase)` helper now calls `save_state`/`record_phase` (state.py) after every
    phase block; when `--stop-after <phase>` matches it persists state + exchange and `return`s
    (propose-only, no push). Fresh runs use `fresh_state(bd)`; continuation runs use
    `load_state(bd)` and rehydrate `draft/approved/batch/code_passed/audit` into `history`,
    `phase_summaries` (L3 chain) and `RAW_OUTPUTS`.
  - **Hard-refuse on missing state**: a bare `--resume` (or any continuation flag) with NO prior
    `state.json` raises `RuntimeError("[HALT] no prior state for <bd> ...")` — never silently starts
    a fresh run over a continuation intent.
  - `run_orchestrator_continue.sh`: `CONTINUE_FLAG` replaced by `STOP_FLAG` (editable). Empty =
    forward `--resume`; non-empty = forwarded verbatim (`--stop-after <phase>` | `--from <phase>`).
  - `run_orchestrator.sh`: destructive wipe now suppressed for `--stop-after`/`--resume` too (not just `--from`).
  - `models.py`: `OrchestratorState.current_phase` default changed `"PLAN"` → `"planner"` (a
    `_PHASE_ORDER` role key) to unify the label mismatch.
  - Tests: `tests/test_stop_continue.py` added; `tests/test_state.py` updated to role keys.
    Full suite: 55 passed, 1 skipped. ruff clean.

- **Spawn-all coders + halt-on-block in EXECUTE phase (ticket `uqj06`).**
  - `run_execute_phase` (`runner.py`, `process_group`): REMOVED the upfront skip-short-circuit
    that axed an entire dependent DAG group when a prerequisite group produced 0 usable (blocked)
    tasks. Every group now ALWAYS spawns and executes regardless of sibling/group outcome.
    The `await group_events[d].wait()` dependency gating is preserved (a group still starts only
    after its prerequisites complete).
  - Added a post-gather halt scan: after ALL groups finish, if ANY task is `blocked`/`failed`
    or produced no result, the run is hard-halted with
    `RuntimeError("[HALT] EXECUTE phase incomplete: <ids>")` listing every incomplete task id.
    This guarantees incomplete work never reaches supervisor_review / red_team / ops; staged
    files under `admin/orchestrator/temp/` remain for manual recovery.
  - Root cause (run `hbh1`): planner put `task_1` alone in `group-1` and tasks 2-6
    in `group-2 depends_on group-1`; `task_1` returned `blocked` (a false read-budget/"truncation"
    excuse — the coder had the full file) which cascaded to silently skip the entire `group-2`,
    so 5 unrelated coders never spawned.
  - Tests: `tests/test_spawn_all_halt.py` added (3 cases: spawn-all on single block, halt lists
    all incomplete ids, no-halt when all done). ruff clean.

### Changed
- **Red-team gate Site C now FORCED-PASS on final attempt (ticket `7w11i`).**
  - `run_red_team_gate` (`runner.py:1589-1591`): when `attempt == MAX_RETRIES` and the gate is still
    failing, it now prints `FORCED PASS -> proceed to ops` and `return batch` instead of raising
    `RuntimeError` and aborting the whole run. Mirrors the existing supervisor attempt-3 force-pass.
    Rationale: 95% review-noise coverage ceiling — a stubborn-but-minor finding must not discard a
    near-complete pipeline. Sites A (Critical/High risk with no resolvable `task_id`, untargetable)
    and B (findings referencing unknown task ids not in plan, phantom) stay HARD FAIL and still abort.
  - `templates/red_team.yaml` + `customised/red_team.yaml` reworded to keep the `hard fail` marker in
    the "unless final attempt, which force-passes to propose-only OPS" clause (contract test unaffected).
  - `tests/test_red_team_contract.py` gained `test_runner_forced_pass_on_final_attempt` locking the
    new behavior. Full suite: 52 passed, 1 skipped.
  - OPS remains propose-only (`pushed=False`), so the blast radius is an unpushed commit + bd close.
  - `wip-harness` skill + `ops-propose-only-green-rederived` bead updated; note added to `fvv2` (C2).
- **MD-twin per-turn re-injection wired (ticket `mb1k5`).**
  - NEW `admin/orchestrator/common/md_bridge.py`: `build_md_bridge(role, agent_id=None) -> list[ModelMessage] | None`.
    Resolves the EXACT `.md` twin via `artefacts._history_filename(role, agent_id)` (+`.md`) — NO mtime-glob
    (the old `read_latest_md` glob was the coder-tagging bug). Cold spawn (no twin) → `None` (no HALT). Wraps
    the MD text as a single `ModelRequest(UserPromptPart(content="<!-- MD_LEDGER -->…"))` for injection.
  - `runner.load_skill` (`runner.py:615`): replaced `_load_role_messages(role, agent_id)` (raw `.jsonl` replay)
    with `build_md_bridge(role, agent_id=agent_id)`. The `.md` twin is now the per-turn re-injection source fed
    as `message_history` to ALL agents EVERY spawn (token-saving ~67% lighter than jsonl + visibility assurance:
    on-screen `.md` == what the agent got). JSONL stays internal-only accumulation (pydantic-ai owns it).
  - Per-coderN isolation (ticket `a101k`) preserved BY CONSTRUCTION: `build_md_bridge` reuses
    `_history_filename` which already returns `coderN.jsonl` for coder+agent_id → the `.md` sibling is `coderN.md`.
  - The planner→supervisor_plan raw-JSON phase-output handoff (`RAW_OUTPUTS["supervisor_plan"]`) is unchanged
    (separate channel, still requires raw JSON in history).
  - Tests: `tests/test_md_bridge.py` added (4 cases: cold-spawn None, role twin inject, coder agent isolation,
    unknown role None). ruff clean.
  - `wip-harness` skill references (`02_architecture.md`, `05_context_mgmt.md`, `03_state.md`,
    `06_resume_checklist.md`) corrected to describe the MD-bridge design (removed the stale "`.md` was a red
    herring / jsonl replay" claim).
- **Skills made lazy-load (context-bloat fix, ticket `1wzum`).**
  - `.agents/skills/wip-harness/SKILL.md` — rewritten from a 555-line monolith into a thin
    LAZY-LOAD INDEX: metadata + the load-bearing §0.0 answer-workflow contract + sandbox rule +
    a contents table pointing at `references/*.md`. Deep sections (architecture, DONE/OPEN/
    DEFERRED state, decisions, forensics, context-mgmt, resume checklist) moved to
    `references/00_answer_workflow.md` … `06_resume_checklist.md`. Added
    `references/07_corrections.md` documenting verified overrides of stale claims (fallbacks
    GONE, `factory.py`/`observability.py`/`orchestrator.py` DELETED, `run_orchestrator_continue.sh`
    EXISTS, `--from` full ladder, OPS real push, C2/H8 invariants enforced, `ROLE_MAX_ATTEMPTS`
    not in `control_orchestrator.py`) so an LLM reading any reference isn't confused by old
    falsehoods.
  - `.agents/skills_archive/pydantic-ai-coding/SKILL.md` — trimmed to a thin index: inline
    specific rules (Pydantic V2 only, `OpenAIChatModel`+`OpenAIProvider`,
    agent conventions) + a lazy-load table pointing at the existing `references/*.md`. No
    generic pattern content retained inline.

Prompt-review fixes — blind rerun + adversarial supervisors + frozen contract
(tickets `nw9ov` [R1], `g1lvv` [R2+R4],
`6gizg` [R5], from review `g17uq`):

- **R1 — coder rerun is no longer blind.** Added a `feedback` parameter to
  `run_execute_phase` (runner.py). The supervisor_review gate builds a
  task_id -> findings map via `_feedback_from_review_findings(review)` and the
  red_team gate via `_feedback_from_audit(augmented_findings, audit)`; both pass
  it into the rerun. `execute_task` now augments the coder brief with a
  `=== PRIOR FEEDBACK ===` block carrying the exact prior blocker findings +
  `traceback_route` (review) or `findings`/`risks` (red_team) keyed by task_id.
  The rerun coder (per-agent isolated `coderN.jsonl`, effectively fresh) is told
  exactly what changed. Falls back to a generic "reopened, re-read your memory"
  note when a rerun task has no captured findings.
- **R5 — frozen EXPECTED CODER BEHAVIOUR appendix.** `execute_task` now appends a
  structured, frozen behaviour contract (derived from the task's acceptance/DoD)
  to the coder brief, independent of the planner's raw prose — anchors coder
  behaviour to a contract regardless of planner wording.
- **R2 — adversarial supervisors.** `templates/supervisor_plan.yaml` now says
  "assume the plan is wrong until proven", mandates a `rejected_subtasks` entry
  when the plan is large, and replaces "Never invent findings" with "only report
  findings you can cite file:line for". `templates/supervisor_review.yaml`
  similarly hardened (challenge the coder's claims, don't rubber-stamp). R3
  (remove FORCED PASS on attempt 3) was explicitly REJECTED by the user — two
  review passes cover ~95%; the FORCED PASS at runner.py:1279 stays.
- **R4 — frozen token/tool/context contract block.** Every `templates/*.yaml`
  `_BASE_` now carries the facts previously enforced only in code and invisible to
  the model: `request_limit=40`, `AGENT_RUN_TIMEOUT=600s`, compaction at 60% of
  the window, write-root `admin/orchestrator/temp/`, "show diff not full file",
  and the role's tool allow-list. ruff clean; all templates valid YAML.

Per-`coderN` isolated memory (ticket `a101k`, LOCKED design from
grill-me 2026-07-18 `orchestrator-coder-per-agent-memory-locked`): replaces the
shared `history/coder/coder.jsonl` store that ALL parallel coder subagents read
and wrote, which caused context bloat, redundancy (parallel coders == 1 coder ×
N), and write races under `asyncio.gather`. Each coder agent now gets its OWN
`history/coder/coderN.jsonl` where `N` derives from the planner's
`ApprovedTask.id` (e.g. `task_3` -> `coder3`), resume-safe and stable across
ruff re-spawns of the same task. The `context-prepend-compaction-gate` is
re-pointed at the per-`coderN` file (200K -> `keep_memory` -> rotate to
`coderN.compactM.jsonl` + reseed); `keep_memory` stays PRIVATE to `coderN`
(never promoted to `global_alignment`). `remember`/`keep_memory` route via a new
`_current_agent` contextvar. Implemented in `infra/artefacts.py`
(`_history_filename`, `load_role_messages`/`remember_note`/`rotate_role_transcript`/
`persist_role`/`persist_messages` gain an `agent_id` overload), `infra/tools.py`
(`set_current_agent`/`get_current_agent`), `infra/runner.py` (`_coder_agent_id`,
`load_skill`/`record_coder`/`execute_task` thread `task_id`), and `infra/_loopguard.py`
(`compact_memory_gate` forwards `agent_id`). The shared `coder.jsonl` is now
retired; the never-prune rule is rescoped to `coderN` + `coderN.compactM`
snapshots. Tests green (`_coder_factory` double accepts the new `task_id` arg).

coder.md pollution cleanup + test-leak isolation (ticket `hb8b`):
stopped the loopguard compaction tests from writing synthetic junk into the
live `artefacts/history/coder/coder.jsonl` + `coder.md` (which then leaked as
the coder's D2 continuity bridge on real runs). `infra/artefacts.py`
`ARTEFACTS_DIR` is now resolved lazily via `artefacts_dir()` and overridable by
the `ORCHESTRATOR_ARTEFACTS_DIR` env var; `tests/test_loopguard.py` sets it to
`tmp_path` so role-history writes never touch the sandbox. Polluted fixtures
removed. Tests green, live sink stays clean.

Phase-ladder `--from` resume expansion (design locked via grill-me, session
`ses_08cf`): `--from` now accepts the full cumulative ladder
`planner | supervisor_plan | coder | supervisor_review | red_team` (was only
`coder`). Each value starts that phase and runs everything downstream, skipping
only earlier phases. `_SKIPPED_PHASES` already generalized via
`_PHASE_ORDER.index`. `run_orchestrator.sh` suppresses the destructive wipe for
ANY `--from <phase>` (not just `coder`), preserving predecessor artefacts;
`run_orchestrator_continue.sh` documents all 5 resume points. Added a
fail-loudly HALT when resuming at/after `coder` with no persisted `ApprovedPlan`.

keep_memory context-prepend compaction gate (ticket `wkxy`,
LOCKED design from grill-me 2026-07-18 `context-prepend-compaction-gate`):
bounds each role's prepended `prior_history` (the `.jsonl` message stream, NOT
the `.md` twin) to 60K–200K so the working LLM never ingests 700K+.

### Added
- **`infra/_loopguard.py` `compact_memory_gate(prior_history, agent_model, state, phase, role=None)`**
  — Function B: when `prior_history` exceeds `CONTEXT_COMPACT_CEILING` (200K) it
  runs up to `EMPTY_EXT_RETRIES` (3) passes with an agent whose ONLY tool is
  `keep_memory` (the SAME working LLM, no separate compaction agent). Each pass
  sends `prior_history` + "compact your memory now, call keep_memory"; the LLM
  dumps its essentials once via `keep_memory`; if the dump is `< CONTEXT_COMPACT_FLOOR`
  (60K) it becomes `[SystemPromptPart(keep_memory)] + safe recent tail`. Else it
  re-loops with "compact further". After 3 failed passes it falls back to the
  `summarizer_model` (reusing `maybe_compact`). Fails loudly (`RuntimeError`)
  on empty externalization or a floor-violating fallback.
- **`infra/artefacts.py` `rotate_role_transcript(role, compacted_messages)`** — write-back
  rotation: renames the old `<role>.jsonl` → `<role>.compact<N>.jsonl` (snapshot,
  N increments, never deleted) and writes the fresh aggregated `.jsonl` =
  `[SystemPromptPart(keep_memory)] + recent tail`, re-rendering the `.md` twin.
- **`infra/tools.py` `keep_memory(note)`** — named alias of `remember` reusing the
  exact same `artefacts.remember_note` single-writer path (a role writes only its
  own history). This is the compaction agent's sole tool.
- **`infra/prompt/compact_memory.yaml`** — the "compact now / compact further"
  instruction set (inline fallbacks in `_loopguard.py` if missing).
- **`control_orchestrator.py` `COMPACTION_CONFIG`** — `CONTEXT_COMPACT_CEILING=200_000`,
  `CONTEXT_COMPACT_FLOOR=60_000`, `EMPTY_EXT_RETRIES=3`.

### Changed
- **`infra/runner.py` `load_skill`** — Function A gate: after
  `prior_history = _load_role_messages(role)`, measure `estimate_tokens(prior_history)`;
  if `> CONTEXT_COMPACT_CEILING` call `compact_memory_gate` (same working LLM via
  `agent.model`) and feed the compacted history as `message_history`. Reverses the
  locked `coder-history-injection-intent` stance (capping coder history is now the
  design). Gate failure is a HARD HALT — it must NOT silently prepend the unbounded
  700K history (Fail-Loudly, per ticket `wkxy`).

### Fixed
- The 700K+ prepended-history bloat: `coder.md` had reached 359KB and the true
  bloat source (the `.jsonl`→`prior_history` message replay) was uncapped. The gate
  now bounds it before prepend.

- **Framework-rejected tool-call no longer silently drops a task (ticket
  `78j9m`).** When pydantic-ai's own tool-dispatch validator rejects
  a structurally-invalid `final_result` call (e.g. `MALFORMED_FUNCTION_CALL`: the
  model emitted a `list` where an `object` was required), the framework discards the
  offending args and persists no valid `ToolCallPart`. Previously `extract_model_json`
  returned `None`, the harness fell back to the framework's error *string*, and the
  role was `[WARN]`-dropped from the batch. Now `output_sanitizer.extract_tool_call_payload(exc)`
  reclaims the attempted payload from the exception (`body`/`message`/`str(exc)`) and
  `runner.py` routes it through the **same** `clean_role_output` pipeline at **all three**
  recovery seams (`load_skill`, `do_role`, `record_coder`). The malformed-call path and
  the malformed-JSON path now share ONE fail-loud `[HALT]` exit — no leniency, no silent drop.
  Tests: `tests/test_sanitizer_malformed_call.py` added (reclaim from body/message,
  recoverable validates, unrecoverable HALTs, absent → `None`). ruff clean.

Anti-duplication refactor: created `admin/orchestrator/common/` as the single
source of truth for shared harness utilities, and added a duplicate-function
gate to `TEST/agent_guardrail.py`.

### Added
- **`admin/orchestrator/common/`** — SSoT package for shared harness utils:
  - `common/operator.py` — `log_operator` (moved from `infra/tools.py:65`).
  - `common/subprocess.py` — `_run_tool` (moved from `infra/tools.py:549`,
    Fail-Loudly: raises `RuntimeError` on timeout).
- **`TEST/agent_guardrail.py` `detect_duplicate_functions`** — new `validate()`
  stage. Fails when an edit *introduces* a module-level function that already
  exists elsewhere in `infra/` + `common/` (the LLM-recreates-a-util pattern),
  and on within-file module-level redefinitions. Pre-existing duplicates are not
  flagged (checkpoint-baseline) so legacy code is never blocked. Methods /
  nested closures are ignored to avoid false positives on names like `get`.

### Changed
- **`infra/tools.py`** — `log_operator` and `_run_tool` now imported from
  `common`; dropped unused `subprocess` import and `TOOL_SUBPROCESS_TIMEOUT`.
- **`infra/runner.py`** — `log_operator` imported from `common`.
- **`infra/ledger.py`** — `_run_tool` imported from `common`; its two call
  sites wrap `RuntimeError` to preserve ledger's string-return contract.

### Fixed
- **`ydiv` (P0): wire `output_sanitizer` to the model's REAL output,
  not the exception string.** The `model → json → fast-json-repair → normaliser →
  validator` pipeline (`output_sanitizer.clean_role_output`) existed but was
  bypassed: on `UnexpectedModelBehavior`, `load_skill` fed `e.message` (the literal
  `"Exceeded maximum output retries (5)"` error string) to the sanitizer, which
  always rejected it → `[HALT]`. Now `load_skill` (and `do_role`/`record_coder`)
  reloads the role's persisted message history (`_load_role_messages`) and extracts
  the model's last `final_result` `ToolCallPart` args via the new
  `extract_model_json(messages)` helper, feeding THAT to `clean_role_output`. `e.message`
  is now only a fallback when no `final_result` tool-call exists. A role emitting
  malformed `final_result` 5× is salvaged by the sanitizer or fails with the REAL
  validation error, never the framework string.
- **`ydiv` (FIX B): bound `recall_fact`.** It was unbounded — the coder
  spammed 11× in run `hbh1`, bloating context and degrading structured-output accuracy
  (the upstream cause of the `final_result` 5× validation failure). `GuardToolset` now
  enforces `recall_budget` (default `RECALL_BUDGET=5`, mirroring `batch_read`), returning
  the read-FATAL nudge on exhaustion to force `final_result`.
- **`bs1d` (P0): coder confined to `admin/orchestrator/temp/` only.** The
  coder may now WRITE **only** under `temp/` (subfolders allowed) and must not create/modify/
  delete/move/overwrite anything outside it — including `src2/`. Prompt prose alone was not
  enforced; the real write confinement is `wrap_with_acl(task.file_paths)`. Added
  `CODER_WRITE_ROOTS = ["admin/orchestrator/temp/"]` and the coder's MODIFY_TOOLS are now
  ACL-wrapped to it, OVERRIDING the planner's `task.file_paths` so a broad/malicious planner
  entry cannot broaden the coder's reach. Reads remain `deny_only` (repo-boundary + secret
  deny-list) so the coder can still READ `src2/` to analyse and emit patch files under `temp/`
  for human review. `user_prompt.md` CONSTRAINTS + ANTI-PATTERNS rewritten to state this as the
  single clear rule.
- **`infra/runner.py` immediate crash (regression from this refactor)** —
  `load_skill` / `build_role_agent` indexed `common.OUTPUT_TYPE_REGISTRY` by
  *role name* (`supervisor_plan`, `coder`, …) but that registry is keyed by
  *output-type name* (`ApprovedPlan`, `TaskResult`, …). Every role therefore
  hit `if role not in OUTPUT_TYPE_REGISTRY` and returned
  `"[HALT] unknown role '…'"`, so `run_orchestrator.sh` died at the plan-gate
  before any model call. Added `common.ROLE_OUTPUT_TYPE` (role → output-type
  name, derived from `SKILL_MAP`) and pointed the 3 sites
  (`build_role_agent` output_type, `load_skill` role guard, `load_skill`
  model_cls) at `OUTPUT_TYPE_REGISTRY[ROLE_OUTPUT_TYPE[role]]`. Run now
  proceeds past the plan-gate into the planner phase. (ticket: orchestrator
  role→output-type registry regression)

### Removed
- **`infra/observability.py`** — deleted entirely. It was unimported repo-wide
  (no references to `LogEvent` / `configure_logfire` / structlog sink anywhere);
  the only live symbols it duplicated (`log_operator`, `update_status_board`)
  already have canonical homes in `common/` and `runner.py`.
- **`infra/factory.py`** — deleted entirely. It was 100% unreferenced dead
  code: a divergent `RoleSpec` YAML pipeline (`infrastructure/prompt/<role>.yaml`,
  a dir that does not exist), its own `_OUTPUT_TYPE_LOOKUP`, and a `build_role_agent`
  that nothing imported. The live forge path is `runner.build_role_agent` →
  `tools.build_skill_spec` (shared `SKILL_MAP`).

## [Unreleased] - 2026-07-18 (behaviorial-duplication consolidation)

Second pass of the anti-duplication refactor — this time keyed on *behavior*
(different names doing the same job), not just name collisions.

### Added
- **`common/registry.py`** — shared harness registries + resolvers:
  - `OUTPUT_TYPE_REGISTRY` — canonical `output_type`/`role` → `models.py` class
    map. Replaces the three copies that carried the same 6+ classes under
    three different keyings: `tools.OUTPUT_TYPE_MAP`, `factory._OUTPUT_TYPE_LOOKUP`
    (dead), `runner.ROLE_OUTPUT`.
  - `resolve_model(key)` — HALT-guarded `model_key` → `OpenAIChatModel`
    resolver. Replaces the unguarded `CONTROL_SHEET.models[key]` lookups that
    raised a bare `KeyError` (e.g. `runner.build_role_agent`).
  - `resolve_run_dir(bd_id)` — picks the newest `run_<ts>_<bd_id>` dir that
    holds a `state.json` (crash-resume), else falls back to `TEMP_DIR/<bd_id>`.
    Replaces the divergent `state.load_state` (reports-only) and
    `runner._resolve_run_dir` (looser glob + temp fallback) copies.
- **`common/subprocess.py` `_run_proc(...)`** — generic argv runner, the single
  source of truth for *every* harness subprocess spawn. Parameterised by
  `cwd` / `timeout` / `raise_on_error` / `return_format`
  (`"stdout"` | `"tuple"` | `"completed"`); kills + `RuntimeError`s on timeout
  (Fail Loudly). `_run_tool` is now a thin wrapper over it.

### Changed
- **`infra/tools.py`** — `OUTPUT_TYPE_MAP` deleted; imports `OUTPUT_TYPE_REGISTRY`
  + `resolve_model` from `common`; unguarded `CONTROL_SHEET.models[...]`
  lookups switched to `resolve_model`.
- **`infra/runner.py`** — `ROLE_OUTPUT` deleted; imports
  `OUTPUT_TYPE_REGISTRY` / `resolve_model` / `resolve_run_dir` from `common`;
  `build_role_agent` model lookup now guarded via `resolve_model`;
  `_resolve_run_dir` delegates to `common.resolve_run_dir`.
- **`infra/state.py`** — `load_state` delegates run-dir resolution to
  `common.resolve_run_dir` (removed the local `_RUN_DIR_RE` duplicate).
- **`infra/shadow_tools.py`** — `_acl_log` / `_acl_within_repo` now imported
  from `tools` (removed the local fallback duplicates); `_run_read_cli`
  delegates to the shared `common` subprocess runner.
- **`infra/control_orchestrator.py`** — `verify_gateways_reachable` now reuses
  `create_resilient_http_client` (which sets `verify=False`) instead of opening a
  *second* bare `httpx.AsyncClient` missing `verify=False`. Fixes a latent
  TLS-failure-on-self-signed-proxy bug (the gateways are local proxies).

## [0.1.11] - 2026-07-18

Planner-transcript JSON-rubbish root-cause fix (the real one). The
2026-07-17 `planner.md` garbage (`{"success": true, "message": ..., "data": {...}}`
envelopes + `\n`-escaped content) was NOT role-output JSON — it was the
**`read_file` CLI tool** emitting a JSON envelope as its stdout, which
`batch_read` concatenated and the harness stored verbatim into every
transcript. Nothing in the live harness parses that envelope (`_run_tool`
returns stdout as-is); it was legacy cruft polluting model context.

### Fixed
- **`admin/tools/read_file.py`** — now emits SCOPED PLAIN content with a clean
  `=== File read: <path> (lines X-Y of N) ===` header; the
  `{"success": true, "data": {...}}` envelope is dropped entirely.
  Errors print as plain `ERROR: ...` text. (This is the actual source of the
  `planner.md` garbage — ticket `ggsq` class, root cause.)
- **`admin/orchestrator/infra/tools.py` `batch_read`** — joins the now-clean
  `read_file` outputs directly (no re-wrapping `=== File read: ===` header).
- **`admin/orchestrator/infra/artefacts.py`** — added a `batch_read` eviction
  branch (collapses to `File read: <path>` anchors + dead-stores full content in
  `file_cache`), matching the `read_file` eviction. Implements the `evict-reads`
  design: full file bodies never stay in the token stream.
- **`admin/orchestrator/infra/converter.py` `_strip_read_envelope`** — defense-in-
  depth: unwraps any residual `{"success": true, "data": {...}}` envelope (bare,
  or `=== File read: ===`-prefixed) and renders only `data.content` (the file
  text). Re-running the converter on the stale `planner.jsonl` yields **0 envelope
  hits** and ~67% token reduction vs the raw `.jsonl`.

### Changed
- **`admin/orchestrator/infra/runner.py` `do_role` / `record_coder`** — render each
  role's Pydantic output to compact markdown via `_model_to_md(result.output)`
  (Pydantic-AI v2.0: `result.output` IS the parsed model — no `json.loads` round-
  trip of our own serialized output) and store that MD in `history` /
  `phase_summaries`. The `prior_role_outputs` injection renders every `history`
  entry to MD at injection time, so raw JSON never leaks into prompts while
  `history` stays raw JSON for the `approved_json` parse contract at `run_phase`.
  (Tickets `p0vt` / `-31y5` JSON->MD injection mandate.)

## [0.1.10] - 2026-07-18

Planner-run forensics remediation. Four tickets from the 2026-07-17 planner
transcript (`artefacts/history/planner/planner.md`) — double-escaped final_result
JSON, 3× duplicated/truncated context injection, planner burning its tool budget on
discovery instead of planning, and `get_repo_structure` emitting `\uXXXX` garbage.

### Fixed
- **`admin/tools/get_repo_structure.py`** — `json.dumps(..., ensure_ascii=False)`
  so box-drawing chars (`├──`) render instead of raw `\u251c\u2500\u2500` escapes.
  (Ticket `ggsq`.)
- **`admin/orchestrator/infra/converter.py`** — `tool-call` args that are already a
  JSON string are rendered verbatim, not double-`json.dumps`-escaped (kills the
  `\"rejected_subtasks\"` corruption that made Pydantic reject `ApprovedPlan`).
- **`admin/orchestrator/infra/artefacts.py`** — `_evict_dicts` now parses JSON-string
  `tool-return` content to a structured dict so it is not re-serialized as an escaped
  string on the next round-trip. Combined with the converter fix, injected/echoed
  model JSON stays single-encoded. (Ticket `p0vt` — MD-only injection
  at the record seam for ALL roles; raw JSON lives only in `.jsonl` for
  `model_validate_json` replay, never in the injected prompt.)
- **`admin/orchestrator/infra/runner.py` `build_role_agent`** — read-bucket
  protocol defense-in-depth (re-applied here after the dead `orchestrator.py` was
  deleted): hard-rejects any `_DISCOVERY_TOOLS` name (get_repo_structure/
  investigate/search/...) appearing in a role's `tool_allow_list`, so the planner
  can never receive discovery tools even from a leaked spec. (Ticket `c8lh`.)
- **`admin/orchestrator/infra/runner.py` `load_skill`** — wired the pre-existing
  `assert_planner_emitted` guard for `planner`/`planner_sup`: if the
  `GuardToolset` budget is exhausted without a `final_result`, the run HALTS loudly
  instead of proceeding on a `None` plan (the q9lt failure mode). `build_role_agent`
  now also returns the `GuardToolset` instance so the caller can inspect
  `guard.exhausted`. (Ticket `4mn8` / M11 structural final_result guard.)

### Changed
- **`admin/orchestrator/infra/orchestrator.py` DELETED** — it was a Build_08
  alternative conductor that was never wired into `run_orchestrator.sh` (which
  launches `admin.orchestrator.infra.runner`). Multiple prior fix commits
  (including the original `c7b61989`) erroneously edited the dead file, so all live
  conductor fixes now live ONLY in `runner.py` (plus the shared infra modules
  `tools.py` / `factory.py` / `artefacts.py` / `converter.py` /
  `control_orchestrator.py`). See bead `dead-file-orchestrator-py-deleted-2026-07-18`.

## [0.1.9] - 2026-07-18

Build from `docs/06_Implement.md` (grill-me plan): coder tool-instruction +
harness-owned validation loop, coding-philosophy hardening, parallelism ownership.
Tickets: `wi3i`, `4lrm`, `zu9u`,
`ieek`.

### Added
- **`admin/tools/guardrail_check.py` (new, harness-side)**. Post-edit gate
  patterned on `TEST/agent_guardrail.py`: `checkpoint -> ruff -> scoped pyright ->
  diff_vs_checkpoint`. `validate <file>` prints JSON
  `{success, ruff_ok, pyright_ok, ruff_output, pyright_output, diff_vs_checkpoint}`.
  NOT exposed to any agent `tool_allow_list`.
- **Harness-owned coder validation re-spawn loop (`runner.py` `execute_task`)**.
  Coder declares done via JSON; harness runs `guardrail_check.py` on the staged
  files; on **RUFF failure only** (max `CODER_VALIDATION_PASSES = 3`) spawns a
  fresh coder with the ruff feedback appended so it self-corrects. Structurally
  removes the `shell`-tool hallucination (the model is never told to execute).
  Pyright errors are surfaced as warnings, never a re-spawn trigger.
- **`build_tool_usage_guide` (`tools.py`)** now renders the real
  `inspect.signature` + per-parameter type annotations + an output line (replaces
  the placeholder `Signature: tool(name, **kwargs)`).

### Changed
- **Coding philosophy baked into `templates/*.yaml` `_BASE_`** (all 5 roles):
  FAIL FAST / FAIL LOUDLY / FAIL CHEAPLY / ZERO-SPECULATION / USE STRICT PYDANTIC.
  The no-LLM forge preserves `_BASE_` verbatim, so it survives into `customised/`.
  Closes the coder-prompt-gutting regression.
- **`templates/planner.yaml`** gained a PARALLELISM OWNERSHIP instruction: the
  Planner (PM) owns file-disjoint groups + `depends_on` ordering; the runner
  asserts and HALTS loudly on a cross-group file clash (it does not silently
  reorder the DAG).
- **`runner.py`** logs `[DAG] planner topology: concurrent_groups=N
  sequential_groups=M` as a planner-quality signal.

### Removed
- **Q4 fallback model** — already deleted (`control_orchestrator.py:699` marker;
  zero `FALLBACK` / `run_with_fallback` refs in `runner.py`). Single model per
  role, raw crash on failure. (`output_sanitizer.py` remains — it is JSON-repair,
  not model-fallback.)

## [0.1.8] - 2026-07-17

Global JSON-output sanitizer (ticket cqjb). Kills the
empty/structurally-broken-model-output failure mode (SA4-F6 class) with a
deterministic offline backstop instead of a silent fail-safe.

### Added
- **`output_sanitizer.py` (new)**. One-pass helper `clean_role_output(raw, model)`:
  extract the first balanced `{...}`/`[...]` JSON block (handles markdown
  fences) -> `fast-json-repair` structural repair -> FROZEN whitelist normalize
  (the 2 severity `Literal` fields: `blocker|warn` and `Critical|High|Medium|Low`,
  case-normalized only) -> Pydantic validate. Truncated Literals (e.g. `"bloc"`)
  are NOT guessed -> raises `RuntimeError("[HALT] …")` (fail loudly, Decision A).
  Ships a `--selftest` CLI. `fast-json-repair>=0.2.0` added to `pyproject.toml`.

### Changed
- **`load_skill` (`runner.py`)**. Now catches `UnexpectedModelBehavior`, extracts
  the raw body, and attempts `_recover_role_output` (sanitizer salvage). On success
  logs `[RECOVERED]`; on failure raises `[HALT]` instead of dying raw. Recovered
  output is wrapped in a minimal `_SanitizedResult` shim so downstream transcript /
  eval / persist consumers keep working. This covers the planner `DraftPlan` and
  every `output_type` role.
- **Three `model_validate_json` boundaries (`runner.py`)**. `supervisor_review`
  (CodePassed), `red_team` (AuditResult), and `supervisor_plan` (ApprovedPlan) now
  route through `clean_role_output` and FAIL LOUDLY (`[HALT]`) when sanitize+
  validate fails — the prior silent `passed=False` / `green=False` / "flat coder
  gate" degradations are removed.

## [0.1.7] - 2026-07-17

Coder blank-completion crash incident remediation (run hbh1). Traces to bead `xvy0`. Model swap (A.2: coder_model gemini-3.1-pro-low -> deepseek_flash) handled by user directly; this entry covers A.1/B/C.

### Fixed
- **A.1 / xvy0 — surfaced coder empty-output HALT** (`runner.py`). `record_coder` now catches `UnexpectedModelBehavior` (low-tier model returning empty `finish_reason=stop` completions) and raises a clean `[record_coder] coder emitted empty/invalid output …` RuntimeError instead of letting it propagate raw and kill the run with no diagnostic. The existing failure-persistence path writes a FAILED coder transcript so the run is resumable/diagnosable.
- **B / xvy0 — DAG fast-fail on blocked upstream** (`runner.py`). `process_group` now inspects each dependency group's results after `wait_for`; if the upstream produced ONLY `blocked` tasks (e.g. coder crashed), the downstream group short-circuits in <1s with a `[DAG] group … SKIPPED — prerequisite … produced 0 usable tasks` message instead of hanging the full 300s `wait_for` watchdog and surfacing a misleading `TimeoutError`.
- **C / xvy0 — coder bounded-research hard_rule** (`templates/coder.yaml` + `customised/coder.yaml`). Added explicit rule: at most ~3 read-only discovery calls per target file then WRITE; if no file written after ~12 read-only calls, STOP and emit `final_result` (status `blocked`) rather than looping on discovery. Hardens against the research-loop class of failure (sibling of `q9lt`).

## [0.1.6] - 2026-07-17

Verified-audit remediation pass (9 findings: 4 P0 MUST-FIX, 5 P1 GOOD-TO-FIX). Each fix traces to a beads ticket + the orchestrator-only audit (bd remember audit-orchestrator-verified-2026-07-17).

### Fixed (P0 — MUST)
- **C2 / frf3 — phase-order invariant before OPS** (`orchestrator.py`). OPS is PROPOSE-ONLY + stop-and-review; a server-side assert now re-derives `green` from `audit.risks` severities (no High/Critical, no context-leak, no future-proofing violations) and confirms red_team ran before any ops dispatch. `_catastrophic` HALT otherwise.
- **H8 / zu9u — cross-group file-disjointness** (`runner.py`). Added a global pass over every workplan group's `file_paths`; raises `RuntimeError("[DAG] cross-group file overlap …")` if the same file appears in 2+ concurrently-run groups. Intra-group assert retained.
- **M5 / fwfk — logfire secret logging** (`runner.py` + `observability.py`). Dropped `instrument_httpx(capture_all=True)` in both `_configure_logfire` and `configure_logfire`; Authorization: Bearer headers are no longer captured into local logs.
- **M7 / rhh4 — loopguard recovery marker** (`runner.py`). Added `_detect_and_mark_recovery` + `mark_recovered`; a loopguard RECOVER (fabricated best-effort output from `tools=[]` recovery agent) is now surfaced loudly to stderr and counted — never silently accepted as a clean pass.

### Fixed (P1 — GOOD-TO-FIX)
- **M9 / gf6y — CJK-aware token estimate** (`_loopguard.py`). `estimate_tokens` fallback now counts CJK chars at ~2 chars/token and non-CJK at ~4; compaction gate no longer fires too late on Chinese-heavy payloads.
- **M11 / 4mn8 — planner budget guard** (`tools.py`). `GuardToolset` exposes `exhausted`; added `assert_planner_emitted()` raising if the planner budget is exhausted without a `final_result`.
- **M12 / ew3z — per-message record-time timestamp** (`converter.py` + `artefacts.py`). `messages_to_md` accepts a per-message `timestamps` list sourced from each pydantic-ai message's own `.timestamp`, so history `.md` timelines are accurate instead of all sharing the rewrite time.
- **M3 / vo94 — enriched status board** (`runner.py`). LIVE block now shows active task, loopguard-recovery count, and compaction count; per-task `update_status_board` during the coder DAG reflects live EXECUTE activity.
- **M4 / ugvt — SINK-2 phase_summaries** (`runner.py`). Added `PHASE_SUMMARIES` populated after each role run and injected as a compact "PRIOR PHASE SUMMARIES" block into subsequent phase briefs for richer cross-phase context.

## [0.1.5] - 2026-07-16

Planner infinite research loop fix: removed grep/read_file from agents, systemic steering to search/investigate.

### Removed
- **grep and read_file tool access from all non-coder roles** (`templates/*.yaml`). Planner, supervisor_plan, supervisor_review, red_team can no longer call grep or read_file — they must use search or investigate. Coder retains read_file for write verification.
- **Launcher wipe of customised/ and artefacts/** (`run_orchestrator.sh`). Skill YAML configs and history transcripts now survive across launches.

### Changed
- **Planner template instructions** (`templates/planner.yaml`). Replaced "USE grep/read_file to verify EVERY file_path + store as evidence" with "Use search/investigate. Research MAX 3 rounds. Do NOT loop."
- **All role templates** (`templates/{supervisor_plan,supervisor_review,red_team,coder}.yaml`). Same fix: replaced grep/read_file instructions with search/investigate + research cap.
- **Evidence validator** (`models.py`). Updated `_require_evidence` error text from "use grep/read_file" to "use search/investigate".
- **SubTaskBrief.evidence docstring** (`models.py`). Changed "grep/snippet" to "search/investigate output".
- **Control orchestrator hard_rules** (`control_orchestrator.py`). Removed grep/read_file verification requirements from planner and supervisor_plan.
- **load_skill failure persistence** (`runner.py`). All roles now run under loopguard (`_run_agent_retry` with `loopguard=True`), so failure transcripts are persisted to `artefacts/history/<role>/FAILED.jsonl` for every role, not just coder.

### Added
- **Runtime tool steering** (`tools.py`). grep and read_file functions append a tip to their return value: "search and investigate provide faster code understanding". Agents learn through repetition even if the tools are re-added later.

## [0.1.4] - 2026-07-16

Structural hardening: fallback removal, parallel coder, coding philosophy, tool usage guide (fix-04).

### Removed
- **Fallback model chains (`control_orchestrator.py`).** Deleted `FallbackSheet`, `load_fallback_sheet()`, `FALLBACK_SHEET` constant — single model per role, raw crash on failure (grill-me B1).
- **Fallback dispatch (`runner.py`).** Deleted `_build_role_agent_for_model`, `_validate_role_output_json`, `_run_role_with_fallback`. `load_skill` now runs a single `agent.run()` and crashes loudly on failure.

### Changed
- **Parallel coder dispatch (`orchestrator.py`).** Replaced sequential `for group` loop with DAG-respecting parallel dispatch: `asyncio.Event` per group for `depends_on`, `asyncio.Semaphore(20)` capping concurrent LLM calls, `asyncio.gather` for concurrent tasks within groups. Group-level retry on gate failure preserved.
- **`_run_role` catches ALL exceptions (`orchestrator.py`).** Now catches `Exception` (not just `ModelHTTPError`) with clean `[HALT]` summary, making non-retryable errors fail-loudly instead of silently propagating.
- **Coding philosophy globally injected (`tools.py`).** New `CODING_PHILOSOPHY_BLOCK` constant (FAIL FAST/LOUD/CHEAP, ZERO-SPECULATION, PYDANTIC ONLY) injected into ALL agents in `load_skill` and `build_worker_spec`.
- **Pydantic enforcement unconditional (`templates/coder.yaml`).** Removed `When epic.must_be_pydantic is true` conditional — always enforce strict Pydantic models.
- **Pydantic hard_rule added to ALL templates.** Added same Pydantic hard_rule to `planner.yaml`, `supervisor_plan.yaml`, `supervisor_review.yaml`, `red_team.yaml`.

### Added
- **Tool usage guide (`tools.py`).** `build_tool_usage_guide()` generates per-agent tool documentation from `TOOL_REGISTRY` docstrings, injected for all roles. Includes `_infer_tool_usage()` heuristic classification. Full format: description, signature, usage guidance.

## [0.1.3] - 2026-07-15

Harness reliability + run-targeting fixes from the yrev / hbh1 sessions.

### Added
- **Red-team anti-laziness guard (`runner.py`, 71z2).** New `_blocker_findings_from_risks()` promotes any Critical/High `AuditRisk` with a resolvable `task_id` into a blocker `ReviewFinding`, so a lazy model can no longer flag real defects in `risks` yet leave `findings` empty (which let the gate pass and ship defects unreviewed). Critical/High risks with no resolvable `task_id` HARD FAIL as unresolvable. Wired into `run_red_team_gate` before the deterministic verdict.

### Changed
- **Run targeting (`run_orchestrator.sh` + `runner.py`, y5zp).** Launcher now reads an explicit `bd:` line (line 2 of `user_prompt.md`, after `Resume:`) when launched with no `--bd` arg, so no-arg runs target the correct ticket instead of auto-creating a smoke ticket. `read_prompt` strips the `bd:` line from the task spec so it never reaches the planner.
- **tmux session naming.** Session is now named after the bd ticket (e.g. `hbh1`) instead of the hardcoded `orchestrator`, so the operator can confirm the running ticket at a glance.
- **Status board header (`runner.py`, ez54).** `Roles completed: X/Y` → `Roles completed (executions/phases): X/Y` to disambiguate numerator (role executions) from denominator (phase types).
- **Task spec (`user_prompt.md`, hbh1).** Rewritten to the real zero-dicts remediation: convert `unified.py:625/777/786` `dict[str,Model]` fields to `DictMap` RootModels (reuse `TenGodMap`; define `ExternalPillarTriggerMap`/`PalaceAssociationMap`), skip intentional C4 fields `:3110/3114/3115`, convert `session.py` dict fields, replace `isinstance(x,dict)` shims across 5 engine files. Acceptance gate: `ruff clean` + `verify_dict_access_runtime.py → 0 CONFIRMED_CRASH`.
- **HTTP/2 + pool tuning for all LLM providers (`control_orchestrator.py` → `http_client.py`, hbh1).** Shared client config extracted into `admin/orchestrator/infra/http_client.py` (`create_resilient_http_client`): `http2=True`, `verify=False` (all providers are local self-signed LiteRouter-style proxies), `limits=httpx.Limits(max_connections=200, max_keepalive_connections=60)` (RAM headroom; was 100/20), `timeout=ORCH_HTTP_TIMEOUT` (connect=15s, read=300s — long enough for slow models; reverted from a briefly-tried 10s that tripped constant `ModelAPIError` retries on deepseek-v4-pro). `literouter_url` default flipped `http://`→`https://localhost:7766/v1`, so the orchestrator→proxy hop negotiates HTTP/2 over TLS. Change takes effect on next run launch.
- **Centralized transport-level retry (`http_client.py`, hbh1).** Retries on transient 429/5xx **and** connect/timeout errors are now handled at the HTTP transport layer via `pydantic_ai.retries.AsyncTenacityTransport` with `validate_retryable_response` as the gate: 90/120/240s `wait_exponential`, `MAX_MODEL_RETRIES=3`, `reraise=True`. The agent layer (`runner._run_agent_retry`) no longer retries — it just catches the final `ModelAPIError` and aborts gracefully. Retries are the transport's single responsibility (no double-retry / compounding backoff).
- **Removed `openrouter` provider (`control_orchestrator.py`).** All providers are now local (mcpmart/antigravity = `10.32.34.243`, literouter/pydantic = localhost), so the public `openrouter.ai` endpoint (and its `verify=False` TLS-exposure) is gone. Model names like `openrouter/...` continue to route through the `literouter` provider.

### Fixed
- **Model request timeout (`control_orchestrator.py`).** `ORCH_HTTP_TIMEOUT` `read` 60s → 300s so slow free-tier models (`zen/deepseek-v4-flash-free`) no longer crash the run with `ModelAPIError: Request timed out`. Still bounded by `_loopguard` `AGENT_RUN_TIMEOUT=600`; `connect=15s` still fails fast on unreachable endpoints.
- **Gateway 401 (`control_orchestrator.py`, fcdff83b).** Hardcoded gateway auth keys (literouter/mcpmart/antigravity/pydantic) + fixed `env_file` path resolution, resolving the 401 Unauthorized on the literouter gateway.
- **Transient provider timeout killed the whole run (`runner.py`, hbh1).** `_run_agent_retry` only caught `ModelHTTPError`, so a bare `openai.APITimeoutError` (`ModelAPIError`) at `supervisor_plan` propagated and crashed the entire run. Broadened the `except` to `ModelAPIError`; HTTP errors keep the status-based retry gate, all other `ModelAPIError` (timeouts / connection / stream) are now retried.
- **Graceful abort on final failure (`runner.py`, hbh1).** On a final `ModelAPIError` (after the transport's retries are exhausted) **or** a non-retryable error, `_run_agent_retry` writes a structured `orch/logs/runtime/FAIL_<phase>.json` report via `_report_run_failure` and exits cleanly with `SystemExit(1)` + an `[RUN ABORTED]` banner — no unhandled traceback crash. (The retry schedule itself now lives in the transport layer; see above.)

## [0.1.2] - 2026-07-14

Maintenance release. Hardens the red-team go/no-go contract so it can never silently
drift between the runner, the reviewer check, and the prompt again.

### Fixed

- **Duplicated red-team gating logic (`runner.py`).** The verdict was computed twice —
  inline in `run_red_team_gate` and again in the `passed()` reviewer check — and the two
  had already diverged from `templates/red_team.yaml` (which called `rubric_cube`
  "informational ONLY" while the runner HARD FAILs on an unresolvable global blocker).
  Extracted `red_team_passed(findings, rubric_cells)` as the **single source of truth**
  and routed both code paths through it. `rubric_cube` is now correctly documented as
  *informational for recode targeting* with an *unresolvable blocker → HARD FAIL* contract.
- **Stale frozen template (`templates/red_team.yaml`).** Synced its wording to match the
  active `customised/red_team.yaml` so SkillForge regeneration never reintroduces the
  divergent "informational ONLY" language.

### Added

- **Contract guard test (`tests/test_red_team_contract.py`).** Two layers make regression
  impossible: (A) asserts every red-team prompt (`templates/` + `customised/`) carries the
  canonical contract markers (`findings`-driven, `unresolvable`, `HARD FAIL`); (B) asserts
  `red_team_passed` actually implements it (global blocker + empty findings ⇒ fail; clean
  ⇒ pass; task-keyed blocker finding ⇒ fail). Any prompt↔runner drift now breaks CI.

## [0.1.1] - 2026-07-14

Bug-fix release. No pipeline or behavior changes — restores importability and
correct red-team re-execution accounting.

### Fixed

- **Import crash (`control_orchestrator.py`).** Two `OpenAIChatModel` definitions
  (`nemotron_nano`, `nemotron_nano_reasoning`) placed `provider=PROVIDERS[...]`
  *after* a `profile=OpenAIModelProfile(openai_supports_tool_choice_required=None,`
  line whose trailing comma swallowed `provider=` into the `OpenAIModelProfile(...)`
  call. `OpenAIChatModel` then fell back to `provider='openai'`, which triggers
  `infer_provider('openai')` and requires `OPENAI_API_KEY` — crashing the module at
  import time (and every module that imports it: `runner`, `_loopguard`, `tools`,
  `state`, and the test suite). Reordered `provider=` before `profile=` so the
  explicit `OpenAIProvider` instance is used. All 18 model definitions now import
  cleanly without credentials.
- **Red-team re-execution double-count (`runner.py`).** `run_execute_phase` re-ran
  *every* task whenever `rerun_ids is None`, even when a `prior` batch was supplied.
  The red-team gate therefore re-executed the already-completed code-review batch
  before re-running the failing tasks, so coder turns were counted twice. Now
  `prior` is adopted verbatim when `rerun_ids is None` and a prior exists; tasks are
  only re-run when explicitly listed in `rerun_ids`. `test_gates.py` now passes.

### Notes

- The `DEFAULT_AGENT_SETTINGS` / `ROLE_AGENT_SETTINGS` registry
  (`tool_choice="none"`, `parallel_tool_calls=False`) added earlier is intact and
  applied at `runner.py:191` and `_loopguard.py:229,345`.
- `OpenAIModelProfile(openai_supports_tool_choice_required=None)` still emits a
  static-type warning (param is typed `bool`); this is pre-existing, runtime-safe,
  and intentional — left unchanged.

## [0.1.0] - 2026-07-14

First successful end-to-end operational run of the orchestrator.

### Added

- **Deterministic 6-role pipeline** (`runner.py`): `planner → supervisor_plan →
  coder → supervisor_review → red_team → ops`. The conductor is pure Python — no LLM
  orchestrator decides control flow.
- **`GuardToolset`** (`tools.py`): a `WrapperToolset` subclass that intercepts unknown /
  hallucinated tool names (e.g. `shell`, `bash`) and returns a warning instead of
  exhausting `Agent(retries=5)` into `UnexpectedModelBehavior`. This guard is what made
  the first full run possible.
- **Loop guard with RECOVER-not-EXIT** (`_loopguard.py`): `AGENT_RUN_TIMEOUT = 600.0`,
  `MAX_LOOPGUARD_TURNS = 20`, per-run `UsageLimits(request_limit=40)`, and a recovery
  agent spawned with `tools=[]` to force a best-effort answer rather than killing the
  pipeline. `parallel_tool_calls=False` on every tool-using agent.
- **Tool ACL sandbox** (`tools.py`): every worker capability is a subprocess wrapper
  around `admin/tools/*.py`; `wrap_with_acl` confines path args to approved prefixes and
  denies `.env` / `controls.py`. Agents have zero raw shell or filesystem access.
- **Crash-resume** (`state.py`): atomic `state.json` checkpoints (write-temp +
  `os.replace`) per `bd` id; `reset_stale_in_progress` flips crashed tasks back to
  `pending` for exactly-once re-execution.
- **Compaction gate** (`_loopguard.py`): per-role token budget with a safe-boundary
  slicer (`get_safe_recent_messages`) that never starts a history slice mid tool-call;
  compacted context persisted to `orch/context/`.
- **tmux dashboard** (`run_orchestrator.sh`): 4-pane session (runner / `STATUS.md` /
  `run.log` / transcript inspector) with `--fresh` wipe and bd-ticket auto-resolution.
- **Observability**: `STATUS.md` kanban (symlink to `orch/prompt/kanban.md`),
  `run.log`, `eval.jsonl`, per-run `state.json`, and `fail_*.json` dumps.
- **Frozen skill specs** (`customised/*.yaml`): per-role `tool_allow_list` asserted as a
  subset of `TOOL_REGISTRY`; supervisors and red-team are strictly read-only.
- **Typed hand-offs** (`models.py`): `DraftPlan → ApprovedPlan → TaskBatch → TaskResult →
  CodePassed → AuditResult → GitResult → OrchestratorState`, so malformed role output is
  rejected and re-prompted.

### Fixed

- Model hallucination of a `shell` tool no longer crashes the run (see `GuardToolset`).
- Runaway loops and hung agents are now bounded by timeouts and turn caps instead of
  blocking indefinitely.
- Resumed runs continue at the exact failed unit rather than restarting from PLAN.

### Notes

- `red_team` is a **hard gate** (no forced pass); `supervisor_*` reviews force-pass on
  the 3rd attempt.
- `ops` verifies the git push and `commit_sha` before closing the beads ticket.
- `admin/controls/controls.py` (model registry + tunables) and the repo `.env` are
  protected read-only files; edit them outside of normal operation.
