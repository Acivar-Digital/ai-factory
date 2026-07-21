"""
doc_graph.py — Knowledge Graph Builder for baziforecaster_docs

Reads doc chunks from the baziforecaster_docs Qdrant collection,
extracts entities, relationships, and hierarchies using:
  - BGEM3 (fastembed) for semantic similarity
  - Markdown heading structure for hierarchy
  - Inline references / markdown links for cross-doc relationships

Outputs:
  - doc_knowledge_graph.json  (structured graph)

CLI:
  uv run doc_graph.py --build     rebuild the graph
  uv run doc_graph.py --dirty     mark the graph as stale
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DEFAULT_COLLECTION = "baziforecaster_docs"

_factory_root = str(Path(__file__).resolve().parents[3])
if _factory_root not in sys.path:
    sys.path.insert(0, _factory_root)

from factory.infra.models import to_relative_path  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GRAPH_DIR = PROJECT_ROOT / "infra" / "graph"

def get_graph_paths(collection: str):
    """Return (json_path, dirty_path) for a collection."""
    if collection == DEFAULT_COLLECTION:
        return GRAPH_DIR / "doc_knowledge_graph.json", GRAPH_DIR / ".doc_graph_dirty"
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
class HierarchyNode:
    name: str
    type: str = "section"  # section | file | heading
    children: dict[str, "HierarchyNode"] = field(default_factory=dict)
    content_hash: str = ""


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


def _extract_headings(content: str) -> list[tuple[int, str, int]]:
    """Extract markdown headings as (level, text, line_number)."""
    headings = []
    for i, line in enumerate(content.splitlines(), 1):
        m = re.match(r"^(#{1,6})\s+(.+)", line)
        if m:
            headings.append((len(m.group(1)), m.group(2).strip(), i))
    return headings


def _extract_references(content: str, base_path: str) -> list[tuple[str, str]]:
    """Extract markdown links and file references as (target, context_text)."""
    base_path = to_relative_path(base_path)
    refs = []
    # Markdown links: [text](path)
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+\.(?:md|txt|html))\)", content):
        refs.append((m.group(2), m.group(1)))
    # Inline code references to files/modules
    for m in re.finditer(r"`([^`]+(?:\.py|\.json|\.yaml|\.yml|\.toml|\.sh|\.ts|\.md))`", content):
        refs.append((m.group(1), "code reference"))
    # Plain mention of doc files
    for m in re.finditer(r"(?:see|ref|in)\s+([\w\-]+\.md)", content, re.IGNORECASE):
        refs.append((m.group(1), "mentioned"))
    return refs


def _extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """Simple keyword extraction via word frequency (no external NLP needed)."""
    stop = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
            "for", "of", "and", "or", "with", "by", "from", "as", "that", "this",
            "it", "be", "can", "will", "has", "have", "not", "but", "if", "then",
            "do", "does", "did", "so", "up", "out", "also", "into", "its", "all",
            "each", "every", "which", "what", "how", "when", "where", "who", "why",
            "may", "use", "used", "using", "via", "than", "more", "most", "such",
            "only", "other", "some", "any", "both", "same", "new", "old", "first",
            "last", "next", "must", "should", "need", "like", "way", "make", "made",
            "two", "one", "many", "set", "get", "run", "call", "pass", "return",
            "value", "data", "file", "path", "name", "type", "function", "method",
            "class", "module", "system", "user", "input", "output", "result",
            "default", "option", "config", "setting", "parameter", "argument",
            "string", "number", "list", "dict", "array", "object", "key", "index"}
    words = re.findall(r"[a-z][a-z0-9_\-]{2,}", text.lower())
    freq: dict[str, int] = defaultdict(int)
    for w in words:
        if w not in stop and len(w) > 2:
            freq[w] += 1
    return sorted(freq, key=freq.get, reverse=True)[:top_n]


def _extract_entities_from_content(content: str, file_path: str) -> list[Entity]:
    """Extract entities from a doc chunk using heading structure and keywords."""
    file_path = to_relative_path(file_path)
    entities = []
    headings = _extract_headings(content)
    keywords = _extract_keywords(content, top_n=15)

    # Headings as entities (major concepts / sections)
    for level, text, line_no in headings:
        if level <= 3:  # H1-H3 are significant section headers
            clean = re.sub(r"[^\w\s]", "", text).strip()
            if len(clean) > 3:
                entities.append(Entity(
                    id=f"{hashlib.md5(f'{file_path}:{text}'.encode()).hexdigest()[:8]}",
                    name=clean,
                    type="concept" if level >= 2 else "module",
                    description=f"Section in {file_path} (line {line_no})",
                    source_docs=[file_path],
                ))

    # Top keywords as concept entities
    for kw in keywords[:6]:
        entities.append(Entity(
            id=f"{hashlib.md5(f'{file_path}:kw:{kw}'.encode()).hexdigest()[:8]}",
            name=kw,
            type="concept",
            description=f"Key topic in {file_path}",
            source_docs=[file_path],
        ))

    return entities


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a < 1e-10 or mag_b < 1e-10:
        return 0.0
    return dot / (mag_a * mag_b)


def _extract_by_similarity(
    chunks: list[dict[str, Any]], threshold: float = 0.75
) -> list[tuple[str, str, float, str]]:
    """Find highly similar file pairs that likely describe the same topic using composite embeddings."""
    # Group normalized embeddings by file path
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

    # Compute average embedding per file
    file_avg: dict[str, list[float]] = {}
    for fp, vecs in file_embeddings.items():
        n = len(vecs)
        dim = len(vecs[0])
        avg = [sum(v[d] for v in vecs) / n for d in range(dim)]
        mag = sum(x * x for x in avg) ** 0.5
        if mag > 1e-10:
            file_avg[fp] = [x / mag for x in avg]

    # Compare unique file pairs
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
    """Main orchestrator: read Qdrant, extract, build graph."""
    print(f"[Graph] Connecting to Qdrant at {QDRANT_URL}...")
    client = QdrantClient(url=QDRANT_URL)

    collections = [c.name for c in client.get_collections().collections]
    if collection_name not in collections:
        print(f"[Graph] Collection '{collection_name}' not found. Run the indexer first.")
        sys.exit(1)

    # Scroll all points from the docs collection
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

    print(f"[Graph] Loaded {len(chunks)} doc chunks. Extracting...")

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
        content = chunk["payload"].get("content", "")
        file_path = to_relative_path(chunk["payload"].get("file_path", ""))

        if not content:
            continue

        entities = _extract_entities_from_content(content, file_path)
        for ent in entities:
            key = f"{ent.name}:{ent.type}"
            if key in all_entities:
                if file_path not in all_entities[key].source_docs:
                    all_entities[key].source_docs.append(file_path)
            else:
                all_entities[key] = ent

        # Intra-file relationships from heading hierarchy
        headings = _extract_headings(content)
        for i, (lvl, text, _) in enumerate(headings):
            if i > 0:
                prev_lvl, prev_text = headings[i - 1][0], headings[i - 1][1]
                if lvl > prev_lvl:
                    rel = Relationship(
                        source=re.sub(r"[^\w\s]", "", prev_text).strip(),
                        target=re.sub(r"[^\w\s]", "", text).strip(),
                        rel_type="contained_in",
                        confidence=0.9,
                        evidence=f"hierarchy in {file_path}",
                    )
                    all_relationships.append(rel)

        # Extract cross-references
        refs = _extract_references(content, file_path)
        for target, ctx in refs:
            rel = Relationship(
                source=file_path,
                target=target,
                rel_type="references",
                confidence=0.8,
                evidence=ctx,
            )
            all_relationships.append(rel)

    # --- Phase 2: Cross-chunk similarity ---
    print("[Graph] Computing chunk similarity...")
    similar_pairs = _extract_by_similarity(chunks, threshold=0.78)
    for src, tgt, score, evidence in similar_pairs:
        rel = Relationship(
            source=src,
            target=tgt,
            rel_type="related_to",
            confidence=round(score, 2),
            evidence=evidence,
        )
        # Avoid duplicates
        dup = any(
            r.source == src and r.target == tgt and r.rel_type == "related_to"
            for r in all_relationships
        )
        if not dup:
            all_relationships.append(rel)

    # --- Phase 3: Build hierarchy from directory structure ---
    print("[Graph] Building directory hierarchy...")
    hierarchy_root: dict[str, Any] = {"name": "baziforecaster/_docs", "type": "root", "children": {}}
    for chunk in chunks:
        fp = to_relative_path(chunk["payload"].get("file_path", ""))
        if not fp:
            continue
        parts = Path(fp).parts
        node = hierarchy_root
        for part in parts:
            if part not in node.get("children", {}):
                node["children"][part] = {"name": part, "type": "file" if part.endswith((".md", ".txt")) else "directory", "children": {}}
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
    parser = argparse.ArgumentParser(description="Docs knowledge graph builder")
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
