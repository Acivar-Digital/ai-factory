"""
code_graph.py — Knowledge Graph Builder for baziforecaster_code

Reads code chunks from the baziforecaster_code Qdrant collection,
extracts entities, relationships, and hierarchies using:
  - AST annotations (chunk_type: class_def, function_def, module_imports)
  - Semantic similarity using file-level composite embeddings
  - Directory structures for architectural hierarchy

Outputs:
  - code_knowledge_graph.json  (structured graph)

CLI:
  uv run code_graph.py --build     rebuild the graph
  uv run code_graph.py --dirty     mark the graph as stale
"""

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DEFAULT_COLLECTION = "baziforecaster_code"

_factory_root = str(Path(__file__).resolve().parents[3])
if _factory_root not in sys.path:
    sys.path.insert(0, _factory_root)

from factory.infra.models import to_relative_path  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GRAPH_DIR = PROJECT_ROOT / "infra" / "graph"

def get_graph_paths(collection: str):
    """Return (json_path, dirty_path) for a collection."""
    if collection == DEFAULT_COLLECTION:
        return GRAPH_DIR / "code_knowledge_graph.json", GRAPH_DIR / ".code_graph_dirty"
    return GRAPH_DIR / f"{collection}_knowledge_graph.json", GRAPH_DIR / f".{collection}_graph_dirty"

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class Entity:
    id: str
    name: str
    type: str  # component | concept | person | system | module | feature | api
    description: str
    source_docs: list[str] = field(default_factory=list)


@dataclass
class Relationship:
    source: str
    target: str
    rel_type: str  # depends_on | implements | describes | uses | part_of
                   # references | related_to | supersedes | contained_in
    confidence: float = 0.0
    evidence: str = ""


@dataclass
class KnowledgeGraph:
    version: str = "1.0"
    entities: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    hierarchy: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Extraction Helpers
# ---------------------------------------------------------------------------


def _extract_entities_from_chunk(chunk: dict[str, Any]) -> list[Entity]:
    """Extract code entities (classes, functions, modules) based on chunk_type."""
    entities = []
    payload = chunk.get("payload", {})
    content = payload.get("content", "")
    file_path = to_relative_path(payload.get("file_path", ""))
    chunk_type = payload.get("chunk_type", "")

    if not content or not file_path:
        return entities

    # Always represent the file itself as an entity
    clean_fp = Path(file_path).name
    entities.append(Entity(
        id=f"{hashlib.md5(f'file:{file_path}'.encode()).hexdigest()[:8]}",
        name=clean_fp,
        type="component",
        description=f"Source file: {file_path}",
        source_docs=[file_path],
    ))

    if chunk_type == "class_def":
        m = re.search(r"class\s+(\w+)", content)
        if m:
            cname = m.group(1)
            entities.append(Entity(
                id=f"{hashlib.md5(f'{file_path}:class:{cname}'.encode()).hexdigest()[:8]}",
                name=cname,
                type="component",
                description=f"Class defined in {file_path}",
                source_docs=[file_path],
            ))
    elif chunk_type == "function_def":
        m = re.search(r"def\s+(\w+)", content)
        if m:
            fname = m.group(1)
            entities.append(Entity(
                id=f"{hashlib.md5(f'{file_path}:func:{fname}'.encode()).hexdigest()[:8]}",
                name=fname,
                type="api",
                description=f"Function defined in {file_path}",
                source_docs=[file_path],
            ))
    elif chunk_type == "module_imports":
        for m in re.finditer(r"(?:import|from)\s+([a-zA-Z0-9_\.]+)", content):
            mod = m.group(1).split(".")[0]
            if len(mod) > 2:
                entities.append(Entity(
                    id=f"{hashlib.md5(f'mod:{mod}'.encode()).hexdigest()[:8]}",
                    name=mod,
                    type="module",
                    description="Imported module",
                    source_docs=[file_path],
                ))

    return entities


def _extract_relationships_from_chunk(chunk: dict[str, Any]) -> list[Relationship]:
    """Extract intra-file and dependency relationships."""
    rels = []
    payload = chunk.get("payload", {})
    content = payload.get("content", "")
    file_path = to_relative_path(payload.get("file_path", ""))
    chunk_type = payload.get("chunk_type", "")

    if not content or not file_path:
        return rels

    clean_fp = Path(file_path).name

    if chunk_type == "class_def":
        m = re.search(r"class\s+(\w+)", content)
        if m:
            cname = m.group(1)
            rels.append(Relationship(
                source=cname,
                target=clean_fp,
                rel_type="contained_in",
                confidence=1.0,
                evidence=f"Class definition in {file_path}",
            ))
    elif chunk_type == "function_def":
        m = re.search(r"def\s+(\w+)", content)
        if m:
            fname = m.group(1)
            rels.append(Relationship(
                source=fname,
                target=clean_fp,
                rel_type="contained_in",
                confidence=1.0,
                evidence=f"Function definition in {file_path}",
            ))
    elif chunk_type == "module_imports":
        for m in re.finditer(r"(?:import|from)\s+([a-zA-Z0-9_\.]+)", content):
            mod = m.group(1).split(".")[0]
            if len(mod) > 2:
                rels.append(Relationship(
                    source=clean_fp,
                    target=mod,
                    rel_type="depends_on",
                    confidence=0.9,
                    evidence=f"Import statement in {file_path}",
                ))

    return rels


def _extract_by_similarity(
    chunks: list[dict[str, Any]], threshold: float = 0.75
) -> list[tuple[str, str, float, str]]:
    """Find highly similar file pairs that likely describe related logic using composite embeddings."""
    file_embeddings: dict[str, list[list[float]]] = {}
    for chunk in chunks:
        fp = to_relative_path(chunk["payload"].get("file_path", ""))
        vec = chunk.get("embedding", [])
        if not fp or not vec:
            continue
        mag = sum(x * x for x in vec) ** 0.5
        if mag > 1e-10:
            norm_vec = [x / mag for x in vec]
            file_embeddings.setdefault(fp, []).append(norm_vec)

    file_avg: dict[str, list[float]] = {}
    for fp, vecs in file_embeddings.items():
        n = len(vecs)
        dim = len(vecs[0])
        avg = [sum(v[d] for v in vecs) / n for d in range(dim)]
        mag = sum(x * x for x in avg) ** 0.5
        if mag > 1e-10:
            file_avg[fp] = [x / mag for x in avg]

    files = list(file_avg.keys())
    pairs = []
    for i in range(len(files)):
        fp_a = files[i]
        vec_a = file_avg[fp_a]
        for j in range(i + 1, len(files)):
            fp_b = files[j]
            vec_b = file_avg[fp_b]
            sim = sum(x * y for x, y in zip(vec_a, vec_b))
            if sim >= threshold:
                pairs.append((
                    fp_a,
                    fp_b,
                    sim,
                    f"composite semantic similarity {sim:.2f}",
                ))
    return pairs


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------


def build_graph(collection_name: str) -> KnowledgeGraph:
    """Main orchestrator: read Qdrant, extract, build code graph."""
    print(f"[Graph] Connecting to Qdrant at {QDRANT_URL}...")
    client = QdrantClient(url=QDRANT_URL)

    collections = [c.name for c in client.get_collections().collections]
    if collection_name not in collections:
        print(f"[Graph] Collection '{collection_name}' not found. Run the indexer first.")
        sys.exit(1)

    print(f"[Graph] Reading all points from '{collection_name}'...")
    offset = None
    chunks: list[dict[str, Any]] = []
    while True:
        res, next_offset = client.scroll(
            collection_name=collection_name,
            limit=1000,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        for pt in res:
            payload = pt.payload or {}
            chunks.append({
                "id": pt.id,
                "payload": payload,
                "embedding": pt.vector if pt.vector else [],
            })
        offset = next_offset
        if offset is None:
            break

    print(f"[Graph] Loaded {len(chunks)} code chunks. Extracting...")

    graph = KnowledgeGraph(
        metadata={
            "source_collection": collection_name,
            "chunk_count": len(chunks),
        }
    )

    all_entities: dict[str, Entity] = {}
    all_relationships: list[Relationship] = []

    # --- Phase 1: Per-chunk extraction ---
    for chunk in chunks:
        raw_fp = chunk["payload"].get("file_path", "")
        if not raw_fp:
            continue
        file_path = to_relative_path(raw_fp)
        if not file_path:
            continue

        entities = _extract_entities_from_chunk(chunk)
        for ent in entities:
            key = f"{ent.name}:{ent.type}"
            if key in all_entities:
                if file_path not in all_entities[key].source_docs:
                    all_entities[key].source_docs.append(file_path)
            else:
                all_entities[key] = ent

        rels = _extract_relationships_from_chunk(chunk)
        all_relationships.extend(rels)

    # --- Phase 2: Cross-chunk similarity ---
    print("[Graph] Computing code chunk similarity...")
    similar_pairs = _extract_by_similarity(chunks, threshold=0.78)
    for src, tgt, score, evidence in similar_pairs:
        rel = Relationship(
            source=src,
            target=tgt,
            rel_type="related_to",
            confidence=round(score, 2),
            evidence=evidence,
        )
        dup = any(
            r.source == src and r.target == tgt and r.rel_type == "related_to"
            for r in all_relationships
        )
        if not dup:
            all_relationships.append(rel)

    # --- Phase 3: Build hierarchy from directory structure ---
    print("[Graph] Building directory hierarchy...")
    hierarchy_root: dict[str, Any] = {"name": "baziforecaster/_code", "type": "root", "children": {}}
    for chunk in chunks:
        fp = to_relative_path(chunk["payload"].get("file_path", ""))
        if not fp:
            continue
        parts = Path(fp).parts
        node = hierarchy_root
        for part in parts:
            if part not in node.get("children", {}):
                node["children"][part] = {"name": part, "type": "file" if "." in part else "directory", "children": {}}
            node = node["children"][part]

    # --- Assemble ---
    graph.entities = [asdict(e) for e in all_entities.values()]
    graph.relationships = [asdict(r) for r in all_relationships]
    graph.hierarchy = hierarchy_root

    # Deduplicate relationships
    seen = set()
    deduped = []
    for r in graph.relationships:
        key = (r["source"], r["target"], r["rel_type"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    graph.relationships = deduped

    print(f"[Graph] Done: {len(graph.entities)} entities, {len(graph.relationships)} relationships")

    client.close()
    return graph


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def save_graph(graph: KnowledgeGraph, output_path: Path) -> None:
    """Save graph as JSON."""
    data = asdict(graph)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(output_path, json.dumps(data, indent=2, ensure_ascii=False))
    print(f"[Graph] Saved JSON → {output_path}")


def _atomic_write(path: Path, content: str) -> None:
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Code knowledge graph builder")
    parser.add_argument("--collection", type=str, default=DEFAULT_COLLECTION, help=f"Qdrant collection (default: {DEFAULT_COLLECTION})")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--build", action="store_true", help="Rebuild the graph from Qdrant")
    group.add_argument("--dirty", action="store_true", help="Mark the graph as dirty/stale")
    args = parser.parse_args()

    graph_json, dirty_marker = get_graph_paths(args.collection)

    if args.dirty:
        dirty_marker.parent.mkdir(parents=True, exist_ok=True)
        dirty_marker.touch()
        print(f"[Graph] Dirty flag set for {args.collection}. Run --build to regenerate.")
        return

    if args.build:
        graph = build_graph(args.collection)
        save_graph(graph, graph_json)
        if dirty_marker.exists():
            dirty_marker.unlink()
        print(f"[Graph] Build complete for {args.collection}.")
        return


if __name__ == "__main__":
    main()
