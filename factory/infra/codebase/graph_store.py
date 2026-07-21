#!/usr/bin/env python3
"""
graph_store.py — SQLite-backed dependency graph store for multi-repo impact analysis.

Manages:
  - SQLite database with repos, nodes, edges, artifacts tables
  - Per-repo .acivar/ artifact directories (JSONL, JSON, MD)
  - Graph building via AST import parsing (delegates to impact_core)
  - Staleness detection via git commit + dirty tree + file hashes

All functions accept repo_name (not Path) — resolved via config.get_repo_root().
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:
    from .config import PROJECT_ROOT, get_repo_root
except ImportError:
    from config import get_repo_root

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CURRENT_GRAPH_VERSION = "1.0"
SQLITE_PATH = Path(__file__).resolve().parent / "graph_store.sqlite"

# Files relevant to graph freshness (only these trigger hard_stale)
GRAPH_RELEVANT_EXTENSIONS = {".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml"}
GRAPH_RELEVANT_NAMES = {"pyproject.toml", "requirements.txt", "package.json", "Dockerfile"}
GRAPH_RELEVANT_PATTERNS = {".acivar/manual_overrides."}

# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    """Get SQLite connection, creating tables if needed."""
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection):
    """Idempotent table creation."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS repos (
            repo_name TEXT PRIMARY KEY,
            repo_root TEXT NOT NULL,
            last_generated_at TEXT,
            git_commit TEXT,
            working_tree_dirty INTEGER DEFAULT 0,
            graph_version TEXT DEFAULT '1.0'
        );

        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            module_name TEXT,
            tier INTEGER DEFAULT 3,
            blast_radius TEXT DEFAULT 'unknown',
            used_by_count INTEGER DEFAULT 0,
            risk_tags TEXT DEFAULT '[]',
            manual_override INTEGER DEFAULT 0,
            UNIQUE(repo_name, file_path),
            FOREIGN KEY (repo_name) REFERENCES repos(repo_name)
        );

        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_name TEXT NOT NULL,
            from_file TEXT NOT NULL,
            to_file TEXT NOT NULL,
            edge_type TEXT DEFAULT 'imports',
            source TEXT DEFAULT 'ast',
            UNIQUE(repo_name, from_file, to_file, edge_type),
            FOREIGN KEY (repo_name) REFERENCES repos(repo_name)
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            repo_name TEXT PRIMARY KEY,
            edges_jsonl_path TEXT,
            scores_json_path TEXT,
            impact_map_md_path TEXT,
            manifest_json_path TEXT,
            FOREIGN KEY (repo_name) REFERENCES repos(repo_name)
        );

        CREATE INDEX IF NOT EXISTS idx_nodes_repo ON nodes(repo_name);
        CREATE INDEX IF NOT EXISTS idx_edges_repo ON edges(repo_name);
        CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(repo_name, from_file);
        CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(repo_name, to_file);
    """)


# ---------------------------------------------------------------------------
# Git state helpers
# ---------------------------------------------------------------------------

def _get_git_commit(repo_root: Path) -> str | None:
    """Return current git HEAD commit hash, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=str(repo_root),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _get_git_dirty_files(repo_root: Path) -> list[str]:
    """Return list of uncommitted changed files (porcelain format)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
            cwd=str(repo_root),
        )
        if result.returncode == 0:
            files = []
            for line in result.stdout.strip().splitlines():
                if line:
                    # Porcelain format: "XY filename" or "XY filename -> new_name"
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        filepath = parts[1].split(" -> ")[-1].strip()
                        files.append(filepath)
            return files
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return []


def _is_graph_relevant(filepath: str) -> bool:
    """Check if a changed file is relevant to graph freshness."""
    p = Path(filepath)
    if p.name in GRAPH_RELEVANT_NAMES:
        return True
    if p.suffix in GRAPH_RELEVANT_EXTENSIONS:
        return True
    for pattern in GRAPH_RELEVANT_PATTERNS:
        if pattern in filepath:
            return True
    return False


def _hash_file(filepath: Path) -> str:
    """Return SHA-256 hash of a file."""
    h = hashlib.sha256()
    try:
        h.update(filepath.read_bytes())
    except (OSError, IOError):
        return ""
    return f"sha256:{h.hexdigest()}"


def _hash_file_list(repo_root: Path, files: list[str]) -> str:
    """Return a combined hash of a sorted list of file paths."""
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(f.encode())
    return f"sha256:{h.hexdigest()}"


# ---------------------------------------------------------------------------
# Graph building
# ---------------------------------------------------------------------------

def build_graph(repo_name: str, src_subdir: str = "src") -> dict:
    """Build dependency graph for a repo from AST, store in SQLite + .acivar/ artifacts.

    Returns summary dict with node_count, edge_count, file_count.
    """
    from impact_core import build_module_graph

    repo_root = get_repo_root(repo_name)
    src_root = repo_root / src_subdir

    if not src_root.exists():
        raise ValueError(f"{src_subdir}/ not found in {repo_name} ({repo_root})")

    # Build module graph via existing impact_core
    graph = build_module_graph(repo_root, src_root)
    forward = graph["forward"]
    reverse = graph["reverse"]
    module_files = graph["module_files"]

    # Collect all .py files
    py_files = sorted(src_root.rglob("*.py"))
    py_file_paths = [f.relative_to(repo_root).as_posix() for f in py_files]

    # Compute used_by_count for each file
    used_by: dict[str, int] = {}
    for f in py_file_paths:
        used_by[f] = len(reverse.get(f, []))

    # Determine tiers based on reverse dependency count
    tiers = _compute_tiers(used_by, reverse)

    # Git state
    git_commit = _get_git_commit(repo_root)
    dirty_files = _get_git_dirty_files(repo_root)
    working_tree_dirty = len(dirty_files) > 0

    # Write to SQLite
    conn = _get_db()
    try:
        # Clear old data for this repo
        conn.execute("DELETE FROM edges WHERE repo_name = ?", (repo_name,))
        conn.execute("DELETE FROM nodes WHERE repo_name = ?", (repo_name,))
        conn.execute("DELETE FROM repos WHERE repo_name = ?", (repo_name,))
        conn.execute("DELETE FROM artifacts WHERE repo_name = ?", (repo_name,))

        # Insert repo record
        conn.execute(
            "INSERT INTO repos (repo_name, repo_root, last_generated_at, git_commit, working_tree_dirty, graph_version) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (repo_name, str(repo_root), datetime.now(timezone.utc).isoformat(),
             git_commit, int(working_tree_dirty), CURRENT_GRAPH_VERSION),
        )

        # Insert nodes
        for f in py_file_paths:
            mod_name = _file_to_module(f, repo_root)
            tier_info = tiers.get(f, {"tier": 3, "blast_radius": "low", "risk_tags": []})
            conn.execute(
                "INSERT INTO nodes (repo_name, file_path, module_name, tier, blast_radius, used_by_count, risk_tags) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (repo_name, f, mod_name, tier_info["tier"], tier_info["blast_radius"],
                 used_by.get(f, 0), json.dumps(tier_info["risk_tags"])),
            )

        # Insert edges
        edge_count = 0
        for from_file, to_files in forward.items():
            for to_file in to_files:
                conn.execute(
                    "INSERT OR IGNORE INTO edges (repo_name, from_file, to_file, edge_type, source) "
                    "VALUES (?, ?, ?, 'imports', 'ast')",
                    (repo_name, from_file, to_file),
                )
                edge_count += 1

        conn.commit()
    finally:
        conn.close()

    # Generate .acivar/ artifacts
    acivar_dir = _get_acivar_dir(repo_root)
    _write_artifacts(repo_name, repo_root, acivar_dir, forward, reverse, module_files, tiers, used_by)

    return {
        "repo_name": repo_name,
        "node_count": len(py_file_paths),
        "edge_count": edge_count,
        "file_count": len(py_file_paths),
        "git_commit": git_commit,
        "working_tree_dirty": working_tree_dirty,
        "acivar_dir": str(acivar_dir),
    }


def _compute_tiers(used_by: dict[str, int], reverse: dict) -> dict[str, dict]:
    """Compute tier assignments based on reverse dependency count.

    Tier 1: used_by >= 10 (massive blast radius — foundation)
    Tier 2: used_by 4-9 (high blast radius — core engine)
    Tier 3: used_by 1-3 (moderate — feature modules)
    Tier 4: used_by 0 (leaf modules)
    """
    tiers: dict[str, dict] = {}
    for f, count in used_by.items():
        if count >= 10:
            tiers[f] = {"tier": 1, "blast_radius": "massive", "risk_tags": ["foundation"]}
        elif count >= 4:
            tiers[f] = {"tier": 2, "blast_radius": "high", "risk_tags": ["core"]}
        elif count >= 1:
            tiers[f] = {"tier": 3, "blast_radius": "moderate", "risk_tags": ["feature"]}
        else:
            tiers[f] = {"tier": 4, "blast_radius": "low", "risk_tags": ["leaf"]}
    return tiers


def _file_to_module(file_path: str, repo_root: Path) -> str:
    """Convert file path to module name: src/engine/bazi_data.py → src.engine.bazi_data."""
    p = Path(file_path)
    if p.name == "__init__.py":
        parts = p.parent.parts
    else:
        parts = p.with_suffix("").parts
    return ".".join(parts)


# ---------------------------------------------------------------------------
# Artifact generation
# ---------------------------------------------------------------------------

def _get_acivar_dir(repo_root: Path) -> Path:
    """Return (and create) the .acivar/ directory for a repo."""
    d = repo_root / ".acivar"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_artifacts(
    repo_name: str,
    repo_root: Path,
    acivar_dir: Path,
    forward: dict,
    reverse: dict,
    module_files: dict,
    tiers: dict,
    used_by: dict,
):
    """Write all .acivar/ artifact files."""
    # 1. dependency_edges.jsonl
    edges_path = acivar_dir / "dependency_edges.jsonl"
    with open(edges_path, "w", encoding="utf-8") as f:
        for from_file, to_files in sorted(forward.items()):
            for to_file in sorted(to_files):
                record = {
                    "repo": repo_name,
                    "from": from_file,
                    "to": to_file,
                    "edge_type": "imports",
                    "source": "ast",
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 2. module_scores.json
    scores_path = acivar_dir / "module_scores.json"
    modules = {}
    for file_path, tier_info in sorted(tiers.items()):
        modules[file_path] = {
            "tier": tier_info["tier"],
            "blast_radius": tier_info["blast_radius"],
            "used_by_count": used_by.get(file_path, 0),
            "manual_override": False,
            "risk_tags": tier_info["risk_tags"],
        }
    scores_data = {"repo": repo_name, "modules": modules}
    scores_path.write_text(json.dumps(scores_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. IMPACT_MAP.md
    md_path = acivar_dir / "IMPACT_MAP.md"
    md_lines = [
        f"# IMPACT MAP — {repo_name}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Git commit: {_get_git_commit(repo_root) or 'N/A'}",
        "",
        "## Tier Summary",
        "",
    ]
    for tier_num, tier_label, tier_icon in [
        (1, "Foundation", "🔴"),
        (2, "Core Engine", "🟠"),
        (3, "Feature Modules", "🟡"),
        (4, "Leaf Modules", "🟢"),
    ]:
        tier_files = [f for f, t in sorted(tiers.items()) if t["tier"] == tier_num]
        md_lines.append(f"### {tier_icon} Tier {tier_num} — {tier_label} ({len(tier_files)} modules)")
        md_lines.append("")
        for f in tier_files:
            md_lines.append(f"- `{f}` — used by {used_by.get(f, 0)} modules")
        md_lines.append("")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    # 4. index_manifest.json
    manifest_path = acivar_dir / "index_manifest.json"
    py_files = sorted((repo_root / "src").rglob("*.py")) if (repo_root / "src").exists() else []
    py_file_paths = [f.relative_to(repo_root).as_posix() for f in py_files]
    file_hashes = {str(p): _hash_file(repo_root / p) for p in py_file_paths}

    manifest = {
        "repo": repo_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _get_git_commit(repo_root),
        "working_tree_dirty": len(_get_git_dirty_files(repo_root)) > 0,
        "graph_version": CURRENT_GRAPH_VERSION,
        "indexed_file_count": len(py_file_paths),
        "indexed_paths_hash": _hash_file_list(repo_root, py_file_paths),
        "file_hashes": file_hashes,
        "source": "ast_import_graph",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Impact query
# ---------------------------------------------------------------------------

def get_impact(repo_name: str, target_path: str, depth: int = 2) -> dict:
    """Query the graph for the impact neighborhood of a target file.

    Returns:
        target: the file path
        direct_dependents: files that directly import target
        transitive_dependents: files affected up to `depth` hops
        upstream_dependencies: files that target imports
        risk_summary: tier breakdown of affected modules
    """
    conn = _get_db()
    try:
        # Direct dependents (reverse edges)
        direct_dependents = [
            row["from_file"] for row in
            conn.execute(
                "SELECT from_file FROM edges WHERE repo_name = ? AND to_file = ? AND edge_type = 'imports'",
                (repo_name, target_path),
            ).fetchall()
        ]

        # Transitive dependents via BFS
        transitive = set()
        frontier = list(direct_dependents)
        for _ in range(depth):
            next_frontier = []
            for f in frontier:
                if f in transitive:
                    continue
                transitive.add(f)
                rows = conn.execute(
                    "SELECT from_file FROM edges WHERE repo_name = ? AND to_file = ? AND edge_type = 'imports'",
                    (repo_name, f),
                ).fetchall()
                next_frontier.extend(r["from_file"] for r in rows)
            frontier = next_frontier

        # Upstream dependencies (forward edges)
        upstream = [
            row["to_file"] for row in
            conn.execute(
                "SELECT to_file FROM edges WHERE repo_name = ? AND from_file = ? AND edge_type = 'imports'",
                (repo_name, target_path),
            ).fetchall()
        ]

        # Risk summary: tier breakdown of affected modules
        all_affected = set(direct_dependents) | transitive
        tier_counts: dict[int, int] = {}
        for f in all_affected:
            row = conn.execute(
                "SELECT tier FROM nodes WHERE repo_name = ? AND file_path = ?",
                (repo_name, f),
            ).fetchone()
            if row:
                t = row["tier"]
                tier_counts[t] = tier_counts.get(t, 0) + 1

        return {
            "target": target_path,
            "direct_dependents": sorted(direct_dependents),
            "transitive_dependents": sorted(transitive),
            "upstream_dependencies": sorted(upstream),
            "total_affected": len(all_affected),
            "tier_breakdown": {str(k): v for k, v in sorted(tier_counts.items())},
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------

def check_freshness(repo_name: str) -> dict:
    """Check graph freshness for a repo.

    Returns freshness dict with status, reason, and details.
    """
    repo_root = get_repo_root(repo_name)
    acivar_dir = repo_root / ".acivar"
    manifest_path = acivar_dir / "index_manifest.json"

    if not manifest_path.exists():
        return {
            "status": "unknown",
            "reason": "No manifest found — graph has not been built",
            "graph_fresh": False,
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "status": "unknown",
            "reason": "Manifest corrupt or unreadable",
            "graph_fresh": False,
        }

    current = {
        "git_commit": _get_git_commit(repo_root),
        "working_tree_dirty": len(_get_git_dirty_files(repo_root)) > 0,
        "changed_graph_files": [],
        "indexed_paths_hash": "",
    }

    # Compute current indexed paths hash
    src_root = repo_root / "src"
    if src_root.exists():
        py_files = sorted(src_root.rglob("*.py"))
        py_paths = [f.relative_to(repo_root).as_posix() for f in py_files]
        current["indexed_paths_hash"] = _hash_file_list(repo_root, py_paths)

        # Check for changed graph-relevant files
        dirty_files = _get_git_dirty_files(repo_root)
        current["changed_graph_files"] = [f for f in dirty_files if _is_graph_relevant(f)]

    status, reason = classify_staleness(manifest, current)

    return {
        "status": status,
        "reason": reason,
        "graph_fresh": status == "fresh",
        "generated_commit": manifest.get("git_commit"),
        "current_commit": current["git_commit"],
        "working_tree_dirty": current["working_tree_dirty"],
        "changed_graph_relevant_files": current["changed_graph_files"],
        "generated_at": manifest.get("generated_at"),
    }


def classify_staleness(manifest: dict, current: dict) -> tuple[str, str]:
    """Classify staleness level.

    Returns (status, reason) where status is one of:
        fresh, soft_stale, hard_stale, unknown
    """
    if not manifest:
        return "unknown", "No manifest found"

    if manifest.get("graph_version") != CURRENT_GRAPH_VERSION:
        return "hard_stale", f"Graph version changed: {manifest.get('graph_version')} → {CURRENT_GRAPH_VERSION}"

    if manifest.get("git_commit") != current.get("git_commit"):
        return "hard_stale", "Git commit changed"

    if current.get("working_tree_dirty"):
        if current.get("changed_graph_files"):
            return "hard_stale", "Graph-relevant files changed in working tree"
        else:
            return "soft_stale", "Only non-graph files changed"

    if manifest.get("indexed_paths_hash") != current.get("indexed_paths_hash"):
        return "hard_stale", "Indexed file set changed"

    return "fresh", "Graph matches current repo state"


def get_target_freshness(repo_name: str, target_path: str) -> dict:
    """Check freshness specific to a target file's neighborhood.

    Even if the global graph is stale, the target's local neighborhood
    might still be accurate.
    """
    global_freshness = check_freshness(repo_name)

    if global_freshness["status"] == "fresh":
        return {
            "global_freshness": "fresh",
            "target_freshness": "fresh",
            "target_file_changed": False,
            "target_neighbor_changed": False,
        }

    repo_root = get_repo_root(repo_name)
    dirty_files = set(_get_git_dirty_files(repo_root))

    # Check if target file itself changed
    target_changed = target_path in dirty_files

    # Check if any direct dependent changed
    conn = _get_db()
    try:
        direct_dependents = {
            row["from_file"] for row in
            conn.execute(
                "SELECT from_file FROM edges WHERE repo_name = ? AND to_file = ?",
                (repo_name, target_path),
            ).fetchall()
        }
    finally:
        conn.close()

    neighbor_changed = bool(dirty_files & direct_dependents)

    if target_changed or neighbor_changed:
        target_status = "stale"
    elif global_freshness["status"] == "soft_stale":
        target_status = "probably_fresh"
    else:
        target_status = "unknown"

    return {
        "global_freshness": global_freshness["status"],
        "target_freshness": target_status,
        "target_file_changed": target_changed,
        "target_neighbor_changed": neighbor_changed,
    }


# ---------------------------------------------------------------------------
# Graph refresh
# ---------------------------------------------------------------------------

def refresh_graph(repo_name: str, force: bool = False, src_subdir: str = "src") -> dict:
    """Rebuild graph for a repo.

    If force=False and working tree is dirty, refuse to refresh.
    """
    repo_root = get_repo_root(repo_name)

    if not force:
        dirty = _get_git_dirty_files(repo_root)
        graph_dirty = [f for f in dirty if _is_graph_relevant(f)]
        if graph_dirty:
            return {
                "success": False,
                "message": f"Working tree has {len(graph_dirty)} uncommitted graph-relevant changes. Use force=True to override.",
                "dirty_files": graph_dirty,
            }

    result = build_graph(repo_name, src_subdir)
    return {
        "success": True,
        "message": f"Graph rebuilt for {repo_name}",
        **result,
    }


# ---------------------------------------------------------------------------
# List repos
# ---------------------------------------------------------------------------

def list_graph_repos() -> list[dict]:
    """List all repos that have a graph in SQLite."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT r.repo_name, r.repo_root, r.last_generated_at, r.git_commit, "
            "r.working_tree_dirty, r.graph_version, "
            "COUNT(DISTINCT n.id) as node_count, COUNT(DISTINCT e.id) as edge_count "
            "FROM repos r "
            "LEFT JOIN nodes n ON r.repo_name = n.repo_name "
            "LEFT JOIN edges e ON r.repo_name = e.repo_name "
            "GROUP BY r.repo_name"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
