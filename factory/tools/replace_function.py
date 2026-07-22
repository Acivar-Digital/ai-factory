import argparse
import difflib
import json
import sys

from _codebase_common import (
    _normalize_content,
    fail,
    ok,
    resolve_repo_path,
)


def _bounded_diff(old_text, new_text, context=15):
    # Guarantee a trailing newline so difflib emits a lineterm on the final
    # source line (ast.unparse output has none, which would otherwise fuse
    # the last two hunk lines together).
    if old_text and not old_text.endswith("\n"):
        old_text += "\n"
    if new_text and not new_text.endswith("\n"):
        new_text += "\n"
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(
            old_lines, new_lines, fromfile="a", tofile="b", n=context, lineterm="\n"
        )
    )
    if not diff:
        return "(no changes detected)"
    return "".join(diff)


def _find_function(tree, name, class_name=None):
    import ast

    if class_name:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef) and sub.name == name:
                        return sub, True
        return None, False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node, True
    return None, False


def main():
    parser = argparse.ArgumentParser(
        description="Replace a function's source via AST manipulation."
    )
    parser.add_argument("relative_path", help="Path relative to project root.")
    parser.add_argument("function_name", help="Function name to replace.")
    parser.add_argument("new_function_code", help="Full new function source.")
    parser.add_argument("--class-name", default=None, help="Optional enclosing class.")
    args = parser.parse_args()

    try:
        path = resolve_repo_path(args.relative_path)
    except ValueError as e:
        print(json.dumps(fail(str(e)), indent=2))
        sys.exit(1)

    if not path.exists():
        print(json.dumps(fail(f"File not found: {args.relative_path}"), indent=2))
        sys.exit(1)
    if path.suffix != ".py":
        print(json.dumps(fail("Not a Python file."), indent=2))
        sys.exit(1)

    import ast

    try:
        content = _normalize_content(path.read_text(encoding="utf-8"))
        tree = ast.parse(content)
        new_func = ast.parse(args.new_function_code)
        if not new_func.body or not isinstance(
            new_func.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            print(
                json.dumps(
                    fail("new_function_code must be a single function definition."),
                    indent=2,
                )
            )
            sys.exit(1)
        new_node = new_func.body[0]

        target, found = _find_function(tree, args.function_name, args.class_name)
        if not found:
            print(
                json.dumps(
                    fail(
                        f"Function {args.function_name}"
                        + (f" in class {args.class_name}" if args.class_name else "")
                        + " not found."
                    ),
                    indent=2,
                )
            )
            sys.exit(1)

        assert target is not None
        start_line = target.lineno
        if target.decorator_list:
            start_line = min(d.lineno for d in target.decorator_list)
        end_line = target.end_lineno

        lines = content.splitlines(keepends=True)
        target_line = lines[start_line - 1]
        indent = target_line[:len(target_line) - len(target_line.lstrip())]

        new_func_lines = args.new_function_code.splitlines(keepends=True)
        if new_func_lines and not new_func_lines[-1].endswith("\n"):
            new_func_lines[-1] += "\n"

        new_code_indented = ""
        for line in new_func_lines:
            if line.strip():
                new_code_indented += indent + line
            else:
                new_code_indented += line

        old_src = "".join(lines[start_line - 1 : end_line])
        new_src = new_code_indented

        updated_lines = lines[:start_line - 1] + [new_code_indented] + lines[end_line:]
        updated_content = "".join(updated_lines)

        path.write_text(updated_content, encoding="utf-8")
        print(
            json.dumps(
                ok(
                    f"Replaced function {args.function_name} in {args.relative_path}",
                    {
                        "changed": True,
                        "diff": _bounded_diff(old_src, new_src),
                    },
                ),
                indent=2,
            )
        )
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps(fail(f"replace_function failed: {e}"), indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
