import os
from typing import Any

from pydantic_ai.mcp import MCPToolset, StdioTransport

from .skills import Skill


class CodebaseSkill(Skill):
    def __init__(self):
        mcp_python = "/home/yapilwsl/arthityap/infra/codebase/.venv/bin/python"
        mcp_script = "/home/yapilwsl/arthityap/infra/codebase/mcp_codebase.py"
        os.environ["FASTMCP_SHOW_SERVER_BANNER"] = "false"
        self._tools = MCPToolset(StdioTransport(mcp_python, args=[mcp_script]))

    @property
    def toolsets(self) -> list[Any]:
        return [self._tools]

    @property
    def instructions(self) -> str:
        return """
MANDATORY READ-FIRST PROTOCOL (before writing ANY file):
1. Use grep_codebase to find the exact class/function names in the target file.
2. Use read_file with the exact line range to read the code you are about to modify.
3. Only after reading and quoting the existing code may you propose and write changes.

REPLACEMENT TOOL TIPS:
- PREFER `replace_function` over `replace_text` for updating entire functions/methods. It uses AST parsing so you do not have to worry about exact preceding whitespace.
- When using `replace_function`, the `new_function_code` MUST contain the fully valid new function, correctly indented relative to itself (e.g. starting with `    def ...` if it's a class method).
- If you MUST use `replace_text`, remember that the `old_text` must be a PIXEL-PERFECT match to the existing file, including all exact leading spaces, tabs, and newlines.

WRITING RULES:
4. Use write_file ONLY when creating a brand-new file. Never use it to overwrite an existing file.
5. Never modify files inside the src/ folder — only src2/, admin/, migrations/.
6. Keep changes minimal. Do NOT reformat unrelated lines or change quote styles.

VERIFICATION RULES:
7. If the task provides a VERIFY COMMAND (like `uv run ruff check`), you MUST use the `run_shell_command` tool to execute it.
8. Do NOT guess or hallucinate tool names like `run_verify`.
9. Ensure the shell command passes with exit code 0 before completing your turn.
"""
