"""VirtualASTBuffer — in-memory AST replacement for surgical code edits.

Incorporated from WIP/code_hygiene/scanners/virtual_ast_buffer.py patterns.
Allows replacing a function's body or helper functions in memory
without touching disk, then verifying the result via AST + lint checks.
"""

import ast
import logging

logger = logging.getLogger("virtual_ast_buffer")


class VirtualASTBuffer:
    """In-memory AST buffer for surgical code replacement.

    Takes full file source and a file path. Provides methods to
    replace a function body or inject helper functions, returning
    the modified source as a string — without writing to disk.
    """

    def __init__(self, source: str, file_path: str) -> None:
        self.original_source = source
        self.file_path = file_path
        self._tree: ast.Module | None = None
        self._source = source

    @property
    def tree(self) -> ast.Module:
        if self._tree is None:
            self._tree = ast.parse(self._source)
        return self._tree

    def replace_function(
        self,
        function_name: str,
        new_function_code: str,
        helper_functions: list[str] | None = None,
    ) -> str:
        """Replace a function's body in memory and optionally inject helpers.

        Args:
            function_name: Name of the function to replace.
            new_function_code: Full source of the replacement function.
            helper_functions: List of helper function source strings to inject
                before the main function.

        Returns:
            The modified full file source as a string.
        """
        tree = self.tree
        target: ast.FunctionDef | ast.AsyncFunctionDef | None = None
        parent: ast.Module | ast.ClassDef | None = None

        # Search top-level functions first
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                target = node
                parent = tree
                break
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == function_name:
                        target = sub
                        parent = node
                        break
                if target:
                    break

        if target is None:
            raise ValueError(f"Function `{function_name}` not found in {self.file_path}")

        # Parse the new function code
        new_func_tree = ast.parse(new_function_code)
        if not new_func_tree.body:
            raise ValueError("new_function_code is empty")

        new_node = new_func_tree.body[0]
        if not isinstance(new_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise ValueError("new_function_code must be a function definition")

        # Preserve the original node's position metadata
        new_node.lineno = target.lineno
        new_node.col_offset = target.col_offset
        new_node.end_lineno = target.end_lineno
        new_node.end_col_offset = target.end_col_offset

        # Replace in parent
        if isinstance(parent, ast.ClassDef):
            for i, sub in enumerate(parent.body):
                if sub is target:
                    parent.body[i] = new_node
                    break
        else:
            for i, node in enumerate(tree.body):
                if node is target:
                    tree.body[i] = new_node
                    break

        # Inject helper functions before the main function
        if helper_functions:
            helpers_to_inject: list[ast.AST] = []
            for helper_code in helper_functions:
                try:
                    helper_tree = ast.parse(helper_code)
                    if helper_tree.body:
                        helpers_to_inject.append(helper_tree.body[0])
                except SyntaxError as e:
                    logger.warning(f"[VirtualASTBuffer] SyntaxError in helper: {e}")

            if helpers_to_inject and isinstance(parent, ast.Module):
                func_idx = None
                for i, node in enumerate(tree.body):
                    if node is new_node:
                        func_idx = i
                        break
                if func_idx is not None:
                    for j, helper in enumerate(helpers_to_inject):
                        tree.body.insert(func_idx + j, helper)  # type: ignore[arg-type]

        return ast.unparse(tree)

    def inject_helper(
        self,
        helper_code: str,
        anchor_function: str | None = None,
    ) -> str:
        """Inject a helper function into the file in memory.

        Args:
            helper_code: Full source of the helper function.
            anchor_function: If given, insert the helper right before
                this function. If None, append to top level.

        Returns:
            The modified full file source as a string.
        """
        tree = self.tree
        helper_tree = ast.parse(helper_code)
        if not helper_tree.body:
            raise ValueError("helper_code is empty")

        helper_node = helper_tree.body[0]
        if not isinstance(helper_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise ValueError("helper_code must be a function definition")

        if anchor_function and isinstance(tree, ast.Module):
            for i, node in enumerate(tree.body):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == anchor_function:
                    tree.body.insert(i, helper_node)
                    return ast.unparse(tree)

        # Append to top level
        if isinstance(tree, ast.Module):
            tree.body.append(helper_node)

        return ast.unparse(tree)

    def get_source(self) -> str:
        """Return the current in-memory source."""
        if self._tree is not None:
            return ast.unparse(self._tree)
        return self._source


def ensure_pydantic_imports(source: str, refactored_code: str) -> str:
    """Auto-inject pydantic imports if the refactored code uses pydantic types.

    Incorporated from kill_tries.py's ensure_pydantic_imports pattern.
    """
    if "model_validate" in refactored_code or "model_dump" in refactored_code or "BaseModel" in refactored_code:
        if "from pydantic" not in source and "import pydantic" not in source:
            source = "from pydantic import BaseModel\n" + source
    return source