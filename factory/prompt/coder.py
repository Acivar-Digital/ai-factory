def get_behaviour_appendix(acceptance: str) -> str:
    return (
        "=== EXPECTED CODER BEHAVIOUR (frozen contract) ===\n"
        "- Implement ONLY this task; do not touch other tasks' files.\n"
        "- Satisfy EVERY acceptance_criteria line below verbatim; if a criterion "
        "is unachievable, return status 'blocked' with the reason — never fake it.\n"
        "- Use STRICT Pydantic models / typed fields only; no bare dicts for "
        "domain logic; no dict access on Pydantic models.\n"
        "- Code MUST pass `uv run ruff check`. Write output under "
        "factory/temp/ (PROPOSE-ONLY); never write src/ or src2/.\n"
        "- Return a TaskResult (task_id, status, files_changed, diff_summary, "
        "notes) with NO file content inside it.\n"
        f"- ACCEPTANCE (verbatim):\n{acceptance}\n"
    )

def get_feedback_block(task_id: str, feedback: dict[str, str] | None, is_rerun: bool) -> str:
    if feedback and task_id in feedback:
        return (
            "\n=== PRIOR FEEDBACK (why this task was reopened) ===\n"
            "You are FIXING a previously-failed attempt. The harness reopened "
            "this task based on the review/audit findings below. Address EVERY "
            "point. Your own prior attempt context lives in your coder memory "
            "(compacted via keep_memory) — this block is the authoritative list "
            "of what changed.\n"
            f"{feedback[task_id]}\n"
        )
    elif is_rerun:
        return (
            "\n=== PRIOR FEEDBACK ===\n"
            "This task was reopened by the harness (rerun target) but no "
            "structured findings were captured. Re-read your own coder memory "
            "(keep_memory) and the staged files, and re-verify your prior "
            "attempt against the acceptance criteria.\n"
        )
    return ""

def get_discipline_block() -> str:
    return (
        "\n=== FROZEN DISCIPLINE (load-bearing rules — DO NOT VIOLATE) ===\n"
        "- ZERO-DICTS: No bare dict access on Pydantic models. All domain data uses strict Pydantic models/Enums/Literals.\n"
        "- PYDANTIC-ONLY: All domain lookups/tables = Pydantic registry models with typed fields. Enums ONLY as field types.\n"
        "- FAIL LOUDLY: Full tracebacks on errors. No silent except:pass, no hidden fallbacks.\n"
        "- FAIL CHEAPLY: Cheap assertions before expensive LLM calls.\n"
        "- NO src/ or src2/ edits: Write output under factory/temp/ only.\n"
        "- Code MUST pass `uv run ruff check` before being considered done.\n"
    )

def build_coder_brief(
    task_id: str,
    title: str,
    instruction: str,
    acceptance: str,
    file_paths: list[str],
    staged: list[str],
    edit_mode_block: str,
    tier_b_map: str,
    inline_files: str,
    global_alignment: str,
    feedback: dict[str, str] | None,
    is_rerun: bool,
) -> str:
    behaviour_appendix = get_behaviour_appendix(acceptance)
    feedback_block = get_feedback_block(task_id, feedback, is_rerun)
    discipline_block = get_discipline_block()
    
    return (
        "You are implementing EXACTLY ONE task. Do not implement others.\n\n"
        f"TASK ID: {task_id}\nTITLE: {title}\n"
        f"FILE TO EDIT: {file_paths[0] if file_paths else 'None'}\n\n"
        f"INSTRUCTION:\n{instruction}\n\n"
        f"ACCEPTANCE CRITERIA:\n{acceptance}\n\n"
        f"LIVE FILES (read-only reference — DO NOT write here):\n{file_paths}\n\n"
        f"STAGING PATHS (WRITE your proposed files ONLY here, under factory/temp/):\n{staged}\n\n"
        + edit_mode_block
        + "\n"
        + (tier_b_map + "\n\n" if tier_b_map else "")
        + (f"\n=== FULL FILE CONTENT (edit directly; NO read tool needed) ===\n{inline_files}\n" if inline_files else "")
        + global_alignment
        + "\n\n"
        + behaviour_appendix
        + discipline_block
        + feedback_block
    )
