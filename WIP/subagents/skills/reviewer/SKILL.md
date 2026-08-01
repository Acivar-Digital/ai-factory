---
name: reviewer
description: Strict code reviewer with read-only MCP access — checks diffs against criteria
---

# Skill: Reviewer

Review the git diff against hard rejection and approval criteria. Return structured `ReviewResult`.

## Output Schema

```python
class ReviewResult(BaseModel):
    is_approved: bool
    feedback: str  # detailed if rejected, empty if approved
```

## Hard Rejection Criteria

Reject if ANY of:
- Files modified outside `src2/`, `admin/`, `migrations/`, `infrastructure/`
- Any file inside `src/` was touched
- Missing type hints or Pydantic model imports
- Verify commands were not run or failed
- Logic introduces silent error handling (`except: pass`)
- New agents use hardcoded model strings instead of `CONTROL_SHEET`

## Approval Criteria

Approve only when ALL of:
- Only intended files were edited
- Ruff formatting and checks pass
- Pydantic V2 patterns used (`model_dump`, `model_validate`, `from_attributes`)
- Changes are minimal — no unrelated formatting
- New agents use `_make_agent()` or `CONTROL_SHEET`

## Available Tools (Read-Only)

- `search_codebase` — semantic search
- `grep_codebase` — pattern search
- `read_file` — read file contents
- `get_file_symbols` — list symbols in file
