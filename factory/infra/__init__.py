"""Orchestrator infra — pipeline, agents, tooling."""
from factory.infra.runner import main
from factory.infra.exchange import (
    TeeLogger, ExchangeTurn, update_status_board, load_exchange,
    save_exchange, format_exchange, append_exchange_turn, mark_recovered,
    mark_compaction, _model_to_md, _render_verdict_block, compact_exchange_transcript,
)
from factory.infra.control import (
    REPO_ROOT, TEMP_DIR, RUNTIME_DIR, STATUS_MD, LOGS_DIR,
    CONTROL_SHEET, SKILL_MAP, settings, DEFAULT_AGENT_SETTINGS,
    ROLE_AGENT_SETTINGS, MAX_AGENTS,
)
from factory.infra._runtime import (
    RAW_OUTPUTS, PHASE_SUMMARIES, SCOPE_CONTEXT,
    _PHASE_ORDER, _SKIPPED_PHASES, _RECOVERY_COUNT, _COMPACTION_COUNT,
)
from factory.infra.ast_verifier import (
    verify_refactored_ast,
    run_lint_regression,
    extract_header_symbol_contract,
)
from factory.infra.ast_analyzer import scan_file_for_anti_patterns
from factory.infra.virtual_ast_buffer import (
    VirtualASTBuffer,
    ensure_pydantic_imports,
    extract_function_node_source,
    stitch_function_node_source,
)

__all__ = [
    "main",
    "TeeLogger", "ExchangeTurn", "update_status_board",
    "load_exchange", "save_exchange", "format_exchange",
    "append_exchange_turn", "mark_recovered", "mark_compaction",
    "compact_exchange_transcript", "_model_to_md", "_render_verdict_block",
    "REPO_ROOT", "TEMP_DIR", "RUNTIME_DIR", "STATUS_MD", "LOGS_DIR",
    "CONTROL_SHEET", "SKILL_MAP", "settings",
    "RAW_OUTPUTS", "PHASE_SUMMARIES", "SCOPE_CONTEXT",
    "_PHASE_ORDER", "_SKIPPED_PHASES", "_RECOVERY_COUNT", "_COMPACTION_COUNT",
    "DEFAULT_AGENT_SETTINGS", "ROLE_AGENT_SETTINGS", "MAX_AGENTS",
    "verify_refactored_ast", "run_lint_regression", "extract_header_symbol_contract",
    "extract_function_node_source", "stitch_function_node_source",
    "scan_file_for_anti_patterns",
    "VirtualASTBuffer", "ensure_pydantic_imports",
]
