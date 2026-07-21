#!/usr/bin/env python3
"""
impact_core.py — Pure functions for dependency + module impact analysis.

Uses ONLY stdlib (importlib.metadata + ast). No Syft, no external tools.
Designed to be imported by both the CLI tool and MCP server.

All functions accept an explicit `repo_root: Path` parameter for multi-repo support.
"""

import ast
from collections import defaultdict
from datetime import datetime, timezone
from importlib.metadata import distributions
from pathlib import Path

SNAPSHOT_VERSION = 1

# Stdlib module filter — used to distinguish external packages from stdlib
_STDLIB = {
    "abc", "aifc", "argparse", "ast", "asyncio", "base64", "bisect",
    "calendar", "collections", "concurrent", "contextlib", "copy", "csv",
    "dataclasses", "datetime", "decimal", "email", "enum", "errno",
    "functools", "glob", "gzip", "hashlib", "heapq", "hmac", "html",
    "http", "importlib", "inspect", "io", "itertools", "json", "logging",
    "math", "multiprocessing", "operator", "os", "pathlib", "pickle",
    "platform", "pprint", "queue", "random", "re", "secrets", "shutil",
    "signal", "socket", "sqlite3", "ssl", "stat", "string", "struct",
    "subprocess", "sys", "tempfile", "textwrap", "threading", "time",
    "traceback", "typing", "unicodedata", "urllib", "uuid", "warnings",
    "weakref", "xml", "zipfile", "zlib", "zoneinfo", "__future__",
}


def get_installed_packages() -> dict[str, str]:
    """Return {name: version} for all installed packages via importlib.metadata."""
    return {
        d.metadata["Name"]: d.version
        for d in sorted(distributions(), key=lambda x: x.metadata["Name"].lower())
    }


def get_internal_imports(filepath: Path, src_root: Path) -> list[str]:
    """Extract all internal imports from a Python file via AST.

    Internal imports are those where the module path corresponds to a file
    under src_root (e.g., 'src.engine.bazi_data').
    """
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    imports: set[str] = set()
    src_str = src_root.name  # e.g., "src"
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith(f"{src_str}."):
                imports.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(f"{src_str}."):
                    imports.add(alias.name)
    return list(imports)


def get_external_imports(filepath: Path, src_root: Path) -> list[str]:
    """Extract top-level external package names from a Python file via AST.

    Skips stdlib and internal (src.*) imports.
    E.g., 'import httpx' → 'httpx'; 'from fastapi import FastAPI' → 'fastapi'
    """
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    src_str = src_root.name
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith(f"{src_str}."):
                continue
            top = node.module.split(".")[0]
            if top not in _STDLIB:
                imports.add(top)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(f"{src_str}."):
                    continue
                top = alias.name.split(".")[0]
                if top not in _STDLIB:
                    imports.add(top)
    return list(imports)


def build_module_graph(repo_root: Path, src_root: Path) -> dict:
    """Build internal module dependency graph.

    Returns:
        forward: {module_path: [imported_module_paths]}
        reverse: {module_path: [dependent_module_paths]}
        module_files: {module_name: file_path}
    """
    forward: dict[str, list[str]] = {}
    reverse: dict[str, set[str]] = defaultdict(set)
    module_files: dict[str, str] = {}

    for f in sorted(src_root.rglob("*.py")):
        rel = f.relative_to(repo_root).as_posix()
        # Convert file path to module name: src/engine/bazi_data.py → src.engine.bazi_data
        if f.name == "__init__.py":
            mod_parts = f.parent.relative_to(repo_root).parts
        else:
            mod_parts = f.with_suffix("").relative_to(repo_root).parts
        mod_name = ".".join(mod_parts)
        module_files[mod_name] = rel

        internal_imps = get_internal_imports(f, src_root)
        resolved: list[str] = []
        for imp in internal_imps:
            parts = imp.split(".")
            candidate_file = repo_root / ("/".join(parts) + ".py")
            candidate_init = repo_root / ("/".join(parts) + "/__init__.py")
            if candidate_file.exists():
                resolved.append(candidate_file.relative_to(repo_root).as_posix())
            elif candidate_init.exists():
                resolved.append(candidate_init.relative_to(repo_root).as_posix())

        if resolved:
            forward[rel] = resolved
            for r in resolved:
                reverse[r].add(rel)

    return {
        "forward": forward,
        "reverse": {k: sorted(v) for k, v in reverse.items()},
        "module_files": module_files,
    }


def build_package_file_map(repo_root: Path, src_root: Path) -> dict[str, list[str]]:
    """Map external package names → files that import them.

    Returns: {package_name: [file_paths]}
    """
    pkg_map: dict[str, set[str]] = defaultdict(set)
    for f in sorted(repo_root.rglob("*.py")):
        rel = f.relative_to(repo_root).as_posix()
        for pkg in get_external_imports(f, src_root):
            pkg_map[pkg].add(rel)
    return {k: sorted(v) for k, v in pkg_map.items()}


def take_snapshot(repo_root: Path, src_root: Path) -> dict:
    """Take a full snapshot of packages + module graph + package-file map."""
    packages = get_installed_packages()
    graph = build_module_graph(repo_root, src_root)
    pkg_map = build_package_file_map(repo_root, src_root)

    return {
        "version": SNAPSHOT_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "packages": packages,
        "module_graph": graph,
        "package_file_map": pkg_map,
    }


def diff_packages(old: dict[str, str], new: dict[str, str]) -> dict[str, dict]:
    """Diff two package snapshots. Returns changes keyed by package name."""
    changes: dict[str, dict] = {}
    all_pkgs = set(old) | set(new)

    for pkg in sorted(all_pkgs):
        if pkg not in old:
            changes[pkg] = {"status": "added", "old_version": None, "new_version": new[pkg]}
        elif pkg not in new:
            changes[pkg] = {"status": "removed", "old_version": old[pkg], "new_version": None}
        elif old[pkg] != new[pkg]:
            changes[pkg] = {"status": "updated", "old_version": old[pkg], "new_version": new[pkg]}

    return changes


def find_impacted_modules(changed_files: list[str], reverse_graph: dict) -> list[str]:
    """Walk reverse dependency graph to find all modules affected by file changes."""
    impacted: set[str] = set()
    visited: set[str] = set()

    def dfs(f: str):
        for dep in reverse_graph.get(f, []):
            if dep not in visited:
                visited.add(dep)
                impacted.add(dep)
                dfs(dep)

    for f in changed_files:
        dfs(f)

    return sorted(impacted)


def compute_impact(baseline: dict, repo_root: Path, src_root: Path) -> dict:
    """Full diff pipeline: baseline → current → impact report."""
    current_packages = get_installed_packages()
    current_graph = build_module_graph(repo_root, src_root)
    current_pkg_map = build_package_file_map(repo_root, src_root)

    pkg_changes = diff_packages(baseline["packages"], current_packages)

    # Map changed packages → directly affected files
    direct_files: set[str] = set()
    for pkg in pkg_changes:
        if pkg in current_pkg_map:
            direct_files.update(current_pkg_map[pkg])
        if pkg in baseline.get("package_file_map", {}):
            direct_files.update(baseline["package_file_map"][pkg])

    direct_files_list = sorted(direct_files)

    # Walk internal graph for downstream impact
    impacted_modules = find_impacted_modules(direct_files_list, current_graph["reverse"])

    # Module graph diff (structural changes)
    old_forward = set(baseline["module_graph"]["forward"].keys())
    new_forward = set(current_graph["forward"].keys())

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_timestamp": baseline.get("timestamp", "unknown"),
        "package_changes": pkg_changes,
        "directly_affected_files": direct_files_list,
        "downstream_modules": impacted_modules,
        "new_modules": sorted(new_forward - old_forward),
        "removed_modules": sorted(old_forward - new_forward),
        "summary": {
            "packages_added": sum(1 for c in pkg_changes.values() if c["status"] == "added"),
            "packages_removed": sum(1 for c in pkg_changes.values() if c["status"] == "removed"),
            "packages_updated": sum(1 for c in pkg_changes.values() if c["status"] == "updated"),
            "files_directly_affected": len(direct_files_list),
            "modules_downstream_impacted": len(impacted_modules),
        },
    }


def format_report(report: dict) -> str:
    """Generate human-readable impact report from diff data."""
    s = report["summary"]
    lines = []
    lines.append("=" * 60)
    lines.append("  IMPACT REPORT")
    lines.append("=" * 60)
    lines.append(f"  Baseline:  {report.get('baseline_timestamp', 'unknown')}")
    lines.append(f"  Current:   {report['timestamp']}")
    lines.append(f"  Packages:  +{s['packages_added']} added, -{s['packages_removed']} removed, ~{s['packages_updated']} updated")
    lines.append(f"  Files:     {s['files_directly_affected']} directly affected")
    lines.append(f"  Modules:   {s['modules_downstream_impacted']} downstream impacted")
    lines.append("=" * 60)

    if report["package_changes"]:
        lines.append("\n📦 PACKAGE CHANGES:")
        for pkg, change in report["package_changes"].items():
            status = change["status"]
            if status == "added":
                lines.append(f"  [+] {pkg} → {change['new_version']}")
            elif status == "removed":
                lines.append(f"  [-] {pkg} ({change['old_version']})")
            else:
                lines.append(f"  [~] {pkg}: {change['old_version']} → {change['new_version']}")

    if report["directly_affected_files"]:
        lines.append("\n📄 DIRECTLY AFFECTED FILES:")
        for f in report["directly_affected_files"][:20]:
            lines.append(f"  • {f}")
        if len(report["directly_affected_files"]) > 20:
            lines.append(f"  ... and {len(report['directly_affected_files']) - 20} more")

    if report["downstream_modules"]:
        lines.append("\n🔗 DOWNSTREAM MODULES:")
        for m in report["downstream_modules"][:20]:
            lines.append(f"  • {m}")
        if len(report["downstream_modules"]) > 20:
            lines.append(f"  ... and {len(report['downstream_modules']) - 20} more")

    if report.get("new_modules"):
        lines.append("\n🆕 NEW MODULES:")
        for m in report["new_modules"]:
            lines.append(f"  • {m}")

    if report.get("removed_modules"):
        lines.append("\n🗑️  REMOVED MODULES:")
        for m in report["removed_modules"]:
            lines.append(f"  • {m}")

    lines.append("")
    return "\n".join(lines)


def build_llm_input(report: dict) -> dict:
    """Convert impact report into structured LLM prompt JSON."""
    changes = []
    for pkg, change in report.get("package_changes", {}).items():
        changes.append({
            "package": pkg,
            "status": change["status"],
            "from": change["old_version"],
            "to": change["new_version"],
        })

    return {
        "system": "You are a strict dependency impact analyzer. Do NOT infer dependencies not explicitly listed.",
        "task": "Analyze the impact of dependency and module changes on the codebase",
        "rules": [
            "Use ONLY the provided impacted files and modules",
            "Do NOT assume additional dependencies beyond what is listed",
            "Separate CONFIRMED issues (direct import) from POSSIBLE issues (downstream)",
            "If uncertain, say 'Insufficient information'",
            "Focus on breaking changes, API mismatches, and behavioral regressions",
        ],
        "changes": changes,
        "directly_affected_files": report.get("directly_affected_files", []),
        "downstream_modules": report.get("downstream_modules", []),
        "new_modules": report.get("new_modules", []),
        "removed_modules": report.get("removed_modules", []),
        "instructions": [
            "Explain what might break and why",
            "Identify specific functions or classes at risk",
            "Suggest minimal fixes or migration steps",
            "Return structured JSON output",
        ],
        "output_format": {
            "summary": "string — one-paragraph overview of impact severity",
            "risk_level": "LOW | MEDIUM | HIGH | CRITICAL",
            "issues": [
                {
                    "file": "string",
                    "type": "CONFIRMED | POSSIBLE",
                    "description": "string — what might break",
                    "reason": "string — why this is affected",
                    "fix": "string — suggested remediation",
                }
            ],
            "safe_changes": ["string — packages/modules with no detected risk"],
            "unknowns": ["string — areas needing manual review"],
        },
    }
