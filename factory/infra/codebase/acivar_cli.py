#!/usr/bin/env python3
"""
acivar_cli.py — Multi-repo CLI for dependency graph impact analysis.

Wraps graph_store.py for command-line usage. All commands accept --repo
to specify which repo to operate on (resolved via config.get_repo_root()).

Usage:
  uv run python acivar_cli.py graph build --repo baziforecaster
  uv run python acivar_cli.py graph refresh --repo baziforecaster
  uv run python acivar_cli.py analyze --repo baziforecaster --target src/engine/bazi_data.py
  uv run python acivar_cli.py freshness --repo baziforecaster
  uv run python acivar_cli.py list-repos
  uv run python acivar_cli.py show-impact --repo baziforecaster --target src/engine/bazi_data.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure we can import from infra/codebase/
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from graph_store import (
    build_graph,
    check_freshness,
    get_impact,
    get_target_freshness,
    list_graph_repos,
    refresh_graph,
)


def cmd_graph_build(args):
    """Build dependency graph for a repo."""
    print(f"Building graph for {args.repo}...")
    result = build_graph(args.repo, src_subdir=args.src)
    print(f"✅ Graph built: {result['node_count']} nodes, {result['edge_count']} edges")
    print(f"   Git commit: {result.get('git_commit', 'N/A')}")
    print(f"   Working tree dirty: {result.get('working_tree_dirty')}")
    print(f"   Artifacts: {result.get('acivar_dir')}")


def cmd_graph_refresh(args):
    """Rebuild dependency graph for a repo."""
    print(f"Refreshing graph for {args.repo} (force={args.force})...")
    result = refresh_graph(args.repo, force=args.force, src_subdir=args.src)
    if result.get("success"):
        print(f"✅ {result['message']}")
        print(f"   Nodes: {result.get('node_count')}, Edges: {result.get('edge_count')}")
    else:
        print(f"❌ {result['message']}")
        if "dirty_files" in result:
            for f in result["dirty_files"][:10]:
                print(f"   ⚠️  {f}")


def cmd_analyze(args):
    """Analyze impact of changing a specific file."""
    print(f"Analyzing impact: {args.repo}/{args.target}")

    # Check freshness first
    freshness = check_freshness(args.repo)
    print(f"\nGraph freshness: {freshness['status']}")
    if not freshness["graph_fresh"]:
        print(f"  Reason: {freshness['reason']}")
        print(f"  Generated commit: {freshness.get('generated_commit', 'N/A')}")
        print(f"  Current commit: {freshness.get('current_commit', 'N/A')}")

    # Target-specific freshness
    tgt = get_target_freshness(args.repo, args.target)
    print(f"Target freshness: {tgt['target_freshness']}")
    if tgt["target_file_changed"]:
        print("  ⚠️  Target file has uncommitted changes")
    if tgt["target_neighbor_changed"]:
        print("  ⚠️  Direct dependents have uncommitted changes")

    # Impact
    impact = get_impact(args.repo, args.target, depth=args.depth)
    print(f"\n{'='*60}")
    print(f"  IMPACT ANALYSIS: {impact['target']}")
    print(f"{'='*60}")
    print(f"  Direct dependents:    {len(impact['direct_dependents'])}")
    print(f"  Transitive dependents: {len(impact['transitive_dependents'])}")
    print(f"  Upstream dependencies: {len(impact['upstream_dependencies'])}")
    print(f"  Total affected:       {impact['total_affected']}")

    if impact["tier_breakdown"]:
        print("\n  Tier breakdown:")
        for tier, count in sorted(impact["tier_breakdown"].items()):
            tier_label = {"1": "🔴 Foundation", "2": "🟠 Core", "3": "🟡 Feature", "4": "🟢 Leaf"}.get(tier, f"Tier {tier}")
            print(f"    {tier_label}: {count} modules")

    if args.show_dependents and impact["direct_dependents"]:
        print("\n  Direct dependents:")
        for d in impact["direct_dependents"][:20]:
            print(f"    → {d}")
        if len(impact["direct_dependents"]) > 20:
            print(f"    ... and {len(impact['direct_dependents']) - 20} more")

    print(f"\n  Analysis reliable: {freshness['graph_fresh'] or tgt['target_freshness'] in ('fresh', 'probably_fresh')}")
    print(f"{'='*60}")


def cmd_freshness(args):
    """Check graph freshness for a repo."""
    freshness = check_freshness(args.repo)
    status_icon = {"fresh": "✅", "soft_stale": "⚠️", "hard_stale": "❌", "unknown": "❓"}.get(
        freshness["status"], "❓"
    )
    print(f"{status_icon} {args.repo}: {freshness['status']}")
    print(f"   Reason: {freshness['reason']}")
    if freshness.get("generated_at"):
        print(f"   Generated at: {freshness['generated_at']}")
    if freshness.get("generated_commit"):
        print(f"   Graph commit: {freshness['generated_commit'][:12]}")
    if freshness.get("current_commit"):
        print(f"   Current commit: {freshness['current_commit'][:12]}")
    if freshness.get("working_tree_dirty"):
        print("   Working tree: DIRTY")
        if freshness.get("changed_graph_relevant_files"):
            print(f"   Changed graph files ({len(freshness['changed_graph_relevant_files'])}):")
            for f in freshness["changed_graph_relevant_files"][:5]:
                print(f"     ⚠️  {f}")
            if len(freshness["changed_graph_relevant_files"]) > 5:
                print(f"     ... and {len(freshness['changed_graph_relevant_files']) - 5} more")


def cmd_list_repos(args):
    """List all repos with graphs."""
    repos = list_graph_repos()
    if not repos:
        print("No repos with graphs. Run 'graph build' first.")
        return
    print(f"{'Repo':<25} {'Nodes':>6} {'Edges':>6} {'Version':<8} {'Graph Commit':<14}")
    print("-" * 70)
    for r in repos:
        gc = (r.get("git_commit") or "N/A")[:12]
        dirty = " *" if r.get("working_tree_dirty") else ""
        print(f"{r['repo_name']:<25} {r.get('node_count', 0):>6} {r.get('edge_count', 0):>6} {r.get('graph_version', 'N/A'):<8} {gc:<14}{dirty}")
    print("\n* = working tree dirty")


def cmd_show_impact(args):
    """Show raw JSON impact data for a file."""
    impact = get_impact(args.repo, args.target, depth=args.depth)
    print(json.dumps(impact, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Multi-repo dependency graph impact analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo", default="baziforecaster", help="Repo name (default: baziforecaster)")
    parser.add_argument("--src", default="src", help="Source subdirectory (default: src)")
    parser.add_argument("--depth", type=int, default=2, help="Dependency traversal depth (default: 2)")

    sub = parser.add_subparsers(dest="command", help="Command")

    # graph build
    sub.add_parser("graph", help="Build/refresh graph").add_argument(
        "action", choices=["build", "refresh"], help="Action"
    )
    gbuild = sub.add_parser("graph-build", help="Build dependency graph (alias)")
    grefresh = sub.add_parser("graph-refresh", help="Rebuild dependency graph")
    grefresh.add_argument("--force", action="store_true", help="Force even if dirty")

    # analyze
    panalyze = sub.add_parser("analyze", help="Analyze impact of changing a file")
    panalyze.add_argument("--target", required=True, help="Target file path")
    panalyze.add_argument("--show-dependents", action="store_true", help="Show dependent list")

    # freshness
    sub.add_parser("freshness", help="Check graph freshness")

    # list-repos
    sub.add_parser("list-repos", help="List repos with graphs")

    # show-impact (raw JSON)
    pshow = sub.add_parser("show-impact", help="Show raw impact JSON")
    pshow.add_argument("--target", required=True, help="Target file path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Handle subcommand aliases
    if args.command == "graph":
        if hasattr(args, 'action'):
            if args.action == "build":
                cmd_graph_build(args)
            elif args.action == "refresh":
                cmd_graph_refresh(args)
    elif args.command == "graph-build":
        cmd_graph_build(args)
    elif args.command == "graph-refresh":
        if not hasattr(args, 'force'):
            args.force = False
        cmd_graph_refresh(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "freshness":
        cmd_freshness(args)
    elif args.command == "list-repos":
        cmd_list_repos(args)
    elif args.command == "show-impact":
        cmd_show_impact(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
