"""AST analyzer for anti-pattern detection and code quality pre-flight checks.

Incorporated from WIP/code_hygiene/scanners/kill_tries.py patterns.
Detects try pyramids, deep nesting, cyclomatic complexity violations,
and other control-flow anti-patterns before the intern touches a file.
"""

import ast
from typing import Any

MAX_FILE_SIZE = 1_000_000


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


class FunctionCandidateScanner(ast.NodeVisitor):
    """Scans AST for functions violating control flow standards.

    Detects three priority levels:
    1. Try pyramids / try-else-if anti-patterns (Priority 1)
    2. Deep nesting (depth > 3) (Priority 2)
    3. Cyclomatic complexity (CC > 5) (Priority 3)
    """

    CONTROL_NODES = (ast.If, ast.Try, ast.For, ast.While, ast.With)

    if hasattr(ast, 'AsyncGeneratorExp'):
        CONTROL_NODES = CONTROL_NODES + (ast.AsyncGeneratorExp,)

    if hasattr(ast, 'ExceptGroup'):
        CONTROL_NODES = CONTROL_NODES + (ast.ExceptGroup,)

    def __init__(self, filename: str = "", code_lines: list[str] | None = None, full_file_source: str = "") -> None:
        self.filename = filename
        self.code_lines = code_lines or []
        self.full_file_source = full_file_source
        self.candidates: list[dict[str, Any]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        comp_vis = ComplexityVisitor()
        comp_vis.visit(node)
        cc = comp_vis.complexity

        max_depth, max_depth_line, try_issues = self._check_body_nesting(node.body, depth=0)

        if len(try_issues) > 0 or max_depth > 3 or cc > 5:
            end_line = getattr(node, "end_lineno", node.lineno)
            func_code = ast.unparse(node)
            line_count = end_line - node.lineno + 1
            requires_decomposition = cc > 50 or line_count > 200

            priority = 3
            if len(try_issues) > 0:
                priority = 1
            elif max_depth > 3:
                priority = 2

            self.candidates.append({
                "file_path": self.filename,
                "function_name": node.name,
                "line": node.lineno,
                "end_line": end_line,
                "cc": cc,
                "max_depth": max_depth,
                "priority": priority,
                "try_issues": try_issues,
                "source_code": func_code,
                "line_count": line_count,
                "requires_decomposition": requires_decomposition,
            })

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
                    for inner_stmt in stmt.body:
                        if isinstance(inner_stmt, ast.Try):
                            try_issues.append((inner_stmt.lineno, "Nested Try block inside Try body"))

                    for handler in stmt.handlers:
                        for h_stmt in handler.body:
                            if isinstance(h_stmt, ast.Try):
                                try_issues.append((h_stmt.lineno, "Try block inside Except handler"))

                    if stmt.orelse:
                        for el_stmt in stmt.orelse:
                            if isinstance(el_stmt, (ast.If, ast.Try)):
                                try_issues.append((el_stmt.lineno, f"{el_stmt.__class__.__name__} inside Try-Else block"))

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


def scan_file_for_anti_patterns(source: str, file_path: str = "") -> list[dict[str, Any]]:
    """Scan a file's source for control-flow anti-patterns.

    Returns a list of candidate dicts sorted by priority (1=highest).
    """
    if len(source.encode("utf-8")) > MAX_FILE_SIZE:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    scanner = FunctionCandidateScanner(filename=file_path, code_lines=source.splitlines(), full_file_source=source)
    scanner.visit(tree)
    return sorted(scanner.candidates, key=lambda c: c["priority"])