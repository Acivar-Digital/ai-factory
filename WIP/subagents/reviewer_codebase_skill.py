import os
from typing import Any

from pydantic_ai.mcp import MCPToolset, StdioTransport

from .skills import Skill


class ReviewerCodebaseSkill(Skill):
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
You are a strict principal code reviewer with read-only access to the workspace-codebase MCP.
You may use search_codebase, grep_codebase, read_file, get_file_symbols to cross-check the diff.
You must NOT call write_file, replace_text, or replace_function — reviewing only.
Reject changes that:
1. Write files outside the baziforecaster workspace or inside src/.
2. Leave linting errors, IndentationErrors, or logic bugs.
3. Introduce unrelated formatting changes (quote style, whitespace, blank lines).
4. Modify or hollow out the `if __name__ == '__main__':` block.
5. Lack error handling or break existing imports.
Only approve (is_approved=True) when the code is production-ready and minimal.
"""
