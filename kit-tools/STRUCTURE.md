# kit-tools — Structure

Flat community toolset at `ai-factory/kit-tools/` (sibling of `kit-tests/`).

## Layout
```
kit-tools/
├── *.py (39)            # 10 factory-coupled + 29 portable, flat at root
├── web.sh               # convenience launcher
├── README.md / STRUCTURE.md
└── test/                # run_all.py + 4 test_*.py (kit self-tests)
```

## Origin
- **Community set (kept):** `baziforecaster/tools/` (faithful copy, 39 `.py` + `web.sh` + `test/`).
- **Dropped (not community):** `ai-factory/tools_repo/` — 13 ai-factory-only infra files
  (8 `infra.*` importers + `Semgrep.yaml` + `__init__.py`). Source untouched.
- **Shared-but-differing (4):** `graph_health` / `index_repository` / `verify_file_path` / `web`
  exist in both repos but differ; baziforecaster variant is canonical here.

## Gate
```bash
cd /home/yapilwsl/arthityap/ai-factory
uv run ruff check kit-tools --select E9,F63,F7,F82 --no-cache   # parse-clean
# (standalone portability is documented in README.md#portability; not every tool runs on a bare laptop)
```
