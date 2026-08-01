# READ-ONLY

# Load Skills

- `/home/yapilwsl/arthityap/baziforecaster/.agents/skills/wip-harness`
- `/home/yapilwsl/arthityap/baziforecaster/.agents/skills_archive/pydantic-ai-coding`

# Focus Area

- `/home/yapilwsl/arthityap/baziforecaster/admin/orchestrator`

# Non-Negotiable Rules

- For **no code edits, read-only**, run `bd prime` and `bd ready`.
- Use the **Orchestrator pattern** and maintain a **TODO list**.
- Use **subagents** to avoid context bloat.
- Use `bd` and `bd remember` to track:
  - findings
  - outstanding issues
  - required work
  - key decisions
- Pass important findings between master and subagents using `bd remember`
- Imperative to read the codes and investigate throrugly before a conclusion.
- Making assumptions is banned.

# Task

Read this
/home/yapilwsl/arthityap/baziforecaster/session_crash.md
Read the logs.
Can you check the logs why the last process failed?

# RUN

# Load Skills

- `/home/yapilwsl/arthityap/baziforecaster/.agents/skills/wip-harness`
- `/home/yapilwsl/arthityap/baziforecaster/.agents/skills_archive/pydantic-ai-coding`

# Focus Area

- `/home/yapilwsl/arthityap/baziforecaster/admin/orchestrator`

# Non-Negotiable Rules

- For **all code edits**, run `bd prime` and `bd ready`.
- Use the **Orchestrator pattern** and maintain a **TODO list**.
- Use **subagents** to avoid context bloat.
- Use `bd` and `bd remember` to track:
  - findings
  - outstanding issues
  - required work
  - key decisions
- Pass important findings between master and subagents using `bd remember`.
- Prioritize **AST edits** over raw/manual edits.
- Instruct subagents to also prioritize AST edits over raw edits.
- If logic will be reused across multiple files, consider **pip-ifying** it.

# Test Kit Requirement (Mandatory)

- You **MUST write or update the test kit** for every feature, fix, or behavior change.
- The change is **not complete** unless the relevant tests are added or updated.
- The implementation must **not be considered done** unless the test kit passes.
- The tests must protect against regressions so the feature is **not lost in future changes**.

# Documentation Updates

- Update the **changelog**.
- Update the **wip-harness skill** so any LLM can accurately understand how this harness works.
- Remove any guidance that contradicts this build from **wip-harness** so future LLMs are not misled.

# Commit Rules

- Force commit **only** changes to:
  - `.py`
  - `.md`
  - `.yaml`

# Done Criteria

A task is only done when all of the following are complete:

1. Root cause is identified.
2. Fix is implemented end-to-end.
3. Test kit is created or updated.
4. Tests pass.
5. Changelog is updated.
6. `wip-harness` is updated and cleaned of outdated guidance.
7. Only allowed files are included in the force commit.

# Task

Read and fix everything from start to finish based on:
/home/yapilwsl/arthityap/baziforecaster/session-ses_087c.md
