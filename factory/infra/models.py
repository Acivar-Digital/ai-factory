"""Canonical Pydantic hand-off models for the Orchestrator State Machine.

Every phase imports its input/output model from here. Changing a model is a
compile-time break at the next hand-off — by design.
"""

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_CODER_ID_RE = re.compile(r"^coder\d{2}$")


def _coerce_strategy(raw):
    """Weak/free-tier models (e.g. hy3_free) double-encode the nested `Strategy`
    object as a JSON *string* inside tool-call arguments. Coerce a `str` back
    into a dict so pydantic can build the `Strategy` model. Tolerates stray
    control chars (literal newlines/tabs) inside the stringified JSON.
    """
    if isinstance(raw, str):
        s = raw.strip().replace("\n", " ").replace("\t", " ").replace("\r", " ")
        if not s:
            return raw
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            start, end = s.find("{"), s.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(s[start : end + 1])
                except json.JSONDecodeError:
                    pass
        return raw  # let pydantic raise a clear "should be an object" error
    return raw


# ── Agile Enforcement Layer ───────────────────────────────────────
class Epic(BaseModel):
    """The single epic supplied by the user prompt (must_be_pydantic state)."""
    title: str
    deliverables: list[str]
    must_be_pydantic: bool


class UserStory(BaseModel):
    id: str = ""
    story: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    definition_of_done: list[str] = Field(default_factory=list)


class RubricCell(BaseModel):
    """One cell of the planner / red-team RubricCube.

    A `blocker` cell that is not `passed` fails the go/no-go gate.
    """
    dimension: str   # e.g. "pydantic", "ruff", "dict-access", "acceptance"
    criterion: str   # concrete, checkable statement
    severity: Literal["blocker", "warn"]  # "blocker" | "warn"
    passed: bool = False
    evidence: str = ""  # file:line or command output proving pass/fail
    coder_idents: list[str] = Field(default_factory=list)


class RubricCube(BaseModel):
    cells: list[RubricCell]

    @property
    def gate_failed(self) -> bool:
        """True when any blocker cell is not passed — the hard go/no-go wall."""
        return any(c.severity == "blocker" and not c.passed for c in self.cells)


# ── Phase 1 & 2 Shared ────────────────────────────────────────────
class EvidenceItem(BaseModel):
    file_path: str = Field(
        description="The exact file path string from this subtask's file_paths list (slashes intact)."
    )
    content: str = Field(
        description="Proof that the target file exists and what it contains."
    )


class SubTaskBrief(BaseModel):
    id: str
    title: str
    file_paths: list[str]
    instruction: str
    acceptance: str
    tool_preference: str  # "AST-edit" | "CLI-wrapper" | "python-first-then-agent"
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="List of evidence items proving content existence for each file in file_paths."
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_evidence(cls, data):
        if isinstance(data, dict):
            ev = data.get("evidence")
            if isinstance(ev, dict):
                data = {**data, "evidence": [{"file_path": k, "content": v} for k, v in ev.items()]}
        return data


class ApprovedTask(SubTaskBrief):
    approved: bool = True
    notes: str = ""

    @model_validator(mode="after")
    def _require_coder_id(self) -> "ApprovedTask":
        """Planner OWNS coder naming (ticket baziforecaster-tqpgf): ids MUST be
        `coderNN` so per-coder memory files, status-board lines,
        and planner ids are the identical string. Non-conforming ids HALT + re-plan.
        """
        if not _CODER_ID_RE.match(self.id):
            raise ValueError(
                f"ApprovedTask.id {self.id!r} must match the format 'coderNN' "
                f"(e.g. 'coder01', 'coder02'). Never 'task_N', never concatenated, "
                f"never non-numeric. The planner owns this naming."
            )
        return self

    @model_validator(mode="after")
    def _require_single_file(self) -> "ApprovedTask":
        if len(self.file_paths) != 1:
            raise ValueError(f"exactly one file per coder (task {self.id!r} has {len(self.file_paths)})")
        return self


class WorkGroup(BaseModel):
    id: str
    depends_on: list[str] = []  # empty = MECE; else dependent (C=A+C)
    tasks: list[ApprovedTask] = Field(min_length=1)  # Planner asserts these are file-disjoint


class ParallelisableWorkplan(BaseModel):
    groups: list[WorkGroup] = Field(min_length=1)


class ToolPreferenceItem(BaseModel):
    task_id: str = Field(
        description="The task ID matching one of the subtasks (e.g., 'coder01')."
    )
    preference: str = Field(
        description="The tool preference bucket (e.g., 'AST-edit', 'CLI-wrapper', or 'python-first-then-agent')."
    )


class Strategy(BaseModel):  # Planner is the PM — emits this (Q2/Q8/Q9)
    how_to_fix: str
    tool_preference: list[ToolPreferenceItem] = Field(
        default_factory=list,
        description="List of tool preference mappings for each task ID."
    )
    parallelisable_workplan: ParallelisableWorkplan  # DAG

    @property
    def tool_preference_dict(self) -> dict[str, str]:
        return {item.task_id: item.preference for item in self.tool_preference}

    @model_validator(mode="before")
    @classmethod
    def _coerce_tool_preference(cls, data):
        if isinstance(data, dict):
            tp = data.get("tool_preference")
            if isinstance(tp, dict):
                data = {**data, "tool_preference": [{"task_id": k, "preference": v} for k, v in tp.items()]}
        return data


class DraftPlan(BaseModel):
    epic: Epic
    user_stories: list[UserStory] = Field(default_factory=list)
    definition_of_done: list[str]
    acceptance_criteria: list[str]
    rubric_cube: RubricCube
    summary: str
    subtasks: list[SubTaskBrief] = Field(min_length=1)
    risks: list[str]
    strategy: Strategy

    @model_validator(mode="before")
    @classmethod
    def _coerce_strategy(cls, data):
        if isinstance(data, str):
            data = _coerce_strategy(data)
        if isinstance(data, dict) and isinstance(data.get("strategy"), str):
            data = {**data, "strategy": _coerce_strategy(data["strategy"])}
        return data

    @model_validator(mode="after")
    def _require_evidence(self) -> "DraftPlan":
        for s in self.subtasks:
            ev_paths = {item.file_path for item in s.evidence}
            for fp in s.file_paths:
                if not fp:
                    continue
                if fp not in ev_paths:
                    provided_keys = ", ".join(repr(p) for p in ev_paths) or "<empty>"
                    raise ValueError(
                        f"Subtask {s.id!r} references {fp!r} but no evidence was "
                        f"provided. Add an EvidenceItem with file_path={fp!r}. "
                        f"Your provided paths were: {provided_keys}."
                    )
        return self

    @model_validator(mode="after")
    def _validate_tool_preference_tasks(self) -> "DraftPlan":
        task_ids = {s.id for s in self.subtasks}
        pref_task_ids = {item.task_id for item in self.strategy.tool_preference}
        for tid in task_ids:
            if tid not in pref_task_ids:
                raise ValueError(
                    f"Task {tid!r} is missing from strategy.tool_preference. "
                    f"Please specify a preference for every task."
                )
        for item in self.strategy.tool_preference:
            if item.task_id not in task_ids:
                raise ValueError(
                    f"Tool preference specifies unknown task ID {item.task_id!r}. "
                    f"Tasks in plan are: {sorted(task_ids)}."
                )
        return self


class EvaluationItem(BaseModel):
    item_id: str = Field(
        description="Task ID from the DraftPlan. Must match a proposed task id exactly (e.g. coder01, coder02)."
    )
    approved: Literal["Yes", "No"] = Field(
        description="Yes = task approved, proceed. No = task rejected — MUST explain why in comments.",
        examples=["Yes", "No"]
    )
    comments: str = Field(
        description="Required when approved=No: cite file:line, explain what's wrong, reference the brief's constraints/anti-patterns. When approved=Yes: may be empty string.",
        examples=["", "Instruction tells coder to move _unified_medicine before line 216, but brief says 'Do NOT touch annual Tai Sui section (lines 340-399)'."]
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_approved(cls, data):
        if isinstance(data, dict):
            app = data.get("approved")
            if isinstance(app, str):
                app_lower = app.lower()
                if app_lower.startswith("yes") or app_lower.startswith("approve"):
                    data["approved"] = "Yes"
                elif app_lower.startswith("no") or app_lower.startswith("block"):
                    data["approved"] = "No"
                else:
                    raise ValueError(
                        f"Invalid status {app!r}. Must start with 'yes'/'approve' (for Approved) "
                        f"or 'no'/'block' (for Rejected)."
                    )
            elif isinstance(app, bool):
                data["approved"] = "Yes" if app else "No"
            elif app is not None:
                raise ValueError(
                    f"Invalid status type {type(app).__name__}. Must be a string starting with "
                    f"'yes'/'approve' or 'no'/'block'."
                )
        return data


# ── Phase 1 & 2 Shared ────────────────────────────────────────────
class ApprovedPlan(BaseModel):
    evaluations: list[EvaluationItem] = Field(min_length=1)


class ExecutablePlan(BaseModel):
    epic: Epic
    user_stories: list[UserStory] = Field(default_factory=list)
    definition_of_done: list[str]
    acceptance_criteria: list[str]
    rubric_cube: RubricCube
    summary: str
    tasks: list[ApprovedTask] = Field(min_length=1)
    alignment: str
    workplan: ParallelisableWorkplan
    rejected_subtasks: list[str] = []
    strategy: Strategy
    approved: bool = True

    @model_validator(mode="before")
    @classmethod
    def _coerce_strategy(cls, data):
        if isinstance(data, str):
            data = _coerce_strategy(data)
        if isinstance(data, dict) and isinstance(data.get("strategy"), str):
            data = {**data, "strategy": _coerce_strategy(data["strategy"])}
        return data

    @model_validator(mode="after")
    def _require_unique_coder_ids(self) -> "ExecutablePlan":
        seen: set[str] = set()
        for t in self.tasks:
            if t.id in seen:
                raise ValueError(
                    f"ExecutablePlan has duplicate task id {t.id!r}. Every "
                    f"ApprovedTask.id must be unique (coder01, coder02, …)."
                )
            seen.add(t.id)
        return self


# ── Phase 3 → 4 ───────────────────────────────────────────────
class TaskResult(BaseModel):  # Coder's output_type
    task_id: str
    # Constrained form (docs/02_fix.md): only "done" | "blocked" are accepted.
    # The Literal injects the enum into the pydantic-ai output schema (the coder
    # "form"), and _norm_status (mode="before") normalizes synonyms and rejects
    # anything else — so a coder emitting "completed"/"ok" proceeds, while an
    # unknown value raises ValueError for pydantic-ai to feed back + HALT on retry.
    status: Literal["done", "blocked"]  # "done" | "blocked"
    files_changed: list[str]
    diff_summary: str = Field(
        description="One-line summary of the edit made to each file."
    )
    notes: str = Field(
        description=(
            "If status='blocked': state the ERROR, the ACTION needed, the EXPECTED "
            "outcome, and the DELIVERABLE. If status='done': one line on what was implemented."
        )
    )  # if blocked: script + error for escalation
    # ValidationVerdict (docs/01_fix.md Task 4, D1): cumulative machine verdict
    # fields the harness fills AFTER the smoke + ruff + pyright gates run. The
    # coder's LLM output is the *claim* half; these are the *verdict* half, kept
    # in the same object so reviewers and the operator see both.
    ruff_ok: bool = True
    pyright_ok: bool = True
    exec_ok: bool = True  # smoke-execution type-construction gate passed
    verdict_errors: str = ""  # concatenated ruff/pyright/smoke errors
    verdict_diff: str = ""  # unified diff vs baseline .orig
    dep_pointers: list[str] = Field(default_factory=list)  # file:line/symbol of deps

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status(cls, v: str) -> str:
        s = str(v).strip().lower()
        if s in ("done", "complete", "completed", "completes", "ok", "success", "finished"):
            return "done"
        if s in ("blocked", "fail", "failed", "error"):
            return "blocked"
        raise ValueError("status must be 'done' or 'blocked'")


class TaskBatch(BaseModel):
    results: list[TaskResult] = Field(min_length=1)


# ── Phase 4 → 5 ───────────────────────────────────────────────
class ReviewFinding(BaseModel):
    task_id: str
    severity: Literal["blocker", "warn"]  # "blocker" | "warn"
    file: str
    line: int | None = None
    message: str
    suggestion: str


class CodePassed(BaseModel):
    passed: bool
    findings: list[ReviewFinding] = []
    traceback_route: str = ""  # non-empty → back to Phase 3


class ReviewResult(BaseModel):
    evaluations: list[EvaluationItem] = Field(min_length=1)


# ── Phase 5 → 6 ───────────────────────────────────────────────
class AuditRisk(BaseModel):
    task_id: str = ""  # names offending task (routes Red→EXECUTE by this)
    component: str  # names offending task/file
    severity: Literal["Critical", "High", "Medium", "Low"]  # "Critical" | "High" | "Medium" | "Low"
    description: str
    mitigation: str


class AuditResult(BaseModel):
    evaluations: list[EvaluationItem] = Field(min_length=1)


# ── Phase 6 ────────────────────────────────────────────────────
class GitResult(BaseModel):
    pushed: bool
    commit_sha: str | None = None
    bd_closed: bool
    message: str


# ── Context Compaction Gate ───────────────────────────────────
class CompactedContext(BaseModel):
    summary: str


# ── State Management (Crash-Resume) ───────────────────────────
class TaskState(BaseModel):
    task_id: str
    status: str = "pending"  # pending | in_progress | done | blocked | escalated
    attempts: int = 0
    max_attempts: int = 3
    result: TaskResult | None = None
    last_error: str = ""
    group_id: str = ""


class OrchestratorState(BaseModel):
    bd_id: str
    run_dir: str
    current_phase: str = "planner"  # MUST be a member of _PHASE_ORDER (role keys)
    phase_attempts: dict[str, int] = {}
    phase_reexec: int = 0
    tasks: dict[str, TaskState] = {}
    phase_summaries: dict[str, CompactedContext] = {}

    global_alignment: str = ""  # boot-injected (recall_fact), broadcast-by-copy

    draft: DraftPlan | None = None
    approved: ExecutablePlan | None = None
    batch: TaskBatch | None = None
    code_passed: ReviewResult | None = None
    audit: AuditResult | None = None
    git: GitResult | None = None
    timestamp: str = ""


# ── Sub-Agent Dependency & Yield Tracking ─────────────────────
class AgentDependencies(BaseModel):
    tool_budget: int = 15
    tools_used: int = 0
    modified_files: set[str] = set()
    global_decisions: list[str] = []


class YieldSignal(BaseModel):
    yielded: bool = True
    reason: str

