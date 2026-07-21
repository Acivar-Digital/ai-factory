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
from factory.infra.tools_file import batch_read
from factory.infra.tools_memory import record_plan
from factory.infra.tools_guard import CODING_PHILOSOPHY_BLOCK, MODIFY_TOOLS, TOOL_REGISTRY, TOOL_REGISTRY_KEYS, _DISCOVERY_TOOLS, _TOOL_BY_NAME, _coder_budget_for, _tool_budget_for, _tool_budget_instruction, guard_tools, log_prompt_sent, pydantic_ai_default_block, wrap_with_acl

MAX_FORGE_ITERS = 3

def _extract_returns(doc: str) -> str | None:
    """Pull the 'Returns:' section out of a docstring, if present."""
    lines = doc.splitlines()
    out: list[str] = []
    capturing = False
    for ln in lines:
        stripped = ln.strip()
        if stripped.lower().startswith('returns'):
            capturing = True
            after = stripped.split(':', 1)[1].strip()
            if after:
                out.append(after)
            continue
        if capturing:
            if stripped and (not stripped[0].isalpha()) and (not stripped.startswith('-')):
                break
            if stripped.lower().startswith(('args', 'arguments', 'raises', 'yields', 'examples')):
                break
            out.append(stripped)
    return ' '.join((o for o in out if o)) or None

def _pretty_params(func: Callable[..., Any]) -> list[str]:
    """Render one 'name: annotation' line per parameter of func."""
    sig = inspect.signature(func)
    lines = []
    for pname, param in sig.parameters.items():
        if pname in ('self', 'cls'):
            continue
        ann = param.annotation
        if ann is inspect.Parameter.empty:
            lines.append(f'    {pname}')
        else:
            ann_str = ann if isinstance(ann, str) else getattr(ann, '__name__', str(ann))
            lines.append(f'    {pname}: {ann_str}')
    return lines

def build_tool_usage_guide(allowed_tool_names: set[str]) -> str:
    """Generate a tool usage guide for the given set of allowed tool names.

    Uses the real tool function signatures to produce a reference section
    with description, signature, per-parameter types, output, and usage hints.
    """
    if not allowed_tool_names:
        return ''
    sections = []
    for name in sorted(allowed_tool_names):
        func = _TOOL_BY_NAME.get(name)
        if func is None:
            continue
        doc = inspect.getdoc(func) or 'No documentation available.'
        sig = inspect.signature(func)
        returns = _extract_returns(doc)
        output_line = returns if returns else 'Returns a result string (typically JSON); see description.'
        param_lines = _pretty_params(func)
        sections.append(f'── {name} ──\n  Description: {doc}\n  Signature: {name}{sig}\n  Params:\n' + ('\n'.join(param_lines) if param_lines else '    (none)') + f'\n  Output: {output_line}\n  Use when: {_infer_tool_usage(name, doc)}\n')
    if not sections:
        return ''
    header = '\n---\nIMPORTANT: Call the FEWEST tools needed to complete the task. Do NOT batch_read for context you already hold. Stop and call final_result as soon as you have enough information.\n'
    return '\n\n=== TOOL USAGE GUIDE ===\n' + header + '\n'.join(sections)

def _infer_tool_usage(name: str, doc: str) -> str:
    """Infer when to use a tool from its name and docstring."""
    if 'read' in name or 'search' in name:
        return 'Exploring code, checking file contents, finding references'
    if 'write' in name or 'replace' in name or 'add' in name:
        return 'Modifying code, creating new files, applying changes'
    if 'delete' in name:
        return 'Removing files that are no longer needed'
    if 'rename' in name or 'move' in name:
        return 'Restructuring code, moving symbols between files'
    if 'list' in name or 'get_' in name:
        return 'Understanding project structure, finding symbols'
    if 'investigate' in name:
        return 'Deep code analysis with AI-assisted understanding'
    if 'query' in name or 'find' in name:
        return 'Finding related code, exploring relationships'
    return 'General-purpose code analysis and manipulation'

class SkillSpec(BaseModel):
    name: str
    instructions: str
    tool_allow_list: list[str]
    hard_rules: list[str]

    @model_validator(mode='after')
    def ensure_no_rogue_tools(self) -> 'SkillSpec':
        """Fail loudly if any tool is not in the frozen TOOL_REGISTRY.

        This is the SkillForge guardrail: if the meta-agent (legacy LLM forge
        path) hallucinates a tool name, pydantic-ai's output validation raises
        here, the error is fed back, and the agent retries. The active D8
        static forge can never produce a rogue tool (tool_allow_list is derived
        directly from SKILL_MAP.tool_bucket -> TOOL_REGISTRY), so this validator
        is defense-in-depth against the LLM path.
        """
        rogue = [t for t in self.tool_allow_list if t not in TOOL_REGISTRY_KEYS]
        if rogue:
            raise ValueError(f'[SkillForge HALT] hallucinated tool(s) {rogue!r} absent from TOOL_REGISTRY. tool_allow_list must be a subset of {sorted(TOOL_REGISTRY_KEYS)}.')
        return self

def _render_instructions(instructions: object) -> str:
    """Render a frozen template's `instructions` block (base+generated join).

    Mirrors runner._render_instructions so the cached spec matches the text a
    live phase would receive. Tolerates plain strings.
    """
    if not isinstance(instructions, str):
        return str(instructions)
    try:
        inner = yaml.safe_load(instructions)
        if isinstance(inner, dict) and '_BASE_' in inner:
            base = inner.get('_BASE_') or ''
            gen = inner.get('_GENERATED_') or ''
            return (base + ('\n' + gen if gen else '')).strip()
    except Exception as e:
        log_operator(f'_render_instructions YAML parse failed; falling back to raw instruction string. error={e!r}', level='WARNING')
    return instructions.strip()

def build_skill_spec(role: str) -> SkillSpec:
    """Build the frozen SkillSpec for a role (D1 forge-once). No LLM.

    Prefers factory.infra.agents module (colocated Python + YAML), falls
    back to YAML in the agents/ directory, then to SKILL_MAP defaults.
    """
    if role not in SKILL_MAP.roles:
        raise KeyError(f'[HALT] role {role!r} not in SKILL_MAP')
    entry = SKILL_MAP.roles[role]
    module_map = {'supervisor_plan': 'supervisor', 'supervisor_review': 'supervisor'}
    mod_name = module_map.get(role, role)
    agent_module_name = f'factory.infra.agents.{mod_name}'
    try:
        import importlib
        mod = importlib.import_module(agent_module_name)
        builder_name = f'build_{role}_spec'
        builder = getattr(mod, builder_name, None)
        if builder:
            spec = builder()
            if not spec.tool_allow_list and role in SKILL_MAP.roles:
                bucket = SKILL_MAP.roles[role].tool_bucket
                spec.tool_allow_list = [f.__name__ for f in _ctrl_tool_bucket(bucket)]
            if not spec.hard_rules and role in SKILL_MAP.roles:
                spec.hard_rules = ['never edit src/ or src2/; confined to factory/'] + list(SKILL_MAP.roles[role].hard_rules)
            return spec
    except (ImportError, AttributeError):
        pass
    template_path = PKG_DIR / 'infra' / 'agents' / entry.template
    instructions = ''
    if template_path.exists():
        with open(template_path) as f:
            data = yaml.safe_load(f)
        instructions = _render_instructions(data.get('instructions', ''))
    else:
        print(f'[SkillSpec WARN] template missing for {role}: {template_path}')
        instructions = f'You are the {role}.'
    bucket = entry.tool_bucket
    raw_funcs = _ctrl_tool_bucket(bucket)
    tool_allow_list = [f.__name__ for f in raw_funcs]
    hard_rules = ['never edit src/ or src2/; confined to factory/'] + list(entry.hard_rules)
    return SkillSpec(name=role, instructions=instructions, tool_allow_list=tool_allow_list, hard_rules=hard_rules)

def _ctrl_tool_bucket(bucket: str) -> list:
    """Resolve a SKILL_MAP tool_bucket name to its funcs ("" -> read-only none)."""
    if not bucket:
        return []
    return TOOL_REGISTRY.get(bucket, TOOL_REGISTRY['AST-edit'])

def load_skill_spec(role: str) -> SkillSpec:
    """Read the cached SkillSpec from customised/<role>.yaml (D1/D8 cache)."""
    path = PKG_DIR / 'customised' / f'{role}.yaml'
    if not path.exists():
        raise FileNotFoundError(f'[HALT] cached SkillSpec missing for {role}: {path}. Run forge_skill_spec() at startup.')
    with open(path) as f:
        data = yaml.safe_load(f)
    return SkillSpec(**data)

def _strip_repo_envelope(raw: str) -> str:
    """`get_repo_structure` returns a `{"success","message","data":{...}}` envelope.

    The envelope + the full data dict adds ~60KB of JSON noise to every agent's
    system prompt. We extract ONLY the `structure` text (the ASCII tree) so the
    injected map stays lean (payload-diet, ticket nz4ai).
    """
    raw = (raw or '').strip()
    if not raw:
        return ''
    try:
        obj = json.loads(raw)
        data = obj.get('data')
        if isinstance(data, dict):
            struct = data.get('structure')
            if isinstance(struct, str):
                return struct
    except Exception:
        pass
    return raw

def _build_repo_map(scope_paths: list[str] | None=None, extra_paths: list[str] | None=None) -> str:
    """Build the spawn-time repo map (Read-Bucket Protocol, RBP-2).

    Replaces search/investigate: the agent gets structure + symbols up front so
    it can declare its reads via batch_read instead of probing one file at a time.

    - A bounded ASCII tree of the repo for orientation. Unscoped (broadcast)
      roles get a shallow depth-2 tree (cheap orientation only); scoped coder
      roles get depth-3 so they can locate exact files. The JSON envelope from
      `get_repo_structure` is stripped — only the tree text is injected (nz4ai).
    - Symbols (classes/functions + line numbers) for the files it may touch
      (task.file_paths + any caller-supplied extra_paths), so it knows exact
      line ranges to pass to batch_read.
    """
    lines = ['# REPO MAP (injected at spawn — do NOT call search/investigate; use batch_read)']
    depth = '3' if scope_paths else '2'
    try:
        raw = _run_tool('get_repo_structure', ['--max-depth', depth])
        tree = _strip_repo_envelope(raw)
        if tree:
            if len(tree) > 12000:
                tree = tree[:12000] + '\n…(tree truncated for brevity)'
            lines.append('\n## Tree\n' + tree)
        else:
            lines.append('\n## Tree\n[map error: empty structure]')
    except Exception as e:
        lines.append(f'\n## Tree\n[map error: {e!r}]')
    targets = list(dict.fromkeys((scope_paths or []) + (extra_paths or [])))
    targets = targets[:40]
    if targets:
        lines.append('\n## Symbols (file -> classes/functions @lines)')
        for p in targets:
            try:
                sym = _run_tool('get_file_symbols', [p])
                lines.append(f'\n### {p}\n{sym}')
            except Exception as e:
                lines.append(f'\n### {p}\n[symbol error: {e!r}]')
    return '\n'.join(lines)

def load_skill(role: str, model_key: str | None=None, task: ApprovedTask | None=None, strategy: Strategy | None=None, alignment: str='', run_dir: Path | None=None) -> tuple[SkillSpec, Agent[object, object]]:
    """M3 seam — single spawn point for a role.

    Loads the D8-cached `SkillSpec` for `role` and forges the Capability/Agent
    bound to that role's model + `output_type` (from `SKILL_MAP`/`controls.py`)
    and the allow-listed tools. Returns `(SkillSpec, Agent)`.

    The coder role needs per-task ACL context (file_paths), so it delegates to
    `build_worker_spec` and requires `task`/`strategy`/`run_dir`. All other
    roles are broadcast-only and need no task context. `model_key` overrides the
    bound model (used by `runner.run_phase_model` to spawn the role's agent).
    """
    if role not in SKILL_MAP.roles:
        raise KeyError(f'[HALT] role {role!r} not in SKILL_MAP')
    entry = SKILL_MAP.roles[role]
    spec = load_skill_spec(role)
    if role == 'coder':
        if task is None or strategy is None or run_dir is None:
            raise RuntimeError("[HALT] load_skill('coder') requires task, strategy and run_dir (coder needs per-task ACL context for tool wrapping).")
        agent = build_worker_spec(task, strategy, alignment, run_dir)
        return (spec, agent)
    key = model_key or entry.model_key
    model = resolve_model(key)
    output_type = OUTPUT_TYPE_REGISTRY[entry.output_type]
    unknown_tools = [n for n in spec.tool_allow_list if n not in _TOOL_BY_NAME]
    if unknown_tools:
        raise KeyError(f'[HALT] tool_allow_list for role {role!r} references unregistered tool(s) absent from TOOL_REGISTRY_KEYS: {sorted(unknown_tools)}')
    resolved_tools = [_TOOL_BY_NAME[n] for n in spec.tool_allow_list]
    instructions = spec.instructions
    if spec.hard_rules:
        instructions = instructions + '\n\n' + '\n'.join(spec.hard_rules)
    instructions = pydantic_ai_default_block() + '\n\n' + CODING_PHILOSOPHY_BLOCK + '\n\n' + instructions
    allowed_names = set(spec.tool_allow_list)
    tool_guide = build_tool_usage_guide(allowed_names)
    instructions = instructions + tool_guide
    budget = _tool_budget_for(role)
    instructions = instructions + _tool_budget_instruction(budget)
    instructions = instructions + '\n\n' + _build_repo_map()
    log_prompt_sent(role.upper(), role, role, instructions)
    agent = Agent(model=model, toolsets=[guard_tools(resolved_tools, budget)], instructions=instructions, output_type=output_type, retries=5, model_settings=ModelSettings(parallel_tool_calls=False))
    return (spec, agent)

def forge_skill_spec() -> list[str]:
    """D8 eager forge: build + cache ALL 6 role specs ONCE at startup.

    Writes each SkillSpec to factory/customised/<role>.yaml.
    Returns the list of forged role names. No LLM — pure structural extraction.
    """
    customised_dir = PKG_DIR / 'customised'
    customised_dir.mkdir(parents=True, exist_ok=True)
    forged: list[str] = []
    for role in SKILL_ROLES:
        spec = build_skill_spec(role)
        with open(customised_dir / f'{role}.yaml', 'w') as f:
            yaml.safe_dump(spec.model_dump(), f)
        forged.append(role)
    return forged
_FORGE_INSTRUCTIONS = 'You are SkillForge. Given a frozen skill skeleton and task context, you rewrite ONLY the `instructions` field into a precise, technically-grounded prompt for a coding agent, and select the exact `tools` (by name) the agent may use. Tools MUST be a subset of: ' + ', '.join(sorted(TOOL_REGISTRY_KEYS)) + '. Never invent tools. Be terse. Reference file:line only.'

def forge_skill(role: str, base_template: dict, ctx: str, run_dir: Path, task_id: str='') -> SkillSpec:
    """Bounded SkillForge loop (kept for M3): enrich instructions, validate tools.

    Retained until M3 lands. NOTE: M2 routes build_worker_spec through the
    cached SkillSpec (forge_skill_spec) instead of this per-task forge.
    """
    forge_agent = Agent(CONTROL_SHEET.models['planner_model'], output_type=SkillSpec, instructions=_FORGE_INSTRUCTIONS, model_settings=ModelSettings(parallel_tool_calls=False))
    template_str = yaml.safe_dump(base_template)
    last_err: str | None = None
    skill: SkillSpec | None = None
    for _ in range(MAX_FORGE_ITERS):
        try:
            prompt = f'Context:\n{ctx}\n\nFrozen base template:\n{template_str}\n'
            if last_err:
                prompt += f'\nPREVIOUS ERROR (fix it): {last_err}\n'
            res = forge_agent.run_sync(prompt)
            candidate = res.output
            safe_tools = [t for t in candidate.tool_allow_list if t in TOOL_REGISTRY_KEYS]
            if set(safe_tools) != set(candidate.tool_allow_list):
                last_err = f'rogue tools rejected: {set(candidate.tool_allow_list) - set(TOOL_REGISTRY_KEYS)}'
                candidate.tool_allow_list = safe_tools
                skill = candidate
                continue
            skill = candidate
            break
        except Exception as e:
            last_err = str(e)
    if skill is None:
        print(f'[SkillForge WARN] Forge failed for {role}; falling back to base template. Last error: {last_err}')
        skill = SkillSpec(name=role, instructions=str(base_template.get('instructions', '')), tool_allow_list=[f.__name__ for f in TOOL_REGISTRY.get('AST-edit', [])], hard_rules=['never edit src/ or src2/; confined to factory/'])
    suffix = f'_{task_id}' if task_id else ''
    name = f'skill_{role}{suffix}.yaml'
    customised_dir = PKG_DIR / 'customised'
    customised_dir.mkdir(parents=True, exist_ok=True)
    with open(customised_dir / name, 'w') as f:
        yaml.safe_dump(skill.model_dump(), f)
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / name, 'w') as f:
        yaml.safe_dump(skill.model_dump(), f)
    return skill

def build_worker_spec(task: ApprovedTask, strategy: Strategy, alignment: str, run_dir: Path) -> Agent[object, TaskResult]:
    """Build the Coder agent: allow-list → ACL wrap → cached SkillSpec → Agent.

    M2: instructions + tool contract are READ from the D8-cached SkillSpec
    (customised/coder.yaml) instead of forging per-task. Tool binding still
    honours the per-task strategy override so the python-first escalation of M1
    is preserved (identical runtime).
    """
    bucket = strategy.tool_preference_dict.get(task.id, 'AST-edit')
    raw_funcs = TOOL_REGISTRY.get(bucket, TOOL_REGISTRY['AST-edit'])
    assert {f.__name__ for f in raw_funcs} <= TOOL_REGISTRY_KEYS, 'rogue tool escaped registry'
    allowed_funcs = []
    for func in raw_funcs:
        if func.__name__ in _DISCOVERY_TOOLS:
            continue
        if func.__name__ == 'batch_read':
            allowed_funcs.append(wrap_with_acl(func, task.file_paths, deny_only=True))
            continue
        if func in MODIFY_TOOLS:
            allowed_funcs.append(wrap_with_acl(func, CODER_WRITE_ROOTS))
        else:
            allowed_funcs.append(wrap_with_acl(func, task.file_paths, deny_only=True))
    if not any((f.__name__ == 'batch_read' for f in allowed_funcs)):
        allowed_funcs.append(wrap_with_acl(batch_read, task.file_paths, deny_only=True))
    spec = load_skill_spec('coder')
    assert set(spec.tool_allow_list) <= set(TOOL_REGISTRY_KEYS), 'rogue tool in spec'
    allowed_funcs.append(record_plan)
    instructions = pydantic_ai_default_block() + '\n\n' + CODING_PHILOSOPHY_BLOCK + '\n\n' + spec.instructions
    all_coder_names = set(spec.tool_allow_list)
    tool_guide = build_tool_usage_guide(all_coder_names)
    instructions = instructions + tool_guide
    instructions = instructions + '\n\nPLAN BEFORE YOU ACT: You have a `record_plan(approach)` tool. You MUST call `record_plan` with your concrete edit strategy (which files, what change, in what order) BEFORE calling any write/edit tool (write_file, replace_text, replace_function, add_constant, add_import, delete_file, rename_file, move_symbol). Sequence: (1) record_plan, (2) batch_read the files you need (mandatory line_ranges, max 5 calls), (3) apply edits, (4) emit your final result. NEVER emit your final result before a record_plan call.'
    instructions = instructions + '\n\n' + _build_repo_map(scope_paths=list(task.file_paths))
    budget = _coder_budget_for(len(getattr(task, 'file_paths', []) or []))
    instructions = instructions + _tool_budget_instruction(budget)
    instructions = instructions + f'\n\nREAD BUDGET: you may call batch_read at most {READ_BUDGET} times and read_file at most {CODER_READ_FILE_BUDGET} times this run. After that, reads are disabled and you MUST emit final_result.'
    log_prompt_sent('CODER', task.id, task.id, instructions)
    agent = Agent(model=CONTROL_SHEET.models['coder_model'], toolsets=[guard_tools(allowed_funcs, budget, read_budget=READ_BUDGET, read_file_budget=CODER_READ_FILE_BUDGET)], instructions=instructions, output_type=TaskResult, model_settings=ModelSettings(parallel_tool_calls=False))
    return agent
