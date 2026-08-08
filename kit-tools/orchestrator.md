# kit-tools portability refactor — orchestrator brief
**IF YOU ARE THE ORCHESTRATOR (the LLM that read this file):**
- **DO NOT EDIT FILES YOURSELF. DO NOT "INVESTIGATE" OR "THINK" IN LOOPS.**
- **You ONLY spawn 3 subagents in a single turn** (parallel). Each subagent gets the EXACT pinned prompt in Section 3. No decisions are permitted. No extra reading is permitted. Each subagent reports exactly one line; you pass it through unchanged.
- Canonical env names (SET ONCE — never write `QDRANT_URL`, `BGEM3_*`, `COLLECTION_NAME`, `FLATTEN_SCOPE`, `MCP_NAME`, `REPORT_PROGRESS_CHANNEL_ID`, `DEVELOPER_CHAT_ID`, `src2`, `baziforecaster` elsewhere in kit-tools):
  `KIT_TARGET_ROOT`, `KIT_COLLECTION_NAME`, `KIT_QDRANT_URL`, `KIT_EMBEDDING_URL`, `KIT_EMBEDDING_TOKEN`,
  `KIT_CODEBASE_MODEL`, `KIT_WEB_MODEL`, `KIT_SOURCE_ROOT`, `KIT_MCP_NAME`, `KIT_INFRA_ROOT`,
  `KIT_REPORT_CHANNEL_ID`, `KIT_DEV_CHAT_ID`.
- Live-source invariant: edit ONLY under `kit-tools/`. Touch nothing else.
- Fail-loud: missing required env at import → `RuntimeError` naming the var.
- Standard third-party env names are KEPT as-is: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_BASE`, `EXA_API_KEY`, `TAVILY_API_KEY`, `SEARXNG_URL`, `PYTHON_DEPS`.

---

## 1. Canonical contract (`kit-tools/.env.example`)
**EDIT IN PLACE — create new.** All project-specific names become `KIT_*` (see list above).
Keep standard third-party keys (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_BASE`,
`EXA_API_KEY`, `TAVILY_API_KEY`, `SEARXNG_URL`) unchanged.

The `.env.example` must contain these sections in order:

```env
# === kit-tools — user-downloads / configure-and-run contract ===
# Install:  cp kit-tools/.env.example kit-tools/.env   (then EDIT; .env is NOT version-controlled)
# Run:      uv run python kit-tools/<tool>.py "args"
#           OR                          web.sh "query"   (web tool convenience launcher)

# --- Paths (fail-fast: tool exits non-zero if KIT_TARGET_ROOT is missing) ---
KIT_TARGET_ROOT=<path-to-target-repository>   # The repo to scan/operate on (replaces REPO_ROOT + hardcoded baziforecaster paths)
KIT_INFRA_ROOT=<path-to-infra-codebase>       # Location of infra/codebase modules (replaces hardcoded /home/.../infra/codebase)

# --- Vector DB & embedding ---
KIT_COLLECTION_NAME=codebase_index             # Qdrant collection name (was: baziforecaster_code)
KIT_QDRANT_URL=http://localhost:6333           # Qdrant vector search URL (was: bare QDRANT_URL)
KIT_EMBEDDING_URL=http://localhost:8002        # BGE-M3 embedding endpoint (was: bare BGEM3_URL)
KIT_EMBEDDING_TOKEN=                           # embedding API token (was: bare BGEM3_TOKEN)

# --- LLM models ---
KIT_CODEBASE_MODEL=gemma-4-31b-it              # model for search/investigate agents (was: CONTROL_SHEET.codebase_model)
KIT_WEB_MODEL=gemma-4-31b-it                   # model for web orchestrator (was: CONTROL_SHEET.web_model)

# --- Source tree configuration ---
KIT_SOURCE_ROOT=src                            # source directory marker (was: src2); tools scan for this subpath
KIT_MCP_NAME=kit-tools                         # FastMCP server name (was: git-guardrail)

# --- Telegram notifications (optional) ---
TELEGRAM_BOT_TOKEN=                            # Telegram bot token (standard env, unchanged)
TELEGRAM_API_BASE=https://api.telegram.org     # Telegram API base URL (standard env, unchanged)
KIT_REPORT_CHANNEL_ID=                         # Telegram channel for progress reports (was: REPORT_PROGRESS_CHANNEL_ID)
KIT_DEV_CHAT_ID=                               # Telegram dev chat ID for critical alerts (was: DEVELOPER_CHAT_ID)

# --- Search provider keys (optional, standard env names kept) ---
EXA_API_KEY=                                   # Exa search API key (used by web.py)
TAVILY_API_KEY=                                # Tavily search API key (used by web.py)
SEARXNG_URL=                                   # SearXNG instance URL (used by web.py)

# --- Portable tool runtime (Option A: install list. Leave empty to use the vendored no-dep loader) ---
PYTHON_DEPS=python-dotenv,pydantic-ai,httpx,qdrant-client,numpy,trafilatura,pyyaml,fastmcp
```

---

## 2. Source files (what each subagent touches — pinned, no ambiguity)

**control.py** (NEW) — full content specified in subagent S2's prompt below.
Provides `REPO_ROOT`, `ControlSheet` (with `codebase_model`, `web_model`), and `SystemSettings`
(with `exa_api_key`, `tavily_api_key`, `searxng_url`) read from `KIT_*` / standard env vars.
Fail-loud: if `KIT_TARGET_ROOT` is unset at import → `RuntimeError`.

**`.env.example`** (NEW) — content specified in subagent S1's prompt above.

**Files patched by S3** — the 18 files below. Each receives a pinned line-level diff.

### 2a. Coupled tools (was `admin.*` / `TEST.*` / `infra.*` imports)

| file | current coupling | new |
|---|---|---|
| `search.py` | L17 `parents[2]`, L18 `load_dotenv`, L23 `from admin.controls.controls import CONTROL_SHEET`, L29-32 bare env vars, L52 `CONTROL_SHEET.codebase_model` | L17 `parents[1]`, L23 `from control import ControlSheet`, L29-32 `KIT_*` env vars (via `control.py`), L52 `ControlSheet.codebase_model` |
| `web.py` | L13 `from admin.controls.controls import CONTROL_SHEET, settings`, L128 `CONTROL_SHEET.web_model`, L56/77/105 `settings.*` | L13 `from control import ControlSheet, SystemSettings`, use `SystemSettings.*` for exa/tavily/searxng |
| `investigate.py` | L8 `parents[2]`, L13 `from admin.controls.controls import CONTROL_SHEET, REPO_ROOT`, L73/80/81 `REPO_ROOT`, L122 `CONTROL_SHEET.codebase_model` | L8 `parents[1]`, L13 `from control import ControlSheet, REPO_ROOT`, L52 `ControlSheet.codebase_model` |
| `mcp_git_guardrail.py` | L8 `parents[2]`, L13 `from TEST.agent_guardrail import checkpoint, validate`, L15 `os.getenv("MCP_NAME", "git-guardrail")` | L8 `parents[1]`, L13 `from guardrail_check import checkpoint, validate`, L15 `KIT_MCP_NAME` |
| `_test_tools.py` | L7 `parents[2]`, L11 `from admin.tools.mcp_git_guardrail import mcp`, L65 `BaziForecaster ...`, L26 `/tools/` path | L7 `parents[1]`, L11 `from mcp_git_guardrail import mcp`, L65 generic string, L26 `kit-tools/` path |
| `index_repository.py` | L6-7 `parents[3]` + hardcoded `/home/.../infra/codebase`, L9 `from infra.codebase.mcp_codebase import index_repository` | L6 `parents[1]`, L7 `KIT_INFRA_ROOT` env, L9 local `from _infra_codebase import index_repository` shim |
| `query_knowledge_graph.py` | L6-7 `parents[3]` + hardcoded `/home/.../infra/codebase`, L9 `from infra.codebase.mcp_codebase import query_knowledge_graph` | same pattern as index_repository.py |
| `graph_health.py` | L6-7 `parents[3]` + hardcoded `/home/.../infra/codebase`, L9 `from infra.codebase.mcp_codebase import graph_health` | same pattern |
| `verify_file_path.py` | same coupling | same pattern |

### 2b. Hardcoded paths / env var defaults / comment cleanup

| file | current | new |
|---|---|---|
| `_fix_preprocess2.py` | L3: `/home/yapilwsl/arthityap/baziforecaster/src2/interfaces/telegram/utils.py` | `KIT_TARGET_ROOT` + `KIT_SOURCE_ROOT` |
| `flatten_scripts_agents.py` | L37: `os.environ.get("FLATTEN_SCOPE", "src2")` | `os.environ.get("KIT_SOURCE_ROOT", "src")` |
| `load_schema_gate.py` | L16: `repo_root / "admin" / "orchestrator" / "temp"` | `Path(os.getenv("KIT_TEMP_DIR", str(repo_root / "temp")))` |
| `smoke_test.py` | L42: `# baziforecaster/`, L213: `str(PROJECT_ROOT / "src2")` | `KIT_TARGET_ROOT`, `KDB_SOURCE_ROOT` |
| `guardrail_check.py` | L45: `# baziforecaster/`, L379: `src2`/`src` markers, L430: `PROJECT_ROOT / "src2"` | `KIT_TARGET_ROOT` |
| `web.sh` | comments `/tools/` | `kit-tools/` |
| `web.py` | L336: `/tools/web.py` usage string | `kit-tools/web.py` |

### 2c. Test suite (path + repo name cleanup)

| file | current | new |
|---|---|---|
| `test/run_all.py` | L7: `/tools/test/` | `Path(__file__).parent / script_name` |
| `test/test_discovery.py` | L6: `/tools/`, L42: `/tools/read_file.py` | relative paths |
| `test/test_modifications.py` | L9: `/tools/` | relative paths |
| `test/test_knowledge.py` | L6: `/tools/` | relative paths |
| `test/test_indexing.py` | L19: `"baziforecaster"` repo name | `os.getenv("KIT_COLLECTION_NAME", "codebase_index")` or `KIT_TARGET_ROOT.name` |

### 2d. Non-portable (known coupled — document but do NOT force-portable)

`rewrite_mod6.py`, `restore_missing_unified2.py`, `update_scoring_output.py`,
`update_scoring_output2.py`, `_gen_utils.py`, `fix_midfile_imports.py` — these
import `src2.*` or hardcode `src2/` paths. They are **baziforecaster-bazi-engine-specific**
and remain out-of-scope (see §6). `_gen_utils.py` env vars (`TELEGRAM_*`, `REPORT_PROGRESS_CHANNEL_ID`,
`DEVELOPER_CHAT_ID`) ARE renamed to `KIT_*` where custom; `TELEGRAM_BOT_TOKEN`/`TELEGRAM_API_BASE`
kept.

---

## 3. Three pinned subagent prompts (copy verbatim; deploy all 3 at once)

### S1 — create `kit-tools/.env.example`
```
You are S1. Create kit-tools/.env.example with the EXACT content from brief §1
(Paths → Vector DB → LLM models → Source tree → Telegram → Search providers → PYTHON_DEPS).
Copy every line verbatim — do not reorder, do not add/remove keys.
Then run:
  grep -nE "KIT_|TELEGRAM_|EXA_API_KEY|TAVILY_API_KEY|SEARXNG_URL|PYTHON_DEPS" kit-tools/.env.example | wc -l
  grep -c "baziforecaster\|src2\|ANTIGRAVITY" kit-tools/.env.example
and report EXACTLY one line: "S1 OK: <count>=21 baziforecaster=0 src2=0".
Never mention other files.
```

### S2 — create `kit-tools/control.py` (NEW, fail-loud shim)
```
You are S2. Create kit-tools/control.py with this EXACT body (no edits, no additions):

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

TARGET_ROOT = os.getenv("KIT_TARGET_ROOT")
if not TARGET_ROOT:
    raise RuntimeError("KIT_TARGET_ROOT is required — set it in kit-tools/.env to your target repository path.")
REPO_ROOT = Path(TARGET_ROOT).resolve()

INFRA_ROOT = os.getenv("KIT_INFRA_ROOT")

_source_root = os.getenv("KIT_SOURCE_ROOT", "src")


def _Model(name):
    return type("M", (), {"model_name": name})


class ControlSheet:
    codebase_model = _Model(os.getenv("KIT_CODEBASE_MODEL", ""))
    web_model = _Model(os.getenv("KIT_WEB_MODEL", ""))


class SystemSettings:
    exa_api_key = os.getenv("EXA_API_KEY", "")
    tavily_api_key = os.getenv("TAVILY_API_KEY", "")
    searxng_url = os.getenv("SEARXNG_URL", "https://searxng.com")


class Settings:
    report_channel_id = os.getenv("KIT_REPORT_CHANNEL_ID")
    dev_chat_id = os.getenv("KIT_DEV_CHAT_ID")
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_api_base = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")


if __name__ == "__main__":
    print(f"REPO_ROOT={REPO_ROOT}")
    print(f"ControlSheet.codebase_model.model_name={ControlSheet.codebase_model.model_name}")
    print(f"SystemSettings.exa_api_key={SystemSettings.exa_api_key!r}")

Then run from kit-tools/:
  KIT_TARGET_ROOT=/tmp python3 -c "import control; print('S2 ok')"
  python3 -c "import control" 2>&1 | grep -o "KIT_TARGET_ROOT is required"
  uv run ruff check kit-tools/control.py --select E9,F63,F7,F82 --no-cache
report EXACTLY: "S2 OK: ok missing-fail ruff-green".
```

### S3 — patch all 18 customised files (imports + env vars + hardcoded paths)
```
You are S3. Two groups of files ONLY. Do NOT touch control.py, .env.example, or anything else.

(A) The 5 agent-config tools — replace admin.*/TEST.*/infra.* imports + env vars with control.py shim:

  search.py:
    - L17:  PROJECT_ROOT = Path(__file__).resolve().parents[2]
    -          -> parents[1]
    - L18:  load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
    -          -> delete (control.py handles .env)
    - L23:  from admin.controls.controls import CONTROL_SHEET
    -          -> from control import ControlSheet
    - L25-27: INFRA_ROOT, GRAPH_JSON, DIRECTIVES_DB
    -          -> use KIT_INFRA_ROOT env var
    - L29-32: QDRANT_URL/BGEM3_URL/BGEM3_TOKEN/COLLECTION_NAME = os.environ[...]
    -          -> read via os.getenv("KIT_QDRANT_URL", ...) etc., default COLLECTION_NAME to "codebase_index"
    - L52:  model = CONTROL_SHEET.codebase_model
    -          -> model = ControlSheet.codebase_model
    - L20-21: remove sys.path.insert (no longer needed)

  web.py:
    - L13:  from admin.controls.controls import CONTROL_SHEET, settings
    -          -> from control import ControlSheet, SystemSettings
    - L56:  settings.exa_api_key -> SystemSettings.exa_api_key
    - L77:  settings.tavily_api_key -> SystemSettings.tavily_api_key
    - L105: settings.searxng_url -> SystemSettings.searxng_url
    - L128: self.model = CONTROL_SHEET.web_model -> ControlSheet.web_model
    - L336: print('/tools/web.py') -> 'kit-tools/web.py'

  investigate.py:
    - L8:   WORKSPACE_ROOT = Path(__file__).resolve().parents[2] -> parents[1]
    - L13:  from admin.controls.controls import CONTROL_SHEET, REPO_ROOT
    -          -> from control import ControlSheet, REPO_ROOT
    - L122: getattr(CONTROL_SHEET, "codebase_model") -> ControlSheet.codebase_model

  mcp_git_guardrail.py:
    - L8:   WORKSPACE_ROOT = Path(__file__).resolve().parents[2] -> parents[1]
    - L13:  from TEST.agent_guardrail import checkpoint, validate
    -          -> from guardrail_check import checkpoint, validate
    - L15:  os.getenv("MCP_NAME", "git-guardrail") -> os.getenv("KIT_MCP_NAME", "kit-tools")

  _test_tools.py:
    - L7:   WORKSPACE_ROOT = Path(__file__).resolve().parents[2] -> parents[1]
    - L11:  from admin.tools.mcp_git_guardrail import mcp -> from mcp_git_guardrail import mcp
    - L26:  "/tools/investigate.py" -> str(WORKSPACE_ROOT / "kit-tools" / "investigate.py")
    - L65:  "BaziForecaster Codebase Tools Integration Tests" -> "kit-tools Integration Tests"

(B) The env-var default + hardcoded-path tools:

  flatten_scripts_agents.py:
    - L37: DEFAULT_SCOPE = os.environ.get("FLATTEN_SCOPE", "src2")
    -          -> os.environ.get("KIT_SOURCE_ROOT", "src")

  _fix_preprocess2.py:
    - L3:  f = "/home/yapilwsl/arthityap/baziforecaster/src2/.../utils.py"
    -          -> f = str(Path(os.getenv("KIT_TARGET_ROOT")) / os.getenv("KIT_SOURCE_ROOT", "src") / "interfaces/telegram/utils.py")
    -          add: import os; from pathlib import Path

  load_schema_gate.py:
    - L15: repo_root = Path(__file__).resolve().parent.parent.parent
    -          -> from control import REPO_ROOT; repo_root = REPO_ROOT
    - L16: temp_dir = repo_root / "admin" / "orchestrator" / "temp"
    -          -> temp_dir = repo_root / os.getenv("KIT_TEMP_DIR", "temp")
    -          add: import os at top

  web.sh:
    - L2:  comment "two levels up from /tools/" -> "two levels up from kit-tools/"

  smoke_test.py:
    - L42: comment "baziforecaster/" -> generic
    - L160: markers ("/src2/", "/src/") -> ("/" + KIT_SOURCE_ROOT + "/", "/src/")  -- use os.getenv
    - L160-163: for marker in ("/src2/", "/src/"): -> for marker in ("/" + source_root + "/", "/src/":) where source_root = os.getenv("KIT_SOURCE_ROOT", "src")
    - L184-188: same marker pattern
    - L213: str(PROJECT_ROOT / "src2") -> str(REPO_ROOT / os.getenv("KIT_SOURCE_ROOT", "src"))

  guardrail_check.py:
    - L44-45: SCRIPT_DIR + PROJECT_ROOT comments (remove "baziforecaster/")
    - L379: for marker in ("/src2/", "/src/"): -> for marker in ("/" + source_root + "/", "/src/" where source_root = os.getenv("KIT_SOURCE_ROOT", "src")
    - L430: real_src2 = PROJECT_ROOT / "src2" -> real_src = PROJECT_ROOT / os.getenv("KIT_SOURCE_ROOT", "src")

(C) The 5 test files:

  test/run_all.py:
    - L7: f"/tools/test/{script_name}.py" -> str(Path(__file__).parent / f"{script_name}.py")

  test/test_discovery.py:
    - L6: f"/tools/{args[0]}.py" -> str(Path(__file__).parents[1] / f"{args[0]}.py")
    - L42: "/tools/read_file.py" -> str(Path(__file__).parents[1] / "read_file.py")

  test/test_modifications.py:
    - L9: f"/tools/{args[0]}.py" -> str(Path(__file__).parents[1] / f"{args[0]}.py")

  test/test_knowledge.py:
    - L6: f"/tools/{args[0]}.py" -> str(Path(__file__).parents[1] / f"{args[0]}.py")

  test/test_indexing.py:
    - L19: res = run_tool(["index_repository", "baziforecaster"])
    -          -> res = run_tool(["index_repository", os.getenv("KIT_TARGET_ROOT_NAME", "codebase")])

(D) The 5 non-portable baziforecaster-bazi-engine tools — ONLY rename env vars + comments, do NOT make portable:

  _gen_utils.py:
    - L262,376: os.environ["TELEGRAM_API_BASE"] -> add default: os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org") (no KeyError)
    - L406: os.getenv("REPORT_PROGRESS_CHANNEL_ID") -> os.getenv("KIT_REPORT_CHANNEL_ID")
    - L410: os.getenv("DEVELOPER_CHAT_ID") -> os.getenv("KIT_DEV_CHAT_ID")
    (TELEGRAM_BOT_TOKEN kept as-is — standard env name)

  _test_tools.py already handled in (A).

Then run:
  grep -rn "from admin\.\|from TEST\.\|from infra\.codebase" kit-tools/ --include=*.py | grep -v __pycache__
  grep -rn "baziforecaster_code\|ANTIGRAVITY_MANAGER\|git-guardrail" kit-tools/ --include=*.py --include=*.env.example | grep -v __pycache__
  grep -rn "/tools/" kit-tools/ --include=*.py --include=*.sh | grep -v __pycache__ | grep -v "kit-tools"
  grep -rn "'/tools/\"kit-tools" kit-tools/ --include=*.py | grep -v __pycache__
  uv run ruff check kit-tools/control.py kit-tools/search.py kit-tools/web.py kit-tools/investigate.py kit-tools/mcp_git_guardrail.py kit-tools/_test_tools.py kit-tools/flatten_scripts_agents.py kit-tools/_fix_preprocess2.py kit-tools/load_schema_gate.py kit-tools/smoke_test.py kit-tools/guardrail_check.py kit-tools/_gen_utils.py kit-tools/test/ --select E9,F63,F7,F82 --no-cache
report EXACTLY: "S3 OK: admin=0 TEST=0 infra=0 baziforecaster_code=0 git-guardrail=0 /tools/=0 ruff-green".
(grep for /tools/ must show zero results; the grep command itself may show /tools/ in its own output but that's the grep tool, not source.)
```

---

## 4. Master Final Gate (orchestrator runs once S1/S2/S3 report)
```bash
grep -rn "from admin\.\|from TEST\.\|from infra\.codebase" kit-tools/ --include=*.py | grep -v __pycache__ || echo "OK: no admin.*/TEST.*/infra.codebase coupling"
grep -rn "baziforecaster_code\|ANTIGRAVITY_MANAGER\|git-guardrail" kit-tools/ --include=*.py --include=*.env.example | grep -v __pycache__ || echo "OK: no baziforecaster_code / ANTIGRAVITY / git-guardrail literals"
grep -rn '"/tools/' kit-tools/ --include=*.py --include=*.sh | grep -v __pycache__ || echo "OK: no /tools/ hardcoded paths"
grep -rn "os\.environ\[.QDRANT_URL.\]|os\.environ\[.BGEM3_URL.\]\|os\.environ\[.BGEM3_TOKEN.\]" kit-tools/ --include=*.py | grep -v __pycache__ || echo "OK: no bare QDRANT_URL/BGEM3_* env lookups"
grep -rn "REPORT_PROGRESS_CHANNEL_ID\|DEVELOPER_CHAT_ID" kit-tools/ --include=*.py | grep -v __pycache__ || echo "OK: no bare report/dev channel env names"
grep -rn "/home/yapilwsl/arthityap/baziforecaster" kit-tools/ --include=*.py | grep -v __pycache__ || echo "OK: no hardcoded baziforecaster paths"
uv run ruff check kit-tools/ --select E9,F63,F7,F82 --no-cache
```
SHIP when all print `OK` / green. Otherwise `ESCALATE` (report the failing gate, do not patch).

---

## 5. Runtime contract for end users

After S1/S2/S3 ship, a user downloads `kit-tools/`, copies `.env.example` → `.env`,
fills in `KIT_TARGET_ROOT` (and whichever services they use), and runs:

```bash
cd /path/to/kit-tools
uv venv
uv pip install -r <PYTHON_DEPS from .env>
# or: pip install python-dotenv pydantic-ai httpx qdrant-client numpy trafilatura pyyaml fastmcp
python control.py                          # verify config loads
uv run python search.py "how does Foo work?"    # semantic search on target repo
uv run python investigate.py --filename src/main.py --query "any issues?"
uv run python web.py "latest ai news"           # web search + synthesize
```

No edits to source files are required — everything flows from `.env`.

---

## 6. Known out-of-scope (do NOT touch this pass)

The 5 baziforecaster-bazi-engine-specific tools still carry `src2.*` imports or hardcoded
`src2/` write paths: `rewrite_mod6.py`, `rewrite_mod12.py`, `restore_missing_unified.py`,
`restore_missing_unified2.py`, `update_scoring_output.py`, `update_scoring_output2.py`,
`fix_midfile_imports.py`. They remain PORTABILITY_REVIEW risk; not in S1/S2/S3 scope.
Only their env-var names (if any) are renamed where trivial. `_gen_utils.py` is a stale
generator script (ends with `print("ERROR: ...")`) — env vars renamed in (D) only.
