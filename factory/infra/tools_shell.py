from factory.infra.tools_const import *
'Tool confinement for the Orchestrator State Machine (build.md §4, §5c).\n\nEvery worker capability is a subprocess wrapper around an existing\n`factory/tools/*.py` CLI. Agents NEVER touch the filesystem directly — they\nreceive only the allow-listed, ACL-wrapped tools the orchestrator hands them.\n'
import contextvars
import functools
import inspect
import json
import logging
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel, model_validator
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai._run_context import AgentDepsT
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import FunctionToolset, WrapperToolset
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_core import SchemaValidator
from factory.common import OUTPUT_TYPE_REGISTRY, _run_tool, log_operator, resolve_model
from factory.infra.control import CODER_READ_FILE_BUDGET, CONTROL_SHEET, ORCH_ROOT, PKG_DIR, PYDANTIC_AI_INSTRUCTIONS, READ_BUDGET, REPO_ROOT, SKILL_MAP, SKILL_ROLES
from factory.infra.tools_memory import get_current_role, get_current_agent
from factory.infra.models import ApprovedTask, Strategy, TaskResult
from factory.infra.tools_file import _check_edit_result, _src_write_guard


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
    _auto_remember(f'[replace_text] {relative_path}: replaced {len(target_text)} chars with {len(replacement_text)} chars')
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
    _auto_remember(f'[replace_function] {relative_path}: {scope}')
    return result

def add_constant(relative_path: str, constant_name: str, constant_code: str) -> str:
    """Add a top-level constant to a Python file (AST). Returns JSON result."""
    _g = _src_write_guard('add_constant', relative_path)
    if _g:
        return _g
    result = _check_edit_result('add_constant', _run_tool('add_constant', [relative_path, constant_name, constant_code]))
    _auto_remember(f'[add_constant] {relative_path}: {constant_name} = {constant_code[:80]}')
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
