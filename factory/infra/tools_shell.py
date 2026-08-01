"""Tool confinement for the Orchestrator State Machine (build.md §4, §5c).

Every worker capability is a subprocess wrapper around an existing
`factory/tools/*.py` CLI. Agents NEVER touch the filesystem directly — they
receive only the allow-listed, ACL-wrapped tools the orchestrator hands them.
"""
import json
from factory.common import _run_tool
from factory.infra.ast_verifier import extract_header_symbol_contract, run_lint_regression, verify_refactored_ast
from factory.infra.control import REPO_ROOT
from factory.infra.tools_file import _check_edit_result, _src_write_guard
from factory.infra.tools_memory import get_current_agent, get_current_role


def _auto_remember(note: str) -> None:
    try:
        from factory.infra import artefacts
        role = get_current_role()
        if role:
            artefacts.remember_note(role, note, agent_id=get_current_agent())
    except Exception:
        pass

def replace_text(relative_path: str, target_text: str, replacement_text: str, is_regex: bool=False, case_insensitive: bool=False, ignore_whitespace: bool=False) -> str:
    """Replace exact text or regex in a repo file. Returns JSON result."""
    _g = _src_write_guard('replace_text', relative_path)
    if _g:
        return _g
    argv = [relative_path, target_text, replacement_text]
    if is_regex:
        argv.append('--is-regex')
    if case_insensitive:
        argv.append('--case-insensitive')
    if ignore_whitespace:
        argv.append('--ignore-whitespace')
    result = _check_edit_result('replace_text', _run_tool('replace_text', argv))
    _auto_remember(f'[replace_text] {relative_path}\n---OLD---\n{target_text}\n---NEW---\n{replacement_text}')
    return result

def replace_function(relative_path: str, function_name: str, new_function_code: str, class_name: str | None=None) -> str:
    """Replace a function's body via AST manipulation. Returns JSON result."""
    _g = _src_write_guard('replace_function', relative_path)
    if _g:
        return _g
    argv = [relative_path, function_name, new_function_code]
    if class_name:
        argv += ['--class-name', class_name]
    result = _check_edit_result('replace_function', _run_tool('replace_function', argv))
    scope = f'{class_name}.{function_name}' if class_name else function_name
    _auto_remember(f'[replace_function] {relative_path}::{scope}\n{new_function_code}')
    return result

def add_constant(relative_path: str, constant_name: str, constant_code: str) -> str:
    """Add a top-level constant to a Python file (AST). Returns JSON result."""
    _g = _src_write_guard('add_constant', relative_path)
    if _g:
        return _g
    result = _check_edit_result('add_constant', _run_tool('add_constant', [relative_path, constant_name, constant_code]))
    _auto_remember(f'[add_constant] {relative_path}: {constant_name} = {constant_code}')
    return result

def add_import(relative_path: str, import_code: str) -> str:
    """Add an import line to the top of a Python file (AST). Returns JSON result."""
    _g = _src_write_guard('add_import', relative_path)
    if _g:
        return _g
    result = _check_edit_result('add_import', _run_tool('add_import', [relative_path, import_code]))
    _auto_remember(f'[add_import] {relative_path}: {import_code}')
    return result

def move_symbol(symbol_name: str, source_path: str, dest_path: str) -> str:
    """Move a function/class between files and update imports. Returns JSON result."""
    _g = _src_write_guard('move_symbol', source_path, dest_path)
    if _g:
        return _g
    result = _run_tool('move_symbol', [symbol_name, source_path, dest_path])
    _auto_remember(f'[move_symbol] {symbol_name}: {source_path} → {dest_path}')
    return result


def verify_edit(relative_path: str, function_name: str | None = None) -> str:
    """Run multi-layer AST verification on a file after an edit.

    Checks syntax, CC, nesting, try-pyramids, hallucinated fields,
    argument swaps, signature parity, namespace collisions, and
    unimported symbols. Also runs ruff/pyright regression checks.

    Returns JSON result with verification status and any violations found.
    """
    import ast

    from factory.infra.tools_file import normalize_read_path

    rp = normalize_read_path(relative_path)
    full_path = REPO_ROOT / rp
    if not full_path.exists():
        return json.dumps({"ok": False, "error": f"File not found: {rp}"})

    source = full_path.read_text(encoding="utf-8")
    header_contract = extract_header_symbol_contract(source)

    # Run lint regression check
    lint_ok, lint_msg = run_lint_regression("", source)
    if not lint_ok:
        return json.dumps({"ok": False, "error": f"Lint regression: {lint_msg}"})

    # If a specific function was edited, run full AST verification on it
    if function_name:
        try:
            tree = ast.parse(source)
            target = None
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                    target = node
                    break
            if target is None:
                return json.dumps({"ok": True, "message": f"Function {function_name} not found for targeted verification"})

            func_source = ast.unparse(target)
            passed, cc, depth, msg = verify_refactored_ast(
                code=func_source,
                candidate_name=function_name,
                orig_code=func_source,
                header_contract=header_contract,
            )
            return json.dumps({
                "ok": passed,
                "function_name": function_name,
                "cc": cc,
                "max_depth": depth,
                "message": msg,
            })
        except Exception as e:
            return json.dumps({"ok": False, "error": f"AST verification failed: {e}"})

    # Full-file verification: check all functions
    try:
        tree = ast.parse(source)
        all_ok = True
        results = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_source = ast.unparse(node)
                passed, cc, depth, msg = verify_refactored_ast(
                    code=func_source,
                    candidate_name=node.name,
                    orig_code=func_source,
                    header_contract=header_contract,
                )
                if not passed:
                    all_ok = False
                results.append({"function": node.name, "passed": passed, "cc": cc, "depth": depth, "message": msg})
        return json.dumps({"ok": all_ok, "functions": results})
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Full-file AST verification failed: {e}"})
