# AI-Factory Operator Guide

**Audience**: AI agents and human operators setting up and running the factory.
**Outcome**: You know exactly what to do — from cloning to a completed multi-agent run.

---

## 1. What Is AI-Factory?

An autonomous multi-agent coding framework. You give it a task spec (`user_prompt.md`)
and point it at a target repo. It orchestrates a deterministic pipeline:

```
Planner → Supervisor_Plan → Planner → Supervisor_Plan → Planner
  ↓
Coder → Supervisor_Review → Coder → Supervisor_Review → Coder
  ↓
Red_Team → Coder → Red_Team → Coder
  ↓
Ops (git push)
```

Each role is a Pydantic-AI agent with structured output. No LLM orchestrator —
the runner (`factory/infra/runner.py`) is a deterministic conductor.

---

## 2. Architecture in 30 Seconds

| Concept | What | Config |
|---------|------|--------|
| **Factory repo** | The code that runs the agents — this repo (`ai-factory`) | Cloned once |
| **Target repo** | The codebase being repaired | `CWD` in `.env` |
| **PKG_DIR** | Factory's own package | Hardcoded (always factory repo) |
| **REPO_ROOT** | Target repo root | = `CWD` from `.env` |
| **TEMP_DIR** | Writable scratch area inside factory | `PKG_DIR / "temp"` |

**No symlinks needed.** All tools run `uv run` from factory's package but
operate on `REPO_ROOT` via `cwd`.

---

## 3. Setup Workflow

### Step 1: Configure the target

```bash
cd /path/to/ai-factory
```

Create `factory/infra/.env`:
```env
CWD="/abs/path/to/target/repo"
```

### Step 2: Write the task spec

Edit `factory/prompt/user_prompt.md`:

```yaml
---
Resume: false
bd: my-ticket-id
write_mode: direct        # "direct" or "staged"
language: python          # project language hint
lint_command: "uv run ruff check"
scope:
  - src/foo.py
  - src/bar.py
---
# EPIC
...
```

**Critical**: Always set `scope` if the target doesn't use `src2/` paths
(the auto-context tree hardcodes `src2/` + `tests/` — see `ledger.py:52`).

**Choose write_mode**:
- `direct` — tools edit target files in-place. Faster, riskier.
- `staged` — files copied to `TEMP_DIR` first, edits applied at end. Safer.

### Step 3: Run

```bash
# Run the pipeline
./run.sh
```

> **Phase segmentation**: Set `start_phase` and `stop_phase` in the prompt frontmatter to run only part of the pipeline. Example: `start_phase: planner, stop_phase: supervisor_plan` runs planning only, then exits. Review the plan, then edit the prompt to `start_phase: coder, stop_phase: coder` and re-run.

---

## 4. What the Agents See

Each agent receives a brief built from:

1. **Role YAML** (`factory/templates/<role>.yaml`) — skill definition, tool list
2. **Markdown body** of `user_prompt.md` — the task spec (EPIC, CONTEXT, DELIVERABLES, etc.)
3. **Scope context** — file tree + symbols from the target repo's `scope` paths
4. **Prior phase summaries** — what previous roles concluded
5. **Phase summaries** — if `Resume: true`, prior exchange history

Agents do NOT see the YAML frontmatter — that's machine-parsed by the runner.

---

## 5. Language & Tooling

The factory's shadow tools work on any text-based project:

| Tool | Works on | File type |
|------|----------|-----------|
| `search.py` | Any language | Text |
| `investigate.py` | Any language | Text |
| `read_file.py` | Any language | Any |
| `write_file.py` | Any language | Any |
| `replace_text.py` | Any language | Text (string match) |
| `replace_function.py` | Python only | `.py` (AST) |
| `add_import.py` | Python only | `.py` |

For non-Python projects, use `replace_text.py` instead of AST tools.
Set `lint_command` in frontmatter to match your project (e.g., `biome check`
for TypeScript, `cargo check` for Rust).

---

## 6. Common Operations

### Repair a Python repo (e.g., baziforecaster)

```env
CWD=/home/user/baziforecaster
```

```yaml
write_mode: staged
language: python
scope:
  - src2/engine/
```

### Self-host (repair factory itself)

```env
CWD=/home/user/ai-factory
```

```yaml
write_mode: direct
language: python
scope:
  - factory/infra/
  - factory/common/
  - tests/
```

### Build a Bun project

```env
CWD=/home/user/bun-app
```

```yaml
write_mode: direct
language: typescript
lint_command: biome check
scope:
  - src/routes/
```

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Planner says "no .py sources found" | `_py_tree()` walks `src2/` which doesn't exist | Add `scope` to frontmatter |
| Agent writes to wrong paths | Stale writable constraints in prompt | Update `REQUIREMENTS & CONSTRAINTS` in `user_prompt.md` |
| Tool fails with "path outside REPO_ROOT" | Write path escapes `CWD` | Ensure file paths are relative to target repo root |
| `uv run` fails | Factory's `pyproject.toml` deps not installed | `uv sync` in factory repo |
| Runner halts mid-pipeline | Model timeout or malformed output | Re-run `./run.sh` to resume |
| Red Team blocks changes | Security audit found violations | Read the Red Team report, fix issues, re-run |

---

## 8. Files Reference

| File | Purpose |
|------|---------|
| `factory/infra/.env` | Target CWD + model gateway config |
| `factory/prompt/user_prompt.md` | **The task spec** — edit this per run |
| `factory/prompt/user_prompt_template.md` | Reference template for frontmatter schema |
| `factory/templates/*.yaml` | Role YAMLs (planner, coder, red_team, etc.) |
| `factory/infra/control.py` | Path config, gateway settings, SKILL_MAP |
| `factory/infra/runner.py` | Deterministic conductor (3500+ lines) |
| `factory/infra/ledger.py` | Repo-map injection (`_py_tree()`) |
| `factory/common/subprocess.py` | Tool execution wrapper |
| `docs/configure.md` | Full configuration reference |
| `run.sh` | Entrypoint script (replaces `start.sh` / `continue.sh`) |
