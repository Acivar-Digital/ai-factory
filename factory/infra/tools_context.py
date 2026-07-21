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
from factory.infra.models import ApprovedTask, Strategy, TaskResult

def investigate(filename: str, query: str, lines: str | None=None, pattern: str | None=None) -> str:
    """Investigate a file using the codebase model.

    Args:
        filename: Path to the file.
        query: Specific question or instruction for the model (REQUIRED).
        lines: Optional line range, e.g., '10-100'.
        pattern: Optional regex pattern.
    """
    argv = ['--filename', filename, '--query', query]
    if lines:
        argv += ['--lines', lines]
    if pattern:
        argv += ['--pattern', pattern]
    return _REMEMBER_NUDGE + _run_tool('investigate', argv)

def search(query: str) -> str:
    """Semantic + literal codebase search. Returns a Markdown report."""
    return _REMEMBER_NUDGE + _run_tool('search', [query])

def list_files(directory: str='', extension_filter: str | None=None, recursive: bool=True, limit: int=500, offset: int=0) -> str:
    """List files in a repo directory with pagination. Returns JSON."""
    argv = [directory]
    if extension_filter:
        argv += ['--extension-filter', extension_filter]
    argv += ['--recursive' if recursive else '--no-recursive']
    argv += ['--limit', str(limit), '--offset', str(offset)]
    return _REMEMBER_NUDGE + _run_tool('list_files', argv)

def get_file_symbols(relative_path: str) -> str:
    """List all classes and functions defined in a Python file. Returns JSON."""
    return _REMEMBER_NUDGE + _run_tool('get_file_symbols', [relative_path])

def get_repo_structure(max_depth: int=4) -> str:
    """Return an ASCII tree of the project structure. Returns JSON."""
    return _REMEMBER_NUDGE + _run_tool('get_repo_structure', ['--max-depth', str(max_depth)])

def query_knowledge_graph(query: str, max_entities: int=10) -> str:
    """Natural-language query over the codebase knowledge graph. Returns JSON."""
    return _REMEMBER_NUDGE + _run_tool('query_knowledge_graph', [query, '--max-entities', str(max_entities)])

def find_related_code(entity_or_topic: str, max_results: int=10) -> str:
    """Find code related to an entity or topic. Returns JSON."""
    return _REMEMBER_NUDGE + _run_tool('find_related_code', [entity_or_topic, '--max-results', str(max_results)])

def get_code_hierarchy() -> str:
    """Return the full code hierarchy of the repo. Returns JSON."""
    return _REMEMBER_NUDGE + _run_tool('get_code_hierarchy', [])
