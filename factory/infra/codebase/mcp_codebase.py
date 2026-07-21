"""
MCP Codebase Server for baziforecaster.

Tools exposed to the LLM:
  2. read_file             - read any file in the repo by relative path
  3. list_files            - list all files under a directory (with extension filter)
  4. get_repo_structure    - tree view of the full project structure
  5. get_file_symbols      - list all classes/functions in a Python file (AST)
  6. grep_codebase         - literal text / regex search across the repo
  7. write_file            - create or overwrite files with formatting, validation, and indexing
  8. edit_file             - unified codebase edits (replace_function, add_import, add_constant, text_replace)
  9. delete_file           - remove files and clean index synchronously
  10. rename_file          - move/rename files and sync index synchronously
  11. remember_fact        - persist non-code knowledge across sessions
  12. recall_fact          - retrieve previously persisted facts
  13. list_facts           - list all currently persisted facts
  14. create_execution_plan - save a structured execution plan (JSON)
  15. move_symbol           - move code between files and update imports repo-wide
  16. build_repo_graph     - machine-readable dependency mapping with attribute support
  17. explain_failure      - automated context gathering for error diagnosis
  18. count_lines          - count the number of lines in one or more files
  19. verify_file_path     - resolve and verify a file/directory path exists
"""

import ast
import asyncio
import datetime
import json
import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Dict

import libcst as cst
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

# Shim for libcst 1.0+
if not hasattr(cst, "AsyncFunctionDef"):
    cst.AsyncFunctionDef = cst.FunctionDef


import sys

_codebase_dir = str(Path(__file__).resolve().parent)
if _codebase_dir not in sys.path:
    sys.path.insert(0, _codebase_dir)

from dotenv import load_dotenv
from fastmcp import FastMCP
from indexer_core import index_single_file, remove_single_file
from config import STANDARD_DIRS

try:
    from mcp_watcher import run_preflight, start_embedded_watcher
except ImportError as e:
    import sys
    print(f"Failed to import mcp_watcher: {e}", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Suppress FastMCP informational logs to prevent JSON-RPC corruption on stdout
logging.basicConfig(level=logging.ERROR)
logging.getLogger("fastmcp").setLevel(logging.ERROR)

TARGET_ROOT = Path(os.getenv("TARGET_ROOT", os.getenv("CWD", Path.cwd()))).resolve()
PROJECT_ROOT = TARGET_ROOT
INFRA_ROOT = Path(__file__).resolve().parents[3]

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

INDEX_PATH = INFRA_ROOT / "temp" / "codebase" / "index.json"
FACTS_PATH = INFRA_ROOT / "temp" / "codebase" / "codebase_facts.json"
GRAPH_JSON = INFRA_ROOT / "temp" / "graph" / "code_knowledge_graph.json"

BGEM3_URL = os.getenv("BGEM3_URL", "http://localhost:8002/v1/embeddings")
BGEM3_TOKEN = os.getenv("BGEM3_TOKEN")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
if not BGEM3_TOKEN:
    logging.warning("BGEM3_TOKEN not set; semantic matching will fallback to keyword search.")

# Files/dirs to ignore
EXCLUDE_DIRS = {"__pycache__", ".git", ".venv", "node_modules", ".agent", ".gemini"}
INCLUDE_EXTENSIONS = {".py", ".md", ".json", ".txt", ".yaml", ".yml", ".toml", ".sql", ".sh"}

mcp = FastMCP(os.getenv("MCP_NAME", "baziforecaster-code"))


def _get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _graph_load() -> dict | None:
    """Load the knowledge graph from disk."""
    if not GRAPH_JSON.exists():
        return None
    try:
        return json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logging.warning(f"Knowledge graph JSON is corrupted: {e}")
        return None
    except Exception as e:
        logging.warning(f"Failed to load knowledge graph: {e}")
        return None


def _safe_relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _is_syntax_valid(path: Path) -> bool:
    """Verifies if a Python file is currently healthy."""
    if path.suffix != ".py":
        return True
    try:
        ast.parse(path.read_text(encoding="utf-8"))
        return True
    except SyntaxError:
        return False


def _normalize_content(text: str) -> str:
    """Standardizes whitespace (NBSP to ASCII 0x20) and line endings."""
    # Replace non-breaking spaces
    text = text.replace("\u00a0", " ")
    # Normalize line endings to Unix style
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def _atomic_write(path: Path, content: str) -> None:
    """Writes content to a temporary file then replaces target to ensure atomicity and durability."""
    content = _normalize_content(content)
    # PID + Thread + Random namespaced temp file to prevent collisions
    import random

    suffix = f"{os.getpid()}_{threading.get_ident()}_{random.randint(0, 1000)}"
    temp_path = path.with_suffix(f".tmp_{suffix}")
    try:
        # Strict UTF-8 enforcement
        with open(temp_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            # Physical disk flush
            os.fsync(f.fileno())

        # OS-level atomic replace with retry for Windows concurrency
        import time

        for _ in range(5):
            try:
                temp_path.replace(path)
                break
            except PermissionError:
                time.sleep(0.05)
        else:
            temp_path.replace(path)  # Final attempt
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _resolve_secure_path(relative_path: str) -> Path:
    """Resolves a path and ensures it stays within PROJECT_ROOT."""
    try:
        root = PROJECT_ROOT.resolve()
        target = (root / relative_path).resolve()

        # Strip the repo prefix if it comes from Qdrant payloads indexed at the infra level
        if relative_path.startswith(f"{root.name}/"):
            stripped_relative = relative_path[len(f"{root.name}/") :]
            target_stripped = (root / stripped_relative).resolve()
            
            if target.exists():
                resolved = target
            elif target_stripped.exists():
                resolved = target_stripped
            elif target.parent.exists():
                resolved = target
            elif target_stripped.parent.exists():
                resolved = target_stripped
            else:
                resolved = target_stripped
        elif relative_path == root.name:
            resolved = root
        else:
            resolved = target

        if not resolved.is_relative_to(root):
            # Security warning for directory traversal attempts
            raise ValueError(f"Path escape detected: {relative_path}")
        return resolved
    except Exception as e:
        raise ValueError(f"Invalid path: {relative_path} ({str(e)})")


def _get_import_insert_index(module: cst.Module) -> int:
    """Calculates the optimal PEP 8 insertion point, skipping shebangs, encodings, and docstrings."""
    last_import_idx = -1
    docstring_idx = -1
    shebang_idx = -1
    encoding_idx = -1

    for i, node in enumerate(module.body):
        if isinstance(node, cst.SimpleStatementLine):
            for item in node.body:
                if isinstance(item, (cst.Import, cst.ImportFrom)):
                    last_import_idx = i
                elif (
                    i == 0
                    or (shebang_idx != -1 and i == shebang_idx + 1)
                    or (encoding_idx != -1 and i == encoding_idx + 1)
                ):
                    if isinstance(item, cst.Expr) and isinstance(
                        item.value, (cst.SimpleString, cst.ConcatenatedString)
                    ):
                        docstring_idx = i
        elif i == 0 and isinstance(node, cst.Comment) and node.value.startswith("#!"):
            shebang_idx = i
        elif (i == 0 or (shebang_idx != -1 and i == 1)) and isinstance(node, cst.Comment) and "coding:" in node.value:
            encoding_idx = i

    # Optimal insertion is after the last import
    if last_import_idx != -1:
        return last_import_idx + 1
    # Failing that, after the docstring
    if docstring_idx != -1:
        return docstring_idx + 1
    # Failing that, after the encoding declaration
    if encoding_idx != -1:
        return encoding_idx + 1
    # Failing that, after the shebang
    if shebang_idx != -1:
        return shebang_idx + 1
    # Default to top of file
    return 0


def _finalize_edit_with_rollback(path: Path, original_content: str) -> str | None:
    """Rolls back ONLY if the new change broke a previously healthy file."""
    if path.suffix != ".py":
        return None
    try:
        ast.parse(path.read_text(encoding="utf-8"))
        return None
    except SyntaxError as e:
        _atomic_write(path, original_content)
        return f"SyntaxError introduced: {e.msg} at line {e.lineno}. Changes rolled back."


def _cleanup_ghost_processes() -> None:
    """Search for and terminate any existing instances of this MCP server in the background."""

    def _target():
        import os
        import subprocess
        import time

        try:
            # Short sleep to avoid racing with the current process's handshake
            time.sleep(1.0)
            current_pid = os.getpid()

            if os.name == "nt":
                # Get parent PID (the wrapper like uv.exe) to protect it
                parent_cmd = f'(Get-CimInstance Win32_Process -Filter "ProcessId = {current_pid}").ParentProcessId'
                parent_res = subprocess.run(["powershell", "-Command", parent_cmd], capture_output=True, text=True)
                parent_pid = parent_res.stdout.strip() or "0"

                # Target ONLY python processes with the script name, excluding self and wrapper
                cmd = (
                    f"Get-CimInstance Win32_Process | "
                    f'Where-Object {{ ($PSItem.CommandLine -like "*python*mcp_codebase.py*") '
                    f"-and $PSItem.ProcessId -ne {current_pid} "
                    f"-and $PSItem.ProcessId -ne {parent_pid} }} | "
                    f"ForEach-Object {{ Stop-Process -Id $PSItem.ProcessId -Force -ErrorAction SilentlyContinue }}"
                )
                subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True)
            else:
                # Unix-like: pkill with surgical pattern
                # Exclude current PID using negative lookahead or simple grep filter
                cmd = f"pgrep -f 'python.*mcp_codebase.py' | grep -v '^{current_pid}$' | xargs -r kill -9"
                subprocess.run(cmd, shell=True, capture_output=True)
        except Exception:
            pass

    import threading

    threading.Thread(target=_target, daemon=True).start()


# ---------------------------------------------------------------------------
# Tool 2 — Read File
# ---------------------------------------------------------------------------


@mcp.tool()
def read_file(
    relative_path: Annotated[str, "Path relative to project root."],
    start_line: Annotated[int | None, "First line to read (1-indexed)."] = None,
    end_line: Annotated[int | None, "Last line to read (inclusive)."] = None,
) -> dict[str, Any]:
    """Read a specific line range of a file in the repo."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"File not found: {relative_path}"}

        content = _normalize_content(path.read_text(encoding="utf-8"))
        lines = content.splitlines()
        total_lines = len(lines)

        s = (start_line - 1) if start_line else 0
        e = end_line if end_line else total_lines
        paged = lines[s:e]

        return {
            "success": True,
            "message": f"Read lines {s + 1}-{min(e, total_lines)} from {relative_path}",
            "data": {
                "file_path": relative_path,
                "total_lines": total_lines,
                "start_line": s + 1,
                "end_line": min(e, total_lines),
                "is_truncated": e < total_lines,
                "content": "\n".join(paged),
            },
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to read {relative_path}: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 3 — List Files
# ---------------------------------------------------------------------------


@mcp.tool()
def list_files(
    directory: Annotated[str, "Relative path to directory (empty = project root)."] = "",
    extension_filter: Annotated[str | None, "Only return files with this extension, e.g. '.py'."] = None,
    recursive: Annotated[bool, "Whether to recurse into subdirectories (default True)."] = True,
    limit: Annotated[int, "Maximum number of files to return (default 500)."] = 500,
    offset: Annotated[int, "Number of files to skip for pagination."] = 0,
) -> dict[str, Any]:
    """List files in a repo directory with pagination."""
    try:
        base = _resolve_secure_path(directory) if directory else PROJECT_ROOT
        if not base.exists():
            return {
                "success": False,
                "message": f"Directory not found: {directory}",
                "error": {"type": "FileNotFoundError", "message": directory},
            }

        all_found: list[str] = []
        walker = os.walk(base) if recursive else [(str(base), [], os.listdir(base))]

        for root, dirs, files in walker:
            # print(f"Scanning {root}...")
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in sorted(files):
                fp = Path(root) / f
                if extension_filter:
                    if fp.suffix != extension_filter:
                        continue
                elif fp.suffix not in INCLUDE_EXTENSIONS:
                    continue

                all_found.append(_safe_relative(fp))

        all_found.sort()
        total_count = len(all_found)
        paged = all_found[offset : offset + limit]

        return {
            "success": True,
            "message": f"Found {total_count} files in {directory or 'root'}",
            "data": {
                "files": paged,
                "metadata": {
                    "total": total_count,
                    "returned": len(paged),
                    "offset": offset,
                    "limit": limit,
                    "is_truncated": (offset + limit) < total_count,
                },
            },
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to list files in {directory}: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 4 — Repo structure (tree)
# ---------------------------------------------------------------------------


@mcp.tool()
def get_repo_structure(
    max_depth: Annotated[int, "How many directory levels to show (default 4)."] = 4,
) -> dict[str, Any]:
    """Return an ASCII tree of the project structure."""
    try:
        lines: list[str] = []

        def _tree(path: Path, prefix: str, depth: int) -> None:
            if depth > max_depth:
                return
            try:
                entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
            except PermissionError:
                return

            entries = [e for e in entries if e.name not in EXCLUDE_DIRS]

            for i, entry in enumerate(entries):
                connector = "└── " if i == len(entries) - 1 else "├── "
                lines.append(f"{prefix}{connector}{entry.name}" + ("/" if entry.is_dir() else ""))
                if entry.is_dir():
                    extension = "    " if i == len(entries) - 1 else "│   "
                    _tree(entry, prefix + extension, depth + 1)

        lines.append(f"{PROJECT_ROOT.name}/")
        _tree(PROJECT_ROOT, "", 1)
        tree_str = "\n".join(lines)
        return {
            "success": True,
            "message": f"Project structure at {PROJECT_ROOT} (depth={max_depth})",
            "data": {"structure": tree_str},
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to get repo structure: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 5 — Python file symbols (AST)
# ---------------------------------------------------------------------------


@mcp.tool()
def get_file_symbols(
    relative_path: Annotated[str, "Path relative to project root."],
) -> dict[str, Any]:
    """List all classes and functions defined in a Python file."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"File not found: {relative_path}"}
        if path.suffix != ".py":
            return {"success": False, "message": "Not a Python file."}

        content = _normalize_content(path.read_text(encoding="utf-8"))
        tree = ast.parse(content)
        symbols = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                symbols.append({"name": node.name, "type": "class", "line": node.lineno})
                for child in node.body:
                    if isinstance(child, ast.FunctionDef):
                        symbols.append({"name": f"{node.name}.{child.name}", "type": "method", "line": child.lineno})
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append({"name": node.name, "type": "function", "line": node.lineno})

        return {
            "success": True,
            "message": f"Found {len(symbols)} symbols in {relative_path}",
            "data": {"symbols": symbols},
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to parse {relative_path}: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 6 — Grep (Regex/Literal)
# ---------------------------------------------------------------------------


@mcp.tool()
def grep_codebase(
    pattern: Annotated[str, "Text or regex to search for."],
    directory: Annotated[str, "Limit search to this subdirectory (empty = whole repo)."] = "",
    extension_filter: Annotated[str | None, "Only search files with this extension, e.g. '.py'."] = None,
    case_sensitive: Annotated[bool, "Default False."] = False,
    max_results: Annotated[int, "Cap results (default 50)."] = 50,
) -> dict[str, Any]:
    """Search for a literal string or regex pattern across the repo."""
    try:
        base = _resolve_secure_path(directory) if directory else PROJECT_ROOT
        results = []
        flags = 0 if case_sensitive else re.IGNORECASE

        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                fp = Path(root) / f
                if extension_filter and fp.suffix != extension_filter:
                    continue
                if fp.suffix not in INCLUDE_EXTENSIONS:
                    continue

                try:
                    content = _normalize_content(fp.read_text(encoding="utf-8"))
                    for i, line in enumerate(content.splitlines()):
                        if re.search(pattern, line, flags):
                            results.append({"file_path": _safe_relative(fp), "line": i + 1, "text": line.strip()})
                            if len(results) >= max_results:
                                return {
                                    "success": True,
                                    "message": f"Found max {max_results} results",
                                    "data": {"results": results},
                                }
                except Exception:
                    continue

        return {"success": True, "message": f"Found {len(results)} results", "data": {"results": results}}
    except Exception as e:
        return {"success": False, "message": f"Grep failed: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 7 — Write File
# ---------------------------------------------------------------------------


def _finalize_and_verify_write(path: Path, relative_path: str, original_content: str | None) -> dict[str, Any]:
    """
    Centralized validation, auto-formatting, lint checking, and re-indexing.
    If any check fails, rolls back the file to original_content and returns the error.
    """
    import logging
    import subprocess

    # 1. Formatting and lint fixes (only for Python files)
    if path.suffix == ".py":
        try:
            # Run ruff format
            subprocess.run(["uv", "run", "ruff", "format", str(path)], capture_output=True, text=True, timeout=15)
            # Run ruff check --fix
            subprocess.run(
                ["uv", "run", "ruff", "check", "--fix", str(path)], capture_output=True, text=True, timeout=15
            )
        except Exception as e:
            logging.warning(f"Ruff format/fix failed: {e}")

        # 2. Run agent guardrail validation
        guardrail_script = PROJECT_ROOT / "TEST" / "agent_guardrail.py"
        if guardrail_script.exists():
            try:
                res = subprocess.run(
                    ["uv", "run", "python", str(guardrail_script), "validate", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if res.returncode != 0:
                    # Guardrail validation failed! Roll back!
                    if original_content is not None:
                        _atomic_write(path, original_content)
                    else:
                        if path.exists():
                            path.unlink()
                    return {
                        "success": False,
                        "message": f"Rejected: Guardrail validation failed:\n{res.stdout}\n{res.stderr}",
                    }
            except Exception as e:
                if original_content is not None:
                    _atomic_write(path, original_content)
                else:
                    if path.exists():
                        path.unlink()
                return {"success": False, "message": f"Validation execution error: {str(e)}"}

    # 3. Background re-indexing (Fire-and-forget to prevent timeouts on large files)
    try:
        collection_type = "docs" if path.suffix in (".md", ".txt") else "code"
        collection_name = f"baziforecaster_{collection_type}"

        def _bg_index():
            try:
                import asyncio
                asyncio.run(index_single_file("baziforecaster", collection_name, relative_path))
            except Exception as e:
                logging.error(f"Background re-indexing failed for {relative_path}: {e}")

        threading.Thread(target=_bg_index, daemon=True).start()
    except Exception as e:
        logging.warning(f"Failed to trigger background indexing: {e}")

    # Re-read actual bytes written for return metadata
    try:
        content_len = len(path.read_text(encoding="utf-8"))
    except Exception:
        content_len = 0

    return {
        "success": True,
        "message": f"Successfully finalized and indexed {relative_path}",
        "data": {"file_path": relative_path, "bytes": content_len},
    }


@mcp.tool()
def write_file(
    relative_path: Annotated[str, "Path relative to project root."],
    content: Annotated[str, "The full text content to write."],
) -> dict[str, Any]:
    """Write content to a file in the repo atomically with syntax validation."""
    try:
        path = _resolve_secure_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        original_content = None
        if path.exists():
            original_content = path.read_text(encoding="utf-8")

        content = _normalize_content(content)

        # Pre-write validation for Python files
        if path.suffix == ".py":
            try:
                ast.parse(content)
            except SyntaxError as e:
                return {
                    "success": False,
                    "message": f"Rejected: Change would introduce a SyntaxError: {e.msg} at line {e.lineno}",
                }

        _atomic_write(path, content)

        res = _finalize_and_verify_write(path, relative_path, original_content)
        return res
    except Exception as e:
        return {"success": False, "message": f"Failed to write {relative_path}: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 8 — Replace In File (Hardened)
# ---------------------------------------------------------------------------


class EditFileInput(BaseModel):
    relative_path: str = Field(description="Path of the file to edit, relative to the project root.")
    edit_type: Literal["replace_function", "add_import", "add_constant", "text_replace", "replace_text"] = Field(
        description="The method to use for editing the file."
    )
    function_name: str | None = Field(
        default=None, description="For 'replace_function': Name of the function to replace."
    )
    new_function_code: str | None = Field(default=None, description="For 'replace_function': The new implementation.")
    class_name: str | None = Field(
        default=None, description="For 'replace_function': Optional class name containing the function."
    )
    import_code: str | None = Field(default=None, description="For 'add_import': The import statement.")
    constant_name: str | None = Field(default=None, description="For 'add_constant': The variable name.")
    constant_code: str | None = Field(
        default=None, description="For 'add_constant': The value or assignment statement."
    )
    target_text: str | None = Field(default=None, description="For 'text_replace': Exact string or regex to replace.")
    replacement_text: str | None = Field(default=None, description="For 'text_replace': New text.")
    is_regex: bool = Field(default=False, description="For 'text_replace': Treat target_text as regex.")
    case_insensitive: bool = Field(default=False, description="For 'text_replace': Case insensitive match.")
    ignore_whitespace: bool = Field(
        default=False, description="For 'text_replace': Ignore differences in whitespace/formatting."
    )


@mcp.tool()
def replace_text(
    relative_path: str,
    target_text: str,
    replacement_text: str,
    is_regex: bool = False,
    case_insensitive: bool = False,
    ignore_whitespace: bool = False
) -> dict[str, Any]:
    """Replace exact text or regex in a file. Use this for general string replacements."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"File not found: {relative_path}"}
        original_content = path.read_text(encoding="utf-8")

        res = _replace_in_file(relative_path, target_text, replacement_text, is_regex, case_insensitive, ignore_whitespace)
        if isinstance(res, dict) and not res.get("success", False):
            return res

        return _finalize_and_verify_write(path, relative_path, original_content)
    except Exception as e:
        return {"success": False, "message": f"Failed to replace text: {str(e)}"}

@mcp.tool()
def replace_function(
    relative_path: str,
    function_name: str,
    new_function_code: str,
    class_name: str | None = None
) -> dict[str, Any]:
    """Replace an entire function's code using AST manipulation."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"File not found: {relative_path}"}
        original_content = path.read_text(encoding="utf-8")

        res = _ast_replace_function(relative_path, function_name, new_function_code, class_name)
        if isinstance(res, dict) and not res.get("success", False):
            return res

        return _finalize_and_verify_write(path, relative_path, original_content)
    except Exception as e:
        return {"success": False, "message": f"Failed to replace function: {str(e)}"}

@mcp.tool()
def add_constant(
    relative_path: str,
    constant_name: str,
    constant_code: str
) -> dict[str, Any]:
    """Add a top-level constant to a file using AST manipulation."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"File not found: {relative_path}"}
        original_content = path.read_text(encoding="utf-8")

        res = _ast_add_constant(relative_path, constant_name, constant_code)
        if isinstance(res, dict) and not res.get("success", False):
            return res

        return _finalize_and_verify_write(path, relative_path, original_content)
    except Exception as e:
        return {"success": False, "message": f"Failed to add constant: {str(e)}"}

@mcp.tool()
def add_import(
    relative_path: str,
    import_code: str
) -> dict[str, Any]:
    """Add a new import to the top of a file using AST manipulation."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"File not found: {relative_path}"}
        original_content = path.read_text(encoding="utf-8")

        res = _ast_add_import(relative_path, import_code)
        if isinstance(res, dict) and not res.get("success", False):
            return res

        return _finalize_and_verify_write(path, relative_path, original_content)
    except Exception as e:
        return {"success": False, "message": f"Failed to add import: {str(e)}"}



def _replace_in_file(
    relative_path: str,
    target_text: str,
    replacement_text: str,
    is_regex: bool = False,
    case_insensitive: bool = False,
    ignore_whitespace: bool = False,
) -> str | dict[str, Any]:
    """Helper to perform raw text replacement."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"File not found: {relative_path}"}

        original_content = path.read_text(encoding="utf-8")

        if ignore_whitespace:
            # Fuzzy match: Normalize dashes (en, em) and collapse whitespace
            def _norm(t):
                t = t.replace("\u2013", "-").replace("\u2014", "-")
                return " ".join(t.split())

            norm_content = _norm(original_content)
            norm_target = _norm(target_text)

            if not is_regex:
                regex_pattern = re.escape(norm_target).replace("\\ ", "\\s+")
            else:
                regex_pattern = norm_target

            flags = re.IGNORECASE if case_insensitive else 0
            if not re.search(regex_pattern, norm_content, flags):
                return {"success": False, "message": "Fuzzy target pattern not found."}

            new_content = re.sub(regex_pattern, replacement_text, norm_content, count=1, flags=flags)
        elif is_regex:
            flags = re.IGNORECASE if case_insensitive else 0
            if not re.search(target_text, original_content, flags):
                return {"success": False, "message": f"Regex pattern not found: {target_text}"}
            new_content = re.sub(target_text, replacement_text, original_content, flags=flags)
        else:
            if target_text not in original_content:
                return {"success": False, "message": "Exact text not found. Try ignore_whitespace=True."}
            new_content = original_content.replace(target_text, replacement_text)

        # Pre-write validation for Python files
        if path.suffix == ".py":
            try:
                ast.parse(new_content)
            except SyntaxError as e:
                return {
                    "success": False,
                    "message": f"Rejected: Replacement would introduce a SyntaxError: {e.msg} at line {e.lineno}",
                }

        _atomic_write(path, new_content)
        return new_content
    except Exception as e:
        return {"success": False, "message": f"Replacement failed: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 9 — Delete File
# ---------------------------------------------------------------------------


@mcp.tool()
def delete_file(
    relative_path: Annotated[str, "Path relative to project root."],
) -> dict[str, Any]:
    """Delete a file or directory from the repo and synchronously clean its vector index."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"Not found: {relative_path}"}

        # Delete from vector database synchronously
        import asyncio

        collection_type = "docs" if path.suffix in (".md", ".txt") else "code"
        collection_name = f"baziforecaster_{collection_type}"

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor() as executor:
                executor.submit(lambda: asyncio.run(remove_single_file(collection_name, relative_path))).result()
        else:
            asyncio.run(remove_single_file(collection_name, relative_path))

        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

        return {"success": True, "message": f"Deleted {relative_path} and cleaned its vector index"}
    except Exception as e:
        return {"success": False, "message": f"Failed to delete {relative_path}: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 10 — Rename File
# ---------------------------------------------------------------------------


@mcp.tool()
def rename_file(
    source_relative_path: Annotated[str, "Current relative path."],
    destination_relative_path: Annotated[str, "New relative path."],
) -> dict[str, Any]:
    """Rename or move a file/directory and update the vector index synchronously."""
    try:
        src = _resolve_secure_path(source_relative_path)
        dst = _resolve_secure_path(destination_relative_path)
        if not src.exists():
            return {"success": False, "message": f"Source not found: {source_relative_path}"}

        # 1. Synchronously remove old path vectors from Qdrant
        import asyncio

        src_collection = "baziforecaster_docs" if src.suffix in (".md", ".txt") else "baziforecaster_code"

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor() as executor:
                executor.submit(lambda: asyncio.run(remove_single_file(src_collection, source_relative_path))).result()
        else:
            asyncio.run(remove_single_file(src_collection, source_relative_path))

        # Rename the file on disk
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)

        # 2. Synchronously embed the new file path in Qdrant
        dst_collection = "baziforecaster_docs" if dst.suffix in (".md", ".txt") else "baziforecaster_code"
        if loop and loop.is_running():
            with ThreadPoolExecutor() as executor:
                executor.submit(
                    lambda: asyncio.run(index_single_file("baziforecaster", dst_collection, destination_relative_path))
                ).result()
        else:
            asyncio.run(index_single_file("baziforecaster", dst_collection, destination_relative_path))

        return {
            "success": True,
            "message": f"Moved {source_relative_path} to {destination_relative_path} and synced vector index",
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to rename: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 11 — AST Replace Function (Hardened)
# ---------------------------------------------------------------------------


class _FunctionReplacer(cst.CSTTransformer):
    def __init__(self, target_name: str, new_node: cst.FunctionDef, class_name: str | None = None):
        self.target_name = target_name
        self.new_node = new_node
        self.class_name = class_name
        self.replaced = False
        self._in_target_class = False

    def visit_ClassDef(self, node: cst.ClassDef) -> bool | None:  # noqa: N802
        if self.class_name and node.name.value == self.class_name:
            self._in_target_class = True
        return True

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef:  # noqa: N802
        if self.class_name and original_node.name.value == self.class_name:
            self._in_target_class = False
        return updated_node

    def leave_FunctionDef(  # noqa: N802
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef | cst.RemovalSentinel:
        if original_node.name.value == self.target_name:
            if self.class_name and not self._in_target_class:
                return updated_node
            self.replaced = True
            return self.new_node
        return updated_node


class _ConstantReplacer(cst.CSTTransformer):
    """Transformer to surgically replace Assign or AnnAssign values."""

    def __init__(self, name: str, new_value_node: cst.BaseExpression):
        self.name = name
        self.new_value_node = new_value_node
        self.replaced = False

    def leave_Assign(self, original_node: cst.Assign, updated_node: cst.Assign) -> cst.Assign:  # noqa: N802
        for target in original_node.targets:
            if isinstance(target.target, cst.Name) and target.target.value == self.name:
                self.replaced = True
                return updated_node.with_changes(value=self.new_value_node)
        return updated_node

    def leave_AnnAssign(self, original_node: cst.AnnAssign, updated_node: cst.AnnAssign) -> cst.AnnAssign:  # noqa: N802
        if isinstance(original_node.target, cst.Name) and original_node.target.value == self.name:
            self.replaced = True
            return updated_node.with_changes(value=self.new_value_node)
        return updated_node


def _ast_replace_function(
    relative_path: Annotated[str, "Path to target file."],
    function_name: Annotated[str, "Name of function to replace."],
    new_function_code: Annotated[str, "The new implementation (including any required imports)."],
    class_name: str | None = None,
) -> dict[str, Any]:
    """Deterministically replace a function and auto-inject its imports using LibCST."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"File not found: {relative_path}"}

        # Hardening: Clean provided code (strip backticks)
        code_to_parse = new_function_code.strip()
        if code_to_parse.startswith("```python"):
            code_to_parse = code_to_parse[9:]
        if code_to_parse.endswith("```"):
            code_to_parse = code_to_parse[:-3]
        code_to_parse = code_to_parse.strip()

        try:
            new_module = cst.parse_module(code_to_parse)
        except Exception as pe:
            return {"success": False, "message": f"Syntax error in new code: {str(pe)}"}

        new_func_node = None
        new_imports = []
        for node in new_module.body:
            if isinstance(node, (cst.FunctionDef, cst.AsyncFunctionDef)) and node.name.value == function_name:
                new_func_node = node
            elif isinstance(node, cst.SimpleStatementLine):
                # Imports in LibCST are typically wrapped in SimpleStatementLines
                for item in node.body:
                    if isinstance(item, (cst.Import, cst.ImportFrom)):
                        new_imports.append(node)

        if not new_func_node:
            return {"success": False, "message": f"New code does not contain a function named '{function_name}'."}

        original_content = _normalize_content(path.read_text(encoding="utf-8"))
        was_healthy = _is_syntax_valid(path)
        source_module = cst.parse_module(original_content)
        replacer = _FunctionReplacer(function_name, new_func_node, class_name)
        modified_module = source_module.visit(replacer)

        if not replacer.replaced:
            return {"success": False, "message": f"Target function '{function_name}' not found in {relative_path}."}

        final_body = list(modified_module.body)

        # Calculate optimal insertion point (PEP 8)
        insert_idx = _get_import_insert_index(modified_module)

        # Identify all existing imports for duplicate prevention
        existing_import_codes = set()
        for node in final_body:
            if isinstance(node, cst.SimpleStatementLine):
                for item in node.body:
                    if isinstance(item, (cst.Import, cst.ImportFrom)):
                        existing_import_codes.add(cst.Module([node]).code.strip())

        # Inject only if the new import line doesn't exist
        for imp_line in new_imports:
            if cst.Module([imp_line]).code.strip() not in existing_import_codes:
                final_body.insert(insert_idx, imp_line)
                insert_idx += 1

        _atomic_write(path, modified_module.with_changes(body=final_body).code)
        if was_healthy:
            err = _finalize_edit_with_rollback(path, original_content)
            return {
                "success": not bool(err),
                "message": err or f"Successfully replaced {function_name} in {relative_path}",
            }
        return {
            "success": True,
            "message": f"Replaced {function_name} (Warning: File was already syntactically broken)",
        }
    except Exception as e:
        return {"success": False, "message": f"AST replacement failed: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 12 — AST Add Constant
# ---------------------------------------------------------------------------


def _ast_add_constant(
    relative_path: Annotated[str, "Path to Python file."],
    name: Annotated[str, "Variable name."],
    code: Annotated[str, "Full assignment line or just the value code."],
) -> dict[str, Any]:
    """Add or update a top-level constant in a Python file using LibCST."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"File not found: {relative_path}"}

        original_content = _normalize_content(path.read_text(encoding="utf-8"))
        was_healthy = _is_syntax_valid(path)

        # Parse the new code to extract the value node
        try:
            code_normalized = _normalize_content(code.strip())
            temp_module = cst.parse_module(code_normalized)
            new_value_node = None
            for node in temp_module.body:
                if isinstance(node, cst.SimpleStatementLine):
                    for item in node.body:
                        if isinstance(item, cst.Assign):
                            new_value_node = item.value
                        elif isinstance(item, cst.AnnAssign):
                            new_value_node = item.value

            if not new_value_node:
                # If code was just a value like '{"key": "val"}'
                new_value_node = cst.parse_expression(code.strip())
        except Exception:
            return {"success": False, "message": "Failed to parse 'code' as a valid CST expression or assignment."}

        source_module = cst.parse_module(original_content)
        transformer = _ConstantReplacer(name, new_value_node)
        modified_module = source_module.visit(transformer)

        if transformer.replaced:
            _atomic_write(path, modified_module.code)
        else:
            # Constant not found, insert at optimal PEP 8 position
            final_body = list(modified_module.body)
            insert_idx = _get_import_insert_index(modified_module)

            # Construct the new assignment line
            new_line = cst.parse_module(f"{name} = {code.strip()}").body[0]
            final_body.insert(insert_idx, new_line)
            _atomic_write(path, modified_module.with_changes(body=final_body).code)

        if was_healthy:
            err = _finalize_edit_with_rollback(path, original_content)
            return {
                "success": not bool(err),
                "message": err or f"Successfully updated constant '{name}' in {relative_path}",
            }
        return {"success": True, "message": f"Updated {name} (Warning: File was already syntactically broken)"}
    except Exception as e:
        return {"success": False, "message": f"Failed to update constant: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 13 — AST Add Import
# ---------------------------------------------------------------------------


def _ast_add_import(
    relative_path: Annotated[str, "Path to Python file."],
    import_code: Annotated[str, "Import line (e.g. 'from os import path')."],
) -> dict[str, Any]:
    """Add a top-level import to a Python file."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"File not found: {relative_path}"}

        original_content = _normalize_content(path.read_text(encoding="utf-8"))
        was_healthy = _is_syntax_valid(path)
        if import_code.strip() in original_content:
            return {"success": True, "message": "Import already exists."}

        # Parse file to find PEP 8 insertion point
        source_module = cst.parse_module(original_content)
        final_body = list(source_module.body)
        insert_idx = _get_import_insert_index(source_module)

        new_imp_node = cst.parse_module(import_code.strip()).body[0]
        final_body.insert(insert_idx, new_imp_node)
        _atomic_write(path, source_module.with_changes(body=final_body).code)

        if was_healthy:
            err = _finalize_edit_with_rollback(path, original_content)
            return {"success": not bool(err), "message": err or f"Added import to {relative_path}"}
        return {
            "success": True,
            "message": f"Added import to {relative_path} (Warning: File was already syntactically broken)",
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to add import: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 14 — Clean Imports (Ruff)
# ---------------------------------------------------------------------------


@mcp.tool()
def ast_clean_imports(
    relative_path: Annotated[str, "Path to Python file."],
) -> dict[str, Any]:
    """Remove unused imports from a Python file using ruff."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"File not found: {relative_path}"}

        subprocess.run(
            ["uv", "run", "ruff", "check", "--select", "F401", "--fix", str(path)], capture_output=True, timeout=20
        )
        return {"success": True, "message": f"Cleaned imports in {relative_path}"}
    except Exception as e:
        return {"success": False, "message": f"Failed to clean imports: {str(e)}"}


# ---------------------------------------------------------------------------
# Facts Persistence
# ---------------------------------------------------------------------------


def _load_facts() -> dict[str, str]:
    if not FACTS_PATH.exists():
        return {}
    return json.loads(FACTS_PATH.read_text(encoding="utf-8"))


def _save_facts(facts: dict[str, str]) -> None:
    FACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(FACTS_PATH, json.dumps(facts, indent=2))


@mcp.tool()
def remember_fact(key: str, value: str) -> str:
    """Persist non-code knowledge across sessions."""
    facts = _load_facts()
    facts[key] = value
    _save_facts(facts)
    return f"Fact remembered: {key}"


@mcp.tool()
def recall_fact(key: str) -> str:
    """Retrieve a previously persisted fact."""
    facts = _load_facts()
    return facts.get(key, "Fact not found.")


@mcp.tool()
def list_facts() -> list[str]:
    """List all currently persisted non-code facts."""
    return list(_load_facts().keys())


# ---------------------------------------------------------------------------
# Symbol Movement
# ---------------------------------------------------------------------------


@mcp.tool()
def move_symbol(symbol_name: str, source_path: str, dest_path: str) -> dict[str, Any]:
    """
    Move a function or class between files and update imports.
    Surgically extracts node (including comments) and injects at optimal PEP 8 position.
    Implements transactional rollback to prevent data loss.
    """
    src_backup = None
    dst_backup = None
    try:
        src_p = _resolve_secure_path(source_path)
        dst_p = _resolve_secure_path(dest_path)

        if not src_p.exists() or not dst_p.exists():
            return {"success": False, "message": "Source or destination file not found."}

        # Backup current state for rollback
        src_backup = src_p.read_text(encoding="utf-8")
        dst_backup = dst_p.read_text(encoding="utf-8")

        # 1. Extraction & Deletion Pass
        src_content = _normalize_content(src_backup)
        src_module = cst.parse_module(src_content)

        class SymbolExtractor(cst.CSTTransformer):
            def __init__(self, name):
                self.name = name
                self.extracted_node = None
                self.deleted = False

            def leave_FunctionDef(self, original_node, updated_node):  # noqa: N802
                if original_node.name.value == self.name:
                    self.extracted_node = original_node
                    self.deleted = True
                    return cst.RemovalSentinel.REMOVE
                return updated_node

            def leave_ClassDef(self, original_node, updated_node):  # noqa: N802
                if original_node.name.value == self.name:
                    self.extracted_node = original_node
                    self.deleted = True
                    return cst.RemovalSentinel.REMOVE
                return updated_node

        extractor = SymbolExtractor(symbol_name)
        new_src_module = src_module.visit(extractor)

        if not extractor.extracted_node:
            return {"success": False, "message": f"Symbol '{symbol_name}' not found in {source_path}."}

        # 2. Injection Pass
        dst_content = _normalize_content(dst_backup)
        dst_module = cst.parse_module(dst_content)

        # Collision Check: Does this symbol already exist in the destination?
        class CollisionChecker(cst.CSTVisitor):
            def __init__(self, name):
                self.name = name
                self.collision = False

            def visit_FunctionDef(self, node):  # noqa: N802
                if node.name.value == self.name:
                    self.collision = True

            def visit_ClassDef(self, node):  # noqa: N802
                if node.name.value == self.name:
                    self.collision = True

        checker = CollisionChecker(symbol_name)
        dst_module.visit(checker)
        if checker.collision:
            return {
                "success": False,
                "message": f"Collision Error: Symbol '{symbol_name}' already exists in {dest_path}.",
            }

        final_body = list(dst_module.body)

        # Calculate optimal insertion point using centralized helper
        insert_idx = _get_import_insert_index(dst_module)
        final_body.insert(insert_idx, extractor.extracted_node)
        new_dst_module = dst_module.with_changes(body=final_body)

        # 3. Transactional Validation
        try:
            ast.parse(new_src_module.code)
            ast.parse(new_dst_module.code)
        except SyntaxError as e:
            return {"success": False, "message": f"Move would introduce SyntaxError: {str(e)}"}

        # 4. Atomic Two-Phase Commit with Rollback
        try:
            _atomic_write(src_p, new_src_module.code)
        except Exception as e:
            return {"success": False, "message": f"Source write failed: {str(e)}"}

        try:
            _atomic_write(dst_p, new_dst_module.code)
        except Exception as e:
            # Rollback source file deletion
            _atomic_write(src_p, src_backup)
            return {"success": False, "message": f"Destination write failed, rolled back source: {str(e)}"}

        # 5. Format, validate, and synchronously re-index both files
        finalize_src = _finalize_and_verify_write(src_p, source_path, src_backup)
        if not finalize_src["success"]:
            # Rollback both to backups
            _atomic_write(src_p, src_backup)
            _atomic_write(dst_p, dst_backup)
            return {"success": False, "message": f"Source post-write validation failed: {finalize_src['message']}"}

        finalize_dst = _finalize_and_verify_write(dst_p, dest_path, dst_backup)
        if not finalize_dst["success"]:
            # Rollback both to backups
            _atomic_write(src_p, src_backup)
            _atomic_write(dst_p, dst_backup)
            # Re-index source file to match backup state
            _finalize_and_verify_write(src_p, source_path, None)
            return {"success": False, "message": f"Destination post-write validation failed: {finalize_dst['message']}"}

        return {
            "success": True,
            "message": f"Successfully moved {symbol_name} from {source_path} to {dest_path} and synced index",
            "data": {"symbol": symbol_name, "from": source_path, "to": dest_path},
        }
    except Exception as e:
        return {"success": False, "message": f"Move failed: {str(e)}"}


# ---------------------------------------------------------------------------
# Graphing & Failure Diagnosis
# ---------------------------------------------------------------------------


@mcp.tool()
def build_repo_graph(max_nodes: int = 100) -> dict[str, Any]:
    """Build a machine-readable dependency mapping of repository modules."""
    nodes = {}
    edges = []

    try:
        # Walk project
        py_files = []
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                if f.endswith(".py"):
                    py_files.append(Path(root) / f)

        for fp in py_files[:max_nodes]:
            rel_path = _safe_relative(fp)
            content = _normalize_content(fp.read_text(encoding="utf-8"))

            # File metadata
            tree = ast.parse(content)
            classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
            functions = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

            nodes[rel_path] = {
                "line_count": len(content.splitlines()),
                "classes": classes,
                "functions": functions,
                "size": fp.stat().st_size,
                "last_modified": fp.stat().st_mtime,
            }

            # Extract imports for edges
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        edges.append({"from": rel_path, "to": alias.name, "type": "import", "internal": False})
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        target = node.module
                        # Relative Import Resolution with Physical Existence Check
                        targets = [node.module] if node.module else []
                        # Also check the imported names, as they might be modules
                        for alias in node.names:
                            if node.module:
                                targets.append(f"{node.module}.{alias.name}")
                            else:
                                targets.append(alias.name)

                        for target in targets:
                            final_target = target
                            if node.level > 0:
                                parts = list(fp.parents)
                                if node.level <= len(parts):
                                    parent_dir = parts[node.level - 1]
                                    resolved_path = (parent_dir / target.replace(".", os.sep)).resolve()

                                    if resolved_path.with_suffix(".py").exists():
                                        final_target = _safe_relative(resolved_path.with_suffix(".py"))
                                    elif (resolved_path / "__init__.py").exists():
                                        final_target = _safe_relative(resolved_path)
                                    else:
                                        continue

                            is_internal = final_target.startswith(("src", "codebase", "test")) or final_target.endswith(
                                ".py"
                            )
                            edges.append(
                                {"from": rel_path, "to": final_target, "type": "from_import", "internal": is_internal}
                            )

        return {
            "success": True,
            "message": f"Generated dependency graph with {len(nodes)} nodes.",
            "data": {"nodes": nodes, "edges": edges},
        }
    except Exception as e:
        return {"success": False, "message": f"Graph build failed: {str(e)}"}


@mcp.tool()
def explain_failure(error_message: str) -> str:
    """
    Surgical Failure Diagnosis (RCA Protocol).
    Isolates the deepest project-local frame and provides heuristic context.
    """
    try:
        # Regex to find File "path/to/file.py", line 123
        pattern = r'File "(.*?)", line (\d+)'
        matches = re.findall(pattern, error_message)

        if not matches:
            return f"Could not identify a specific failure point in the error message: {error_message}"

        # Resolve all paths and filter for those within PROJECT_ROOT
        project_frames = []
        for file_path_str, line_num_str in matches:
            p = Path(file_path_str)
            if not p.is_absolute():
                p = (PROJECT_ROOT / file_path_str).resolve()
            else:
                p = p.resolve()

            try:
                if p.is_relative_to(PROJECT_ROOT.resolve()):
                    project_frames.append((_safe_relative(p), int(line_num_str)))
            except ValueError:
                continue

        if not project_frames:
            return (
                f"The error occurred outside the project root (likely in a library). Traceback summary: {error_message}"
            )

        # Deepest project-local frame is the signal
        file_path_str, line_num = project_frames[-1]

        # Read ±10 lines of context with absolute mapping
        context_res = read_file(file_path_str, start_line=max(1, line_num - 10), end_line=line_num + 10)

        if not context_res["success"]:
            return f"Found failure at {file_path_str}:{line_num}, but failed to read context: {context_res['message']}"

        raw_snippet = context_res["data"]["content"]
        start_line_num = max(1, line_num - 10)
        prefixed_lines = []
        for i, line in enumerate(raw_snippet.splitlines()):
            prefixed_lines.append(f"{start_line_num + i}: {line}")
        snippet = "\n".join(prefixed_lines)

        # Heuristic Hint Layer
        hints = []
        if "KeyError" in error_message:
            hints.append(
                "- **Hint**: A dictionary key is missing. Check if the input Bazi data contains all required fields against the bazi_data.py schema."
            )
        elif "ModuleNotFoundError" in error_message or "ImportError" in error_message:
            hints.append(
                "- **Hint**: Import failure detected. If you recently moved a symbol or added a file, run `ast_clean_imports` or verify the relative import path."
            )
        elif "SyntaxError" in error_message:
            hints.append(
                "- **Hint**: Syntax error detected. If this happened after a programmatic edit, run `ast_clean_imports` to resolve potential namespace collisions or use `replace_file_content` for surgical fix."
            )
        elif "RecursionError" in error_message:
            hints.append(
                "- **Hint**: Infinite recursion detected. Check the Bazi cycle lookup logic or relationship calculations for circular references."
            )
        elif "Pillar" in error_message or "Stem" in error_message:
            hints.append(
                "- **Hint**: Calculation error in the core engine. Verify the deterministic lookup tables in engine/bazi_data.py."
            )

        report = [
            "### Principal Failure Diagnosis (RCA)",
            f"**Deepest Project Frame**: `{file_path_str}:{line_num}`",
            "**Context Window (Absolute Line Numbers)**:",
            "```python",
            snippet,
            "```",
            "**Analysis**: The error likely originates in this block.",
            "\n".join(hints)
            if hints
            else "**Analysis**: No specific heuristic hints found. Check variable states in the window above.",
            "**Next Step**: Use read_file to inspect the full module if variable state is unclear.",
        ]
        return "\n".join(report)
    except Exception as e:
        return f"Diagnostics failed: {str(e)}"


@mcp.tool()
def count_lines(files: list[str]) -> dict[str, int]:
    """Count the number of lines in one or more files."""
    counts = {}
    for f in files:
        try:
            path = _resolve_secure_path(f)
            counts[f] = len(path.read_text(encoding="utf-8").splitlines())
        except Exception:
            counts[f] = -1
    return counts


@mcp.tool()
def create_execution_plan(plan_data: dict[str, Any]) -> str:
    """Save a structured execution plan to execution_plan.json atomically."""
    path = _resolve_secure_path("execution_plan.json")
    _atomic_write(path, json.dumps(plan_data, indent=2))
    return f"Plan saved to {path} atomically."


# ---------------------------------------------------------------------------
# Tool 22 — Query Knowledge Graph
# ---------------------------------------------------------------------------


@mcp.tool()
def query_knowledge_graph(
    query: Annotated[str, "Natural language query over the code knowledge graph."],
    max_entities: Annotated[int, "Max entities to return (default 10)."] = 10,
) -> dict[str, Any]:
    """Query the code knowledge graph for structured entity/relationship results.

    Uses BGEM3 embeddings for semantic matching instead of substring search.
    Falls back to keyword overlap if embedding service is unavailable.
    """
    graph = _graph_load()
    if graph is None:
        return {
            "success": False,
            "message": "Knowledge graph not found. Run 'code_graph.py --build' first to generate code_knowledge_graph.json.",
            "data": {},
        }

    entities = graph.get("entities", [])
    if not entities:
        return {
            "success": True,
            "message": "Graph has no entities.",
            "data": {"entities": [], "relationships": []},
        }

    # --- Semantic matching via BGEM3 embeddings ---
    matched_entities = _graph_semantic_match(query, entities, max_entities)

    # --- Relationship traversal: find relationships involving matched entities ---
    matched_names = {e["name"].lower() for e in matched_entities}
    related_rels = []
    for rel in graph.get("relationships", []):
        src_low = rel["source"].lower()
        tgt_low = rel["target"].lower()
        if src_low in matched_names or tgt_low in matched_names:
            related_rels.append(rel)

    return {
        "success": True,
        "message": f"Found {len(matched_entities)} entities and {len(related_rels)} relationships.",
        "data": {
            "entities": matched_entities,
            "relationships": related_rels[: max_entities * 5],
        },
    }


def _graph_semantic_match(query: str, entities: list[dict], max_entities: int) -> list[dict]:
    """Score entities via BGEM3 embedding cosine similarity.

    Uses pre-computed embeddings when available in entity["embedding"].
    Falls back to keyword overlap if the embedding service is unavailable.
    """
    if not entities:
        return []

    # Cap query length to prevent DoS
    if len(query) > 4096:
        query = query[:4096]
        logging.warning("Query truncated to 4096 chars for embedding.")

    # Check for pre-computed embeddings (eliminates HTTP calls for entities)
    precomputed = [e for e in entities if "embedding" in e]
    if precomputed and len(precomputed) == len(entities):
        try:
            import numpy as np

            query_vec = None
            q_norm = 0.0
            if BGEM3_TOKEN:
                import httpx

                headers = {"Authorization": f"Bearer {BGEM3_TOKEN}"} if BGEM3_TOKEN else {}
                resp = httpx.post(
                    BGEM3_URL,
                    json=[query],
                    headers=headers,
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                query_vec = np.array(
                    data["embeddings"][0] if isinstance(data, dict) and "embeddings" in data else data[0]
                )
                q_norm = np.linalg.norm(query_vec)
            if query_vec is not None and q_norm >= 1e-10:
                all_scores = []
                for i, ent in enumerate(entities):
                    e_vec = np.array(ent["embedding"])
                    e_norm = np.linalg.norm(e_vec)
                    if e_norm < 1e-10:
                        continue
                    score = float(np.dot(query_vec, e_vec) / (q_norm * e_norm))
                    if np.isnan(score):
                        continue
                    all_scores.append((i, score))
                all_scores.sort(key=lambda x: x[1], reverse=True)
                top_indices = [idx for idx, _ in all_scores[:max_entities]]
                return [entities[idx] for idx in top_indices]
        except Exception:
            logging.exception("Pre-computed embedding search failed; falling back to keyword.")
        return _graph_keyword_fallback(query, entities, max_entities)

    # No pre-computed embeddings: use BGEM3 embedding service
    try:
        import httpx
        import numpy as np

        # Embed query
        headers = {"Authorization": f"Bearer {BGEM3_TOKEN}"} if BGEM3_TOKEN else {}
        resp = httpx.post(
            BGEM3_URL,
            json=[query],
            headers=headers,
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        query_vec = np.array(data["embeddings"][0] if isinstance(data, dict) and "embeddings" in data else data[0])
        q_norm = np.linalg.norm(query_vec)
        if q_norm < 1e-10:
            return _graph_keyword_fallback(query, entities, max_entities)

        # Embed entity descriptions in batches (BGEM3 max 32 per call)
        texts = []
        for ent in entities:
            name = ent.get("name", "")
            desc = ent.get("description", "")
            texts.append(f"{name}: {desc}" if desc else name)

        all_scores = []
        batch_size = 32
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            headers = {"Authorization": f"Bearer {BGEM3_TOKEN}"} if BGEM3_TOKEN else {}
            resp = httpx.post(
                BGEM3_URL,
                json=batch,
                headers=headers,
                timeout=30.0,
            )
            resp.raise_for_status()
            batch_data = resp.json()
            batch_vecs = batch_data["embeddings"] if isinstance(batch_data, dict) else batch_data

            for j, vec in enumerate(batch_vecs):
                e_vec = np.array(vec)
                e_norm = np.linalg.norm(e_vec)
                if e_norm < 1e-10:
                    continue
                score = float(np.dot(query_vec, e_vec) / (q_norm * e_norm))
                if np.isnan(score):
                    continue
                all_scores.append((i + j, score))

        # Sort by score descending, return top entities
        all_scores.sort(key=lambda x: x[1], reverse=True)
        top_indices = [idx for idx, _ in all_scores[:max_entities]]
        return [entities[idx] for idx in top_indices]

    except httpx.HTTPError as e:
        logging.warning(f"BGEM3 HTTP error: {e}")
    except json.JSONDecodeError as e:
        logging.warning(f"BGEM3 returned malformed JSON: {e}")
    except Exception:
        logging.exception("BGEM3 semantic matching failed; falling back to keyword.")
    return _graph_keyword_fallback(query, entities, max_entities)


def _graph_keyword_fallback(query: str, entities: list[dict], max_entities: int) -> list[dict]:
    """Fallback: keyword overlap matching when embedding service is unavailable."""
    query_lower = query.lower()
    query_keywords = set(re.findall(r"[a-z][a-z0-9_\-]{2,}", query_lower))
    scored = []
    for ent in entities:
        name_lower = ent["name"].lower()
        desc_lower = ent.get("description", "").lower()
        combined = f"{name_lower} {desc_lower}"
        name_words = set(re.findall(r"[a-z][a-z0-9_\-]{2,}", combined))
        overlap = query_keywords & name_words
        if overlap or query_lower in name_lower or query_lower in desc_lower:
            scored.append((len(overlap), ent))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [ent for _, ent in scored[:max_entities]]


# ---------------------------------------------------------------------------
# Tool 23 — Codebase Hierarchy
# ---------------------------------------------------------------------------


@mcp.tool()
def get_code_hierarchy() -> dict[str, Any]:
    """Return the codebase hierarchy/tree structure from the knowledge graph.

    If the full graph isn't available, returns the directory tree instead.
    """
    graph = _graph_load()
    if graph and graph.get("hierarchy"):
        return {
            "success": True,
            "message": "Codebase hierarchy from knowledge graph.",
            "data": {"hierarchy": graph["hierarchy"]},
        }

    # Fallback: build directory tree from filesystem
    def _build_tree(directory: Path, depth: int = 0, max_depth: int = 5) -> dict:
        if depth > max_depth:
            return {"name": directory.name, "type": "directory", "truncated": True}
        result = {"name": directory.name, "type": "directory", "children": []}
        try:
            for item in sorted(directory.iterdir()):
                if item.is_dir() and item.name not in EXCLUDE_DIRS:
                    result["children"].append(_build_tree(item, depth + 1, max_depth))
                elif item.is_file() and item.suffix in INCLUDE_EXTENSIONS:
                    result["children"].append({"name": item.name, "type": "file"})
        except PermissionError:
            pass
        return result

    tree = _build_tree(PROJECT_ROOT)
    return {
        "success": True,
        "message": "Directory-based hierarchy (graph not built yet). Run code_graph.py --build for richer structure.",
        "data": {"hierarchy": tree},
    }


# ---------------------------------------------------------------------------
# Tool 24 — Graph Health
# ---------------------------------------------------------------------------


@mcp.tool()
def graph_health() -> dict[str, Any]:
    """Report the knowledge graph's health and staleness."""
    try:
        exists = GRAPH_JSON.exists()
        last_built = ""
        node_count = 0
        edge_count = 0
        graph_mtime = 0.0

        if exists:
            stat = GRAPH_JSON.stat()
            graph_mtime = stat.st_mtime
            last_built = datetime.datetime.fromtimestamp(graph_mtime, tz=datetime.UTC).isoformat()
            graph = _graph_load()
            if graph:
                node_count = len(graph.get("entities", []))
                edge_count = len(graph.get("relationships", []))

        dirty_marker = PROJECT_ROOT / "infra" / "graph" / ".code_graph_dirty"
        is_dirty = dirty_marker.exists()

        files_changed_since = 0
        if graph_mtime > 0:
            for root, dirs, files in os.walk(PROJECT_ROOT):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for f in files:
                    if f.endswith(".py"):
                        fp = Path(root) / f
                        try:
                            if fp.stat().st_mtime > graph_mtime:
                                files_changed_since += 1
                        except OSError:
                            continue

        stale = is_dirty or files_changed_since > 0

        return {
            "exists": exists,
            "last_built": last_built,
            "node_count": node_count,
            "edge_count": edge_count,
            "is_dirty": is_dirty,
            "files_changed_since": files_changed_since,
            "stale": stale,
        }
    except Exception:
        return {
            "exists": False,
            "last_built": "",
            "node_count": 0,
            "edge_count": 0,
            "is_dirty": False,
            "files_changed_since": 0,
            "stale": True,
        }


# ---------------------------------------------------------------------------
# Tool 25 — Find Related Code
# ---------------------------------------------------------------------------


@mcp.tool()
def find_related_code(
    entity_or_topic: Annotated[str, "Entity name or topic to find related code files for."],
    max_results: Annotated[int, "Maximum number of related code files to return (default 10)."] = 10,
) -> dict[str, Any]:
    """Find all code files related to a given entity or topic via graph traversal.

    If the graph isn't built yet, falls back to keyword search in filenames.
    """
    graph = _graph_load()
    if graph:
        entity_lower = entity_or_topic.lower()

        # Step 1: Find matching entities
        matched_entities = []
        for ent in graph.get("entities", []):
            name_low = ent["name"].lower()
            desc_low = ent.get("description", "").lower()
            if entity_lower in name_low or entity_lower in desc_low:
                matched_entities.append(ent)
            elif any(w in name_low for w in entity_lower.split()):
                matched_entities.append(ent)

        # Step 2: Traverse relationships to find connected code files
        connected_files: dict[str, list[str]] = {}
        for ent in matched_entities:
            src_name = ent["name"].lower()
            for rel in graph.get("relationships", []):
                src_low = rel["source"].lower()
                tgt_low = rel["target"].lower()
                rel_type = rel.get("rel_type", "")

                if src_low == src_name or tgt_low == src_name:
                    other = rel["target"] if src_low == src_name else rel["source"]
                    if other.lower() != src_name:
                        connected_files.setdefault(other, []).append(f"{rel_type} (via {ent['name']})")

        # Step 3: Also check entity source docs
        for ent in matched_entities:
            for doc in ent.get("source_docs", []):
                connected_files.setdefault(doc, []).append(f"entity definition ({ent['name']})")

        results = []
        for filepath, reasons in list(connected_files.items())[:max_results]:
            results.append({"file_path": filepath, "reasons": reasons})

        # Step 4: Also find by keyword overlap among graph entities
        if not results:
            topic_keywords = set(re.findall(r"[a-z][a-z0-9_\-]{2,}", entity_lower))
            for ent in graph.get("entities", []):
                name_words = set(re.findall(r"[a-z][a-z0-9_\-]{2,}", ent["name"].lower()))
                if topic_keywords & name_words:
                    for doc in ent.get("source_docs", []):
                        connected_files.setdefault(doc, []).append(f"keyword match ({ent['name']})")
            results = [
                {"file_path": fp, "reasons": reasons} for fp, reasons in list(connected_files.items())[:max_results]
            ]

        if results:
            return {
                "success": True,
                "message": f"Found {len(results)} related code files for '{entity_or_topic}'.",
                "data": {"results": results},
            }

    # Fallback: grep for the topic in filenames
    fallback_results = []
    entity_words = entity_or_topic.lower().split()
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            fp = Path(root) / f
            if fp.suffix in INCLUDE_EXTENSIONS:
                rel = _safe_relative(fp)
                score = sum(1 for w in entity_words if w in fp.stem.lower() or w in f.lower())
                if score > 0:
                    fallback_results.append({"file_path": rel, "match_score": score})
    fallback_results.sort(key=lambda x: x["match_score"], reverse=True)

    return {
        "success": True,
        "message": f"Found {len(fallback_results)} related files (filename-based, graph not built). Run code_graph.py --build for graph traversal.",
        "data": {"results": fallback_results[:max_results]},
    }


# ---------------------------------------------------------------------------
# Tool 26 — Verify File Path
# ---------------------------------------------------------------------------


@mcp.tool()
def verify_file_path(
    path: Annotated[str, "File or directory path to verify. Supports ~ expansion and relative paths."],
) -> dict[str, Any]:
    """Resolve and verify whether a file or directory path exists on disk."""
    try:
        resolved = Path(path).expanduser().resolve()
        if resolved.exists():
            import datetime

            mtime = os.path.getmtime(resolved)
            iso_mtime = datetime.datetime.fromtimestamp(mtime, tz=datetime.UTC).isoformat()
            kind = "file" if resolved.is_file() else "directory"
            return {
                "exists": True,
                "path": str(resolved),
                "last_modified": iso_mtime,
                "kind": kind,
            }
        return {"exists": False, "path": str(resolved)}
    except Exception as e:
        return {"exists": False, "path": path, "error": str(e)}


if __name__ == "__main__":
    if not run_preflight(["baziforecaster_code", "baziforecaster_docs"], "codebase"):
        sys.exit(1)
    start_embedded_watcher(scope="code", run_graph_build=True)

    _cleanup_ghost_processes()

    mcp.run()

# ============================================================================
# ADDED TOOLS - Index Repository, Delete Collection, Get Stats
# ============================================================================

@mcp.tool()
def index_repository(
    repo_name: Annotated[str, "Repository folder name under PROJECT_ROOT"],
    reset: Annotated[bool, "Drop and recreate collection"] = False,
    collection_name: Annotated[Optional[str], "Custom collection name"] = None,
) -> Dict[str, Any]:
    """Index a repository into a Qdrant collection via BGEM3 embeddings."""
    collection = collection_name or repo_name
    hash_cache_path = PROJECT_ROOT / "infra" / "codebase" / f".file_hashes_{collection}.json"
    include_dirs = [f"{repo_name}/{d}" for d in STANDARD_DIRS]

    async def _run_index():
        from indexer_local import embed_with_retry as emb_fn
        client = _get_qdrant_client()
        existing = [c.name for c in client.get_collections().collections]
        if reset and collection in existing:
            client.delete_collection(collection)
            existing = []
            try:
                hash_cache_path.unlink()
            except:
                pass
        if collection not in existing:
            client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
        hash_cache = {}
        if hash_cache_path.exists():
            try:
                hash_cache = json.loads(hash_cache_path.read_text())
            except Exception:
                pass
        all_chunks = []
        files_to_delete = []
        new_hashes = {}
        for inc in include_dirs:
            dir_path = PROJECT_ROOT / inc
            if not dir_path.exists():
                continue
            for root, dirs, files in os.walk(dir_path):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for fname in files:
                    fp = Path(root) / fname
                    if fp.suffix not in INCLUDE_EXTENSIONS:
                        continue
                    try:
                        rel = str(fp.resolve().relative_to(PROJECT_ROOT))
                        cont = fp.read_text(encoding="utf-8")
                        h = hashlib.md5(cont.encode()).hexdigest()
                    except Exception:
                        continue
                    if hash_cache.get(rel) == h:
                        continue
                    if rel in hash_cache:
                        files_to_delete.append(rel)
                    chunks = process_file(fp, rel, h)
                    all_chunks.extend(chunks)
                    new_hashes[rel] = h
        if files_to_delete:
            client.delete(
                collection_name=collection,
                points_selector=Filter(must=[FieldCondition(
                    key="file_path", match=MatchAny(any=files_to_delete)
                )]),
            )
        if not all_chunks:
            return f"No new/changed files in '{collection}' (cached)."
        texts = [c["content"][:8000] for c in all_chunks]
        try:
            vectors = asyncio.run(emb_fn(texts))
        except Exception:
            async def _embed():
                model = _get_embedding_model()
                if model:
                    return list(model.embed(texts))
                import httpx
                resp = await httpx.AsyncClient(timeout=60.0).post(
                    BGEM3_URL, json=texts,
                    headers={"Authorization": f"Bearer {BGEM3_TOKEN}"}
                )
                resp.raise_for_status()
                d = resp.json()
                return d.get("embeddings", d) if isinstance(d, dict) else d
            vectors = asyncio.run(_embed())
        points = []
        for chunk, vec in zip(all_chunks, vectors):
            cid_str = f"{chunk['file_path']}:{chunk['start_line']}:{chunk['content'][:64]}"
            cid = int(hashlib.md5(cid_str.encode()).hexdigest()[:16], 16) % (2 ** 63)
            points.append(PointStruct(
                id=cid, vector=vec,
                payload={
                    "file_path": chunk["file_path"], "file_name": chunk["file_name"],
                    "start_line": chunk["start_line"], "chunk_type": chunk["chunk_type"],
                    "content": chunk["content"],
                },
            ))
        client.upsert(collection_name=collection, points=points)
        hash_cache.update(new_hashes)
        hash_cache_path.parent.mkdir(parents=True, exist_ok=True)
        hash_cache_path.write_text(json.dumps(hash_cache, indent=2))
        return f"Indexed {len(all_chunks)} chunks from {len(new_hashes)} files into '{collection}'."

    result = asyncio.run(_run_index())
    return {"success": True, "message": result}


@mcp.tool()
def delete_collection(collection: Annotated[str, "Collection to delete"]) -> Dict[str, Any]:
    """Delete a collection from Qdrant and its hash cache."""
    client = _get_qdrant_client()
    existing = [c.name for c in client.get_collections().collections]
    if collection in existing:
        client.delete_collection(collection)
        cache = PROJECT_ROOT / "infra" / "codebase" / f".file_hashes_{collection}.json"
        if cache.exists():
            cache.unlink()
        return {"success": True, "message": f"Deleted '{collection}'"}
    return {"success": False, "message": f"Not found: {collection}"}


@mcp.tool()
def get_collection_stats_tool(collection: Annotated[str, "Collection name"]) -> str:
    """Get statistics about a collection. Returns JSON."""
    client = _get_qdrant_client()
    count_res = client.count(collection_name=collection, count_filter=None)
    points, _ = client.scroll(
        collection_name=collection, limit=10000,
        with_payload=True, with_vectors=False,
    )
    chunk_types = {}
    files = set()
    for p in points:
        ct = p.payload.get("chunk_type", "unknown")
        chunk_types[ct] = chunk_types.get(ct, 0) + 1
        files.add(p.payload.get("file_path"))
    return json.dumps({
        "collection": collection, "total_points": count_res.count,
        "unique_files": len(files), "chunk_types": chunk_types,
    }, indent=2)


# ============================================================================
# MCP RESOURCES
# ============================================================================

@mcp.resource("codebase://collections/list")
def list_collections():
    """List all Qdrant collections with vector counts. Returns JSON."""
    client = _get_qdrant_client()
    cols = client.get_collections().collections
    result = {
        "collections": [
            {"name": c.name, "vectors_count": client.count(collection_name=c.name, count_filter=None).count}
            for c in cols
        ]
    }
    return json.dumps(result, indent=2)


@mcp.resource("codebase://files/{collection}")
def list_files_in_collection(collection: str):
    """List unique files in a collection. Returns JSON."""
    client = _get_qdrant_client()
    points, _ = client.scroll(
        collection_name=collection, limit=10000,
        with_payload=True, with_vectors=False,
    )
    files = {}
    for p in points:
        fp = p.payload.get("file_path")
        fn = p.payload.get("file_name")
        if fp and fp not in files:
            files[fp] = {"file_path": fp, "file_name": fn, "chunk_count": 1}
        elif fp:
            files[fp]["chunk_count"] += 1
    return json.dumps({"collection": collection, "total_files": len(files), "files": list(files.values())}, indent=2)


@mcp.resource("codebase://collections/{collection}/stats")
def get_collection_stats_resource(collection: str):
    """Get statistics about a collection. Returns JSON."""
    return get_collection_stats_tool(collection)


# ============================================================================
# MCP PROMPTS
# ============================================================================

@mcp.prompt()
def codebase_query(collection: str, question: str, search_limit: int = 5):
    """Generate a prompt for codebase Q/A with semantic search."""
    result = search_codebase(query=question, collection=collection, limit=search_limit, min_score=0.0)
    if result.get("success") and result.get("results"):
        parts = []
        for r in result["results"][:3]:
            parts.append(f"File: {r['file_path']} (score {r['score']})\nChunk: {r['content'][:300]}")
        context = "\n\n".join(parts)
    else:
        context = "No relevant code found."
    return f"""You are an expert codebase assistant.

User question: {question}
Collection: {collection}

Relevant code context:
{context}

Answer the user's question based on the code context above.
"""


@mcp.prompt()
def file_analysis(collection: str, file_path: str, analysis_request: str):
    """Generate a prompt for analyzing a specific file."""
    result = read_file(relative_path=file_path)
    if result.get("success"):
        content_preview = result["data"]["content"][:2000]
    else:
        content_preview = "(Could not read file)"
    return f"""You are an expert code reviewer and analyzer.

Request: {analysis_request}
Collection: {collection}
File: {file_path}

File content (first 2000 chars):
{content_preview}

Analyze the file according to the request above.
"""

