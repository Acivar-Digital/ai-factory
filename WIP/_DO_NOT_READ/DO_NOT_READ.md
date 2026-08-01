Act as a Senior Backend Architect. We are auditing our dict -> Pydantic migration (comparing `src` against `src2`).

⚠️ CRITICAL INSTRUCTIONS:

- READ ONLY. NO CODE EDITS.
- Use `bd prime` and `bd ready`.
- You MUST use the Orchestrator pattern. Use a TODO list to sequence this out.
- Use subagents to avoid context bloat. Use `bd remember` to pass findings between the Master and Subagents.
- Deploy all agents at one go max 20

### PHASE 1: DISCOVERY (Scan)

Use `uv run python admin/tools/search.py` and `admin/tools/get_file_symbols.py` to identify the EXACT entry point functions/files in `src2` for these three core domains:

1. LLM Interaction (Intake / Conversational boundary)
2. Engine Calculation (Bazi math, palace logic, transformations)
3. Report Generation (Monthly Report, Daily forecast, Markdown generation, Egress)

### PHASE 2: ORCHESTRATED AUDIT (Batch Reporting)

For EACH of the three entry points you identified, spawn a subagent (or isolate your context) to perform a Deterministic Payload Diff Analysis (`src` vs `src2`).

Use `uv run python admin/tools/investigate.py` to compare them.
For each domain, generate a markdown report analyzing:

- EXACT MISSING FIELDS (dropped by Pydantic)
- ENUM REGRESSIONS (Enum objects vs Strings)
- SERIALIZATION TRAPS (exclude_none dropping nulls)
- ALIAS/CASING MISMATCHES

### DELIVERABLES

Save the following three artifacts in `/home/yapilwsl/arthityap/baziforecaster/_docs/MANUAL/troubleshoot/ux/`:

1. `audit_llm_interaction.md`
2. `audit_engine_calculation.md`
3. `audit_report_generation.md`

Close the task with `bd close <id> --reason "Global audit complete"` when all three files are written.

⚠️ CRITICAL INSTRUCTIONS:

- When doing CODE edits.
- Use `bd prime` and `bd ready`.
- You MUST use the Orchestrator pattern. Use a TODO list to sequence this out.
- Use subagents to avoid context bloat. Use `bd remember` to pass findings between the Master and Subagents.

now deep dive
do a reivew and mermaid on coder and red team audit- their back and off interactions
from how it > starts - loop - exit  
check context management and artefect management
save new file here
/home/yapilwsl/arthityap/baziforecaster/admin/orchestrator/infra

now deep dive infra
do a reivew and mermaid on retires and backoffs in the long running harness
from how it > starts - loop - exit
model retries and tool retries  
check context management and artefect management, tool use
save new file here
/home/yapilwsl/arthityap/baziforecaster/admin/orchestrator/infra

NO FALLBACK SHIT REMEMEBERYEES
