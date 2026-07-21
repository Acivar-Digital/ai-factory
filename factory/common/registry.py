"""Shared harness registries + resolvers — single source of truth.

Consolidates three behavioral duplicates that lived under different names in
infra/tools.py (OUTPUT_TYPE_MAP), infra/factory.py (_OUTPUT_TYPE_LOOKUP, dead),
and infra/runner.py (ROLE_OUTPUT): one canonical output-type registry, one
model-key resolver, and one bd_id->run-dir resolver.

Cycle-safe: imports only control + models (neither imports common).
"""

import re
from pathlib import Path

from pydantic_ai.models.openai import OpenAIChatModel

from factory.infra.control import (
    CONTROL_SHEET,
    REPORTS_DIR,
    SKILL_MAP,
    TEMP_DIR,
)
from factory.infra.models import (
    ApprovedPlan,
    AuditResult,
    CodePassed,
    CompactedContext,
    DraftPlan,
    GitResult,
    ReviewResult,
    TaskBatch,
    TaskResult,
)

# output_type string -> concrete models.py Pydantic class (built from models.py).
# Canonical SSoT: replaces tools.OUTPUT_TYPE_MAP, factory._OUTPUT_TYPE_LOOKUP,
# runner.ROLE_OUTPUT (all three carried the same 6+ classes under 3 keyings).
OUTPUT_TYPE_REGISTRY: dict[str, type] = {
    "DraftPlan": DraftPlan,
    "ApprovedPlan": ApprovedPlan,
    "TaskResult": TaskResult,
    "TaskBatch": TaskBatch,
    "CodePassed": CodePassed,
    "ReviewResult": ReviewResult,
    "AuditResult": AuditResult,
    "GitResult": GitResult,
    "CompactedContext": CompactedContext,
    "str": str,
}

# role name -> output-type NAME (e.g. "supervisor_plan" -> "ApprovedPlan").
# Derived from SKILL_MAP (the role->spawn-binding SSoT) so a role's
# expected output type stays defined in ONE place. Replaces the old
# runner.ROLE_OUTPUT dict that the pqr2 refactor dropped — callers that
# resolve a role's output model MUST go role -> ROLE_OUTPUT_TYPE -> registry,
# never index OUTPUT_TYPE_REGISTRY directly by role name.
ROLE_OUTPUT_TYPE: dict[str, str] = {
    role: entry.output_type for role, entry in SKILL_MAP.roles.items()
}


def resolve_model(key: str) -> OpenAIChatModel:
    """Resolve a ``model_key`` to its ``OpenAIChatModel`` from the ControlSheet.

    Fails LOUDLY (KeyError HALT) when the key is absent — mirrors
    ControlSheet.model() so callers can drop their own unguarded
    ``CONTROL_SHEET.models[key]`` lookups (which raise a bare KeyError).
    """
    if key not in CONTROL_SHEET.models:
        raise KeyError(
            f"[HALT] model_key {key!r} not in CONTROL_SHEET.models"
        )
    return CONTROL_SHEET.models[key]


_RUN_DIR_RE = re.compile(r"^run_(?P<ts>[\dT]+)_(?P<bd>.+)$")


def resolve_run_dir(
    bd_id: str,
    reports_dir: Path | None = None,
    temp_dir: Path | None = None,
) -> Path | None:
    """Resolve ``bd_id`` to its ``run_<ts>_<bd_id>`` directory.

    Scans ``REPORTS_DIR`` for the NEWEST ``run_*_<bd_id>`` dir that holds a
    ``state.json`` (so crash-resume resumes the latest run), then falls back to
    ``TEMP_DIR/<bd_id>`` if no reports dir matches. Replaces the divergent
    copies in state.py (reports-only) and runner.py (reports + temp fallback,
    looser glob).
    """
    base = reports_dir or REPORTS_DIR
    candidates: list[tuple[str, Path]] = []
    if base.exists():
        for d in base.iterdir():
            m = _RUN_DIR_RE.match(d.name)
            if m and m.group("bd") == bd_id and (d / "state.json").exists():
                candidates.append((m.group("ts"), d))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    fallback = temp_dir or TEMP_DIR
    cand = fallback / bd_id
    if cand.exists():
        return cand
    return None
