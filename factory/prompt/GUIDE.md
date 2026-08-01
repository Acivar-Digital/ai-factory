# AI-Factory Operator Guide

**Audience**: AI agents and human operators setting up and running the factory or generating `user_prompt.md`.
**Outcome**: You know exactly how to structure prompt specs, select model tiers, and execute the multi-agent pipeline.

---

## 1. What Is AI-Factory?

An autonomous multi-agent coding framework. You provide a task spec (`user_prompt.md`)
and point it at a target repo. The system coordinates execution via a 3-Tier Code Review Pipeline:

```
Intern Builder (intern_model: ling_flash)
  ↓
Engineer (engineer_model: gemini_3_6_flash_high)
  ↓
Senior Principal Engineer (senior_model: gemini_3_1_pro_high)
```

Each tier is powered by a specialized Pydantic-AI agent with strict output schemas. The runner
(`factory/infra/runner.py`) is a deterministic Python conductor — no LLM orchestrator.

---

## 2. Model Control Sheet Wiring (`factory/infra/control.py`)

| Tier / Role | Model Key | Model ID / Provider | Role & Responsibility |
|:---|:---|:---|:---|
| **Intern** | `intern_model` | `ling_flash` (`openrouter/inclusionai/ling-3.0-flash:free`) | Initial code creation & single-file task implementation. |
| **Engineer** | `engineer_model` | `gemini_3_6_flash_high` (`gemini-3.6-flash-high`) | AST verification, inline pyright/ruff lint fixes, and structural refactoring. |
| **Senior** | `senior_model` | `gemini_3_1_pro_high` (`gemini-pro-agent`) | Final security & quality audit gate, AST contract verification, production deployment. |

---

## 3. Architecture in 30 Seconds

| Concept | What | Config Location |
|---------|------|-----------------|
| **Factory repo** | The code running the agents — this repo (`ai-factory`) | Cloned workspace |
| **Target repo** | The codebase being repaired or developed | `CWD` in `factory/infra/.env` |
| **PKG_DIR** | Factory's internal package root | Hardcoded (`ai-factory/factory`) |
| **REPO_ROOT** | Target repo root directory | Read from `CWD` |
| **TEMP_DIR** | Scratch buffer for staged writes | `factory/temp/` |

---

## 4. How to Write a Valid `user_prompt.md`

To generate a valid `user_prompt.md` file for the factory, adhere to this structure:

### A. Required Frontmatter (YAML)
```yaml
---
Resume: false
bd: ticket-id-123
write_mode: staged        # "staged" (safer) or "direct" (in-place)
language: python          # python, typescript, rust, etc.
lint_command: "uv run ruff check"
start_phase: intern       # intern | engineer | senior | planner | coder
stop_phase: senior        # intern | engineer | senior | ops
scope:
  - path/to/file1.py
  - path/to/file2.py
---
```

### B. Standard Markdown Body
```markdown
# EPIC
One-line summary statement of the task.

## CONTEXT
Background information, root cause analysis, or motivation.

## DELIVERABLES
1. Concrete, file:line-anchored code modifications.
2. Itemized list of specific function/module updates.

## REQUIREMENTS & CONSTRAINTS
- Strict Pydantic v2 domain models; zero bare dicts for logic.
- AST comment-preserving edits (do not strip existing docstrings).
- Surgical edits only; no unrequested architectural refactoring.
- Fail loudly on errors; no silent exception swallowing.

## ANTI-PATTERNS (CRITICAL)
- Do NOT use `except: pass` or ignore diagnostic errors.
- Do NOT edit files outside the specified `scope`.

## ACCEPTANCE
1. Passes 7-layer AST verification and `uv run ruff check <file>`.
2. All target unit tests pass without regression.
```

---

## 5. Setup & Execution Workflow

### Step 1: Configure Target Environment
Create `factory/infra/.env`:
```env
CWD="/abs/path/to/target/repo"
```

### Step 2: Save Prompt Spec
Write your task spec to `factory/prompt/user_prompt.md`.

### Step 3: Run the Orchestrator
```bash
./run.sh
```

---

## 6. Files Reference

| File | Purpose |
|------|---------|
| `factory/infra/.env` | Target `CWD` + gateway API definitions |
| `factory/prompt/user_prompt.md` | Active task specification |
| `factory/prompt/user_prompt_template.md` | Reference cheat-sheet template |
| `factory/prompt/GUIDE.md` | Master operator guide & LLM prompt instructions |
| `factory/infra/agents/*.yaml` | Agent YAML specifications (`intern.yaml`, `engineer.yaml`, `senior.yaml`) |
| `factory/infra/control.py` | Model mappings (`CONTROL_SHEET`) & runtime paths |
| `factory/STATUS.md` | Real-time orchestrator progress board |
