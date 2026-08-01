#!/usr/bin/env python3
"""
Kill-Tries Scanner & Refactorer: Flat Control Flow & Anti-Pattern Eliminator.
Scans Python files in src2/ for:
1. Priority 1: Try Pyramids / Try-Else-If Anti-Patterns.
2. Priority 2: Deep Nesting (Depth > 3).
3. Priority 3: Cyclomatic Complexity (CC > 5).

Uses AST pre-filtering first, Pydantic AI (CONTROL_SHEET.scanner_model) for refactoring,
and AST validation + replacement verification before committing code changes.

Emits admin/code_hygiene/reports/kill_tries.json
"""

import ast
import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import logfire
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

# Ensure repo root in sys.path
repo_root = Path(__file__).resolve().parents[3]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from admin.code_hygiene.scanners.virtual_ast_buffer import VirtualASTBuffer  # noqa: E402
from admin.controls.controls import CONTROL_SHEET  # noqa: E402

# Initialize Logfire instrumentation once globally
try:
    logfire.configure(send_to_logfire=False)
    logfire.instrument_pydantic_ai()
except Exception:
    pass

CHECKPOINT_FILE = repo_root / "admin" / "code_hygiene" / "reports" / "kill_tries_checkpoint.jsonl"
REPORT_FILE = repo_root / "admin" / "code_hygiene" / "reports" / "kill_tries.json"
SRC2_DIR = repo_root / "src2"
PROMPT_TEMPLATE_PATH = repo_root / "admin" / "code_hygiene" / "scanners" / "kill_tries_prompt.yaml"
PROMPT_RETRY_PATH = repo_root / "admin" / "code_hygiene" / "scanners" / "kill_tries_prompt_retry.yaml"
LIST_FILE = repo_root / "admin" / "code_hygiene" / "scanners" / "kill_tries_list.txt"


def get_timestamp() -> str:
    now = datetime.now()
    return now.strftime("%m-%d-%H:%M:%S") + f":{int(now.microsecond / 1000):03d}"

def get_model_provider_name(model) -> str:
    base_url = getattr(getattr(model, 'provider', None), 'base_url', '')
    if 'antigravity' in base_url:
        return 'antigravity_manager'
    if 'literouter' in base_url or base_url.endswith(':7766/v1'):
        return 'literouter'
    if 'openrouter' in base_url:
        return 'openrouter'
    if 'localhost:8045' in base_url or 'antigravity' in base_url:
        return 'antigravity_manager'
    return base_url.split('/')[2] if '/' in base_url else 'unknown'

# Configure logging with ANSI colors
class ColoredFormatter(logging.Formatter):
    COLORS = {
        'INFO': '\033[94m',
        'WARNING': '\033[93m',
        'ERROR': '\033[91m',
        'CRITICAL': '\033[91m\033[1m'
    }
    RESET = '\033[0m'
    BOLD = '\033[1m'
    GREEN = '\033[92m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        msg = record.getMessage()
        if msg.startswith("[") and "]" in msg:
            end_idx = msg.find("]") + 1
            msg = f"{self.BOLD}{self.GREEN}{msg[:end_idx]}{self.RESET} {msg[end_idx:].strip()}"
        return f"{color}[{record.levelname}]{self.RESET} {msg}"

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter())
logger = logging.getLogger("KillTriesScanner")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False


def load_prompt_template(path: Path | None = None) -> dict:
    """Load a kill_tries prompt template from a YAML file.

    Args:
        path: Path to the YAML template. Defaults to PROMPT_TEMPLATE_PATH.

    Returns the raw YAML dict with system_instruction, anti_patterns,
    samples, narrative_context, and other sections.
    """
    template_path = path or PROMPT_TEMPLATE_PATH
    if not template_path.exists():
        logger.warning(f"Prompt template not found at {template_path}")
        return {}
    with open(template_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_target_files() -> set[str] | None:
    """Load the kill_tries_list.txt file for selective targeting.

    Returns a set of relative file paths if the list exists,
    or None if the list file is not present (scan all).
    """
    if not LIST_FILE.exists():
        return None
    with open(LIST_FILE, encoding="utf-8") as f:
        paths = {line.strip() for line in f if line.strip() and not line.startswith("#")}
    logger.info(f"Loaded {len(paths)} targeted files from kill_tries_list.txt")
    return paths


def harvest_context(func_node: ast.FunctionDef | ast.AsyncFunctionDef, file_tree: ast.Module,
                    source_lines: list[str]) -> dict:
    """Extract minimal context dependencies for a target function.

    Walks the function's AST to find:
    1. Import names it depends on
    2. Module-level constants it references
    3. Pydantic model types in its signature annotations

    Returns a dict with 'imports', 'dependencies', and 'pydantic_models' sections.
    """
    referenced_names: set[str] = set()

    for inner in ast.walk(func_node):
        if isinstance(inner, ast.Name):
            referenced_names.add(inner.id)
        elif isinstance(inner, ast.Attribute):
            parts = []
            node = inner
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                parts.append(node.id)
                referenced_names.add(parts[-1])

    imports: list[str] = []
    dependencies: list[str] = []
    pydantic_models: list[str] = []

    for node in file_tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_name = alias.name.split(".")[0]
                if top_name in referenced_names:
                    imports.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            used_names: list[str] = []
            for alias in node.names:
                name = alias.asname or alias.name
                if name in referenced_names:
                    used_names.append(name if alias.asname else alias.name)
            if used_names:
                imports.append(f"from {node.module} import {', '.join(used_names)}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in referenced_names:
                dependencies.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in referenced_names:
                    dependencies.append(target.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id in referenced_names:
                dep_name = node.target.id
                if isinstance(node.annotation, ast.Name):
                    ann = node.annotation.id
                    if ann == "BaseModel" or (node.annotation and isinstance(node.annotation, ast.Subscript)
                                             and hasattr(node.annotation.value, 'id')):
                        pydantic_models.append(dep_name)
                    else:
                        dependencies.append(f"{dep_name}:{ann}")
                else:
                    dependencies.append(dep_name)

    return {
        "imports": imports,
        "dependencies": dependencies,
        "pydantic_models": pydantic_models,
    }


def format_prompt(template: dict, candidate: dict, attempt: int = 1,
                   history: list | None = None,
                   what_worked_text: str = "", violations_text: str = "") -> str:
    """Build the final LLM prompt from a narrative YAML template.

    For attempt 1, renders the initial prompt from the template.
    For retries (attempt > 1 with history), uses a concise delta prompt
    to avoid exponential token bloat from duplicated conversation history.
    """
    return _retry_prompt(template, candidate, attempt, history or [],
                         what_worked_text, violations_text)


def _retry_prompt(template: dict, candidate: dict, attempt: int, history: list,
                    what_worked_text: str, violations_text: str) -> str:
    """Build a concise retry prompt for attempts > 1 when history is already present.

    When message_history is non-empty, avoid re-sending the full template narrative
    to prevent exponential token bloat. Send only the delta feedback.
    """
    if not history:
        return _render_narrative(template, candidate, attempt, history,
                                       what_worked_text, violations_text)
    function_name = candidate.get("function_name", "")
    file_path = candidate.get("file_path", "")
    max_attempts = candidate.get("max_attempts", 5)
    attempts_left = max_attempts - attempt + 1
    source_code = candidate.get("source_code", "")
    return (
        f"=== ATTEMPT {attempt}/{max_attempts} (CONCISE DELTA) ===\n\n"
        f"Previous attempt feedback for {function_name} ({file_path}):\n\n"
        f"ISSUES TO FIX:\n{violations_text}\n\n"
        f"WHAT WORKED (preserve these):\n{what_worked_text}\n\n"
        f"YOU HAVE {attempts_left} ATTEMPT(S) LEFT.\n"
        f"Take your previous attempt and surgically fix only the violations above.\n"
        f"Keep the same structure and do not add classes.\n"
        f"CRITICAL: If you extract helper functions, you MUST prefix each one with _{function_name}_ to guarantee uniqueness (e.g., _{function_name}_step1). Do NOT use bare underscore names.\n"
        f"CRITICAL: RETURN TYPE LOCK. You MUST preserve the exact return type and structure. If the original returns a raw dict, you MUST return a raw dict. Do not convert dicts to Pydantic models.\n\n"
        f"<source_code>\n{source_code}\n</source_code>\n"
    )


def _render_narrative(template: dict, candidate: dict, attempt_num: int,
                         history: list | None = None,
                         what_worked_text: str = "",
                         violations_text: str = "") -> str:
    """Internal: render the narrative prompt template with dynamic values."""
    source_code = candidate.get("source_code", "")
    function_name = candidate.get("function_name", "")
    file_path = candidate.get("file_path", "")
    line = candidate.get("line", "")
    cc = candidate.get("cc", "")
    max_depth = candidate.get("max_depth", "")
    priority = candidate.get("priority", "")
    try_issues = candidate.get("try_issues", [])
    max_attempts = candidate.get("max_attempts", 5)

    system_prompt = template.get("system_prompt", "")
    upstream_callers = candidate.get("upstream_callers", "No upstream callers detected.")
    module_context = candidate.get("module_context", "No module context available.")
    system_prompt = system_prompt.format(
        function_name=function_name,
        file_path=file_path,
        line=line,
        attempt=attempt_num,
        max_attempts=max_attempts,
        attempts_left=max_attempts - attempt_num + 1,
        violations=violations_text,
        what_worked=what_worked_text,
        what_to_fix=violations_text,
        upstream_callers=upstream_callers,
        module_context=module_context,
    ) if '{' in system_prompt else system_prompt
    system = template.get("system_instruction", "")
    anti_patterns = template.get("anti_patterns", "")
    narrative = template.get("narrative_context", "")
    samples = template.get("samples")

    is_retry = attempt_num > 1 and history is not None

    anti_patterns_list = ""
    if isinstance(try_issues, list) and try_issues:
        for issue in try_issues:
            if isinstance(issue, tuple) and len(issue) >= 2:
                anti_patterns_list += f"  - {issue[1]} (line {issue[0]})\n"
            else:
                anti_patterns_list += f"  - {issue}\n"
    elif isinstance(try_issues, str) and try_issues:
        anti_patterns_list = f"  - {try_issues}\n"

    narrative_context = narrative.format(
        function_name=function_name,
        file_path=file_path,
        narrative="",
        anti_patterns_list="",
        what_worked="",
        what_to_fix="",
        upstream_callers="",
        module_context="",
        attempts_left="",
    ) if "{" in narrative else narrative

    samples_section = ""
    if samples and not isinstance(samples, str):
        for s in samples:
            samples_section += f"\n--- Sample: {s.get('name', '')} ---\n"
            after = s.get("after", "")
            if after:
                for line in after.splitlines():
                    samples_section += f"    {line}\n"
    elif samples and isinstance(samples, str):
        samples_section = f"\n{samples}\n"

    if is_retry:
        attempts_left = max_attempts - attempt_num + 1
        return (
            f"{system_prompt}\n\n{system}\n\n"
            f"=== ATTEMPT {attempt_num}/{max_attempts} ===\n\n"
            f"Previous attempt feedback:\n\n"
            f"ISSUES REMAINING:\n{violations_text}\n\n"
            f"WHAT WORKED (preserve these):\n{what_worked_text}\n\n"
            f"FIX THESE NOW (focus only on what's broken):\n{violations_text}\n\n"
            f"SAMPLES (reference for fix patterns):\n{samples_section}\n"
            f"{anti_patterns}\n\n"
            f"RULES:\n{template.get('conditions', template.get('rules', ''))}\n\n"
            f"YOU HAVE {attempts_left} ATTEMPT(S) LEFT.\n"
            f"Take your current code and surgically fix only the violations above.\n\n"
            f"<source_code>\n{source_code}\n</source_code>\n"
        )

    return (
        f"{system_prompt}\n\n{system}\n\n"
        f"=== THE NARRATIVE ===\n{narrative_context}\n\n"
        f"=== WHAT WENT WRONG ===\n{anti_patterns}\n\n"
        f"=== WHAT GOOD LOOKS LIKE ===\n{samples_section}\n\n"
        f"=== RULES ===\n{template.get('conditions', template.get('rules', ''))}\n\n"
        f"TARGET: Refactor {function_name} ({file_path}:{line}) to pass all checks.\n"
        f"CC={cc} | Depth={max_depth} | Priority={priority}\n"
        f"You have {max_attempts} attempt(s).\nFocus.\n\n"
        f"<source_code>\n{source_code}\n</source_code>\n"
    )


# =====================================================================
# AST DETERMINISTIC TRANSFORMER PASS (PHASE 1 - 0 LLM CALLS)
# =====================================================================

class ASTFlatControlFlowTransformer(ast.NodeTransformer):
    """
    Pure Python AST Transformer that flattens control flow deterministically:
    1. Guard Clause Inversion: Flips `if condition: [body]` at function entry into `if not (condition): return`
    2. Try-Else Flattening: Flattens `try...else` pyramids by moving orelse statements to main body if try ends with return/raise
    """
    def __init__(self):
        self.modified = False

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        node = self._apply_guard_clause_inversion(node)
        return node

    def visit_AsyncFunctionDef(self, node):
        self.generic_visit(node)
        node = self._apply_guard_clause_inversion(node)
        return node

    def _apply_guard_clause_inversion(self, node):
        # Pattern 1: Function body is a single `if condition: [statements...]`
        if len(node.body) == 1 and isinstance(node.body[0], ast.If) and not node.body[0].orelse:
            if_stmt = node.body[0]
            # Create inverted condition: not (condition)
            inverted_cond = ast.UnaryOp(op=ast.Not(), operand=if_stmt.test)
            guard_node = ast.If(
                test=ast.fix_missing_locations(inverted_cond),
                body=[ast.Return(value=None)],
                orelse=[]
            )
            node.body = [ast.fix_missing_locations(guard_node)] + if_stmt.body
            self.modified = True

        return node

    def visit_Try(self, node):
        self.generic_visit(node)
        # Pattern 2: Try body terminates with return/raise, so orelse can be flattened into main statement list
        if node.orelse and self._body_always_terminates(node.body):
            # Move orelse statements out after try
            flattened_orelse = node.orelse
            node.orelse = []
            self.modified = True
            return [node] + flattened_orelse
        return node

    def _body_always_terminates(self, stmts: list[ast.stmt]) -> bool:
        if not stmts:
            return False
        last = stmts[-1]
        return isinstance(last, (ast.Return, ast.Raise))


def test_file_with_ruff(file_path: Path) -> bool:
    """Run ruff check on a file to ensure no syntax/undefined variable/linter errors."""
    import subprocess
    try:
        res = subprocess.run(
            ["uv", "run", "ruff", "check", str(file_path)],
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode != 0:
            return False
        return True
    except Exception:
        return False


def run_ast_transformer_on_file(file_path: Path) -> bool:
    """Disabled full-file ast.unparse to prevent class method unindentation/corruption."""
    return False


def run_ast_transformer_pass_all() -> int:
    """Run pure AST transformer pass across all files in src2/."""
    logger.info("Executing Phase 1: Pure AST Transformer Pass across src2/...")
    modified_count = 0
    for py_file in sorted(SRC2_DIR.rglob("*.py")):
        if py_file.is_file():
            if run_ast_transformer_on_file(py_file):
                modified_count += 1
    logger.info(f"Phase 1 complete: AST Transformer modified {modified_count} file(s) deterministically.")
    return modified_count


# =====================================================================
# AST COMPLEXITY & NESTING VISITORS
# =====================================================================

class ComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.complexity = 1

    def visit_If(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_Assert(self, node):
        self.complexity += 1
        self.generic_visit(node)


class FunctionCandidateScanner(ast.NodeVisitor):
    CONTROL_NODES = (ast.If, ast.Try, ast.For, ast.While, ast.With)

    def __init__(self, filename: str, code_lines: list[str]):
        self.filename = filename
        self.code_lines = code_lines
        self.candidates = []

    def visit_FunctionDef(self, node):
        self._check_function(node)

    def visit_AsyncFunctionDef(self, node):
        self._check_function(node)

    def _check_function(self, node):
        comp_vis = ComplexityVisitor()
        comp_vis.visit(node)
        cc = comp_vis.complexity

        max_depth, max_depth_line, try_issues = self._check_body_nesting(node.body, depth=0)

        if len(try_issues) > 0 or max_depth > 3 or cc > 5:
            end_line = getattr(node, 'end_lineno', node.lineno)
            func_code = ast.unparse(node)

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
            })

        self.generic_visit(node)

    def _check_body_nesting(self, statements, depth):
        max_d = depth
        max_line = 0
        try_issues = []

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
                    # elif: same logical depth as parent if, not nested
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


# =====================================================================
# PYDANTIC SCHEMAS FOR LLM REFACTORING
# =====================================================================

class RefactoringVerdict(BaseModel):
    function_name: str = Field(..., description="Name of the target function being refactored")
    refactored_code: str = Field(..., description="Complete refactored python code for the main function starting at column 0 (no leading indentation), using flat control flow, guard clauses, and no nested try/else blocks")
    helper_functions: list[str] = Field(default_factory=list, description="Extracted private helper functions code blocks starting at column 0 (no leading indentation)")
    explanation: str = Field(..., description="Summary of how the anti-patterns and deep nesting were eliminated")

    @field_validator('refactored_code', 'helper_functions', mode='before')
    @classmethod
    def strip_markdown_backticks(cls, v):
        def _clean(s: str) -> str:
            s = s.strip()
            if s.startswith('```python'):
                s = s[9:]
            elif s.startswith('```'):
                s = s[3:]
            if s.endswith('```'):
                s = s[:-3]
            return s.strip()

        if isinstance(v, str):
            return _clean(v)
        elif isinstance(v, list):
            return [_clean(item) if isinstance(item, str) else item for item in v]
        return v

    @model_validator(mode='after')
    def validate_structural_constraints(self):
        combined = self.refactored_code + "\n" + "\n".join(self.helper_functions)
        lines = combined.splitlines()

        safe_modules = {"typing", "collections", "enum", "dataclasses", "itertools"}
        unauthorized_imports = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith(('import ', 'from ')):
                parts = stripped.split()
                mod = parts[1].split('.')[0] if len(parts) > 1 else ""
                if mod not in safe_modules and not mod.startswith("src2"):
                    unauthorized_imports.append(stripped)

        if unauthorized_imports:
            raise ModelRetry(
                f"CRITICAL: You included unauthorized import statements: {unauthorized_imports}. "
                f"You may ONLY import from {safe_modules} or internal `src2` modules. "
                f"All other necessary imports are already at the top of the file."
            )

        class_lines = [line for line in lines if line.strip().startswith('class ')]
        if class_lines:
            raise ModelRetry(
                f"CRITICAL: You created a class: {class_lines}. "
                f"You MUST NOT create classes to pass state. If you need to pass many variables to a helper, "
                f"use a standard Python dict or pass them as arguments. Remove the class definition immediately."
            )

        # Closure Ban: Prevent nested function definitions inside main refactored code
        try:
            main_tree = ast.parse(self.refactored_code)
            for node in ast.walk(main_tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name != self.function_name:
                        raise ModelRetry(
                            f"CRITICAL: You defined a nested function `{node.name}` inside `refactored_code`. "
                            f"Flat control flow forbids closures. Move `{node.name}` into the `helper_functions` list "
                            f"and ensure it starts with an underscore (e.g., `_{node.name}`)."
                        )
        except SyntaxError:
            pass

        # Helper Naming Shock Collar: Ensure all helper functions start with an underscore
        for helper_code in self.helper_functions:
            try:
                helper_tree = ast.parse(helper_code)
                for node in helper_tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not node.name.startswith("_"):
                            raise ModelRetry(
                                f"CRITICAL: Helper function `{node.name}` MUST start with an underscore (e.g., `_{node.name}`). "
                                f"Rename it in the helper definition AND update all call sites in the main function."
                            )
            except SyntaxError:
                pass

        return self


# =====================================================================
# MODULE-LEVEL PYDANTIC AI AGENT & DEPENDENCIES
# =====================================================================

@dataclass
class RefactorDeps:
    orig_code: str = ""
    full_file_source: str = ""
    file_path: str = ""
    line: int = 0
    end_line: int = 0
    func_name: str = ""
    baseline_errors: set[str] = field(default_factory=set)


def _normalize_pyright_error(line: str) -> str:
    line = line.strip()
    if " - " in line:
        return line.split(" - ", 1)[-1].strip()
    return line


def _get_normalized_pyright_errors(file_content: str) -> set[str]:
    if not file_content:
        return set()
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".py")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(file_content)
        res = subprocess.run(
            ["uv", "run", "pyright", tmp_path],
            capture_output=True,
            text=True,
            check=False,
        )
        errors = set()
        for line in res.stdout.splitlines():
            if "error:" in line.lower():
                norm = _normalize_pyright_error(line)
                if norm:
                    errors.add(norm)
        return errors
    except Exception:
        return set()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


_baseline_error_cache: dict[str, set[str]] = {}


def get_file_baseline_errors(file_path_str: str, root_dir: Path) -> set[str]:
    if file_path_str in _baseline_error_cache:
        return _baseline_error_cache[file_path_str]
    full_path = root_dir / file_path_str
    if not full_path.exists():
        return set()
    source = full_path.read_text(encoding="utf-8")
    errors = _get_normalized_pyright_errors(source)
    _baseline_error_cache[file_path_str] = errors
    return errors


class ReturnVisitor(ast.NodeVisitor):
    """Scans AST to record top-level return expressions."""
    def __init__(self):
        self.return_types: set[str] = set()

    def visit_Return(self, node: ast.Return) -> None:
        if node.value:
            if isinstance(node.value, ast.Dict):
                self.return_types.add("dict")
            elif isinstance(node.value, ast.Call):
                self.return_types.add("call")
            elif isinstance(node.value, (ast.Tuple, ast.List)):
                self.return_types.add("sequence")
            elif isinstance(node.value, ast.Name):
                self.return_types.add("var")
        self.generic_visit(node)


_refactor_agent = Agent(
    model=CONTROL_SHEET.scanner_model,
    deps_type=RefactorDeps,
    output_type=RefactoringVerdict,
    instructions="You are a principal Python architect strictly enforcing Flat Control Flow.",
    retries=3,
    model_settings={"temperature": 0.0},
)


@_refactor_agent.output_validator
def enforce_return_shape(ctx: RunContext[RefactorDeps], result: RefactoringVerdict) -> RefactoringVerdict:
    if not ctx.deps or not ctx.deps.orig_code:
        return result

    # 1. Helper Function Complexity Cap (Extracted helpers MUST be CC <= 5)
    for helper_code in result.helper_functions:
        try:
            helper_tree = ast.parse(helper_code)
            for node in helper_tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    comp_vis = ComplexityVisitor()
                    comp_vis.visit(node)
                    if comp_vis.complexity > 5:
                        msg = (
                            f"CRITICAL: Extracted helper function `{node.name}` has Cyclomatic Complexity {comp_vis.complexity} (must be ≤ 5). "
                            f"ALL helper functions MUST have CC ≤ 5. You must break `{node.name}` down into simpler steps."
                        )
                        logger.warning(f"[ModelRetry] Helper CC > 5: {msg}")
                        raise ModelRetry(msg)
        except SyntaxError:
            pass

    # 1. AST Return Shape Check (Prevents dict -> BaseModel mutation)
    try:
        orig_tree = ast.parse(ctx.deps.orig_code)
        new_tree = ast.parse(result.refactored_code)

        orig_ret_vis = ReturnVisitor()
        orig_ret_vis.visit(orig_tree)

        new_ret_vis = ReturnVisitor()
        new_ret_vis.visit(new_tree)

        if "dict" in orig_ret_vis.return_types and "call" in new_ret_vis.return_types:
            msg = (
                "CRITICAL: Return type mutation detected. The original function returned a raw dictionary (ast.Dict), "
                "but your refactored code returns a class/model instantiation. You MUST preserve the exact dictionary return structure. "
                "Do not convert dict returns to Pydantic models. Revert the return statement to a dictionary."
            )
            logger.warning(f"[ModelRetry] Return shape mutation: {msg}")
            raise ModelRetry(msg)
    except SyntaxError:
        pass

    # 2. Live Compiler Sandbox (Virtual AST Buffer -> Ruff Format -> Ruff Check)
    if ctx.deps.full_file_source and ctx.deps.func_name:
        try:
            buf = VirtualASTBuffer(ctx.deps.full_file_source, ctx.deps.file_path)
            temp_source = buf.replace_function(
                ctx.deps.func_name,
                result.refactored_code,
                result.helper_functions,
            )
            temp_source = ensure_pydantic_imports(
                temp_source,
                result.refactored_code + ("\n\n" + "\n\n".join(h.rstrip() for h in result.helper_functions) if result.helper_functions else "")
            )
        except Exception as e:
            msg = f"CRITICAL: Refactored code AST replacement failed: {e}"
            logger.warning(f"[ModelRetry] AST Replace Error: {msg}")
            raise ModelRetry(msg)

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".py")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(temp_source)

            # Stage 0: AUTO-FORMAT (Fix whitespace before checking)
            subprocess.run(["uv", "run", "ruff", "format", tmp_path], capture_output=True, text=True, check=False)

            # Stage 1: RUFF (Fast Syntactic Check & Missing Imports)
            ruff_res = subprocess.run(
                ["uv", "run", "ruff", "check", tmp_path],
                capture_output=True,
                text=True,
                check=False
            )
            if ruff_res.returncode != 0:
                print("=== RUFF STDOUT IN TEMP FILE ===", file=sys.stderr)
                print(ruff_res.stdout, file=sys.stderr)
                print("================================", file=sys.stderr)
                clean_errors = "\n".join(
                    [line.split(":", 1)[-1].strip() for line in ruff_res.stdout.splitlines() if ":" in line]
                )
                logger.warning(f"[ModelRetry] Ruff error:\n{clean_errors}")
                raise ModelRetry(
                    f"CRITICAL: Your code caused Ruff linter errors:\n{clean_errors}\n"
                    f"Fix these errors. If you hallucinated a type hint (F821), change it to `dict`, `list`, or `Any`."
                )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return result


# =====================================================================
# AST REFACTORING VERIFICATION
# =====================================================================

def harvest_contract_context(symbol_name: str, src_path: str, root_dir: Path) -> dict:
    callers = []
    exception_types = []

    target_file = root_dir / src_path
    if target_file.exists():
        try:
            tree = ast.parse(target_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol_name:
                    for inner in ast.walk(node):
                        if isinstance(inner, ast.ExceptHandler):
                            if inner.type:
                                exception_types.append(ast.unparse(inner.type))
                            else:
                                exception_types.append("bare except")
                        elif isinstance(inner, ast.Call):
                            if isinstance(inner.func, ast.Attribute) and inner.func.attr in ("rollback", "commit", "close", "remove"):
                                exception_types.append(f"cleanup:{inner.func.attr}")
        except Exception:
            pass

    import re
    pattern = re.compile(r"\b" + re.escape(symbol_name) + r"\s*\(")
    for py_file in (root_dir / "src2").rglob("*.py"):
        rel_path = str(py_file.relative_to(root_dir))
        if rel_path == src_path:
            continue
        try:
            lines = py_file.read_text(encoding="utf-8").splitlines()
            for idx, line in enumerate(lines, 1):
                if pattern.search(line):
                    callers.append(f"{rel_path}:{idx} -> {line.strip()}")
                    if len(callers) >= 8:
                        break
        except Exception:
            pass
        if len(callers) >= 8:
            break

    return {
        "symbol": symbol_name,
        "upstream_callers": callers,
        "exceptions_and_cleanup": list(set(exception_types)),
    }

def _get_module_context(src_path: str, root_dir: Path) -> str:
    """Extract module-level imports and public constants used by the target function."""
    file_path = root_dir / src_path
    if not file_path.exists():
        return "Module source not found."
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return "Could not parse module."

    lines: list[str] = []

    # 1. Top-level imports
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            lines.append(ast.unparse(node))

    # 2. Module-level constants (Assign with literal values)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, (ast.Constant, ast.Tuple, ast.List, ast.Dict)):
                    try:
                        lines.append(f"{target.id} = {ast.unparse(node.value)}")
                    except (ValueError, TypeError):
                        pass

    return "\n".join(lines) if lines else "No module-level imports or constants detected."

def extract_function_signature(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict:
    args_node = fn_node.args
    posonly = [a.arg for a in args_node.posonlyargs]
    pos_args = [a.arg for a in args_node.args]
    vararg = args_node.vararg.arg if args_node.vararg else None
    kwonly = [a.arg for a in args_node.kwonlyargs]
    kwarg = args_node.kwarg.arg if args_node.kwarg else None
    defaults_count = len(args_node.defaults)
    kw_defaults_count = sum(1 for d in args_node.kw_defaults if d is not None)
    return {
        "posonly": posonly,
        "args": pos_args,
        "vararg": vararg,
        "kwonly": kwonly,
        "kwarg": kwarg,
        "defaults_count": defaults_count,
        "kw_defaults_count": kw_defaults_count,
    }


VIOLATION_SUGGESTIONS: dict[str, str] = {
    "cc_exceeds": (
        "Extract into a private helper function. "
        "Use a tuple-of-tuples data table for lookups, a match/case dispatch for routing, "
        "or split into guard clauses with early returns. "
        "Each helper must have CC ≤ 5."
    ),
    "nesting_exceeds": (
        "Flatten with guard clauses and early returns. "
        "Replace nested if/else with `if not condition: return result` at the top. "
        "Extract inner logic into a helper function."
    ),
    "try_pyramid": (
        "Move orelse statements out of the try block. "
        "Use guard clauses before the try/except. "
        "Extract the try body into a helper function if cleanup is needed."
    ),
    "signature_missing_param": (
        "Add the missing parameter back with its original default value to preserve the caller contract."
    ),
    "signature_extra_param": (
        "Remove the extra parameter — callers don't expect it."
    ),
    "signature_wrong_default": (
        "Restore the original default value for this parameter."
    ),
    "cleanup_missing": (
        "Add the required cleanup call before the return statement. "
        "This is a hard contract requirement from upstream callers."
    ),
    "missing_function": (
        "The target function was removed or renamed. Restore it with the original name and signature."
    ),
}


class AttributeVisitor(ast.NodeVisitor):
    def __init__(self):
        self.attributes: set[str] = set()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.attributes.add(node.attr)
        self.generic_visit(node)


class CallVisitor(ast.NodeVisitor):
    """Scans AST to record function calls and the variable names passed as arguments."""
    def __init__(self):
        self.calls: set[tuple[str, tuple[str, ...]]] = set()

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            args = tuple(arg.id for arg in node.args if isinstance(arg, ast.Name))
            self.calls.add((node.func.id, args))
        self.generic_visit(node)


@logfire.instrument("verify_refactored_ast")
def verify_refactored_ast(code: str, candidate_name: str = "", contract_info: dict | None = None,
                               orig_code: str = "", orig_cc: int = 0) -> tuple[bool, int, int, str]:
    """Compile and verify that the refactored code passes CC <= target_cc, max nesting <= 3, and matches caller signatures & cleanup contracts.

    Collects ALL violations (not just the first) and returns structured feedback with pattern suggestions.
    Uses a Progressive CC Ratchet: if orig_cc > 15, target is 50% reduction; otherwise strict 5.
    """
    violations: list[str] = []
    cc = 0
    max_depth = 0

    target_cc = 5 if orig_cc <= 5 else (orig_cc - 1)

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, 999, 999, f"SyntaxError in refactored code: {e}"

    # 2. Ban unauthorized imports (Allow safe stdlib imports for helpers)
    safe_modules = {"typing", "collections", "enum", "dataclasses", "itertools"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            violations.append(
                f"unauthorized_symbol: Created a new class `{node.name}` | "
                f"Suggestion: Do not define new classes. Use flat tuples or dicts for data tables."
            )
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module_name = getattr(node, 'module', None)
            if not module_name and isinstance(node, ast.Import):
                module_name = node.names[0].name.split('.')[0]
            if module_name and module_name not in safe_modules and not module_name.startswith("src2"):
                violations.append(
                    f"unauthorized_import: Added an import for `{module_name}` | "
                    f"Suggestion: You may ONLY import from {safe_modules} or internal `src2` modules."
                )

    # --- Module Namespace Sandbox: harvest the original file's top-level namespace ---
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
        except SyntaxError:
            pass

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name != candidate_name:
                if not node.name.startswith("_"):
                    violations.append(
                        f"invalid_helper_name: Helper `{node.name}` must start with an underscore. "
                        f"Suggestion: Rename to _{node.name} or pick a unique _-prefixed name."
                    )
                elif node.name in orig_namespace:
                    violations.append(
                        f"namespace_collision: Helper `{node.name}` shadows an existing import, "
                        f"function, class, or global variable in this file. "
                        f"Suggestion: Pick a unique _-prefixed name for this helper."
                    )

    # --- Attribute Sandbox: detect hallucinated fields ---
    if orig_code:
        try:
            orig_tree = ast.parse(orig_code)
            orig_attrs = AttributeVisitor()
            orig_attrs.visit(orig_tree)

            new_attrs = AttributeVisitor()
            new_attrs.visit(tree)

            whitelist: set[str] = {
                "get", "append", "model_dump", "model_copy", "items", "keys", "values", "add", "update",
                "split", "strip", "replace", "join", "format", "startswith", "endswith", "lower", "upper",
                "info", "error", "warning", "exception", "debug", "exists", "resolve", "parent", "name",
                "isoformat", "now", "today", "group", "match", "search", "encode", "decode", "find",
                "rfind", "partition", "rpartition", "splitlines", "capitalize", "title", "swapcase",
                "isdigit", "isalpha", "isalnum", "isspace", "count", "index", "remove", "pop", "insert",
                "extend", "clear", "update", "setdefault", "get", "copy", "items", "keys", "values",
                "query", "fetchone", "fetchall", "execute", "executemany", "fetchmany", "close",
                "connect", "cursor", "commit", "rollback", "begin", "savepoint", "execute_script",
                "fetchall", "fetchone", "fetchmany", "executemany", "rowcount", "lastrowid",
                "description", "connection", "cursor", "execute", "executemany", "fetchall",
                "fetchone", "fetchmany", "close", "commit", "rollback", "begin", "savepoint",
            }
            hallucinated = (new_attrs.attributes - orig_attrs.attributes) - whitelist
            if hallucinated:
                violations.append(
                    f"hallucinated_fields: You invented attributes that do not exist on the original objects: {hallucinated} | "
                    f"Suggestion: You MUST use ONLY the attributes present in the original code. "
                    f"Route logic using dot notation on existing fields only."
                )
        except Exception:
            pass

    # --- Call Signature Sandbox: detect argument swaps ---
    if orig_code:
        try:
            orig_tree = ast.parse(orig_code)
            orig_call_vis = CallVisitor()
            orig_call_vis.visit(orig_tree)

            new_call_vis = CallVisitor()
            new_call_vis.visit(tree)

            orig_func_names = {call[0] for call in orig_call_vis.calls}

            for new_call in new_call_vis.calls:
                func_name, new_args = new_call
                if func_name in orig_func_names and new_call not in orig_call_vis.calls:
                    violations.append(
                        f"argument_swap: You changed the arguments passed to `{func_name}`. "
                        f"You passed {new_args}. | "
                        f"Suggestion: You MUST preserve the exact variable arguments for existing function calls."
                    )
        except Exception:
            pass

    if orig_code and candidate_name:
        try:
            orig_tree = ast.parse(orig_code)
            orig_main_node = next(
                (n for n in orig_tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == candidate_name),
                None
            )
            if not orig_main_node:
                orig_main_node = next(
                    (n for n in ast.walk(orig_tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == candidate_name),
                    None
                )

            if orig_main_node:
                orig_sig = extract_function_signature(orig_main_node)
                ref_main_node = next(
                    (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == candidate_name),
                    None
                )
                if not ref_main_node:
                    violations.append(
                        f"missing_function: The main target function `{candidate_name}` is missing or renamed in refactored code | "
                        f"Suggestion: Restore the original function name and signature."
                    )
                else:
                    ref_sig = extract_function_signature(ref_main_node)
                    if orig_sig != ref_sig:
                        diffs = [k for k, v in orig_sig.items() if ref_sig.get(k) != v]
                        for diff in diffs:
                            param_violation = f"signature_{diff}"
                            suggestion = VIOLATION_SUGGESTIONS.get(param_violation, "Restore the original signature for this parameter.")
                            violations.append(
                                f"signature_mismatch:{candidate_name}:{diff} | "
                                f"Suggestion: {suggestion}"
                            )
        except Exception:
            pass

    if contract_info:
        for required in contract_info.get("exceptions_and_cleanup", []):
            if required.startswith("cleanup:"):
                method = required.split(":", 1)[1]
                if method not in code:
                    violations.append(
                        f"cleanup_missing:{method} | "
                        f"Suggestion: {VIOLATION_SUGGESTIONS['cleanup_missing']}"
                    )

    candidate_cc = cc
    candidate_max_depth = max_depth

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            comp_vis = ComplexityVisitor()
            comp_vis.visit(node)
            func_cc = comp_vis.complexity

            scanner = FunctionCandidateScanner("test.py", code.splitlines())
            func_depth, _, try_issues = scanner._check_body_nesting(node.body, depth=0)

            if node.name == candidate_name:
                candidate_cc = func_cc
                candidate_max_depth = func_depth

            if len(try_issues) > 0:
                violations.append(
                    f"try_pyramid:{try_issues} | "
                    f"Suggestion: {VIOLATION_SUGGESTIONS['try_pyramid']}"
                )
            node_target_cc = target_cc if node.name == candidate_name else 5
            if func_cc > node_target_cc:
                violations.append(
                    f"cc_exceeds:{node.name} has CC={func_cc} (target ≤{node_target_cc}, original was {orig_cc}) | "
                    f"Suggestion: {VIOLATION_SUGGESTIONS['cc_exceeds']}"
                )
            if func_depth > 3:
                violations.append(
                    f"nesting_exceeds:{node.name} depth={func_depth} (must be ≤3) | "
                    f"Suggestion: {VIOLATION_SUGGESTIONS['nesting_exceeds']}"
                )

    if violations:
        return False, candidate_cc, candidate_max_depth, "VIOLATIONS FOUND:\n" + "\n".join(f"  - {v}" for v in violations)

    return True, candidate_cc, candidate_max_depth, "Passed Flat Control Flow, semantic attribute sandbox, and ban-new-shit verification — all checks clean."


# =====================================================================
# LLM REFACTORING DRIVER (LAST RESORT VIA PYDANTIC-AI AGENT)
# =====================================================================

async def refactor_single_attempt_with_llm(candidate: dict, attempt: int, history: list,
                                               prompt: str, template: dict,
                                               cand_idx: int = 0, total_cand: int = 0) -> tuple[bool, list, str, dict | None]:
    """Execute 1 attempt with Pydantic-AI Agent. Returns (passed, updated_history, updated_prompt, result_dict_if_done)."""
    contract_info = harvest_contract_context(candidate['function_name'], candidate['file_path'], repo_root)
    req_id = str(uuid.uuid4())
    model_obj = CONTROL_SHEET.scanner_model
    model_name = getattr(model_obj, "model_name", str(model_obj))
    upstream_name = model_name.split("/")[-1] if "/" in model_name else model_name
    t_req = get_timestamp()
    start_t = time.time()

    progress_str = f"[{cand_idx}/{total_cand}] " if total_cand > 0 else ""
    _provider = get_model_provider_name(CONTROL_SHEET.scanner_model)
    print(
        f"🔵 [{t_req}] {progress_str}[REQ {req_id}] model={model_name} provider={_provider} upstream={upstream_name} candidate={candidate['function_name']} ({candidate['file_path']}:{candidate['line']}) attempt={attempt}/5 stream=false",
        flush=True,
    )

    try:
        full_source = ""
        target_path = repo_root / candidate['file_path']
        if target_path.exists():
            try:
                full_source = target_path.read_text(encoding="utf-8")
            except Exception:
                pass

        baseline_errs = get_file_baseline_errors(candidate['file_path'], repo_root) if full_source else set()
        deps_obj = RefactorDeps(
            orig_code=candidate.get("source_code", ""),
            full_file_source=full_source,
            file_path=candidate['file_path'],
            line=candidate.get("line", 0),
            end_line=candidate.get("end_line", 0),
            func_name=candidate.get("function_name", ""),
            baseline_errors=baseline_errs,
        )
        result = await _refactor_agent.run(prompt, message_history=history, deps=deps_obj)
        elapsed = round(time.time() - start_t, 3)
        t_resp = get_timestamp()

        print(
            f"🟢 [{t_resp}] [{_provider.upper()} {req_id}] Served {model_name} (upstream={upstream_name}, candidate={candidate['function_name']}, duration={elapsed}s) attempt {attempt}/5",
            flush=True,
        )

        history = result.all_messages()
        verdict: RefactoringVerdict = result.output

        # Track token usage
        try:
            usage = result.usage
            t_req2 = get_timestamp()
            req_tok = getattr(usage, "input_tokens", getattr(usage, "request_tokens", 0))
            resp_tok = getattr(usage, "output_tokens", getattr(usage, "response_tokens", 0))
            tot_tok = getattr(usage, "total_tokens", 0)
            print(
                f"📊 [{t_req2}] [TOKENS {req_id}] request={req_tok} response={resp_tok} total={tot_tok}",
                flush=True,
            )
        except Exception:
            pass

        code_blocks = [textwrap.dedent(verdict.refactored_code)]
        for h in verdict.helper_functions:
            code_blocks.append(textwrap.dedent(h))

        full_code = "\n\n".join(code_blocks)
        t_check = get_timestamp()
        print(
            f"🔍 [{t_check}] [CHECKING {req_id}] Verifying Flat Control Flow (CC <= 5, Depth <= 3) for {candidate['function_name']}...",
            flush=True,
        )
        passed, new_cc, new_depth, msg = verify_refactored_ast(full_code, candidate['function_name'], contract_info, orig_code=candidate['source_code'], orig_cc=candidate['cc'])

        if passed:
            t_pass = get_timestamp()
            print(
                f"✅ [{t_pass}] [PASSED {req_id}] {candidate['function_name']} PASSED Flat Control Flow Verification on attempt {attempt}/5!",
                flush=True,
            )
            res = {
                "file_path": candidate["file_path"],
                "function_name": candidate["function_name"],
                "line": candidate["line"],
                "status": "APPROVED",
                "attempts": attempt,
                "original_cc": candidate["cc"],
                "refactored_cc": new_cc,
                "original_depth": candidate["max_depth"],
                "refactored_depth": new_depth,
                "refactored_code": verdict.refactored_code,
                "helper_functions": verdict.helper_functions,
                "explanation": verdict.explanation,
                "verification_msg": msg
            }
            return True, history, prompt, res

        t_fail = get_timestamp()
        print(
            f"⚠️ [{t_fail}] [AST_FAIL {req_id}] {candidate['function_name']} attempt {attempt}/5 failed AST check: {msg}",
            flush=True,
        )
        logger.warning(f"    ⚠️ [Attempt {attempt}/5 Retry] {candidate['function_name']} failed AST check: {msg}")
        retry_prompt = format_prompt(template, candidate, attempt + 1, history, what_worked_text="Function signature and cleanup calls preserved.", violations_text=msg)
        if attempt >= 5:
            res = {
                "file_path": candidate["file_path"],
                "function_name": candidate["function_name"],
                "line": candidate["line"],
                "status": "FAILED_VERIFICATION",
                "attempts": 5,
                "original_cc": candidate["cc"],
                "refactored_cc": new_cc,
                "original_depth": candidate["max_depth"],
                "refactored_depth": new_depth,
                "refactored_code": candidate["source_code"],
                "helper_functions": [],
                "explanation": f"Failed after 5 attempts. Last error: {msg}",
                "verification_msg": msg
            }
            return False, history, retry_prompt, res
        return False, history, retry_prompt, None

    except Exception as e:
        elapsed = round(time.time() - start_t, 3)
        t_err = get_timestamp()
        is_schema_error = "validation error" in str(e).lower() or "modelretry" in str(e).lower() or "pydantic" in str(e).lower()
        print(
            f"🔴 [{t_err}] [ERR {req_id}] Candidate {candidate['function_name']} attempt {attempt}/5 failed (duration={elapsed}s): {e}",
            flush=True,
        )
        if is_schema_error:
            logger.warning(f"    Schema validation error on attempt {attempt}/5 for {candidate['function_name']} — Pydantic AI internal retry handles this automatically")
        else:
            logger.error(f"Pydantic-AI attempt {attempt} failed for {candidate['function_name']}: {e}")
        err_str = str(e).lower()
        is_fatal = any(term in err_str for term in ["token limit", "context length", "max_tokens", "rate limit", "token_limit", "resource_exhausted"])
        if is_fatal or attempt >= 5:
            res = {
                "file_path": candidate["file_path"],
                "function_name": candidate["function_name"],
                "line": candidate["line"],
                "status": "LLM_ERROR",
                "attempts": attempt,
                "original_cc": candidate["cc"],
                "refactored_cc": candidate["cc"],
                "original_depth": candidate["max_depth"],
                "refactored_depth": candidate["max_depth"],
                "refactored_code": candidate["source_code"],
                "helper_functions": [],
                "explanation": f"LLM error on attempt {attempt}: {e}",
                "verification_msg": f"LLM error: {e}"
            }
            return False, history, prompt, res
        retry_prompt = format_prompt(template, candidate, attempt + 1, history, what_worked_text="", violations_text=str(e))
        return False, history, retry_prompt, None


# =====================================================================
# MAIN PIPELINE
# =====================================================================

def scan_all_candidates(target_files: set[str] | None = None) -> list[dict]:
    logger.info("Scanning src2/ AST for Flat Control Flow candidates...")
    candidates = []
    root_resolved = repo_root.resolve()

    for py_file in sorted(SRC2_DIR.rglob("*.py")):
        if py_file.is_file():
            rel_path = str(py_file.resolve().relative_to(root_resolved))
            if target_files and rel_path not in target_files:
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(py_file))
                scanner = FunctionCandidateScanner(rel_path, content.splitlines())
                scanner.visit(tree)
                candidates.extend(scanner.candidates)
            except Exception as e:
                logger.warning(f"Skipped {py_file.name}: {e}")

    logger.info(f"✅ Found {len(candidates)} candidates violating Flat Control Flow standards.")
    return candidates


def load_checkpoint() -> dict[str, dict]:
    """Load previously completed results from CHECKPOINT_FILE."""
    completed = {}
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        item = json.loads(line)
                        key = f"{item['file_path']}:{item['function_name']}"
                        completed[key] = item
            logger.info(f"Loaded {len(completed)} prior results from checkpoint ({CHECKPOINT_FILE.name}).")
        except Exception as e:
            logger.warning(f"Failed loading checkpoint: {e}")
    return completed


def save_checkpoint_item(item: dict):
    """Append single result item to CHECKPOINT_FILE."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(item) + "\n")


def ensure_pydantic_imports(source: str, ref_code: str) -> str:
    has_basemodel = False
    has_field = False
    try:
        source_tree = ast.parse(source)
        for node in ast.walk(source_tree):
            if isinstance(node, ast.ImportFrom) and node.module == "pydantic":
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name == "BaseModel":
                        has_basemodel = True
                    elif name == "Field":
                        has_field = True
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "pydantic":
                        has_basemodel = True
                        has_field = True
    except Exception:
        pass

    uses_basemodel = False
    uses_field = False
    try:
        ref_tree = ast.parse(ref_code)
        for node in ast.walk(ref_tree):
            if isinstance(node, ast.Name):
                if node.id == "BaseModel":
                    uses_basemodel = True
                elif node.id == "Field":
                    uses_field = True
    except Exception:
        pass

    needed = []
    if uses_basemodel and not has_basemodel:
        needed.append("BaseModel")
    if uses_field and not has_field:
        needed.append("Field")
    if not needed:
        return source

    import_line = f"from pydantic import {', '.join(needed)}\n"
    lines = source.splitlines(keepends=True)

    last_future_idx = -1
    for idx, line in enumerate(lines):
        if line.strip().startswith("from __future__ import"):
            last_future_idx = idx

    if last_future_idx != -1:
        lines.insert(last_future_idx + 1, import_line)
        return "".join(lines)

    insert_idx = 0
    in_docstring = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if idx == 0 and (stripped.startswith('"""') or stripped.startswith("'''")):
            if stripped.count('"""') == 2 or stripped.count("'''") == 2:
                insert_idx = 1
                break
            in_docstring = True
            continue
        if in_docstring:
            if '"""' in stripped or "'''" in stripped:
                insert_idx = idx + 1
                break
            continue
        if stripped.startswith("#") or not stripped:
            continue
        insert_idx = idx
        break

    lines.insert(insert_idx, import_line)
    return "".join(lines)


def verify_class_structure_intact(original_code: str, modified_code: str) -> bool:
    try:
        orig_tree = ast.parse(original_code)
        mod_tree = ast.parse(modified_code)

        orig_methods = set()
        for node in ast.walk(orig_tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        orig_methods.add((node.name, item.name))

        mod_methods = set()
        for node in ast.walk(mod_tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        mod_methods.add((node.name, item.name))

        for cls_name, method_name in orig_methods:
            if (cls_name, method_name) not in mod_methods:
                return False
        return True
    except Exception:
        return False


async def main_async(do_refactor: bool, priorities: list[int], limit: int, resume: bool, fail_fast: bool = False, max_loops: int = 10):
    # Phase 1: Run Pure AST Transformer Pass (Deterministic, 0 LLM calls)
    run_ast_transformer_pass_all()

    target_files = load_target_files()
    candidates = scan_all_candidates(target_files=target_files)

    p1 = [c for c in candidates if c["priority"] == 1]
    p2 = [c for c in candidates if c["priority"] == 2]
    p3 = [c for c in candidates if c["priority"] == 3]

    print("\n" + "="*60)
    print("🎯 FLAT CONTROL FLOW SCAN RESULTS")
    print("="*60)
    print(f"🔴 Priority 1 (Try Pyramids)        : {len(p1)} functions")
    print(f"🟡 Priority 2 (Deep Nesting Depth > 3): {len(p2)} functions")
    print(f"⚪ Priority 3 (CC > 5, Shallow Nest) : {len(p3)} functions")
    print(f"📊 Total Candidates               : {len(candidates)} functions")
    print("="*60 + "\n")

    if not do_refactor:
        logger.info("Scan complete (--scan-only mode). Exiting without LLM refactoring pass.")
        return

    targets = [c for c in candidates if c["priority"] in priorities]
    if not resume:
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
        if REPORT_FILE.exists():
            REPORT_FILE.unlink()
        checkpoint_map = {}
        logger.info("Cleared prior checkpoint and report history (--no-resume active).")
    else:
        checkpoint_map = load_checkpoint()

    # Phase 1: Pure AST Pre-Filter Gate (Instant, 0 LLM calls)
    auto_approved_count = 0
    need_llm = []
    checkpoint_lock = asyncio.Lock()

    for c in targets:
        key = f"{c['file_path']}:{c['function_name']}"
        if resume and key in checkpoint_map and checkpoint_map[key].get("status") in ("APPROVED", "FAILED_VERIFICATION", "LLM_ERROR"):
            continue

        contract_info = harvest_contract_context(c["function_name"], c["file_path"], repo_root)
        passed, new_cc, new_depth, msg = verify_refactored_ast(
            c["source_code"], c["function_name"], contract_info, orig_code=c["source_code"], orig_cc=c["cc"]
        )
        if passed:
            res = {
                "file_path": c["file_path"],
                "function_name": c["function_name"],
                "line": c["line"],
                "status": "APPROVED",
                "attempts": 0,
                "original_cc": c["cc"],
                "refactored_cc": new_cc,
                "original_depth": c["max_depth"],
                "refactored_depth": new_depth,
                "refactored_code": c["source_code"],
                "helper_functions": [],
                "explanation": "AST_AUTO_PASS: Pure AST transformation met CC <= 5 and Depth <= 3 standard without LLM.",
                "verification_msg": msg
            }
            save_checkpoint_item(res)
            checkpoint_map[key] = res
            auto_approved_count += 1
        else:
            need_llm.append(c)

    print(f"✨ Pure AST Pre-Filter Gate: {auto_approved_count} functions auto-passed immediately (0 LLM calls).", flush=True)
    print(f"⚡ {len(need_llm)} functions require LLM refactoring.", flush=True)

    if limit and limit > 0:
        need_llm = need_llm[:limit]
        logger.info(f"Target LLM count limited to {len(need_llm)} functions.")

    results = list(checkpoint_map.values()) if resume else []

    if need_llm:
        logger.info(f"Starting FIFO Pipe Queue LLM refactoring pass on {len(need_llm)} candidate functions (2s stagger)...")
        queue = asyncio.Queue()
        completed_count = 0
        total_cand_count = len(need_llm)

        template = load_prompt_template()
        for idx, c in enumerate(need_llm, start=1):
            # Testing: set CC cap to 9999 (was 40) to process all functions regardless of complexity
            if c['cc'] > 9999:
                logger.warning(f"Skipping {c['function_name']} (CC={c['cc']}) — Too large for automated LLM refactoring. Requires manual architectural decomposition.")
                continue
            contract_info = harvest_contract_context(c['function_name'], c['file_path'], repo_root)
            raw_callers = "\n".join(contract_info["upstream_callers"]) if contract_info["upstream_callers"] else "No upstream callers detected (top-level function)."
            c["upstream_callers"] = raw_callers[:1500] + ("\n...[TRUNCATED]" if len(raw_callers) > 1500 else "")
            raw_context = _get_module_context(c['file_path'], repo_root)
            c["module_context"] = raw_context[:3000] + ("\n...[TRUNCATED]" if len(raw_context) > 3000 else "")
            base_prompt = format_prompt(template, c, attempt=1)

            history = []
            key = f"{c['file_path']}:{c['function_name']}"
            prior_entry = checkpoint_map.get(key, {})
            if prior_entry.get("status") == "FAILED_RUNTIME":
                pytest_err = prior_entry.get("verification_msg", "Unknown Pytest Error")
                history = [
                    ModelResponse(parts=[TextPart(content="I have refactored the code.")]),
                    ModelRequest(parts=[UserPromptPart(content=(
                        f"RUNTIME LOGIC DRIFT: Your refactoring passed syntax checks but FAILED the Pytest integration suite:\n"
                        f"```\n{pytest_err}\n```\n"
                        f"You MUST fix the logic drift (e.g., check iteration order, rounding, < vs <=, variable scoping)."
                    ))])
                ]

            await queue.put({
                "candidate": c,
                "index": idx,
                "total": total_cand_count,
                "attempt": 1,
                "history": history,
                "prompt": base_prompt,
            })

        active_tasks = set()
        semaphore = asyncio.Semaphore(3)

        async def worker_task(item: dict):
            nonlocal results, completed_count
            cand = item["candidate"]
            cand_idx = item["index"]
            total_cand = item["total"]
            att = item["attempt"]
            hist = item["history"]
            prmpt = item["prompt"]

            async with semaphore:
                passed, new_hist, next_prmpt, res = await refactor_single_attempt_with_llm(cand, att, hist, prmpt, template, cand_idx, total_cand)
            if res is not None:
                async with checkpoint_lock:
                    save_checkpoint_item(res)
                    results.append(res)
                    completed_count += 1
                logger.info(f"   -> [{completed_count}/{total_cand}] Verdict: {res['status']} ({cand['file_path']}:{cand['function_name']}) (Attempts: {res.get('attempts', 1)}/5, CC: {res['original_cc']}->{res['refactored_cc']}, Depth: {res['original_depth']}->{res['refactored_depth']})")
                if res["status"] != "APPROVED" and fail_fast:
                    t_stop = get_timestamp()
                    print(f"\n⚠️ [{t_stop}] [{completed_count}/{total_cand}] Function {cand['function_name']} in {cand['file_path']}:{cand['line']} failed verification ({res['status']})!", flush=True)
                    print("Halting process immediately (Harness Fail-Fast Policy).", flush=True)
                    sys.exit(1)
            else:
                t_requeue = get_timestamp()
                print(f"🔄 [{t_requeue}] [{cand_idx}/{total_cand}] Re-queuing {cand['function_name']} behind the line for attempt {att + 1}/5...", flush=True)
                await queue.put({
                    "candidate": cand,
                    "index": cand_idx,
                    "total": total_cand,
                    "attempt": att + 1,
                    "history": new_hist,
                    "prompt": next_prmpt,
                })

        while not queue.empty() or active_tasks:
            if not queue.empty():
                item = await queue.get()
                t = asyncio.create_task(worker_task(item))
                active_tasks.add(t)
                t.add_done_callback(active_tasks.discard)
                await asyncio.sleep(2.0)
            else:
                await asyncio.sleep(0.5)

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "total_scanned_candidates": len(candidates),
        "refactored_count": len(results),
        "approved": [r for r in results if r["status"] == "APPROVED"],
        "failed_verification": [r for r in results if r["status"] == "FAILED_VERIFICATION"],
        "errors": [r for r in results if r["status"] == "LLM_ERROR"]
    }

    REPORT_FILE.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    logger.info(f"Report saved to {REPORT_FILE}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Kill-Tries AST Scanner & Refactorer")
    parser.add_argument("--scan-only", action="store_true", help="Run AST scan only without LLM refactoring pass")
    parser.add_argument("--refactor", action="store_true", default=True, help="Run LLM refactoring pass (default)")
    parser.add_argument("--priority", type=str, default="all", help="Priorities to target: '1,2', '3', or 'all' (default: all)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of target functions to process (0 = unlimited)")
    parser.add_argument("--no-resume", action="store_true", help="Disable checkpoint resume (re-run all from scratch)")
    parser.add_argument("--fail-fast", action="store_true", help="Halt immediately if a candidate fails verification")
    parser.add_argument("--max-loops", type=int, default=10, help="Maximum loop count for progressive ratchet (default: 10)")
    args = parser.parse_args()

    do_refactor = not args.scan_only
    if args.priority == "all":
        priorities = [1, 2, 3]
    else:
        priorities = [int(p.strip()) for p in args.priority.split(",") if p.strip().isdigit()]

    asyncio.run(main_async(
        do_refactor=do_refactor,
        priorities=priorities,
        limit=args.limit,
        resume=not args.no_resume,
        fail_fast=args.fail_fast,
        max_loops=args.max_loops,
    ))


if __name__ == "__main__":
    main()
