# Planner & KG Architecture Fixes (Handoff Plan)

## 1. KG Injection & Fail Loudly (Option B)
**Bug:** `query_knowledge_graph.py` crashes due to missing `libcst` and a legacy hardcoded path (`/home/yapilwsl/arthityap/infra/codebase`). `ledger.py` swallows this crash, injecting `KG ERROR` into the Planner's prompt.
**Fix (The Builder Task):**
- Update `factory/tools/query_knowledge_graph.py` to use correct local imports and ensure `libcst` is available.
- **Option B (Fail Loudly):** Modify `query_knowledge_graph.py` and `get_file_symbols.py` to gracefully return `exit 0` with `[]` if a file does not exist (to support greenfield creation).
- Remove the `try...except` blocks in `factory/infra/ledger.py` (`inject_repo_map` and `_kg_for_file`). If the CLI tool returns a non-zero exit code, the orchestrator MUST hard-halt.

## 2. Planner Prompt Tightening
**Bug:** The planner lacks a cognitive strategy and is lied to about its read budget.
**Fix (The Builder Task):**
- Do NOT create a separate skill file. Update `factory/infra/agents/planner.yaml` directly.
- Fix budget lie: Change `5 batch_read calls spent` to `15 batch_read calls spent`.
- Replace the `=== PLANNING METHOD ===` block with a concrete 4-step workflow:
  1. IDENTIFY & GATHER (From user_prompt and SCOPE_CONTEXT)
  2. DEEP INSPECTION (batch_read)
  3. TYPE-CONTRACT TRACING (Producers vs Consumers)
  4. DISJOINT GROUPING (1 file = 1 coder, sequence via depends_on).