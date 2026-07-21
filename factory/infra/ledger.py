"""Deterministic, zero-LLM infrastructure for the Orchestrator State Machine.

Holds the amnesiac coder hand-off, a scoped repo-map injector, and a thin
ledger that mirrors `AgentDependencies` state. Everything that touches the
filesystem / CLI is routed through the `factory/tools/*.py` wrappers via
`uv run`, exactly as the conductor (A8) expects.
"""

import json
import logging
import re

from pydantic import BaseModel, Field

from factory.common import _run_tool
from factory.infra.control import REPO_ROOT
from factory.infra.models import (
    AgentDependencies,
    ApprovedPlan,
    ApprovedTask,
)

_logger = logging.getLogger("orchestrator.ledger")

# _run_tool is shared in factory.common (Fail-Loudly: raises
# RuntimeError on timeout). inject_repo_map below preserves ledger's
# string-return contract by catching that RuntimeError per call.


def _is_dir(rel: str) -> bool:
    """Best-effort check whether a scope entry is a directory (truthful hint)."""
    p = REPO_ROOT / rel
    try:
        return p.is_dir()
    except OSError:
        return False


def _py_tree() -> str:
    """Compact list of .py files under src2/ (and tests/), gitignored excluded.

    Replaces the whole-repo ``get_repo_structure`` dump, which flooded the
    planner brief with _docs/, _prd/, .beads/, WEB/, logs/ and audit noise.
    Rules (per user directive):
      1. walk starts from src2/ (and tests/),
      2. .py files only,
      3. drop any path matched by .gitignore (so .beads/, logs/, _prd/,
         training_data *.json, etc. never appear).
    """
    import subprocess

    roots = [REPO_ROOT / "src2", REPO_ROOT / "tests"]
    candidates: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                rel = str(path.relative_to(REPO_ROOT))
            except ValueError:
                continue
            candidates.append(rel)
    if not candidates:
        return "(no .py sources found under src2/ or tests/)"
    # Exclude gitignored paths in one batch subprocess call.
    shown: list[str] = []
    if candidates:
        try:
            proc = subprocess.run(
                ["git", "check-ignore", "--stdin", "--no-index"],
                input="\n".join(candidates),
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                timeout=30,
            )
            ignored = set(proc.stdout.splitlines())
            shown = [c for c in candidates if c not in ignored]
        except (subprocess.SubprocessError, OSError):
            shown = candidates
    if not shown:
        return "(no tracked .py sources found under src2/ or tests/)"
    # Render as an indented tree by path segments.
    tree_lines: list[str] = []
    for rel in shown:
        parts = rel.split("/")
        indent = "    " * (len(parts) - 1)
        tree_lines.append(f"{indent}└── {parts[-1]}")
    return "\n".join(tree_lines)


def _unwrap_tool_output(raw: str) -> str:
    """Strip the shadow-tool JSON envelope into clean, LLM-readable text.

    The codebase tools emit ``{"success": true, "message", "data": {...}}``
    (or ``{"success": false, "message"}`` on failure). Injecting that raw
    envelope into a planner brief is noise — we want the *payload* only:
    for a success, the single non-trivial value in ``data`` (the tree string
    or the symbols listing); for a failure, the ``message`` as an ERROR note.
    """
    text = raw.strip()
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Not JSON — already clean text (or a CLI ERROR(...) string). Pass through.
        return text
    if not isinstance(obj, dict):
        return text
    if obj.get("success") is True:
        data = obj.get("data", {})
        if isinstance(data, dict) and len(data) == 1:
            # Common case: {"structure": "..."} / {"symbols": [...]} — flatten.
            value = next(iter(data.values()))
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                # get_file_symbols returns [{"name","type","line"}, ...] —
                # render a compact symbol listing, not raw JSON objects.
                return _render_symbol_list(value)
            return json.dumps(value, ensure_ascii=False, indent=2)
        if isinstance(data, dict):
            return json.dumps(data, ensure_ascii=False, indent=2)
        return str(data)
    # success is False (or missing): surface the human message.
    return f"ERROR: {obj.get('message', text)}"


def _render_symbol_list(symbols: list) -> str:
    """Compact, LLM-readable rendering of a ``get_file_symbols`` payload.

    Each entry is ``{"name", "type", "line"}``; emit ``name: type (line N)``
    one per line so the planner gets a scannable symbol index, not a JSON dump.
    """
    lines: list[str] = []
    for sym in symbols:
        if not isinstance(sym, dict):
            lines.append(str(sym))
            continue
        name = sym.get("name", "?")
        stype = sym.get("type", "")
        line = sym.get("line", "")
        if stype or line:
            lines.append(f"{name}: {stype} (line {line})")
        else:
            lines.append(str(name))
    return "\n".join(lines)


def _kg_for_file(rel: str, symbols: str) -> str:
    """Deterministic KG lookup keyed off the file path + its top-level symbols.

    Failed/empty KG falls back to a short note so a noisy graph never breaks
    the scoped map.
    """
    names: list[str] = []
    for ln in symbols.splitlines():
        s = ln.strip()
        # grab the first token of each symbol line (name before signature)
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\b", s)
        if m:
            names.append(m.group(1))
        if len(names) >= 12:
            break
    query = f"{rel} " + " ".join(names) if names else rel
    try:
        return _unwrap_tool_output(_run_tool("query_knowledge_graph", [query, "--max-entities", "8"]))
    except RuntimeError as e:
        return f"KG ERROR: {e}"


def inject_repo_map(target_files: list[str]) -> str:
    """Produce a fresh, scoped structural map of `target_files`.

    Combines a compact repo-structure overview with per-file symbol listings
    and a deterministic knowledge-graph (KG) lookup per file. Folders in
    `target_files` are expanded to their subtree via ``get_repo_structure``.

    Subprocess failures are captured per call as ERROR lines — never raised to
    the caller. No size cap: this bundle lands at turn-1 only (the
    compact_memory_gate watcher bounds it on subsequent turns).
    """
    if not target_files:
        # No-scope fallback: .py-only tree + explicit note.
        lines: list[str] = ["REPO MAP (no scope declared; discover as needed)", "=" * 40]
        try:
            structure = _py_tree()
        except RuntimeError as e:
            structure = f"ERROR: {e}"
        lines.append("STRUCTURE (src2/ + tests/, .py only):")
        lines.append(structure)
        lines.append("-" * 40)
        return "\n".join(lines)

    lines: list[str] = ["REPO MAP (scoped, Python sources only)", "=" * 40]

    # Orientation tree: .py files under src2/ (and tests/), NOT the whole repo
    # (which would drag in _docs/, _prd/, .beads/, WEB/, audit logs, ...).
    try:
        structure = _py_tree()
    except RuntimeError as e:
        structure = f"ERROR: {e}"
    lines.append("STRUCTURE (src2/ + tests/, .py only):")
    lines.append(structure)
    lines.append("-" * 40)

    for rel in target_files:
        if _is_dir(rel):
            # get_repo_structure emits the whole repo tree once (see STRUCTURE
            # above); folders are recorded as in-scope scopes so the planner
            # knows where to focus. (No per-folder subtree CLI exists yet.)
            lines.append(f"FOLDER (in scope): {rel}")
            lines.append("-" * 40)
            continue

        lines.append(f"FILE: {rel}")
        try:
            symbols = _unwrap_tool_output(_run_tool("get_file_symbols", [rel]))
        except RuntimeError as e:
            symbols = f"ERROR: {e}"
        lines.append(symbols)
        lines.append("KG (knowledge graph):")
        lines.append(_kg_for_file(rel, symbols))
        lines.append("-" * 40)

    return "\n".join(lines)


def build_coder_brief(task: ApprovedTask, plan: ApprovedPlan) -> str:
    """Build the *amnesiac* coder hand-off.

    Returns ONLY the coder's scoped task (instruction, file_paths, acceptance,
    tool_preference) plus the workplan context it needs to execute — the global
    alignment and workplan DAG. The planner's raw prompt, rubric reasoning and
    supervisor prose are deliberately excluded. This fixes the old
    `runner.py:664` "accumulate all role history" context-leak bug.
    """
    out: list[str] = [
        "CODER BRIEF (amnesiac hand-off)",
        "=" * 40,
        f"TASK ID: {task.id}",
        f"TITLE: {task.title}",
        "",
        "INSTRUCTION:",
        task.instruction,
        "",
        "FILE PATHS:",
        *[f"  - {p}" for p in task.file_paths],
        "",
        "ACCEPTANCE:",
        task.acceptance,
        "",
        f"TOOL PREFERENCE: {task.tool_preference}",
        "",
        "WORKPLAN CONTEXT:",
        f"alignment: {plan.alignment}",
    ]

    if plan.workplan and plan.workplan.groups:
        out.append("groups:")
        for g in plan.workplan.groups:
            deps = ",".join(g.depends_on) if g.depends_on else "MECE"
            task_ids = ",".join(t.id for t in g.tasks)
            out.append(f"  - {g.id} [concurrent={g.concurrent}, depends_on={deps}] tasks={task_ids}")
    else:
        out.append("groups: (none)")

    return "\n".join(out)


class OrchestratorLedger(BaseModel):
    """Thin state ledger mirroring `AgentDependencies`.

    Keeps the three orchestrator-tracked collections (`modified_files`,
    `global_decisions`, `blockers`) in lock-step with the canonical
    `AgentDependencies` contract so the conductor can serialize the whole
    ledger without inventing new symbols.
    """

    deps: AgentDependencies = Field(default_factory=AgentDependencies)
    modified_files: set[str] = Field(default_factory=set)
    global_decisions: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)

    def record_files(self, files: list[str]) -> None:
        """Record files touched this turn (ledger + AgentDependencies mirror)."""
        for f in files:
            self.modified_files.add(f)
            self.deps.modified_files.add(f)

    def note_decision(self, s: str) -> None:
        """Append a global decision (ledger + AgentDependencies mirror)."""
        self.global_decisions.append(s)
        self.deps.global_decisions.append(s)

    def note_blocker(self, s: str) -> None:
        """Append a blocker the conductor must escalate."""
        self.blockers.append(s)

    @property
    def tools_used(self) -> int:
        return self.deps.tools_used
