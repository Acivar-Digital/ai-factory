# Factory Upgrade — YOLO Autonomous Execution Plan

## Mission

Upgrade the AI-Factory harness to production-grade quality by autonomously executing the plan defined in `docs/01_Factory_Upgrade.md`. The orchestrator (me) runs the pipeline end-to-end without human intervention, self-corrects based on verification results, and adjusts the harness whenever output quality falls short of Senior Architect standards.

---

## Execution Model

### Start Sequence

1. **Load `ai-factory` skill** — inject full architecture context into every agent session.
2. **Load `pydantic-ai-coding` skill** — ensure Pydantic v2 + Pydantic AI v2 conventions are enforced in all generated code.
3. **Prime beads workspace** — `bd prime` to recover any interrupted state.
4. **Read `user_prompt.md`** — extract scope, deliverables, `start_phase`, `stop_phase`, and `TARGET_REPO`.
5. **Read `docs/01_Factory_Upgrade.md`** — load the upgrade specification as the authoritative design tree.

### Autonomous Loop

For each tier in `_PHASE_ORDER = ["intern", "engineer", "senior"]`:

```
FOR tier IN ["intern", "engineer", "senior"]:
    1. Spawn agent with tier-specific YAML (intern.yaml / engineer.yaml / senior.yaml)
    2. Inject upfront diagnostic context (prior diffs + verification logs from previous tiers)
    3. Agent executes edits on factory/temp/ working copies ONLY
    4. Post-edit: run verify_edit() on the tier's output
       - run_lint_regression() (ruff + pyright diff vs .orig)
       - verify_refactored_ast() (7-layer AST sandbox)
    5. Evaluate VerificationResult
       - PASS  → advance to next tier
       - FAIL  → retry same tier up to MAX_RETRIES=3
       - 3rd consecutive FAIL on same file:
           IF tier == senior → Fail Loudly & Halt (RuntimeError)
           ELSE              → cascade diagnostics to next tier, advance
```

### Post-Run Quality Alignment Gate

After the Senior tier completes (or halts):

1. **Read `user_prompt.md`** scope and deliverables.
2. **Self-evaluate**: "Would I have produced this output? Does it meet every requirement cleanly, without silent swallows or unnecessary fluff?"
3. **If output is substandard** (compared to what a Senior Architect would produce):
   - Identify the specific gap (missing deliverable, sloppy formatting, unhandled edge case, etc.)
   - Update the relevant harness artifact:
     - `factory/infra/agents/senior.yaml` — tighten system prompt instructions
     - `factory/infra/ast_verifier.py` — add missing verification layer or tighten thresholds
     - `factory/infra/agents/intern.yaml` — add missing constraints or refactoring goals
   - Re-run the pipeline from the affected tier (not from scratch).
4. **Repeat** until the harness output matches the Lead Architect's quality bar.

---

## Decision Log (Locked)

| # | Decision | Value |
|---|----------|-------|
| 1.1 | Mandatory 3-pass execution | Always Intern → Engineer → Senior, no early exit |
| 1.2 | Tier handover format | Upfront Diagnostic Injection (structured verification block prepended to next tier prompt) |
| 2.1 | Circuit breaker escalation | Tier cascade (Intern→Engineer→Senior); Senior trips → Fail Loudly & Halt |
| 2.2 | Pre-flight anti-pattern handling | Inject as advisory refactoring goals into Intern prompt |
| 3.1 | AST buffer dependency | Standard library `ast` slicing only; zero external CST dependencies |
| 4.1 | Deployment boundary | Files stay in `factory/temp/`; no automatic write to `TARGET_REPO` |
| 5.1 | Definition of Done | Senior Engineer + Orchestrator evaluate against `user_prompt.md`; harness adjusts when output falls short |

---

## Key Files Involved (No Code Changes in This Phase)

| File | Role |
|------|------|
| `docs/01_Factory_Upgrade.md` | Authoritative design specification |
| `docs/01_Factory_Upgrade_YOLO.md` | This plan (YOLO execution strategy) |
| `factory/infra/pipeline.py` | Orchestrator loop; `_run_verify_edit()` after each tier |
| `factory/infra/_runtime.py` | `_PHASE_ORDER = ["intern", "engineer", "senior"]` |
| `factory/infra/validation.py` | `MAX_RETRIES=3`, `REVIEW_PASS_FIELD`, `EXCHANGE_ROLES` |
| `factory/infra/agents/intern.yaml` | Intern Builder system prompt |
| `factory/infra/agents/engineer.yaml` | Engineer Fixer system prompt |
| `factory/infra/agents/senior.yaml` | Senior Auditor system prompt |
| `factory/infra/ast_verifier.py` | 7-layer AST verification + `run_lint_regression()` |
| `factory/infra/virtual_ast_buffer.py` | Comment-preserving CST replacement |
| `factory/infra/ast_analyzer.py` | Pre-flight anti-pattern scanner |
| `factory/infra/tools_shell.py` | `verify_edit()` CLI wrapper |
| `factory/infra/tools_guard.py` | `verify_edit` registered in `MODIFY_TOOLS` + `TOOL_REGISTRY` |
| `factory/infra/deploy.py` | Target repo sync (stays gated, no auto-deploy) |
| `factory/infra/tools_guard.py` | `verify_edit` registered in `MODIFY_TOOLS` + `TOOL_REGISTRY` |

---

## Autonomy Boundaries

### What I Do Autonomously
- Spawning and managing LLM agent tiers via the pipeline
- Running `verify_edit()` after each tier
- Evaluating verification results and deciding retry vs. advance
- Self-evaluating final output against `user_prompt.md`
- Adjusting harness prompts/verifiers when quality gaps are detected
- Running `ruff check` and `pytest` for quality gates
- Committing and pushing changes at session end

### What I Do NOT Do Autonomously
- Modify `TARGET_REPO` (user's external codebase) — files stay in `factory/temp/`
- Deploy to production without explicit user approval
- Change the 3-tier pipeline structure (Intern → Engineer → Senior)
- Override the `Fail Loudly & Halt` rule on Senior circuit breaker trips
- Skip the quality alignment gate post-run

---

## Exit Conditions

The autonomous run completes when:
1. All 3 tiers pass verification cleanly, AND
2. The post-run quality alignment gate confirms output meets `user_prompt.md` requirements, AND
3. All `ruff check` and `pytest` quality gates pass.

If the Senior circuit breaker trips 3 times → **Fail Loudly & Halt** with structured error logs. The user then decides whether to intervene or adjust the harness.

---

## Session Close Protocol

On completion (or halt):
1. `git status` — check what changed
2. `git add <files>` — stage code changes
3. `git commit -m "..."` — commit with descriptive message
4. `git push` — push to remote
5. Record key decisions with `bd remember`
6. Create beads issue for any follow-up harness adjustments
