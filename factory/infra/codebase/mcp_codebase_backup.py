"""
MCP Codebase Server for baziforecaster.

Tools exposed to the LLM:
  1. search_codebase       - semantic vector search over indexed chunks
  2. read_file             - read any file in the repo by relative path
  3. list_files            - list all files under a directory (with extension filter)
  4. get_repo_structure    - tree view of the full project structure
  5. get_file_symbols      - list all classes/functions in a Python file (AST)
  6. grep_codebase         - literal text / regex search across the repo
  7. write_file            - create or overwrite files
  8. replace_in_file       - surgical edits (regex and fuzzy matching supported)
  9. delete_file           - remove files
  10. rename_file          - move/rename
  11. ast_replace_function - deterministically replace a function and auto-inject imports via CST
  12. ast_add_constant     - add or update a top-level constant in a Python file
  13. ast_add_import       - add a top-level import to a Python file
  14. remember_fact        - persist non-code knowledge across sessions
  15. recall_fact          - retrieve previously persisted facts
  16. list_facts           - list all currently persisted facts
  17. create_execution_plan - save a structured execution plan (JSON)
  18. move_symbol           - move code between files and update imports repo-wide
  19. build_repo_graph     - machine-readable dependency mapping with attribute support
  20. explain_failure      - automated context gathering for error diagnosis
  21. count_lines          - count the number of lines in one or more files
"""

import ast
import json
import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Annotated, Any

import libcst as cst

# Shim for libcst 1.0+
if not hasattr(cst, "AsyncFunctionDef"):
    cst.AsyncFunctionDef = cst.FunctionDef


from dotenv import load_dotenv
from fastmcp import FastMCP
from qdrant_client import QdrantClient

# Optional High-Fidelity Embedding Support (Lazy Loaded)
_embedding_model_cache = None


def _get_embedding_model():
    global _embedding_model_cache
    if _embedding_model_cache is not None:
        return _embedding_model_cache
    try:
        from fastembed import TextEmbedding

        _embedding_model_cache = TextEmbedding()
        return _embedding_model_cache
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv()

# Suppress FastMCP informational logs to prevent JSON-RPC corruption on stdout
logging.basicConfig(level=logging.ERROR)
logging.getLogger("fastmcp").setLevel(logging.ERROR)

PROJECT_ROOT = Path(__file__).parent.parent.absolute()
INDEX_PATH = PROJECT_ROOT / "codebase" / "index.json"
FACTS_PATH = PROJECT_ROOT / "codebase" / "codebase_facts.json"

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = "baziforecaster"

# Files/dirs to ignore
EXCLUDE_DIRS = {"__pycache__", ".git", ".venv", "node_modules", ".agent", ".gemini"}
INCLUDE_EXTENSIONS = {".py", ".md", ".json", ".txt", ".yaml", ".yml", ".toml", ".sql", ".sh"}

mcp = FastMCP("baziforecaster-codebase")


def _get_qdrant_client() -> QdrantClient | None:
    """Returns a transient Qdrant client to prevent persistent file locks on codebase/qdrant_db."""
    try:
        local_db = PROJECT_ROOT / "codebase" / "qdrant_db"
        if local_db.exists():
            return QdrantClient(path=str(local_db))
        return QdrantClient(url=QDRANT_URL)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        if not target.is_relative_to(root):
            # Security warning for directory traversal attempts
            # print(f"[SECURITY WARNING] Attempted access outside project root: {relative_path}")
            raise ValueError(f"Path escape detected: {relative_path}")
        return target
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


def _get_scope_expanded_snippet(rel_path: str, match_text: str) -> str:
    """Attempts to find the parent function/class header for a given match."""
    try:
        path = _resolve_secure_path(rel_path)
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)

        # Find the line containing match_text
        match_line = -1
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if match_text in line:
                match_line = i + 1
                break

        if match_line == -1:
            return match_text[:300] + "..."

        parent_header = ""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.lineno <= match_line <= (node.end_lineno or node.lineno):
                    # Found the scope
                    header_line = lines[node.lineno - 1].strip()
                    parent_header = f"[{header_line}] "
                    break

        snippet = lines[max(0, match_line - 3) : match_line + 5]
        return parent_header + "\n".join(snippet)
    except Exception:
        return match_text[:300] + "..."


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
# Tool 1 — Semantic Search
# ---------------------------------------------------------------------------


@mcp.tool()
def search_codebase(
    query: Annotated[str, "Natural language or code query."],
    limit: Annotated[int, "Number of results to return (default 10, max 20)."] = 10,
) -> dict[str, Any]:
    """
    Semantic search over the indexed codebase using Qdrant.
    Implements 'Scope-Aware' discovery to return parent headers (function/class) for each match.
    """
    qdrant = _get_qdrant_client()
    if not qdrant:
        return {
            "success": False,
            "message": "Qdrant client not configured or database currently locked by another process (e.g. indexer).",
        }

    try:
        embedding_model = _get_embedding_model()
        if not embedding_model:
            return {
                "success": False,
                "message": "Dependency Error: Semantic search requires the fastembed library. Please run 'pip install fastembed' to enable this feature.",
            }

        # Vectorization via fastembed
        query_vector = list(embedding_model.embed([query]))[0]

        results = qdrant.search(
            collection_name=COLLECTION_NAME, query_vector=query_vector, limit=limit, with_payload=True
        )

        matches = []
        for res in results:
            rel_path = res.payload.get("file_path", "unknown")
            raw_content = res.payload.get("content", "")

            # Scope-Aware Snippet Expansion
            snippet = _get_scope_expanded_snippet(rel_path, raw_content)

            matches.append({"file_path": rel_path, "score": res.score, "snippet": snippet})

        if not matches:
            return {"success": True, "message": "No relevant code chunks found.", "data": {"results": []}}

        return {
            "success": True,
            "message": f"Found {len(matches)} scope-aware relevant chunks.",
            "data": {"results": matches},
        }
    except Exception as e:
        return {"success": False, "message": f"Search failed (Qdrant service may be down or unindexed): {str(e)}"}
    finally:
        if qdrant:
            qdrant.close()


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
        base = PROJECT_ROOT / directory
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
        base = PROJECT_ROOT / directory
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


@mcp.tool()
def write_file(
    relative_path: Annotated[str, "Path relative to project root."],
    content: Annotated[str, "The full text content to write."],
) -> dict[str, Any]:
    """Write content to a file in the repo atomically with syntax validation."""
    try:
        path = _resolve_secure_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = _normalize_content(content)

        # Pre-write validation for Python files
        if path.suffix == ".py":
            try:
                ast.parse(content)
            except SyntaxError as e:
                return {
                    "success": False,
                    "message": f"Rejected: Change would introduce a SyntaxError: {e.msg} at line {e.lineno}. Use ast_clean_imports if this is an import issue.",
                }

        _atomic_write(path, content)
        return {
            "success": True,
            "message": f"Successfully wrote to {relative_path}",
            "data": {"file_path": relative_path, "bytes": len(content)},
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to write {relative_path}: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 8 — Replace In File (Hardened)
# ---------------------------------------------------------------------------


@mcp.tool()
def replace_in_file(
    relative_path: Annotated[str, "Path relative to project root."],
    target_text: Annotated[str, "Exact string or regex to replace."],
    replacement_text: Annotated[str, "New text."],
    is_regex: bool = False,
    case_insensitive: bool = False,
    ignore_whitespace: bool = False,
) -> dict[str, Any]:
    """Surgical replacement in a file with atomic safety and syntax validation."""
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
        return {"success": True, "message": f"Replaced text in {relative_path}"}
    except Exception as e:
        return {"success": False, "message": f"Replacement failed: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 9 — Delete File
# ---------------------------------------------------------------------------


@mcp.tool()
def delete_file(
    relative_path: Annotated[str, "Path relative to project root."],
) -> dict[str, Any]:
    """Delete a file or directory from the repo."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"Not found: {relative_path}"}
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return {"success": True, "message": f"Deleted {relative_path}"}
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
    """Rename or move a file/directory."""
    try:
        src = _resolve_secure_path(source_relative_path)
        dst = _resolve_secure_path(destination_relative_path)
        if not src.exists():
            return {"success": False, "message": f"Source not found: {source_relative_path}"}
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return {"success": True, "message": f"Moved {source_relative_path} to {destination_relative_path}"}
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


@mcp.tool()
def ast_replace_function(
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


@mcp.tool()
def ast_add_constant(
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


@mcp.tool()
def ast_add_import(
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

        return {
            "success": True,
            "message": f"Successfully moved {symbol_name} from {source_path} to {dest_path}",
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


if __name__ == "__main__":
    _cleanup_ghost_processes()
    mcp.run()
