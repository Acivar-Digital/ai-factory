# Fix: Separate Target Repo Root from Harness Repo Root

## Problem

`REPO_ROOT` is used for everything: harness infra, staged paths, BD scripts, AND
resolving source file paths (`src2/...`). But `src2/` lives in the target repo
(`baziforecaster/`), not the factory repo (`ai-factory/`). Changing `CWD` to
point at the target repo would break all harness paths.

Every tool under `factory/tools/` imports from `_codebase_common.py`, which
hardcodes `PROJECT_ROOT = Path(__file__).resolve().parents[2]` (= `ai-factory/`).
When a tool receives `src2/engine/module1_macro.py`, it resolves against
`ai-factory/` → not found.

## Design

Introduce `TARGET_REPO` — a second root pointing to the repo containing `src2/`.
Set via **user prompt YAML frontmatter** (`target_repo:` field). The user is the
only one who knows which repo to target — the prompt is the seam.

Core rule: **when `TARGET_REPO` is set, agents ONLY read from the target repo.**
Factory files (`.env`, `runner.py`, `control.py`) are invisible — they are
private infrastructure the agent has no business reading.

The env var is checked at **call time** (not import time), because
`_codebase_common.py` is imported at module load — before the prompt is parsed.

Two resolution functions:
- `resolve_secure_path(path)` — resolves against `TARGET_REPO` (for reads).
  Falls back to `PROJECT_ROOT` when `TARGET_REPO` is unset (backward compat).
- `resolve_repo_path(path)` — always resolves against `PROJECT_ROOT` (for
  writes to `factory/temp/...`).

No prefix routing. When `TARGET_REPO` is set, ALL paths resolve there.

## Changes

### 1. `factory/infra/pipeline.py` — Parse `target_repo` from frontmatter

In `read_prompt`, set `os.environ["TARGET_REPO"]` immediately after parsing the
YAML frontmatter — before any tool call resolves a path.

```python
# After parsing scope, start_phase, stop_phase:
target_repo = front.get("target_repo")
if target_repo is not None:
    os.environ["TARGET_REPO"] = str(target_repo).strip()
```

### 2. `factory/tools/_codebase_common.py` — Two resolution functions

```python
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def _resolve_root() -> Path:
    """Return TARGET_REPO if set (reads), else PROJECT_ROOT (backward compat)."""
    tr = os.environ.get("TARGET_REPO")
    return Path(tr).resolve() if tr else PROJECT_ROOT.resolve()

def resolve_secure_path(relative_path: str) -> Path:
    """Resolve against TARGET_REPO if set, else PROJECT_ROOT. For reads."""
    root = _resolve_root()
    # ... existing sandbox logic (is_relative_to check, path escape guard) ...
    return root / relative_path  # simplified; actual logic has more guards

def resolve_repo_path(relative_path: str) -> Path:
    """Resolve against PROJECT_ROOT (factory repo). For writes to factory/temp/."""
    root = PROJECT_ROOT.resolve()
    # ... same sandbox logic ...
    return root / relative_path
```

`resolve_secure_path` keeps its name (no import changes in 4 read tools).

### 3. Read tools — No code change

`read_file.py`, `grep_codebase.py`, `list_files.py`, `get_file_symbols.py` all
import `resolve_secure_path` — the function now resolves against `TARGET_REPO`
at call time. No changes needed.

Exception: `get_repo_structure.py` imports `PROJECT_ROOT` directly. Change to
use `resolve_secure_path` or a dynamic `_resolve_root()` import.

### 4. Write tools — Switch to `resolve_repo_path`

```python
# Before:
from _codebase_common import resolve_secure_path, ...
# After:
from _codebase_common import resolve_repo_path, ...
```

Replace calls from `resolve_secure_path(...)` → `resolve_repo_path(...)`.

Affected: `write_file.py`, `replace_text.py`, `replace_function.py`,
`add_constant.py`, `add_import.py`, `delete_file.py`, `rename_file.py`,
`move_symbol.py`.

### 5. `factory/infra/context.py` — Staging reads from target repo

`stage_workspace_from_draft` (line 398) uses `REPO_ROOT / fp` to locate
source. Change to:

```python
target_root = Path(os.environ.get("TARGET_REPO") or REPO_ROOT)
is_existing_src = (target_root / fp).is_file()
src_path = target_root / fp
```

Same for `_real_source_paths` (line 442).

### 6. `factory/infra/tools_const.py` — batch_read example is now correct

The example `batch_read(paths=["src2/core/schemas/unified.py"])` now resolves
against `TARGET_REPO` → works. No change needed.

### 7. `factory/infra/runner.py` — Also parse `target_repo` (parallel path)

The `runner.py` has its own copy of `read_prompt`. Apply same change as #1.

### 8. `factory/tools/smoke_test.py` / `guardrail_check.py` — No change

Both use `SCRIPT_DIR.parent.parent` which already resolves to the target repo.

## Summary of Edits

| File | Change |
|---|---|
| `factory/infra/pipeline.py` | Parse `target_repo` from frontmatter, set `os.environ` |
| `factory/infra/runner.py` | Same parse change |
| `factory/infra/context.py` | Staging + `_real_source_paths` use `TARGET_REPO` env var |
| `factory/tools/_codebase_common.py` | Add `resolve_repo_path`; `resolve_secure_path` checks `TARGET_REPO` at call time |
| `factory/tools/write_file.py` | Import `resolve_repo_path` instead of `resolve_secure_path` |
| `factory/tools/replace_text.py` | Same |
| `factory/tools/replace_function.py` | Same |
| `factory/tools/add_constant.py` | Same |
| `factory/tools/add_import.py` | Same |
| `factory/tools/delete_file.py` | Same |
| `factory/tools/rename_file.py` | Same |
| `factory/tools/move_symbol.py` | Same |
| `factory/tools/get_repo_structure.py` | Stop importing `PROJECT_ROOT` directly; use dynamic root |
