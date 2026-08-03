# Codebase Indexing Setup Plan for `baziforecaster`

Goal: Stand up the baziforecaster codebase-indexing stack (Qdrant vector search +
SQLite KG + BGE-M3 embeddings) so that AI-Factory's `factory/tools/search.py` and
`factory/tools/investigate.py` discovery tools can query the baziforecaster repo.

---

## VERIFIED STATUS (checked live)

| Component | State | Details |
|---|---|---|
| Qdrant | **UP** (`localhost:6333`) | `healthz` → "healthz check passed" |
| `baziforecaster_code` collection | **ACTIVE (8357 points)** | 8291 indexed vectors, 1024-dim, Cosine, green |
| `daemon.py` watcher | **RUNNING** (PID 13668) | Auto-indexes `baziforecaster/src2/` → on every file save |
| BGE-M3 embeddings | **UP** (port 8002) | `text-embeddings-router --model-id BAAI/bge-m3` |
| KG graph | **exists** | `/home/yapilwsl/arthityap/infra/graph/code_knowledge_graph.json` |

> The daemon already indexes `baziforecaster` into `baziforecaster_code`.
> **No manual `--reset` needed** — file-watching keeps it fresh.

---

## Architecture (verified)

```
~/arthityap/
├── infra/
│   ├── codebase/                ← shared indexer layer
│   │   ├── config.py            ← QDRANT_URL, BGEM3_*, WATCHED_REPOS, DUAL_COLLECTION_REPOS
│   │   ├── daemon.py            ← FileSystemEventHandler — watches repos, auto-indexes
│   │   ├── indexer.py           ← index_repository(), embed_with_retry(), PointStruct pipeline
│   │   └── .env                 ← OPENROUTER_API_KEY, BGEM3_URL=..., BGEM3_TOKEN=''
│   ├── graph/code_knowledge_graph.json
│   └── .ctx/agents_graph.db     ← SQLite directives table
├── baziforecaster/
│   ├── .env                     ← QDRANT_URL, (BGEM3 inherited from infra)
│   ├── admin/tools/search.py    ← existing local CLI (QDRANT_URL from .env)
│   ├── admin/tools/investigate.py
│   ├── admin/tools/index_repository.py  ← thin wrapper: index_repository(repo_name, ...)
│   ├── admin/controls/controls.py ← SystemSettings (CONTROL_SHEET.codebase_model)
│   └── src2/                    ← active code root (core, engine, interfaces, worker)
└── ai-factory/
    └── docs/codebase.md         ← this file
```

### Collection naming (`config.py: get_collection_name`)

| Repo | Is dual-collection? | Code collection | Docs collection |
|---|---|---|---|
| `baziforecaster` | **YES** | `baziforecaster_code` ✅ (8357 pts) | `baziforecaster_docs` ❌ (not seeded) |
| `flourishME` | YES | `flourishME_code` | `flourishME_docs` |
| `ats` | YES | `ats_code` | `ats_docs` |
| other repos | no (single) | `<repo_name>` | — |

`DUAL_COLLECTION_REPOS = ["baziforecaster", "ats", "flourishME"]` (config.py:125)
`WATCHED_REPOS = ["baziforecaster", "flourishME", "literouter"]` (config.py:143)

---

## Decision: New collection or reuse?

User explicitly said: **"it should be a new collection like flourishme and baziforecaster"**

✅ **VERIFIED:** `baziforecaster_code` already exists and is auto-maintained. This **is** the kimi-cli-style split collection naming (`repo_code`).

- ✅ Code collection: `baziforecaster_code` (8357 points, indexed)
- ❌ Docs collection: `baziforecaster_docs` (NOT created — `get_allowed_extensions` gates `.md` into docs-only, but no `index_single_file` run for docs yet)

## Decision: New port?

User said: **"i dun want to run another stupid port"**

✅ **VERIFIED:** No new port. All services run on existing infra:
- Qdrant: `localhost:6333` (daemon + search.py agree)
- BGE-M3: `localhost:8002` (daemon uses `BGEM3_URL`)
- No new container/process needed.

---

## What actually needs building

### Option A: Just reuse the daemon (minimal)
- Daemon already auto-indexes `src2/` → `baziforecaster_code`.
- Use `/home/yapilwsl/arthityap/baziforecaster/admin/tools/search.py` directly:
  ```bash
  cd /home/yapilwsl/arthityap/baziforecaster
  uv run python admin/tools/index_repository.py --repo-name baziforecaster --reset
  uv run python admin/tools/search.py "how does session handling work"
  ```

### Option B: Create `tools_repo/` (new folder, per user request)
If `tools_repo/` is still wanted (e.g. to isolate AI-Factory's access):

```bash
mkdir -p /home/yapilwsl/arthityap/baziforecaster/tools_repo
```

**3 thin CLI wrappers** + re-export controls. All delegate to shared infra:

1. `tools_repo/index_repository.py` — wraps `infra/codebase/indexer.py: index_repository`
2. `tools_repo/search.py` — mirrors `admin/tools/search.py` (QDRANT_URL + COLLECTION_NAME from baziforecaster/.env)
3. `tools_repo/investigate.py` — mirrors `admin/tools/investigate.py` (sandboxed REPO_ROOT=src2/)

**Indexing command** (one-shot, NOT via daemon):
```bash
cd /home/yapilwsl/arthityap/baziforecaster && \
PYTHONPATH=/home/yapilwsl/arthityap uv run python tools_repo/index_repository.py \
    --repo-name baziforecaster --reset
```

**Verify**:
```bash
PYTHONPATH=/home/yapilwsl/arthityap uv run python tools_repo/search.py "session handling"
```

---

## Decision points (for user)

### **Q1 — Reuse existing, or build `tools_repo/`?**
- **(A)** Reuse `admin/tools/` directly (daemon already indexes, zero new code)
- **(B)** Still build `tools_repo/` (new folder you asked for) — even though it duplicates `admin/tools/`

### **Q2: — Collection name**
- **(A)** Use existing `baziforecaster_code` (8357 points ✓) — this IS the "new collection like flourishme" naming pattern
- **(B)** Create a second one (`baziforecaster_v2` or similar) — would require manual indexing + a second `index_repository` run

### **Q3 — Docs collection?
- **(A)** Skip — we only need code search
- **(B)** Seed `baziforecaster_docs` with .md indexing (extra `index_repository` call)

Awaiting your answer to Q1 before proceeding.

---

## Assessment: baziforecaster/admin/tools/ → ai-factory factory/tools/

**Result: Nothing to copy.** All shared files are already adapted for ai-factory.

### Files already shared (adapted for ai-factory)
| File | Status |
|---|---|
| `search.py` | ✅ Already adapted (uses `factory/infra/control.py`, `CONTROL_SHEET["codebase_model"]`) |
| `investigate.py` | ✅ Already adapted |
| `index_repository.py` | ✅ Already adapted |
| `_codebase_common.py` | ✅ Already adapted (ai-factory version has `_resolve_target_root()` — newer than bazi) |
| `guardrail_check.py` | ✅ ai-factory version is newer (has `diff_vs_orig()`, `_changed_line_set`) |
| `query_knowledge_graph.py` | ✅ ai-factory version is newer (self-contained, greenfield support) |
| `smoke_test.py` | ✅ Trivial diff (path comment only) |
| `web.py` | ✅ Trivial diff (CONTROL_SHEET access style) |

### Baziforecaster-exclusive files (NOT portable)
| File | Reason |
|---|---|
| `_gen_utils.py` | Broken in source (truncated at `PYEOF`), code-gen script for baziforecaster's utils.py |
| `load_schema_gate.py` | Coupled to `admin/orchestrator/temp` (baziforecaster-only path) |
| `mcp_git_guardrail.py` | Imports `TEST.agent_guardrail` (baziforecaster-only) |
| `graph_health.py` | Imports `infra.codebase.mcp_codebase.graph_health` (baziforecaster infra) |
| `query_knowledge_graph.py` | Thin wrapper over `infra.codebase.mcp_codebase` (baziforecaster infra) |

### What was actually built
- `tools_repo/` folder created at `baziforecaster/tools_repo/` with `controls.py`, `search.py`, `index_repository.py`
- Collection `factory` created in Qdrant (1515+ points, green, zero 422 errors)
- BGEM3 batch-size fix applied to `infra/codebase/indexer.py` + `indexer_core.py` (`MAX_BATCH_SIZE=32`)
- `ai-factory` added to `WATCHED_REPOS` in `config.py`, `ai-factory` → `factory` collection mapping in `EXTRA_COLLECTIONS`
- Daemon restarted, indexing live
