"""Operator-facing logging — single source of truth for `log_operator`.

Moved from infra/tools.py so every harness module shares ONE implementation
instead of the LLM re-creating divergent copies.
"""

import logging

_logger = logging.getLogger("orchestrator.common")


def log_operator(message: str, level: str = "WARNING") -> None:
    """Surface a fault/security event to the operator.

    Prints with a high-visibility prefix (guaranteed channel through the
    TeeLogger -> run.log) AND emits a logging record so it lands in the Python
    log/handlers. We never let instrumentation hide the event: print happens
    first, and a logging failure is non-fatal (the alert is already on stdout).
    """
    print(f"[OPERATOR][{level}] {message}", flush=True)
    try:
        getattr(_logger, level.lower(), _logger.warning)(message)
    except Exception:
        pass
