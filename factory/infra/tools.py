"""Tool confinement for the Orchestrator State Machine (build.md §4, §5c).

Every worker capability is a subprocess wrapper around an existing
`factory/tools/*.py` CLI. Agents NEVER touch the filesystem directly — they
receive only the allow-listed, ACL-wrapped tools the orchestrator hands them.
"""

from factory.infra.tools_guard import UNTRUSTED_OPEN
from factory.infra.tools_guard import UNTRUSTED_CLOSE
from factory.infra.tools_guard import CONTEXT_OPEN
from factory.infra.tools_guard import CONTEXT_CLOSE
from factory.infra.tools_guard import detect_prompt_injection
from factory.infra.tools_guard import wrap_untrusted_task
from factory.infra.tools_guard import wrap_injected_context
from factory.infra.tools_guard import DEFAULT_TOOL_BUDGET
from factory.infra.tools_guard import CODER_BUDGET_BASE
from factory.infra.tools_guard import CODER_BUDGET_PER_FILE
from factory.infra.tools_guard import CODER_BUDGET_MIN
from factory.infra.tools_guard import CODER_BUDGET_MAX
from factory.infra.tools_guard import READ_FORGIVE_BUDGET
from factory.infra.tools_file import normalize_read_path
from factory.infra.tools_guard import GuardToolset
from factory.infra.tools_guard import ROLE_TOOL_BUDGET
from factory.infra.tools_guard import guard_tools
from factory.infra.tools_guard import pydantic_ai_default_block
from factory.infra.tools_guard import log_prompt_sent
from factory.infra.tools_guard import log_run_prompt
from factory.infra.tools_guard import log_response_raw
from factory.infra.tools_skill import MAX_FORGE_ITERS
from factory.infra.tools_file import read_file
from factory.infra.tools_file import batch_read
from factory.infra.tools_context import investigate
from factory.infra.tools_context import search
from factory.infra.tools_context import list_files
from factory.infra.tools_context import get_file_symbols
from factory.infra.tools_context import get_repo_structure
from factory.infra.tools_context import query_knowledge_graph
from factory.infra.tools_context import find_related_code
from factory.infra.tools_context import get_code_hierarchy
from factory.infra.tools_file import write_file
from factory.infra.tools_shell import replace_text
from factory.infra.tools_shell import replace_function
from factory.infra.tools_shell import add_constant
from factory.infra.tools_shell import add_import
from factory.infra.tools_file import delete_file
from factory.infra.tools_file import rename_file
from factory.infra.tools_shell import move_symbol, verify_edit
from factory.infra.tools_memory import set_current_role
from factory.infra.tools_memory import get_current_role
from factory.infra.tools_memory import set_current_agent
from factory.infra.tools_memory import get_current_agent
from factory.infra.tools_memory import remember
from factory.infra.tools_memory import keep_memory
from factory.infra.tools_memory import record_plan
from factory.infra.tools_guard import _READ_FATAL
from factory.infra.tools_guard import _READ_REDUNDANT
from factory.infra.tools_guard import _within_repo
from factory.infra.tools_guard import _acl_allows
from factory.infra.tools_guard import _log_acl_denied
from factory.infra.tools_guard import _coder_budget_for
from factory.infra.tools_guard import _tool_budget_for
from factory.infra.tools_guard import READ_ONLY_TOOLS
from factory.infra.tools_guard import READ_FILE_TOOLS
from factory.infra.tools_guard import MODIFY_TOOLS
from factory.infra.tools_guard import TOOL_REGISTRY
from factory.infra.tools_guard import TOOL_REGISTRY_KEYS
from factory.infra.tools_guard import CODING_PHILOSOPHY_BLOCK
from factory.infra.tools_guard import _DISCOVERY_TOOLS
from factory.infra.tools_guard import _TOOL_BY_NAME
from factory.infra.tools_skill import build_tool_usage_guide
from factory.infra.tools_guard import wrap_with_acl
from factory.infra.tools_skill import SkillSpec
from factory.infra.tools_skill import build_skill_spec
from factory.infra.tools_skill import load_skill_spec
from factory.infra.tools_skill import load_skill
from factory.infra.tools_skill import forge_skill_spec
from factory.infra.tools_skill import forge_skill
from factory.infra.tools_skill import build_worker_spec
from factory.infra.tools_const import MAX_BATCH_FILES, CODER_WRITE_ROOTS, _BATCH_READ_DEFAULT_HEAD, _BATCH_READ_NO_PATHS, _BATCH_READ_STEER
from factory.infra.tools_guard import _is_secret_path
from factory.infra.tools_skill import _build_repo_map
from factory.common import _run_tool
from factory.infra.control import PKG_DIR, ORCH_ROOT

__all__ = ['UNTRUSTED_OPEN', 'UNTRUSTED_CLOSE', 'CONTEXT_OPEN', 'CONTEXT_CLOSE', 'detect_prompt_injection', 'wrap_untrusted_task', 'wrap_injected_context', 'DEFAULT_TOOL_BUDGET', 'CODER_BUDGET_BASE', 'CODER_BUDGET_PER_FILE', 'CODER_BUDGET_MIN', 'CODER_BUDGET_MAX', 'MAX_BATCH_FILES', 'READ_FORGIVE_BUDGET', 'CODER_WRITE_ROOTS', 'normalize_read_path', 'GuardToolset', 'ROLE_TOOL_BUDGET', 'guard_tools', 'pydantic_ai_default_block', 'log_prompt_sent', 'log_run_prompt', 'log_response_raw', 'MAX_FORGE_ITERS', 'read_file', 'batch_read', 'investigate', 'search', 'list_files', 'get_file_symbols', 'get_repo_structure', 'query_knowledge_graph', 'find_related_code', 'get_code_hierarchy', 'write_file', 'replace_text', 'replace_function', 'add_constant', 'add_import', 'delete_file', 'rename_file', 'move_symbol', 'verify_edit', 'set_current_role', 'get_current_role', 'set_current_agent', 'get_current_agent', 'remember', 'keep_memory', 'record_plan', 'READ_ONLY_TOOLS', 'READ_FILE_TOOLS', 'MODIFY_TOOLS', 'TOOL_REGISTRY', 'TOOL_REGISTRY_KEYS', 'CODING_PHILOSOPHY_BLOCK', '_DISCOVERY_TOOLS', '_TOOL_BY_NAME', 'build_tool_usage_guide', 'wrap_with_acl', 'SkillSpec', 'build_skill_spec', 'load_skill_spec', 'load_skill', 'forge_skill_spec', 'forge_skill', 'build_worker_spec', '_BATCH_READ_DEFAULT_HEAD', '_BATCH_READ_NO_PATHS', '_BATCH_READ_STEER', '_coder_budget_for', '_tool_budget_for', '_READ_FATAL', '_READ_REDUNDANT', '_within_repo', '_acl_allows', '_is_secret_path', '_log_acl_denied', '_build_repo_map', '_run_tool', 'PKG_DIR', 'ORCH_ROOT']
