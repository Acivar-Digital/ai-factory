# Configuration Guide

How to set up, configure, and run AI-Factory against any target repository.

---

## 1. Two-Repo Architecture (Critical)

The factory uses a **two-path model** — understanding this is essential:

| Path | Variable | What it is | Set via |
|------|----------|------------|---------|
| `PKG_DIR` | `factory/factory/` | Factory's own code + `uv` environment | Hardcoded (always the factory repo itself) |
| `REPO_ROOT` | `CWD` from `.env` | **Target repo** being repaired | `factory/infra/.env` or repo root `.env` |

**No symlink needed.** `CWD` is a plain path string. The factory reads it, and all file operations (search, investigate, read, write, replace) resolve against `REPO_ROOT`.

Shadow tools run as:
```
uv run --no-sync python factory/tools/<tool>.py  # from PKG_DIR (factory's deps)
cwd=REPO_ROOT                                      # but operating on target repo
```

**Temp/scratch area**: `TEMP_DIR = PKG_DIR / "temp"` — inside the factory repo, not the target.

### Self-hosting

To repair `factory` itself:
```env
CWD=/home/yapilwsl/arthityap/ai-factory
```
Everything resolves against the factory repo. Works the same way.

---

## 2. Environment Setup (`.env`)

Create `factory/infra/.env` (or `.env` at repo root):

```env
# Target repository to operate on
CWD="/abs/path/to/target/repo"

# Model gateway URLs
MCPMART_GATEWAY_URL="http://127.0.0.1:8000"
ANTIGRAVITY_GATEWAY_URL="http://127.0.0.1:8001"
LITEROUTER_GATEWAY_URL="http://127.0.0.1:8002"
PYDANTIC_AI_GATEWAY_URL="http://127.0.0.1:8003"

# Per-role model selection
CODER_MODEL="antigravity/claude-3-5-sonnet-20241022"
PLANNER_MODEL="antigravity/claude-3-5-sonnet-20241022"
CODEBASE_MODEL="antigravity/claude-3-5-haiku-20241022"
VERIFIER_MODEL="antigravity/claude-3-5-sonnet-20241022"
```

`CWD` is the only required field — everything else has defaults in `control.py`.

---

## 3. Task Spec (`prompt/user_prompt.md`)

The orchestrator reads `factory/prompt/user_prompt.md` as its sole task instruction. Format:

```yaml
---
Resume: false
bd: my-ticket-id
write_mode: direct
language: python
lint_command: "uv run ruff check"
start_phase: planner
stop_phase: supervisor_plan
scope:
  - path/to/file1.py
  - path/to/file2.py
---
# EPIC
One-line goal statement.

## CONTEXT
Background, audit findings, what's already done.

## DELIVERABLES
1. Concrete file:line-anchored actions grouped into batches.

## REQUIREMENTS & CONSTRAINTS
- Writable paths / sandbox rules
- Coding conventions to follow
- Fail loudly, no `except: pass`

## ANTI-PATTERNS (CRITICAL)
- What NOT to touch
- Patterns NOT to reintroduce

## ACCEPTANCE
1. Verifiable checklist for the run.
```

### Frontmatter fields

| Field | Type | Required | Default | Purpose |
|-------|------|----------|---------|---------|
| `Resume` | bool | yes | — | Seed first coder pass with prior exchange |
| `bd` | string | yes | — | Ticket ID for status tracking + exchange file |
| `scope` | list[str] | no | `[]` | File hints for planner context (not an ACL) |
| `write_mode` | `"direct"` \| `"staged"` | no | `"direct"` | `direct` = edit target files in-place; `staged` = copy to TEMP_DIR, edit there, apply at end |
| `language` | string | no | `"python"` | Project language hint (`python`, `typescript`, `rust`, `html`, etc.) |
| `lint_command` | string | no | `"uv run ruff check"` | Command for acceptance lint gate. Set `""` to skip. |
| `start_phase` | string | no | — | Pipeline phase to start from (seeks to this phase, skipping prior ones). One of: planner, supervisor_plan, coder, supervisor_review, red_team. |
| `stop_phase` | string | no | — | Pipeline phase to stop after (halts after this phase completes). One of: planner, supervisor_plan, coder, supervisor_review, red_team. |

### ⚠️ Critical: Update writable paths for your target

The current `user_prompt.md` has stale baziforecaster constraints:
```
ALL work saved in `admin/orchestrator/temp/`.     ← DOES NOT EXIST in standalone factory
DO NOT edit anything outside `admin/orchestrator/temp/`.  ← WRONG
```

Replace with something appropriate for your target. Example for baziforecaster:
```
- ALL work staged in factory temp, applied to target repo under src2/
- Edits go directly into the target repo via shadow tools
- Target codebase is at REPO_ROOT/src2/
```

Or for self-hosting (repairing factory):
```
- ALL work staged in factory temp, applied to factory/ package
- Edits go directly into factory/ infra, tools, or tests via shadow tools
```

### `scope` field — bypasses the hardcoded repo tree

The planner receives a repo-map context of the target. There is a **known gap** in `ledger.py:_py_tree()` — it hardcodes `src2/` and `tests/` as walk roots. If your target doesn't use `src2/` (e.g., factory itself, or any other repo), the context injection will return "(no .py sources found)".

**Workaround**: Declare the relevant files/folders in the `scope` front-matter list. This gives the planner explicit file-level context without relying on `_py_tree()`. Example:

```yaml
scope:
  - factory/infra/runner.py
  - factory/infra/control.py
  - factory/common/subprocess.py
```

---

## 4. Agent Roles & Pipeline

Fixed 6-role pipeline (deterministic, no LLM orchestrator):

```
planner → supervisor_plan → planner → supervisor_plan → planner
coder → supervisor_review → coder → supervisor_review → coder
red_team → coder → red_team → coder
ops (git push)
```

Each role uses a YAML template from `factory/templates/`:

| Role | Template | Responsibility |
|------|----------|---------------|
| planner | `planner.yaml` | Analyse task, produce DAG workplan |
| supervisor_plan | `supervisor_plan.yaml` | Review plan for gaps/risks |
| coder | `coder.yaml` | Execute tasks, write code |
| supervisor_review | `supervisor_review.yaml` | Review code output |
| red_team | `red_team.yaml` | Security/quality audit |
| healer | `healer.yaml` | Recovery from failures |

---

## 5. Running

```bash
# Run the pipeline
./run.sh

# With specific ticket
./run.sh --bd my-ticket

# Fresh run (wipe all state)
./run.sh --fresh

# Resume from saved state
./run.sh --resume

# Stop after specific role
./run.sh --stop-after=planner
```

---

## 6. Targeting Another Repository

1. Set `CWD` in `.env` to the target repo path
2. Write `factory/prompt/user_prompt.md` with task spec for that repo (see §3)
3. Adjust `REQUIREMENTS & CONSTRAINTS` — writable paths, conventions, etc.
4. Set `scope` to the relevant files (bypasses hardcoded `src2/` tree)
5. Run `./run.sh`

### Example: repair baziforecaster from factory

```env
CWD=/home/yapilwsl/arthityap/baziforecaster
```

`user_prompt.md` frontmatter:
```yaml
scope:
  - src2/engine/module3_interaction.py
  - src2/engine/module11_probability.py
  - src2/engine/shen_classifier.py
```

---

## 7. Verification

```bash
# Lint
uv run ruff check factory/ tests/

# Tests
PYTHONPATH=. uv run pytest tests/
```

---

## 8. Known Gaps

| Gap | Location | Impact | Workaround |
|-----|----------|--------|------------|
| `_py_tree()` hardcodes `src2/` + `tests/` | `ledger.py:52` | Non-`src2/` targets get empty context | Use `scope` in prompt frontmatter |
| `user_prompt.md` has stale baziforecaster paths | `prompt/user_prompt.md` | Planner sees wrong writable constraints | Manually update per target (see §3) |
| Self-hosting untested | N/A | Unknown failure modes | Try with `start_phase: planner, stop_phase: supervisor_plan` in prompt frontmatter first |
