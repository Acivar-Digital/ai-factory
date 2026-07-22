#!/usr/bin/env python3
"""Self-contained CLI wrapper for query_knowledge_graph.

Uses only factory/tools/_codebase_common (no libcst / qdrant_client dependency),
so it works even when those packages are missing. Returns exit 0 with empty
results for missing graph files (greenfield support — Option B Fail Loudly).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from _codebase_common import ok, resolve_repo_path

GRAPH_JSON_REL = "temp/graph/code_knowledge_graph.json"


def _load_graph() -> dict | None:
    """Load the knowledge graph from disk; None if file missing / corrupt."""
    path = resolve_repo_path(GRAPH_JSON_REL)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _keyword_match(query: str, entities: list[dict], max_entities: int) -> list[dict]:
    """Simple keyword-overlap fallback (no BGEM3 / numpy dependency)."""
    if not entities:
        return []
    query_lower = query.lower()
    query_terms = set(query_lower.split())
    scored: list[tuple[int, dict]] = []
    for ent in entities:
        ent_text = json.dumps(ent, ensure_ascii=False).lower()
        ent_terms = set(ent_text.split())
        overlap = len(query_terms & ent_terms)
        if overlap > 0:
            scored.append((overlap, ent))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [ent for _, ent in scored[:max_entities]]


def query_knowledge_graph(query: str, max_entities: int = 10) -> dict:
    """Query the code knowledge graph. Always exits 0; real crashes propagate."""
    graph = _load_graph()
    if graph is None:
        # Greenfield: no graph yet — return empty, NOT an error (Option B).
        return ok(
            "Knowledge graph file not found (greenfield — empty result).",
            {"entities": [], "relationships": []},
        )

    entities = graph.get("entities", [])
    if not entities:
        return ok(
            "Graph has no entities.",
            {"entities": [], "relationships": []},
        )

    matched = _keyword_match(query, entities, max_entities)
    matched_names = {str(e.get("name", "")).lower() for e in matched}
    related_rels: list[dict] = []
    for rel in graph.get("relationships", []):
        src = str(rel.get("source", "")).lower()
        tgt = str(rel.get("target", "")).lower()
        if src in matched_names or tgt in matched_names:
            related_rels.append(rel)

    return ok(
        f"Found {len(matched)} entities and {len(related_rels)} relationships.",
        {
            "entities": matched,
            "relationships": related_rels[: max_entities * 5],
        },
    )


def main():
    parser = argparse.ArgumentParser(description="CLI wrapper for query_knowledge_graph")
    parser.add_argument("query", help="Natural language query")
    parser.add_argument(
        "--max-entities",
        type=int,
        default=10,
        help="Max entities to return (default 10)",
    )
    args = parser.parse_args()

    result = query_knowledge_graph(args.query, max_entities=args.max_entities)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
