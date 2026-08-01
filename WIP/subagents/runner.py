import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import logfire
import yaml
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.usage import UsageLimits

from admin.controls.controls import CONTROL_SHEET
from admin.subagents.codebase_skill import CodebaseSkill
from admin.subagents.reviewer_codebase_skill import ReviewerCodebaseSkill

logfire.configure(send_to_logfire=False)
logfire.instrument_pydantic_ai()
logfire.instrument_httpx(capture_all=True)

# =====================================================================
# 1. SKILLS (MCP toolset providers — loaded lazily by agent context mgr)
# =====================================================================
codebase_skill = CodebaseSkill()
reviewer_skill = ReviewerCodebaseSkill()


# =====================================================================
# 2. STRUCTURED OUTPUT MODELS
# =====================================================================
class ReviewResult(BaseModel):
    is_approved: bool = Field(description="True if changes are clean and correct.")
    feedback: str = Field(description="Feedback if rejected, empty if approved.")


# ─── Plan Models ───────────────────────────────────────────────────
class FixStrategy(StrEnum):
    AST_SURGICAL = "ast_surgical"
    TEXT_REPLACE = "text_replace"
    COMPLEX_REWRITE = "complex_rewrite"


class FixItem(BaseModel):
    fix_id: str = Field(description="Short unique ID e.g. 'F1', 'F2'")
    file: str = Field(description="Relative file path")
    description: str = Field(description="One sentence: what to change and why")
    strategy: FixStrategy = Field(description="Which MCP tool strategy")
    why_strategy: str = Field(description="Why this strategy over alternatives")
    verify_cmd: str | None = Field(default=None, description="Shell command to verify")


class RunPlan(BaseModel):
    fixes: list[FixItem] = Field(description="Ordered safest-first, each independently executable")
    risk_level: str = Field(description="Low | Medium | High")
    order_rationale: str = Field(description="Why this ordering")


# ─── Runner State ──────────────────────────────────────────────────
MAX_REVIEW_RETRIES = 3


class FixState(BaseModel):
    status: str = Field(default="pending", description="pending | coded | reviewing | approved | rejected")
    review_attempts: int = Field(default=0, description="How many times review has rejected this fix")
    last_error: str | None = Field(default=None, description="Last error message if rejected")


class RunnerState(BaseModel):
    bead: str = Field(description="Bead ID")
    phase: str = Field(description="plan | coding | review | push")
    task_prompt: str = Field(default="", description="Original task prompt for resume context")
    failed_fix: str | None = Field(default=None)
    plan: RunPlan | None = Field(default=None)
    fix_states: dict[str, FixState] = Field(default_factory=dict)
    current_diff: str = Field(default="", description="Git diff snapshot of uncommitted changes")
    timestamp: str = Field(default="")


# =====================================================================
# 3. SUB-AGENTS (loaded/unloaded by orchestator tool calls)
# =====================================================================
coding_agent = Agent(
    CONTROL_SHEET.subagent_model,
    toolsets=codebase_skill.toolsets,
    retries=3,
    instructions=(
        "You are a precise coding agent. Execute ONE fix from a plan. "
        "Focus ONLY on the assigned file. Do not modify other files."
        + codebase_skill.instructions
    ),
)


@coding_agent.tool
def run_shell_command(ctx: RunContext, command: str) -> str:
    """Execute a shell command (ruff, pytest, etc.) and return output."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        return f"EXIT CODE: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 15 seconds."
    except Exception as e:
        return f"Error: {e}"


reviewer_agent = Agent(
    CONTROL_SHEET.review_model,
    toolsets=reviewer_skill.toolsets,
    output_type=ReviewResult,
    retries=3,
    instructions=reviewer_skill.instructions,
)





# =====================================================================
# 4. YAML LOADERS
# =====================================================================
def load_yaml_text(yaml_path: Path) -> str:
    return yaml_path.read_text(encoding="utf-8") if yaml_path.exists() else ""


def load_task_from_yaml(yaml_path: Path) -> str | None:
    if not yaml_path.exists():
        return None
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        return data.get("task") if data else None
    except Exception as e:
        print(f"Warning: Error loading {yaml_path}: {e}")
        return None


def load_resume_from_yaml(yaml_path: Path) -> str:
    if not yaml_path.exists():
        return "coding"
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        return (data.get("resume") or "coding").strip().lower() if data else "coding"
    except Exception:
        return "coding"


# =====================================================================
# 4b. STATE FILE
# =====================================================================
STATE_FILE = Path("admin/subagents/runner_state.json")


def save_state(state: RunnerState) -> None:
    state.timestamp = datetime.now(UTC).isoformat()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def load_state() -> RunnerState | None:
    if STATE_FILE.exists():
        try:
            return RunnerState.model_validate_json(STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️  [State] Corrupted state: {e}. Starting fresh.")
            return None
    return None


def clear_checkpoint() -> None:
    if STATE_FILE.exists():
        STATE_FILE.unlink()


# =====================================================================
# 5. HELPERS
# =====================================================================
def get_git_diff() -> str:
    changed = subprocess.run(
        "git diff --name-only -- src2/ admin/ migrations/",
        shell=True, capture_output=True, text=True,
    ).stdout.strip()
    if not changed:
        return ""
    files = [f for f in changed.splitlines() if f]
    res = subprocess.run(["git", "diff", "--"] + files, capture_output=True, text=True)
    return res.stdout


def stream_messages(messages: list, log_fn, section: str) -> None:
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, TextPart) and part.content.strip():
                    log_fn(f"💬 {part.content[:500]}", section)
        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart) and part.content.strip():
                    log_fn(f"🧠 {part.content[:300]}", section)
                elif isinstance(part, ToolCallPart):
                    args_preview = str(part.args)[:200] if part.args else ""
                    log_fn(f"🔧 {part.tool_name}({args_preview})", section)
        elif hasattr(msg, "parts"):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    content_preview = str(part.content)[:300] if part.content else ""
                    log_fn(f"📦 {part.tool_name}: {content_preview}", section)


# =====================================================================
# 7. ORCHESTRATOR FACTORY
# =====================================================================
def _make_orchestrator(task_prompt: str, bead_id: str, log_fn) -> Agent:
    """Create the orchestrator agent with tools to load/unload each skill."""

    # Load orchestrator system prompt from skill file
    skill_path = Path(__file__).parents[2] / ".agents/skills/orchestrator/SKILL.md"
    system_prompt = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
    if system_prompt:
        log_fn(f"📚 [Orch] Loaded orchestrator system prompt ({len(system_prompt)} chars)", "orch-log")

    async def execute_fix(ctx: RunContext, fix_id: str, file_path: str, description: str, strategy: str, verify_cmd: str | None = None) -> str:
        """Execute ONE fix by loading the coding agent with MCP tools. Provide fix_id, file_path, what to do, strategy, and optional verify command."""
        log_fn(f"🤖 [Orch] Loading coder for {fix_id}...", "orch-log")
        max_attempts = 3
        success = False
        for attempt in range(1, max_attempts + 1):
            try:
                fix_prompt = (
                    f"Execute fix {fix_id}.\n"
                    f"File: {file_path}\n"
                    f"What to do: {description}\n"
                    f"Strategy: {strategy}\n"
                    + (f"Verify after: {verify_cmd}\n" if verify_cmd else "")
                    + "\nFocus ONLY on this one fix. Do not modify other files."
                )
                async with coding_agent:
                    result = await coding_agent.run(fix_prompt, usage_limits=UsageLimits(request_limit=50))
                    stream_messages(result.new_messages(), log_fn, "coder-log")
                success = True
                break
            except Exception as e:
                if attempt < max_attempts:
                    log_fn(f"⚠️ [Orch] {fix_id} attempt {attempt}/{max_attempts} failed: {e}. Retrying...", "orch-log")
                    await asyncio.sleep(2 * attempt)
                else:
                    log_fn(f"❌ [Orch] {fix_id} failed after {max_attempts} attempts: {e}", "orch-log")
                    return json.dumps({"status": "error", "fix_id": fix_id, "error": str(e)})

        if not success:
            return json.dumps({"status": "error", "fix_id": fix_id, "error": "exited loop without success"})

        if verify_cmd:
            log_fn(f"🔧 [Orch] Verify: {verify_cmd}", "orch-log")
            try:
                v = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True, timeout=15)
                if v.returncode != 0:
                    log_fn(f"❌ [Orch] {fix_id} verify FAILED:\n{v.stderr[:500]}", "orch-log")
                    return json.dumps({"status": "verify_failed", "fix_id": fix_id, "error": v.stderr[:300]})
                log_fn(f"✅ [Orch] {fix_id} verify passed.", "orch-log")
            except subprocess.TimeoutExpired:
                return json.dumps({"status": "verify_failed", "fix_id": fix_id, "error": "timeout"})

        log_fn(f"✅ [Orch] {fix_id} done.", "orch-log")
        return json.dumps({"status": "success", "fix_id": fix_id})

    async def review_changes(ctx: RunContext) -> str:
        """Load the reviewer agent to inspect the current git diff. Returns ReviewResult JSON."""
        diff = get_git_diff()

        # Auto-format before review
        proc = subprocess.run("git diff --name-only", shell=True, capture_output=True, text=True)
        modified = [f.strip() for f in proc.stdout.splitlines() if f.strip().endswith(".py") and Path(f.strip()).exists()]
        if modified:
            files_str = " ".join(modified)
            subprocess.run(f"uv run ruff format {files_str} >/dev/null 2>&1", shell=True)
            subprocess.run(f"uv run ruff check {files_str} --fix >/dev/null 2>&1", shell=True)
            log_fn(f"🧹 [Orch] Ruff auto-fixed: {', '.join(modified)}", "orch-log")

        log_fn(f"🔍 [Orch] Loading reviewer...\n{diff[:800]}{'...(truncated)' if len(diff) > 800 else ''}", "orch-log")
        try:
            reviewer_context = load_yaml_text(Path(__file__).parent / "reviewer.yaml")
            prompt = (
                f"Task:\n{task_prompt}\n\n"
                + (f"Guidelines:\n{reviewer_context}\n\n" if reviewer_context else "")
                + f"Diff:\n```diff\n{diff}\n```"
            )
            async with reviewer_agent:
                result = await reviewer_agent.run(prompt, usage_limits=UsageLimits(request_limit=150))
                stream_messages(result.new_messages(), log_fn, "reviewer-log")
            return result.output.model_dump_json()
        except Exception as e:
            return json.dumps({"is_approved": False, "feedback": f"Review error: {e}"})

    async def save_checkpoint(ctx: RunContext, state_json: str) -> str:
        """Persist a RunnerState checkpoint to disk. Pass JSON matching RunnerState schema.
        Enforces the 3-retry limit — if any fix has review_attempts >= MAX_REVIEW_RETRIES and is not approved, hard stop.
        Auto-enriches with git diff snapshot and task prompt for resume context."""
        try:
            state = RunnerState.model_validate_json(state_json)
            # Auto-enrich: capture git diff for resume context
            try:
                diff = subprocess.run("git diff", shell=True, capture_output=True, text=True, timeout=10)
                state.current_diff = (diff.stdout + diff.stderr)[:5000]
            except Exception:
                state.current_diff = ""
            # Carry task prompt (not passed by orchestrator — injected here from closure)
            if not state.task_prompt and task_prompt:
                state.task_prompt = task_prompt
            # Hard stop: any fix with 3+ review attempts and not approved = rejected permanently
            rejected_fixes = []
            for fix_id, fix in state.fix_states.items():
                if fix.review_attempts >= MAX_REVIEW_RETRIES and fix.status != "approved":
                    state.fix_states[fix_id].status = "rejected"
                    state.fix_states[fix_id].last_error = f"Rejected after {fix.review_attempts} review attempts (max {MAX_REVIEW_RETRIES})"
                    state.phase = "review"  # signal to orchestrator that max retries hit
                    rejected_fixes.append(fix_id)
            save_state(state)
            if rejected_fixes:
                raise RuntimeError(f"Hard stop: Fixes {rejected_fixes} exceeded maximum review attempts ({MAX_REVIEW_RETRIES})")
            return "saved"
        except RuntimeError:
            raise
        except Exception as e:
            return f"Error saving checkpoint: {e}"

    return Agent(
        CONTROL_SHEET.orchestrator_model,
        tools=[execute_fix, review_changes, save_checkpoint],
        toolsets=codebase_skill.toolsets,
        system_prompt=system_prompt,
        retries=5,
    )


# =====================================================================
# 8. MAIN ORCHESTRATION
# =====================================================================
async def execute_hygiene_loop(
    task_prompt: str,
    resume_from: str = "coding",
    bead_id: str = "unknown",
) -> None:
    def log(msg: str, section: str = "orch-log") -> None:
        prefix = {"orch-log": "🧠", "coder-log": "🤖", "reviewer-log": "🔍", "gitpush-log": "🚀"}.get(section, "·")
        print(f"{prefix} {msg}")

    log(f"Bead: {bead_id} | Resume: [{resume_from.upper()}]")

    # Build resume context from state
    resume_context = ""
    state = load_state()
    if state and state.plan:
        done = [k for k, v in state.fix_states.items() if v.status == "approved"]
        failed = [k for k, v in state.fix_states.items() if v.status == "rejected"]
        pending = [k for k, v in state.fix_states.items() if v.status == "pending"]
        resume_context = (
            f"\n\nRESUME CONTEXT:\n"
            f"Bead: {state.bead}\n"
            f"Approved fixes: {', '.join(done) if done else 'none'}\n"
            f"Rejected fixes (will NOT retry): {', '.join(failed) if failed else 'none'}\n"
            f"Pending fixes: {', '.join(pending) if pending else 'none'}\n"
            f"Current phase: {state.phase}\n"
            f"Plan: {state.plan.model_dump_json(indent=2)}\n\n"
        )
        if resume_from == "coding":
            resume_context += (
                f"Start by continuing from the first pending fix. "
                f"Approved fixes: {', '.join(done) if done else 'none'}. "
                f"Do NOT redo approved fixes."
            )

    # Create the orchestrator and run it
    orchestrator = _make_orchestrator(task_prompt, bead_id, log)
    full_prompt = task_prompt + resume_context

    log("🎬 [Orch] Starting orchestration...", "orch-log")
    try:
        await orchestrator.run(full_prompt, usage_limits=UsageLimits(request_limit=200))
        log("🎉 [Orch] Pipeline complete.", "orch-log")
        clear_checkpoint()
    except Exception as e:
        log(f"🚨 [Orch] Fatal: {e}", "orch-log")
        raise


# =====================================================================
# 9. ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    yaml_dir = Path(__file__).parent
    runner_yaml = yaml_dir / "runner.yaml"

    # Wipe stale state before starting
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        print(f"Wiped stale: {STATE_FILE}")

    task_prompt = load_task_from_yaml(runner_yaml)
    resume_from = load_resume_from_yaml(runner_yaml)

    bead_id = "unknown"
    if task_prompt:
        for line in task_prompt.splitlines():
            if line.strip().startswith("BEAD:"):
                bead_id = line.split("BEAD:", 1)[-1].strip()
                break

    if not task_prompt:
        if len(sys.argv) < 2:
            print("Usage: python -m admin.subagents.runner or configure runner.yaml")
            sys.exit(1)
        task_prompt = sys.argv[1]

    print(f"🎯 Bead: {bead_id} | Resume from: {resume_from.upper()}")
    asyncio.run(execute_hygiene_loop(task_prompt, resume_from, bead_id))
