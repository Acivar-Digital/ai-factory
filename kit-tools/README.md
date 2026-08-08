# kit-tools

Community-facing utility scripts (flat layout, 39 `.py` + `web.sh` + `test/`),
extracted from `baziforecaster/tools/` into `ai-factory/kit-tools/` (sibling of `kit-tests/`).
Runs inside `ai-factory`: `uv run python kit-tools/<tool>.py "args"`.

## Portability & Coupling

**10 of the 39 root tools are *not* standalone-runnable** — they import the ai-factory
runtime (`admin.*`, `infra.*`, `src2.*`, `TEST.*`) or hardcode `/home/.../infra/codebase`.
They are kept (factory-integrated utilities) but will `ImportError` on a bare laptop.

| file | coupling | runs where |
|---|---|---|
| `graph_health.py`, `index_repository.py`, `verify_file_path.py`, `query_knowledge_graph.py` | `from infra.codebase.mcp_codebase import …` + `sys.path.append("/home/…/infra/codebase")` | ai-factory checkout |
| `web.py` | `from admin.controls.controls import …` (factory `settings`) | ai-factory checkout |
| `search.py`, `investigate.py` | `from admin.controls.controls import …` | ai-factory checkout |
| `_test_tools.py` | `from admin.tools.mcp_git_guardrail import …` | ai-factory checkout |
| `mcp_git_guardrail.py` | `from TEST.agent_guardrail import …` | ai-factory checkout |
| `rewrite_mod6.py` | `from src2.core.schemas…` / `src2.engine.bazi_math` (baziforecaster bazi engine) | baziforecaster checkout |

**Standalone-portable** (import only stdlib + sibling `_codebase_common`, +pydantic in `load_schema_gate.py`):
`add_class.py, add_constant.py, add_function.py, add_import.py, fix_midfile_imports.py,
flatten_scripts_agents.py, get_file_symbols.py, get_repo_structure.py, grep_codebase.py,
list_files.py, load_schema_gate.py, move_symbol.py, read_file.py, rename_file.py,
repair_imports.py, replace_function.py, replace_text.py, restore_missing_unified.py,
restore_missing_unified2.py, rewrite_mod12.py, rewrite_module6.py, smoke_test.py,
update_scoring_output.py, update_scoring_output2.py, write_file.py, _codebase_common.py,
_fix_preprocess2.py, _gen_utils.py` → these `python kit-tools/<tool>.py` runs anywhere.

## test/
`run_all.py` + `test_discovery.py, test_indexing.py, test_knowledge.py, test_modifications.py` —
kit self-tests. `cd kit-tools && uv run pytest test/ -q`.

## Origin note
`ai-factory/tools_repo/` (13 files) were staged-then-dropped: they are **ai-factory's own
infra tooling**, not community tools. The 4 names shared with `baziforecaster/tools`
(`graph_health`, `index_repository`, `verify_file_path`, `web`) differ in content; the
baziforecaster variant is canonical here. Want the `ai_factory` variant mirrored under
`kit-tools/_vendor/ai_factory/` for provenance? Say so.
