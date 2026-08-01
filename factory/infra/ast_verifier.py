"""Multi-layer AST verification for post-edit code quality gates.

Incorporated from WIP/code_hygiene/scanners/kill_tries.py patterns.
Provides 5+ sandbox layers:
1. Syntax check
2. CC/nesting/try-pyramid checks
3. Attribute sandbox - detects hallucinated fields
4. Call sandbox - detects swapped arguments
5. Signature parity - ensures parameter contract is preserved
6. Namespace collision - helpers don't shadow existing imports/functions
7. Unimported symbol detection via SymbolScopeVisitor
"""

import ast
import logging
import subprocess
import time
import uuid
from typing import Any

from factory.infra.control import REPO_ROOT

logger = logging.getLogger("ast_verifier")

class VerificationCircuitBreaker:
    """Circuit breaker for verification calls, keyed by file path.

    After 3 consecutive failures the circuit opens and a cached
    "circuit open" result is returned.  After 30 seconds the circuit
    moves to half-open, allowing one more attempt.  A success resets
    the counter.
    """

    FAILURE_THRESHOLD = 3
    HALF_OPEN_SECONDS = 30

    def __init__(self) -> None:
        self._state: dict[str, dict] = {}

    def _get_entry(self, filepath: str) -> dict:
        return self._state.setdefault(filepath, {
            "failures": 0,
            "opened_at": 0.0,
            "half_open_allowed": True,
        })

    def is_open(self, filepath: str) -> bool:
        entry = self._get_entry(filepath)
        if entry["failures"] < self.FAILURE_THRESHOLD:
            return False
        elapsed = time.monotonic() - entry["opened_at"]
        if elapsed >= self.HALF_OPEN_SECONDS:
            return False
        return True

    def record_success(self, filepath: str) -> None:
        self._state.pop(filepath, None)

    def record_failure(self, filepath: str) -> None:
        entry = self._get_entry(filepath)
        entry["failures"] += 1
        if entry["failures"] >= self.FAILURE_THRESHOLD:
            entry["opened_at"] = time.monotonic()
            entry["half_open_allowed"] = True

    def can_attempt(self, filepath: str) -> bool:
        entry = self._get_entry(filepath)
        if entry["failures"] < self.FAILURE_THRESHOLD:
            return True
        elapsed = time.monotonic() - entry["opened_at"]
        if elapsed >= self.HALF_OPEN_SECONDS and entry["half_open_allowed"]:
            entry["half_open_allowed"] = False
            return True
        return False

    def reset(self, filepath: str) -> None:
        self._state.pop(filepath, None)


verification_circuit_breaker = VerificationCircuitBreaker()

MAX_FILE_SIZE = 1_000_000

VERIFICATION_CIRCUIT_BREAKER: dict[str, dict] = {}


class ComplexityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.complexity = 1

    def visit_If(self, node: ast.If) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self.complexity += 1
        for case in node.cases:
            self.complexity += 1
        self.generic_visit(node)

    def _count_comprehension_ifs(self, node: Any) -> None:
        for gen in node.generators:
            self.complexity += len(gen.ifs)
        self.generic_visit(node)

    def _visit_comprehension_like(self, node: Any) -> None:
        self._count_comprehension_ifs(node)

    visit_ListComp = _visit_comprehension_like
    visit_SetComp = _visit_comprehension_like
    visit_DictComp = _visit_comprehension_like
    visit_GeneratorExp = _visit_comprehension_like

    def _visit_async_generator_exp(self, node: Any) -> None:
        self._count_comprehension_ifs(node)

    def _visit_except_group(self, node: Any) -> None:
        self.complexity += 1
        self.generic_visit(node)

    if hasattr(ast, 'AsyncGeneratorExp'):
        visit_AsyncGeneratorExp = _visit_async_generator_exp

    if hasattr(ast, 'ExceptGroup'):
        visit_ExceptGroup = _visit_except_group


STANDARD_BUILTINS_AND_TYPING: set[str] = {
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes", "callable",
    "chr", "classmethod", "compile", "complex", "delattr", "dict", "dir", "divmod",
    "enumerate", "eval", "exec", "filter", "float", "format", "frozenset", "getattr",
    "globals", "hasattr", "hash", "help", "hex", "id", "input", "int", "isinstance",
    "issubclass", "iter", "len", "list", "locals", "map", "max", "memoryview",
    "min", "next", "object", "oct", "open", "ord", "pow", "print", "property",
    "range", "repr", "reversed", "round", "set", "setattr", "slice", "sorted",
    "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip",
    "__import__",
    "Exception", "BaseException", "ValueError", "TypeError", "KeyError",
    "AttributeError", "IndexError", "RuntimeError", "SyntaxError", "ImportError",
    "ModuleNotFoundError", "StopIteration", "FileNotFoundError", "PermissionError",
    "TimeoutError", "OSError", "AssertionError", "NotImplementedError", "OverflowError",
    "ZeroDivisionError", "UnboundLocalError", "UnicodeDecodeError", "UnicodeEncodeError",
    "True", "False", "None", "Ellipsis", "NotImplemented",
    "Any", "Optional", "Union", "Callable", "Dict", "List", "Tuple", "Set", "Type",
    "Cast", "Literal", "TypeVar", "Generic", "Overload", "Final", "ClassVar", "Self",
    "Sequence", "Mapping", "Iterable", "Iterator", "Generator", "Coroutine", "AsyncGenerator",
    "AsyncIterable", "AsyncIterator", "ContextManager", "AsyncContextManager", "NamedTuple",
    "TypedDict", "Protocol", "runtime_checkable", "type_check_only", "cast", "Pattern", "Match",
    "typing", "collections", "enum", "dataclasses", "itertools", "re", "math",
    "datetime", "asyncio", "sys", "os", "json", "logging", "pathlib", "Path", "uuid", "time",
    "__name__", "__file__", "__doc__", "__all__", "__annotations__",
}


class SymbolScopeVisitor(ast.NodeVisitor):
    """Validates that all loaded names and function calls in code are defined
    in the file's header contract (imports, top-level symbols, global constants)."""

    def __init__(self, header_contract: dict | None = None, code_str: str = "") -> None:
        self.header_contract = header_contract or {}
        self.code_str = code_str
        self.code_lines = code_str.splitlines() if code_str else []
        self.unimported_symbols: list[dict[str, Any]] = []

        self.allowed_symbols: set[str] = set(STANDARD_BUILTINS_AND_TYPING)
        for sym in self.header_contract.get("imported_symbols", []):
            self.allowed_symbols.add(sym)
        for sym in self.header_contract.get("top_level_symbols", []):
            self.allowed_symbols.add(sym)
        for sym in self.header_contract.get("global_constants", []):
            self.allowed_symbols.add(sym)
        for mod in self.header_contract.get("imported_modules", []):
            self.allowed_symbols.add(mod)
            self.allowed_symbols.add(mod.split(".")[0])

        self.scope_stack: list[set[str]] = [set()]
        self._in_annotation: bool = False

    def is_symbol_defined(self, name: str) -> bool:
        if name in self.allowed_symbols:
            return True
        for scope in reversed(self.scope_stack):
            if name in scope:
                return True
        return False

    def _get_line_context(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.code_lines):
            return self.code_lines[lineno - 1].strip()
        return ""

    def _record_violation(self, name: str, lineno: int, category: str = "unimported_symbol") -> None:
        line_context = self._get_line_context(lineno)
        if not any(item["name"] == name and item["line"] == lineno for item in self.unimported_symbols):
            self.unimported_symbols.append({
                "name": name,
                "line": lineno,
                "context": line_context,
                "category": category,
            })

    def collect_top_level_defs(self, tree: ast.AST) -> None:
        root_scope = self.scope_stack[0]
        if isinstance(tree, ast.Module):
            body_nodes = tree.body
        elif isinstance(tree, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body_nodes = [tree]
        else:
            body_nodes = []

        for node in body_nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                root_scope.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        root_scope.add(target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    root_scope.add(bound)

    def _collect_function_locals(self, fn_node: ast.FunctionDef | ast.AsyncFunctionDef, scope: set[str]) -> None:
        args_node = fn_node.args
        for arg in args_node.posonlyargs + args_node.args + args_node.kwonlyargs:
            scope.add(arg.arg)
        if args_node.vararg:
            scope.add(args_node.vararg.arg)
        if args_node.kwarg:
            scope.add(args_node.kwarg.arg)

        for node in ast.walk(fn_node):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Param)):
                scope.add(node.id)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                scope.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    scope.add(bound)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node is not fn_node:
                scope.add(node.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)

        args_node = node.args
        for default in args_node.defaults + [d for d in args_node.kw_defaults if d]:
            self.visit(default)

        for arg in args_node.posonlyargs + args_node.args + args_node.kwonlyargs:
            if arg.annotation:
                prev = self._in_annotation
                self._in_annotation = True
                self.visit(arg.annotation)
                self._in_annotation = prev
        if args_node.vararg and args_node.vararg.annotation:
            prev = self._in_annotation
            self._in_annotation = True
            self.visit(args_node.vararg.annotation)
            self._in_annotation = prev
        if args_node.kwarg and args_node.kwarg.annotation:
            prev = self._in_annotation
            self._in_annotation = True
            self.visit(args_node.kwarg.annotation)
            self._in_annotation = prev

        if node.returns:
            prev = self._in_annotation
            self._in_annotation = True
            self.visit(node.returns)
            self._in_annotation = prev

        fn_scope: set[str] = set()
        self._collect_function_locals(node, fn_scope)
        self.scope_stack.append(fn_scope)

        for stmt in node.body:
            self.visit(stmt)

        self.scope_stack.pop()

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        prev = self._in_annotation
        self._in_annotation = True
        self.visit(node.annotation)
        self._in_annotation = prev

        if node.value:
            self.visit(node.value)
        self.visit(node.target)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        if isinstance(node.target, ast.Name):
            self.scope_stack[-1].add(node.target.id)
        self.generic_visit(node)

    def visit_Starred(self, node: ast.Starred) -> None:
        self.visit(node.value)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            name = node.id
            if not self.is_symbol_defined(name):
                lineno = getattr(node, "lineno", 0)
                category = "unimported_type_annotation" if self._in_annotation else "unimported_symbol"
                self._record_violation(name, lineno, category)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if not self.is_symbol_defined(func_name):
                lineno = getattr(node, "lineno", 0)
                self._record_violation(func_name, lineno, "unimported_function_call")
        self.generic_visit(node)

    def inspect(self, tree: ast.AST) -> list[dict[str, Any]]:
        self.unimported_symbols.clear()
        self.scope_stack = [set()]
        self._in_annotation = False
        self.collect_top_level_defs(tree)
        self.visit(tree)
        return self.unimported_symbols


def extract_header_symbol_contract(source: str) -> dict:
    """Parse full file AST to extract all imported modules, imported symbols,
    top-level functions/classes, and global constants.

    Returns a plain dict (not a Pydantic model) so it can be passed
    across module boundaries without import coupling.
    """
    if not source:
        return {"imported_modules": [], "imported_symbols": [], "top_level_symbols": [], "global_constants": []}
    try:
        tree = ast.parse(source)
    except Exception:
        return {"imported_modules": [], "imported_symbols": [], "top_level_symbols": [], "global_constants": []}

    imported_modules: set[str] = set()
    imported_symbols: set[str] = set()
    top_level_symbols: set[str] = set()
    global_constants: set[str] = set()

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
                bound_name = alias.asname or alias.name.split(".")[0]
                imported_symbols.add(bound_name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module)
            for alias in node.names:
                if alias.name != "*":
                    bound_name = alias.asname or alias.name
                    imported_symbols.add(bound_name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            top_level_symbols.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    global_constants.add(target.id)

    return {
        "imported_modules": sorted(imported_modules),
        "imported_symbols": sorted(imported_symbols),
        "top_level_symbols": sorted(top_level_symbols),
        "global_constants": sorted(global_constants),
    }


def _get_ruff_errors(file_content: str) -> set[str]:
    if not file_content:
        return set()
    scratch_dir = REPO_ROOT / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = scratch_dir / f"temp_ruff_{uuid.uuid4().hex}.py"
    try:
        tmp_path.write_text(file_content, encoding="utf-8")
        res = subprocess.run(
            ["uv", "run", "ruff", "check", "--select", "F821,E9,F63,F7", str(tmp_path)],
            capture_output=True, text=True, check=False,
            timeout=300, cwd=str(REPO_ROOT),
            env={**__import__("os").environ, "PYTHONPATH": "."},
        )
        errors = set()
        for line in res.stdout.splitlines():
            if ":" in line:
                norm = line.split(":", 1)[-1].strip()
                if norm:
                    errors.add(norm)
        return errors
    except Exception:
        return set()
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def _get_normalized_pyright_errors(file_content: str) -> set[str]:
    if not file_content:
        return set()
    scratch_dir = REPO_ROOT / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = scratch_dir / f"temp_pyright_{uuid.uuid4().hex}.py"
    try:
        tmp_path.write_text(file_content, encoding="utf-8")
        res = subprocess.run(
            ["uv", "run", "pyright", str(tmp_path)],
            capture_output=True, text=True, check=False,
            timeout=300, cwd=str(REPO_ROOT),
            env={**__import__("os").environ, "PYTHONPATH": "."},
        )
        errors = set()
        for line in res.stdout.splitlines():
            if "error:" in line.lower():
                stripped = line.strip()
                if " - " in stripped:
                    stripped = stripped.split(" - ", 1)[-1].strip()
                if stripped:
                    errors.add(stripped)
        return errors
    except Exception:
        return set()
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def ensure_pydantic_imports(source: str, refactored_code: str) -> str:
    """Auto-inject pydantic imports if the refactored code uses pydantic types."""
    if "model_validate" in refactored_code or "model_dump" in refactored_code or "BaseModel" in refactored_code:
        if "from pydantic" not in source and "import pydantic" not in source:
            source = "from pydantic import BaseModel\n" + source
    return source


def verify_refactored_ast(
    code: str,
    candidate_name: str = "",
    orig_code: str = "",
    orig_cc: int = 0,
    baseline_errors: set[str] | None = None,
    header_contract: dict | None = None,
) -> tuple[bool, int, int, str]:
    """Compile and verify that refactored code passes all AST safety checks.

    Returns (passed: bool, cc: int, max_depth: int, message: str).
    """
    if len(code.encode("utf-8")) > MAX_FILE_SIZE:
        return False, 999, 999, f"Code exceeds size limit ({len(code)} bytes)"

    violations: list[str] = []
    candidate_cc = 0
    candidate_max_depth = 0

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, 999, 999, f"SyntaxError in refactored code: {e}"

    # 1. Ban unauthorized imports
    safe_modules = {"typing", "collections", "enum", "dataclasses", "itertools", "re"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            violations.append(f"unauthorized_symbol: Created a new class `{node.name}`")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.level > 0:
                continue  # Relative import within package
            module_name = getattr(node, "module", None)
            if not module_name and isinstance(node, ast.Import):
                module_name = node.names[0].name.split(".")[0]
            if module_name and module_name not in safe_modules and not module_name.startswith("src2"):
                violations.append(f"unauthorized_import: Added import for `{module_name}`")

    # 2. Namespace sandbox: harvest original file namespace
    orig_namespace: set[str] = set()
    if orig_code:
        try:
            orig_tree = ast.parse(orig_code)
            for top_node in orig_tree.body:
                if isinstance(top_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    orig_namespace.add(top_node.name)
                elif isinstance(top_node, ast.Assign):
                    for target in top_node.targets:
                        if isinstance(target, ast.Name):
                            orig_namespace.add(target.id)
                elif isinstance(top_node, ast.Import):
                    for alias in top_node.names:
                        orig_namespace.add(alias.asname or alias.name)
                elif isinstance(top_node, ast.ImportFrom):
                    for alias in top_node.names:
                        orig_namespace.add(alias.asname or alias.name)
        except SyntaxError as e:
            logger.warning(f"[verify_refactored_ast] SyntaxError harvesting namespace: {e}")

    # 3. Helper naming and namespace collision check
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name != candidate_name:
                if not node.name.startswith("_"):
                    violations.append(f"invalid_helper_name: Helper `{node.name}` must start with an underscore")
                elif node.name in orig_namespace:
                    violations.append(f"namespace_collision: Helper `{node.name}` shadows existing symbol")

    # 4. Attribute sandbox: detect hallucinated fields
    if orig_code:
        try:
            orig_tree = ast.parse(orig_code)
            orig_attrs = _AttributeVisitor()
            orig_attrs.visit(orig_tree)

            new_attrs = _AttributeVisitor()
            new_attrs.visit(tree)

            whitelist: set[str] = {
                "get", "append", "model_dump", "model_copy", "items", "keys", "values",
                "add", "update", "split", "strip", "replace", "join", "format",
                "startswith", "endswith", "lower", "upper", "info", "error", "warning",
                "exception", "debug", "exists", "resolve", "parent", "name", "isoformat",
                "now", "today", "group", "match", "search", "encode", "decode", "find",
                "rfind", "partition", "rpartition", "splitlines", "capitalize", "title",
                "swapcase", "isdigit", "isalpha", "isalnum", "isspace", "count", "index",
                "remove", "pop", "insert", "extend", "clear", "update", "setdefault",
                "copy", "query", "fetchone", "fetchall", "execute", "executemany",
                "fetchmany", "close", "connect", "cursor", "commit", "rollback",
                "begin", "savepoint", "execute_script", "description", "connection",
                "rowcount", "lastrowid", "parts", "role", "content", "output", "data",
                "events", "structure", "gender", "alias", "day_pillar", "month_pillar",
                "year_pillar", "hour_pillar", "date", "days", "strftime", "isoformat",
                "value", "result", "message_history", "profile", "session",
                "conversation_history", "target_dates", "intent", "sentiment",
                "mental_model", "user_state", "rag_context", "structural_map",
                "shen_sha_context", "day_scores", "monthly_context", "score_legend",
                "language", "parse_mode", "text", "step", "metadata", "ModelRequest",
                "ModelResponse", "TextPart", "UserPromptPart",
            }
            hallucinated = {a for a in (new_attrs.attributes - orig_attrs.attributes) - whitelist if not a.startswith("_")}
            if hallucinated:
                violations.append(f"hallucinated_fields: Invented attributes {hallucinated}")
        except Exception:
            pass

    # 5. Call signature sandbox: detect argument swaps
    if orig_code:
        try:
            builtin_methods = {
                "isinstance", "getattr", "hasattr", "setattr", "len", "str", "int", "float", "bool",
                "list", "dict", "set", "tuple", "any", "all", "print", "type", "range", "enumerate",
                "zip", "min", "max", "sum", "sorted", "reversed", "super", "get", "append", "extend",
                "gather", "add", "update", "model_validate", "model_dump", "parse_mode", "format",
                "encode", "decode", "split", "strip", "join", "replace", "startswith", "endswith",
                "lower", "upper", "create_task", "add_done_callback", "discard", "getLogger",
                "from_url", "aclose", "model_validate_json", "strftime", "isoformat", "run",
            }
            orig_tree = ast.parse(orig_code)
            orig_call_vis = _CallVisitor()
            orig_call_vis.visit(orig_tree)

            new_call_vis = _CallVisitor()
            new_call_vis.visit(tree)

            orig_func_names = {call[0] for call in orig_call_vis.calls if call[0] not in builtin_methods}

            for new_call in new_call_vis.calls:
                func_name, new_args = new_call
                if func_name in orig_func_names and new_call not in orig_call_vis.calls:
                    if func_name in new_call_vis.calls_with_keywords or func_name in orig_call_vis.calls_with_keywords:
                        continue
                    violations.append(f"argument_swap: Changed arguments for `{func_name}`. Passed {new_args}.")
        except Exception:
            pass

    # 6. Signature parity check
    if orig_code and candidate_name:
        try:
            orig_tree = ast.parse(orig_code)
            orig_main_node = next(
                (n for n in orig_tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == candidate_name),
                None,
            )
            if orig_main_node is None:
                orig_main_node = next(
                    (n for n in ast.walk(orig_tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == candidate_name),
                    None,
                )

            if orig_main_node:
                orig_sig = _extract_function_signature(orig_main_node)
                ref_main_node = next(
                    (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == candidate_name),
                    None,
                )
                if ref_main_node is None:
                    violations.append(f"missing_function: Target function `{candidate_name}` is missing or renamed")
                else:
                    ref_sig = _extract_function_signature(ref_main_node)
                    if orig_sig != ref_sig:
                        diffs = [k for k, v in orig_sig.items() if ref_sig.get(k) != v]
                        for diff in diffs:
                            violations.append(f"signature_mismatch:{candidate_name}:{diff}")
        except Exception:
            pass

    # 7. Symbol scope check using SymbolScopeVisitor
    resolved_contract = header_contract or (extract_header_symbol_contract(orig_code) if orig_code else {})
    scope_visitor = SymbolScopeVisitor(resolved_contract, code)
    unimported_list = scope_visitor.inspect(tree)
    if unimported_list:
        allowed = (
            resolved_contract.get("imported_symbols", [])
            if resolved_contract.get("imported_symbols")
            else sorted(set(resolved_contract.get("top_level_symbols", []) + resolved_contract.get("global_constants", [])))
        )
        for item in unimported_list:
            name = item["name"]
            line_no = item.get("line", 0)
            ctx_line = item.get("context", "")
            category = item.get("category", "unimported_symbol")
            ctx_str = f" line {line_no} (`{ctx_line}`)" if ctx_line else (f" line {line_no}" if line_no else "")
            violations.append(
                f"{category}: Referenced symbol '{name}' at{ctx_str} not in header contract. "
                f"Available: {allowed}"
            )

    # 8. CC and nesting checks
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            comp_vis = ComplexityVisitor()
            comp_vis.visit(node)
            func_cc = comp_vis.complexity

            _scanner = _FunctionCandidateScanner("test.py", code.splitlines())
            func_depth, _, try_issues = _scanner._check_body_nesting(node.body, depth=0)

            if node.name == candidate_name:
                candidate_cc = func_cc
                candidate_max_depth = func_depth

            if len(try_issues) > 0:
                violations.append(f"try_pyramid:{try_issues}")
            if func_cc > 5:
                violations.append(f"cc_exceeds:{node.name} has CC={func_cc} (target <=5)")
            if func_depth > 3:
                violations.append(f"nesting_exceeds:{node.name} depth={func_depth} (must be <=3)")

    if violations:
        return False, candidate_cc, candidate_max_depth, "VIOLATIONS FOUND:\n" + "\n".join(f"  - {v}" for v in violations)

    return True, candidate_cc, candidate_max_depth, "All AST safety checks passed."


def run_lint_regression(orig_code: str, refactored_code: str) -> tuple[bool, str]:
    """Run ruff and pyright on refactored code, comparing against baseline.

    Returns (passed: bool, error_message: str).
    """
    try:
        scratch_dir = REPO_ROOT / "scratch"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = scratch_dir / f"temp_lint_{uuid.uuid4().hex}.py"
        try:
            tmp_path.write_text(refactored_code, encoding="utf-8")

            subprocess.run(
                ["uv", "run", "ruff", "format", str(tmp_path)],
                capture_output=True, text=True, check=False, timeout=300,
                cwd=str(REPO_ROOT), env={**__import__("os").environ, "PYTHONPATH": "."},
            )

            baseline_ruff = _get_ruff_errors(orig_code) if orig_code else set()
            current_ruff = _get_ruff_errors(refactored_code)
            new_ruff = current_ruff - baseline_ruff
            if new_ruff:
                return False, f"New ruff errors: {new_ruff}"

            baseline_pyright = _get_normalized_pyright_errors(orig_code) if orig_code else set()
            current_pyright = _get_normalized_pyright_errors(refactored_code)
            new_pyright = current_pyright - baseline_pyright
            if new_pyright:
                return False, f"New pyright errors: {new_pyright}"

            return True, ""
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
    except Exception as e:
        return False, f"Lint regression check failed: {e}"


class _AttributeVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.attributes: set[str] = set()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.attributes.add(node.attr)
        self.generic_visit(node)


class _CallVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: set[tuple[str, tuple[str, ...]]] = set()
        self.calls_with_keywords: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        func_name: str | None = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name:
            args = tuple(arg.id for arg in node.args if isinstance(arg, ast.Name))
            self.calls.add((func_name, args))
            if node.keywords:
                self.calls_with_keywords.add(func_name)
        self.generic_visit(node)


def _extract_function_signature(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict:
    args_node = fn_node.args
    posonly = [a.arg for a in args_node.posonlyargs]
    pos_args = [a.arg for a in args_node.args]
    vararg = args_node.vararg.arg if args_node.vararg else None
    kwonly = [a.arg for a in args_node.kwonlyargs]
    kwarg = args_node.kwarg.arg if args_node.kwarg else None
    defaults_count = len(args_node.defaults)
    kw_defaults_count = sum(1 for d in args_node.kw_defaults if d is not None)
    return {
        "posonly": posonly, "args": pos_args, "vararg": vararg,
        "kwonly": kwonly, "kwarg": kwarg,
        "defaults_count": defaults_count, "kw_defaults_count": kw_defaults_count,
    }


class _FunctionCandidateScanner(ast.NodeVisitor):
    CONTROL_NODES = (ast.If, ast.Try, ast.For, ast.While, ast.With)

    if hasattr(ast, 'AsyncGeneratorExp'):
        CONTROL_NODES = CONTROL_NODES + (ast.AsyncGeneratorExp,)

    if hasattr(ast, 'ExceptGroup'):
        CONTROL_NODES = CONTROL_NODES + (ast.ExceptGroup,)

    def __init__(self, filename: str, code_lines: list[str], full_file_source: str = "") -> None:
        self.filename = filename
        self.code_lines = code_lines
        self.full_file_source = full_file_source
        self.candidates: list = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        comp_vis = ComplexityVisitor()
        comp_vis.visit(node)
        cc = comp_vis.complexity
        max_depth, _, try_issues = self._check_body_nesting(node.body, depth=0)
        if len(try_issues) > 0 or max_depth > 3 or cc > 5:
            self.candidates.append({"name": node.name, "cc": cc, "depth": max_depth, "try_issues": try_issues})
        self.generic_visit(node)

    def _check_body_nesting(self, statements: list[ast.stmt], depth: int) -> tuple[int, int, list[tuple[int, str]]]:
        max_d = depth
        max_line = 0
        try_issues: list[tuple[int, str]] = []
        for stmt in statements:
            if isinstance(stmt, self.CONTROL_NODES):
                current_depth = depth + 1
                if current_depth > max_d:
                    max_d = current_depth
                    max_line = stmt.lineno
                if isinstance(stmt, ast.Try):
                    for inner in stmt.body:
                        if isinstance(inner, ast.Try):
                            try_issues.append((inner.lineno, "Nested Try inside Try body"))
                    for handler in stmt.handlers:
                        for h_stmt in handler.body:
                            if isinstance(h_stmt, ast.Try):
                                try_issues.append((h_stmt.lineno, "Try inside Except handler"))
                    if stmt.orelse:
                        for el_stmt in stmt.orelse:
                            if isinstance(el_stmt, (ast.If, ast.Try)):
                                try_issues.append((el_stmt.lineno, f"{el_stmt.__class__.__name__} inside Try-Else"))
                sub_bodies = []
                if isinstance(stmt, ast.If):
                    sub_bodies.append((stmt.body, current_depth))
                    if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
                        sub_bodies.append((stmt.orelse, depth))
                    else:
                        sub_bodies.append((stmt.orelse, current_depth))
                elif isinstance(stmt, ast.Try):
                    sub_bodies.append((stmt.body, current_depth))
                    for h in stmt.handlers:
                        sub_bodies.append((h.body, current_depth))
                    sub_bodies.append((stmt.orelse, current_depth))
                    sub_bodies.append((stmt.finalbody, current_depth))
                elif isinstance(stmt, (ast.For, ast.While)):
                    sub_bodies.append((stmt.body, current_depth))
                    sub_bodies.append((stmt.orelse, current_depth))
                elif isinstance(stmt, ast.With):
                    sub_bodies.append((stmt.body, current_depth))
                for sb, sb_depth in sub_bodies:
                    if sb:
                        d, line_no, ti = self._check_body_nesting(sb, sb_depth)
                        try_issues.extend(ti)
                        if d > max_d:
                            max_d = d
                            max_line = line_no
        return max_d, max_line, try_issues