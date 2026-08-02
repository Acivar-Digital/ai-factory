"""Tool confinement for the Orchestrator State Machine (build.md §4, §5c).

Every worker capability is a subprocess wrapper around an existing
`factory/tools/*.py` CLI. Agents NEVER touch the filesystem directly — they
receive only the allow-listed, ACL-wrapped tools the orchestrator hands them.
"""
import ast
import json
from pathlib import Path
from pydantic_ai import ModelRetry
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


def _rollback_from_orig(staged: str) -> None:
    """Restore staged file from its .orig baseline if available."""
    orig_path = Path(staged + ".orig")
    if orig_path.exists():
        Path(staged).write_text(orig_path.read_text(encoding="utf-8"), encoding="utf-8")

def replace_text(relative_path: str, target_text: str, replacement_text: str, is_regex: bool=False, case_insensitive: bool=False, ignore_whitespace: bool=False) -> str:
    """Replace exact text or regex in a repo file. Returns JSON result."""
    from factory.infra.context import stage_path
    staged = stage_path(relative_path)
    _g = _src_write_guard('replace_text', staged)
    if _g:
        return _g
    argv = [staged, target_text, replacement_text]
    if is_regex:
        argv.append('--is-regex')
    if case_insensitive:
        argv.append('--case-insensitive')
    if ignore_whitespace:
        argv.append('--ignore-whitespace')
    result = _check_edit_result('replace_text', _run_tool('replace_text', argv))
    _auto_remember(f'[replace_text] {staged}\n---OLD---\n{target_text}\n---NEW---\n{replacement_text}')
    try:
        ast.parse(Path(staged).read_text(encoding="utf-8"))
    except SyntaxError:
        _rollback_from_orig(staged)
        raise ModelRetry(
            "AST SyntaxError: edit corrupted file syntax. Staged file auto-restored from .orig baseline. "
            "MANDATORY: Use replace_function on the isolated AST function node instead of whole-file replace_text."
        )
    ast_diag_str = verify_edit(staged, None)
    parsed = json.loads(ast_diag_str)
    if parsed.get("ok") is False or parsed.get("cc", 0) > 5:
        header_contract = extract_header_symbol_contract(
            Path(staged).read_text(encoding="utf-8")
        )
        avail_syms = header_contract.get("imported_modules", []) + header_contract.get("top_level_symbols", [])
        sym_hint = f" Available symbols in module: {avail_syms[:15]}." if avail_syms else ""
        raise ModelRetry(
            f"AST Verification Failed: {parsed.get('message', parsed.get('error', 'CC > 5'))}."
            f"{sym_hint} Please fix the edit to use simple guard clauses and ensure CC <= 5."
        )
    return f"{result}\n[AST Verification]: {ast_diag_str}"

def replace_function(relative_path: str, function_name: str, new_function_code: str, class_name: str | None=None) -> str:
    """Replace a function's body via AST manipulation. Returns JSON result."""
    from factory.infra.context import stage_path
    staged = stage_path(relative_path)
    _g = _src_write_guard('replace_function', staged)
    if _g:
        return _g
    argv = [staged, function_name, new_function_code]
    if class_name:
        argv += ['--class-name', class_name]
    result = _check_edit_result('replace_function', _run_tool('replace_function', argv))
    scope = f'{class_name}.{function_name}' if class_name else function_name
    _auto_remember(f'[replace_function] {staged}::{scope}\n{new_function_code}')
    try:
        ast.parse(Path(staged).read_text(encoding="utf-8"))
    except SyntaxError:
        _rollback_from_orig(staged)
        raise ModelRetry(
            "AST SyntaxError: edit corrupted file syntax. Staged file auto-restored from .orig baseline. "
            "MANDATORY: Use replace_function on the isolated AST function node instead of whole-file replace_text."
        )
    ast_diag_str = verify_edit(staged, function_name)
    parsed = json.loads(ast_diag_str)
    if parsed.get("ok") is False or parsed.get("cc", 0) > 5:
        header_contract = extract_header_symbol_contract(
            Path(staged).read_text(encoding="utf-8")
        )
        avail_syms = header_contract.get("imported_modules", []) + header_contract.get("top_level_symbols", [])
        sym_hint = f" Available symbols in module: {avail_syms[:15]}." if avail_syms else ""
        raise ModelRetry(
            f"AST Verification Failed: {parsed.get('message', parsed.get('error', 'CC > 5'))}."
            f"{sym_hint} Please fix the edit to use simple guard clauses and ensure CC <= 5."
        )
    return f"{result}\n[AST Verification]: {ast_diag_str}"

def add_constant(relative_path: str, constant_name: str, constant_code: str) -> str:
    """Add a top-level constant to a Python file (AST). Returns JSON result."""
    from factory.infra.context import stage_path
    staged = stage_path(relative_path)
    _g = _src_write_guard('add_constant', staged)
    if _g:
        return _g
    result = _check_edit_result('add_constant', _run_tool('add_constant', [staged, constant_name, constant_code]))
    _auto_remember(f'[add_constant] {staged}: {constant_name} = {constant_code}')
    return result

def add_import(relative_path: str, import_code: str) -> str:
    """Add an import line to the top of a Python file (AST). Returns JSON result."""
    from factory.infra.context import stage_path
    staged = stage_path(relative_path)
    _g = _src_write_guard('add_import', staged)
    if _g:
        return _g
    result = _check_edit_result('add_import', _run_tool('add_import', [staged, import_code]))
    _auto_remember(f'[add_import] {staged}: {import_code}')
    return result

def move_symbol(symbol_name: str, source_path: str, dest_path: str) -> str:
    """Move a function/class between files and update imports. Returns JSON result."""
    from factory.infra.context import stage_path
    staged_src = stage_path(source_path)
    staged_dst = stage_path(dest_path)
    _g = _src_write_guard('move_symbol', staged_src, staged_dst)
    if _g:
        return _g
    result = _run_tool('move_symbol', [symbol_name, staged_src, staged_dst])
    _auto_remember(f'[move_symbol] {symbol_name}: {staged_src} → {staged_dst}')
    return result


def verify_edit(relative_path: str, function_name: str | None = None) -> str:
    """Run multi-layer AST verification on a file after an edit.

    Checks syntax, CC, nesting, try-pyramids, hallucinated fields,
    argument swaps, signature parity, namespace collisions, and
    unimported symbols. Also runs ruff/pyright regression checks.

    Returns JSON result with verification status and any violations found.
    """
    import ast

    from factory.infra.context import stage_path

    staged = stage_path(relative_path)
    full_path = REPO_ROOT / staged
    if not full_path.exists():
        return json.dumps({"ok": False, "error": f"File not found: {staged}"})

    source = full_path.read_text(encoding="utf-8")
    orig_file_path = full_path.with_suffix(full_path.suffix + ".orig")
    if orig_file_path.exists():
        orig_code = orig_file_path.read_text(encoding="utf-8")
    else:
        orig_code = source
    header_contract = extract_header_symbol_contract(source)

    # Run lint regression check
    lint_ok, lint_msg = run_lint_regression(orig_code, source)
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
                try:
                    orig_tree = ast.parse(orig_code)
                    orig_exists = any(
                        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and n.name == function_name
                        for n in ast.walk(orig_tree)
                    )
                except SyntaxError:
                    orig_exists = False
                if orig_exists:
                    return json.dumps({"ok": False, "error": f"Function '{function_name}' was removed or unparseable in {staged}"})
                return json.dumps({"ok": True, "message": f"Function '{function_name}' not present in file"})

            func_source = ast.unparse(target)
            passed, cc, depth, msg = verify_refactored_ast(
                code=func_source,
                candidate_name=function_name,
                orig_code=orig_code,
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
                    orig_code=orig_code,
                    header_contract=header_contract,
                )
                if not passed:
                    all_ok = False
                results.append({"function": node.name, "passed": passed, "cc": cc, "depth": depth, "message": msg})
        return json.dumps({"ok": all_ok, "functions": results})
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Full-file AST verification failed: {e}"})
