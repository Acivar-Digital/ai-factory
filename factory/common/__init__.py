"""factory.common — shared harness utilities (single source of truth).

Functions moved here from infra/*.py to prevent LLM-driven duplication:
  * log_operator  (was infra/tools.py:65)
  * _run_tool      (was infra/tools.py:549) — thin wrapper over _run_proc
  * _run_proc      (generic argv runner — SSoT for every harness subprocess)
  * registry: OUTPUT_TYPE_REGISTRY, resolve_model, resolve_run_dir
    (consolidates tools.OUTPUT_TYPE_MAP, factory._OUTPUT_TYPE_LOOKUP,
     runner.ROLE_OUTPUT, and divergent model/run-dir resolvers)

Any harness module that needs these MUST import from here, never redefine them.
The guardrail (TEST/agent_guardrail.py -> detect_duplicate_functions) enforces this.
"""

from factory.common.md_bridge import build_md_bridge
from factory.common.operator import log_operator
from factory.common.registry import (
    OUTPUT_TYPE_REGISTRY,
    ROLE_OUTPUT_TYPE,
    resolve_model,
    resolve_run_dir,
)
from factory.common.subprocess import _run_proc, _run_tool

__all__ = [
    "build_md_bridge",
    "log_operator",
    "_run_tool",
    "_run_proc",
    "OUTPUT_TYPE_REGISTRY",
    "ROLE_OUTPUT_TYPE",
    "resolve_model",
    "resolve_run_dir",
]
