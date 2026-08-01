---
name: plan
description: Analyze a task and produce a structured RunPlan with ordered, ID'd fix items
---

# Skill: Plan

Generate a `RunPlan` that classifies each required code change by strategy and orders them by safety.

Each fix MUST be independently executable — the coder will run ONE fix at a time.

## Output Schema

```python
class FixStrategy(StrEnum):
    AST_SURGICAL = "ast_surgical"       # replace_function / ast_add_* — safest
    TEXT_REPLACE = "text_replace"       # replace_text for targeted string change
    COMPLEX_REWRITE = "complex_rewrite" # multi-step rewrite

class FixItem(BaseModel):
    fix_id: str                        # e.g. "F1", "F2" — unique, sequential
    file: str                          # relative path
    description: str                   # one sentence — what to change and why
    strategy: FixStrategy
    why_strategy: str                  # why this strategy over the alternatives
    verify_cmd: str | None            # shell command to verify, e.g. "uv run ruff check src2/"

class RunPlan(BaseModel):
    fixes: list[FixItem]               # ordered safest first
    risk_level: str                    # Low | Medium | High
    order_rationale: str               # why this ordering
```

## Rules

- Never plan modifications to `src/` — only `src2/`, `admin/`, `migrations/`
- Safest/most isolated fixes first, riskiest last
- Each fix must be independently verifiable
- Verify commands should be cheap to run (ruff check, not full test suite)
- Each `fix_id` is tracked in the runner state file — if the process crashes mid-way,
  the runner will resume from the first uncompleted fix_id
