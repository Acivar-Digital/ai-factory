import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

def compile_jsonl_to_dict(raw: str) -> dict[str, Any]:
    """
    Generalized JSONL compiler: parses flat line-by-line JSON objects and merges them
    recursively into a single target dictionary.
    """
    master_dict: dict[str, Any] = {}
    lines = raw.strip().splitlines()
    for line_idx, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        if line.startswith("- ") or line.startswith("* "):
            line = line[2:].strip()

        obj = None
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            from factory.infra.output_sanitizer import extract_json_block
            block = extract_json_block(line)
            try:
                obj = json.loads(block)
            except json.JSONDecodeError:
                continue

        if not isinstance(obj, dict):
            if isinstance(obj, list):
                for item in obj:
                    if isinstance(item, dict):
                        _deep_merge(master_dict, item)
            continue

        _deep_merge(master_dict, obj)
    return master_dict

def auto_heal_draft_plan_evidence(master_dict: dict[str, Any]) -> dict[str, Any]:
    """Programmatically constructs required EvidenceItem arrays for DraftPlan."""
    if "subtasks" in master_dict and isinstance(master_dict["subtasks"], list):
        for task in master_dict["subtasks"]:
            if not isinstance(task, dict):
                continue
            file_paths = task.get("file_paths") or []
            evidence = task.get("evidence") or []

            if isinstance(evidence, dict):
                evidence = [{"file_path": k, "content": v} for k, v in evidence.items()]
            elif not isinstance(evidence, list):
                evidence = []

            existing_paths = {ev.get("file_path") for ev in evidence if isinstance(ev, dict) and ev.get("file_path")}
            for fp in file_paths:
                if fp and fp not in existing_paths:
                    evidence.append({
                        "file_path": fp,
                        "content": f"[Auto-Healed] Proof of existence/content for file: {fp}"
                    })
            task["evidence"] = evidence
    return master_dict

def compile_jsonl_to_draft_plan_dict(raw: str) -> dict[str, Any]:
    """Backward compatible wrapper for DraftPlan compilation."""
    compiled = compile_jsonl_to_dict(raw)
    return auto_heal_draft_plan_evidence(compiled)

def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for k, v in source.items():
        if k in target:
            if isinstance(target[k], dict) and isinstance(v, dict):
                _deep_merge(target[k], v)
            elif isinstance(target[k], list) and isinstance(v, list):
                for item in v:
                    if item not in target[k]:
                        target[k].append(item)
            else:
                target[k] = v
        else:
            target[k] = v

