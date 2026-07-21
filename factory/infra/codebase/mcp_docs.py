"""
MCP Docs Server for baziforecaster — streamlined documentation search.

Tools exposed to the LLM:
  1. search_docs          - semantic vector search over indexed docs chunks
  2. read_file            - read any file in the repo by relative path
  3. list_files           - list all files under a directory (with extension filter)
  4. grep_docs            - literal text / regex search across the repo
  5. query_knowledge_graph - structured graph queries over doc knowledge graph
  6. get_doc_hierarchy    - return the documentation hierarchy/tree structure
  7. find_related_docs    - find all docs connected to an entity or topic
  8. remember_fact        - persist non-code knowledge across sessions
  9. recall_fact          - retrieve previously persisted facts
  10. list_facts          - list all currently persisted non-code facts
"""

import json
import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv
from fastmcp import FastMCP
from qdrant_client import QdrantClient

try:
    from mcp_watcher import run_preflight, start_embedded_watcher
except ImportError as e:
    import sys
    print(f"Failed to import mcp_watcher: {e}", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Ensure we prioritize control at .env by loading baziforecaster/.env explicitly
env_path = PROJECT_ROOT / "baziforecaster" / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# Suppress FastMCP informational logs to prevent JSON-RPC corruption on stdout
logging.basicConfig(level=logging.ERROR)
logging.getLogger("fastmcp").setLevel(logging.ERROR)

FACTS_PATH = PROJECT_ROOT / "infra" / "codebase" / "codebase_facts.json"

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
BGEM3_URL = os.getenv("BGEM3_URL", "http://localhost:8002/v1/embeddings")
BGEM3_TOKEN = os.getenv("BGEM3_TOKEN", "")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "baziforecaster_docs")

EXCLUDE_DIRS = {"__pycache__", ".git", ".venv", "node_modules", ".agent", ".gemini"}

mcp = FastMCP(os.getenv("MCP_NAME", "baziforecaster-docs"))


def _get_qdrant_client() -> QdrantClient | None:
    try:
        return QdrantClient(url=QDRANT_URL)
    except Exception:
        return None


def _resolve_secure_path(relative_path: str) -> Path:
    root = PROJECT_ROOT.resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Path escape detected: {relative_path}")
    return target


def _safe_relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _normalize_content(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


# ---------------------------------------------------------------------------
# Knowledge Graph Config
# ---------------------------------------------------------------------------

GRAPH_JSON = PROJECT_ROOT / "infra" / "graph" / "doc_knowledge_graph.json"
GRAPH_MMD = PROJECT_ROOT / "infra" / "graph" / "doc_knowledge_graph.mmd"
DIRTY_MARKER = PROJECT_ROOT / "infra" / "graph" / ".doc_graph_dirty"


def _graph_load() -> dict | None:
    """Load the knowledge graph from disk."""
    if not GRAPH_JSON.exists():
        return None
    try:
        return json.loads(GRAPH_JSON.read_text())
    except Exception:
        return None


def _safe_mermaid_id(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)[:32]


def _extract_headings(text: str) -> list[tuple[int, str, int]]:
    """Extract markdown headings as (level, text, line_number)."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^(#{1,6})\s+(.+)", line)
        if m:
            out.append((len(m.group(1)), m.group(2).strip(), i))
    return out


def _extract_references(content: str) -> list[tuple[str, str]]:
    """Extract markdown links and file paths from content."""
    refs = []
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", content):
        link = m.group(2)
        if link.endswith((".md", ".txt")):
            refs.append((link, m.group(1)))
    return refs


def _extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """Extract top keywords via word frequency."""
    stop = {
        "the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
        "to", "for", "of", "and", "or", "with", "by", "from", "as", "that",
        "this", "it", "be", "can", "will", "has", "have", "not", "but", "if",
        "then", "do", "does", "so", "up", "out", "also", "into", "all", "each",
        "every", "which", "what", "how", "when", "must", "use", "via", "than",
        "may", "make", "made", "one", "two", "many", "set", "get", "run",
        "call", "pass", "return", "value", "data", "file", "path", "name",
        "type", "function", "method", "class", "module", "system", "user",
        "input", "output", "result", "default", "option", "config",
    }
    words = re.findall(r"[a-z][a-z0-9_\-]{2,}", text.lower())
    freq: dict[str, int] = defaultdict(int)
    for w in words:
        if w not in stop and len(w) > 2:
            freq[w] += 1
    return sorted(freq, key=freq.get, reverse=True)[:top_n]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a < 1e-10 or mag_b < 1e-10:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Tool 1 — Semantic Search (docs only)
# ---------------------------------------------------------------------------


@mcp.tool()
def search_docs(
    query: Annotated[str, "Natural language query over documentation."],
    limit: Annotated[int, "Number of results to return (default 10, max 20)."] = 10,
) -> dict[str, Any]:
    """Semantic search over the indexed documentation using Qdrant."""
    qdrant = _get_qdrant_client()
    if not qdrant:
        return {
            "success": False,
            "message": "Qdrant client not configured or database currently locked.",
        }

    try:
        try:
            import httpx
            is_openai = "v1/embeddings" in BGEM3_URL
            payload = {"input": query} if is_openai else [query]
            headers = {"Authorization": f"Bearer {BGEM3_TOKEN}"} if BGEM3_TOKEN else {}
            resp = httpx.post(
                BGEM3_URL,
                json=payload,
                headers=headers,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                    query_vector = data["data"][0]["embedding"]
                else:
                    query_vector = data["embeddings"][0]
            else:
                query_vector = data[0]
        except Exception:
            return {
                "success": False,
                "message": "Search unavailable: BGEM3 unreachable.",
            }

        results = qdrant.query_points(
            collection_name=COLLECTION_NAME, query=query_vector, limit=limit, with_payload=True
        ).points

        matches = []
        for res in results:
            rel_path = res.payload.get("file_path", "unknown")
            content = res.payload.get("content", "")
            matches.append({"file_path": rel_path, "score": res.score, "snippet": content[:500]})

        if not matches:
            return {"success": True, "message": "No relevant docs found.", "data": {"results": []}}

        return {
            "success": True,
            "message": f"Found {len(matches)} relevant doc chunks.",
            "data": {"results": matches},
        }
    except Exception as e:
        return {"success": False, "message": f"Search failed: {str(e)}"}
    finally:
        if qdrant:
            qdrant.close()


# ---------------------------------------------------------------------------
# Tool 2 — Read File
# ---------------------------------------------------------------------------


@mcp.tool()
def read_file(
    relative_path: Annotated[str, "Path relative to project root."],
    start_line: Annotated[int | None, "First line to read (1-indexed)."] = None,
    end_line: Annotated[int | None, "Last line to read (inclusive)."] = None,
) -> dict[str, Any]:
    """Read a specific line range of a file in the repo."""
    try:
        path = _resolve_secure_path(relative_path)
        if not path.exists():
            return {"success": False, "message": f"File not found: {relative_path}"}

        content = _normalize_content(path.read_text(encoding="utf-8"))
        lines = content.splitlines()
        total_lines = len(lines)

        s = (start_line - 1) if start_line else 0
        e = end_line if end_line else total_lines
        paged = lines[s:e]

        return {
            "success": True,
            "message": f"Read lines {s + 1}-{min(e, total_lines)} from {relative_path}",
            "data": {
                "file_path": relative_path,
                "total_lines": total_lines,
                "start_line": s + 1,
                "end_line": min(e, total_lines),
                "is_truncated": e < total_lines,
                "content": "\n".join(paged),
            },
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to read {relative_path}: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 3 — List Files
# ---------------------------------------------------------------------------


@mcp.tool()
def list_files(
    directory: Annotated[str, "Relative path to directory (empty = project root)."] = "",
    extension_filter: Annotated[str | None, "Only return files with this extension, e.g. '.md'."] = None,
    recursive: Annotated[bool, "Whether to recurse into subdirectories (default True)."] = True,
    limit: Annotated[int, "Maximum number of files to return (default 500)."] = 500,
    offset: Annotated[int, "Number of files to skip for pagination."] = 0,
) -> dict[str, Any]:
    """List files in a repo directory with pagination."""
    try:
        base = PROJECT_ROOT / directory
        if not base.exists():
            return {
                "success": False,
                "message": f"Directory not found: {directory}",
            }

        all_found: list[str] = []
        walker = os.walk(base) if recursive else [(str(base), [], os.listdir(base))]

        for root, dirs, files in walker:
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in sorted(files):
                fp = Path(root) / f
                if extension_filter:
                    if fp.suffix != extension_filter:
                        continue
                all_found.append(_safe_relative(fp))

        all_found.sort()
        total_count = len(all_found)
        paged = all_found[offset : offset + limit]

        return {
            "success": True,
            "message": f"Found {total_count} files in {directory or 'root'}",
            "data": {
                "files": paged,
                "metadata": {
                    "total": total_count,
                    "returned": len(paged),
                    "offset": offset,
                    "limit": limit,
                    "is_truncated": (offset + limit) < total_count,
                },
            },
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to list files in {directory}: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 4 — Grep Docs
# ---------------------------------------------------------------------------


@mcp.tool()
def grep_docs(
    pattern: Annotated[str, "Text or regex to search for."],
    directory: Annotated[str, "Limit search to this subdirectory (empty = whole repo)."] = "",
    extension_filter: Annotated[str | None, "Only search files with this extension, e.g. '.md'."] = None,
    case_sensitive: Annotated[bool, "Default False."] = False,
    max_results: Annotated[int, "Cap results (default 50)."] = 50,
) -> dict[str, Any]:
    """Search for a literal string or regex pattern across the repo."""
    try:
        base = PROJECT_ROOT / directory
        results = []
        flags = 0 if case_sensitive else re.IGNORECASE

        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                fp = Path(root) / f
                if extension_filter and fp.suffix != extension_filter:
                    continue

                try:
                    content = _normalize_content(fp.read_text(encoding="utf-8"))
                    for i, line in enumerate(content.splitlines()):
                        if re.search(pattern, line, flags):
                            results.append({"file_path": _safe_relative(fp), "line": i + 1, "text": line.strip()})
                            if len(results) >= max_results:
                                return {
                                    "success": True,
                                    "message": f"Found max {max_results} results",
                                    "data": {"results": results},
                                }
                except Exception:
                    continue

        return {"success": True, "message": f"Found {len(results)} results", "data": {"results": results}}
    except Exception as e:
        return {"success": False, "message": f"Grep failed: {str(e)}"}


# ---------------------------------------------------------------------------
# Facts Persistence (shared with code server)
# ---------------------------------------------------------------------------


def _load_facts() -> dict[str, str]:
    if not FACTS_PATH.exists():
        return {}
    return json.loads(FACTS_PATH.read_text(encoding="utf-8"))


def _save_facts(facts: dict[str, str]) -> None:
    FACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_path = FACTS_PATH.with_suffix(".tmp")
    atomic_path.write_text(json.dumps(facts, indent=2), encoding="utf-8")
    atomic_path.replace(FACTS_PATH)


@mcp.tool()
def remember_fact(key: str, value: str) -> str:
    """Persist non-code knowledge across sessions."""
    facts = _load_facts()
    facts[key] = value
    _save_facts(facts)
    return f"Fact remembered: {key}"


@mcp.tool()
def recall_fact(key: str) -> str:
    """Retrieve a previously persisted fact."""
    facts = _load_facts()
    return facts.get(key, "Fact not found.")


@mcp.tool()
def list_facts() -> list[str]:
    """List all currently persisted non-code facts."""
    return list(_load_facts().keys())


# ---------------------------------------------------------------------------
# Tool 8 — Query Knowledge Graph
# ---------------------------------------------------------------------------


@mcp.tool()
def query_knowledge_graph(
    query: Annotated[str, "Natural language query over the docs knowledge graph."],
    max_entities: Annotated[int, "Max entities to return (default 10)."] = 10,
) -> dict[str, Any]:
    """Query the docs knowledge graph for structured entity/relationship results.

    Falls back to vector search if the graph hasn't been built yet.
    """
    graph = _graph_load()
    if graph is None:
        return {
            "success": False,
            "message": "Knowledge graph not found. Run 'doc_graph.py --build' first to generate doc_knowledge_graph.json.",
            "data": {},
        }

    query_lower = query.lower()

    # --- Entity search: find entities whose name/description matches ---
    matched_entities = []
    seen_entities = set()
    for ent in graph.get("entities", []):
        name_lower = ent["name"].lower()
        desc_lower = ent.get("description", "").lower()
        if query_lower in name_lower or query_lower in desc_lower:
            key = ent["id"]
            if key not in seen_entities:
                seen_entities.add(key)
                matched_entities.append(ent)
        elif any(qw in name_lower for qw in query_lower.split()):
            key = ent["id"]
            if key not in seen_entities:
                seen_entities.add(key)
                matched_entities.append(ent)

    matched_entities = matched_entities[:max_entities]

    # --- Relationship traversal: find relationships involving matched entities ---
    matched_names = {e["name"].lower() for e in matched_entities}
    related_rels = []
    for rel in graph.get("relationships", []):
        src_low = rel["source"].lower()
        tgt_low = rel["target"].lower()
        if src_low in matched_names or tgt_low in matched_names:
            related_rels.append(rel)

    # --- Keyword fallback: if no entity match, find entities by keyword overlap ---
    if not matched_entities:
        query_keywords = set(re.findall(r"[a-z][a-z0-9_\-]{2,}", query_lower))
        for ent in graph.get("entities", []):
            name_words = set(re.findall(r"[a-z][a-z0-9_\-]{2,}", ent["name"].lower()))
            overlap = query_keywords & name_words
            if overlap:
                key = ent["id"]
                if key not in seen_entities:
                    seen_entities.add(key)
                    matched_entities.append(ent)

    return {
        "success": True,
        "message": f"Found {len(matched_entities)} entities and {len(related_rels)} relationships.",
        "data": {
            "entities": matched_entities,
            "relationships": related_rels[:50],
        },
    }


# ---------------------------------------------------------------------------
# Tool 9 — Documentation Hierarchy
# ---------------------------------------------------------------------------


@mcp.tool()
def get_doc_hierarchy() -> dict[str, Any]:
    """Return the documentation hierarchy/tree structure from the knowledge graph.

    If the full graph isn't available, returns the directory tree instead.
    """
    graph = _graph_load()
    if graph and graph.get("hierarchy"):
        return {
            "success": True,
            "message": "Documentation hierarchy from knowledge graph.",
            "data": {"hierarchy": graph["hierarchy"]},
        }

    # Fallback: build directory tree from filesystem
    docs_root = PROJECT_ROOT / "baziforecaster" / "_docs"
    if not docs_root.exists():
        return {
            "success": False,
            "message": "Knowledge graph not built and _docs directory not found.",
            "data": {},
        }

    def _build_tree(directory: Path, depth: int = 0, max_depth: int = 5) -> dict:
        if depth > max_depth:
            return {"name": directory.name, "type": "directory", "truncated": True}
        result = {"name": directory.name, "type": "directory", "children": []}
        try:
            for item in sorted(directory.iterdir()):
                if item.is_dir() and item.name not in EXCLUDE_DIRS:
                    result["children"].append(_build_tree(item, depth + 1, max_depth))
                elif item.is_file() and item.suffix in (".md", ".txt"):
                    result["children"].append({"name": item.name, "type": "file"})
        except PermissionError:
            pass
        return result

    tree = _build_tree(docs_root)
    return {
        "success": True,
        "message": "Directory-based hierarchy (graph not built yet). Run doc_graph.py --build for richer structure.",
        "data": {"hierarchy": tree},
    }


# ---------------------------------------------------------------------------
# Tool 10 — Find Related Docs
# ---------------------------------------------------------------------------


@mcp.tool()
def find_related_docs(
    entity_or_topic: Annotated[str, "Entity name or topic to find related documentation for."],
    max_results: Annotated[int, "Maximum number of related docs to return (default 10)."] = 10,
) -> dict[str, Any]:
    """Find all documentation files related to a given entity or topic via graph traversal.

    If the graph isn't built yet, falls back to keyword search in filenames.
    """
    graph = _graph_load()
    if graph:
        entity_lower = entity_or_topic.lower()

        # Step 1: Find matching entities
        matched_entities = []
        for ent in graph.get("entities", []):
            name_low = ent["name"].lower()
            desc_low = ent.get("description", "").lower()
            if entity_lower in name_low or entity_lower in desc_low:
                matched_entities.append(ent)
            elif any(w in name_low for w in entity_lower.split()):
                matched_entities.append(ent)

        # Step 2: Traverse relationships to find connected docs
        connected_files: dict[str, list[str]] = {}  # file_path -> [reasons]
        for ent in matched_entities:
            src_name = ent["name"].lower()
            for rel in graph.get("relationships", []):
                src_low = rel["source"].lower()
                tgt_low = rel["target"].lower()
                rel_type = rel.get("rel_type", "")

                if src_low == src_name or tgt_low == src_name:
                    other = rel["target"] if src_low == src_name else rel["source"]
                    if other.lower() != src_name:
                        connected_files.setdefault(other, []).append(f"{rel_type} (via {ent['name']})")

        # Step 3: Also check entity source docs
        for ent in matched_entities:
            for doc in ent.get("source_docs", []):
                connected_files.setdefault(doc, []).append(f"entity definition ({ent['name']})")

        results = []
        for filepath, reasons in list(connected_files.items())[:max_results]:
            results.append({"file_path": filepath, "reasons": reasons})

        # Step 4: Also find by keyword overlap among graph entities
        if not results:
            topic_keywords = set(re.findall(r"[a-z][a-z0-9_\-]{2,}", entity_lower))
            for ent in graph.get("entities", []):
                name_words = set(re.findall(r"[a-z][a-z0-9_\-]{2,}", ent["name"].lower()))
                if topic_keywords & name_words:
                    for doc in ent.get("source_docs", []):
                        connected_files.setdefault(doc, []).append(f"keyword match ({ent['name']})")
            results = [{"file_path": fp, "reasons": reasons} for fp, reasons in list(connected_files.items())[:max_results]]

        if results:
            return {
                "success": True,
                "message": f"Found {len(results)} related documents for '{entity_or_topic}'.",
                "data": {"results": results},
            }

    # Fallback: grep for the topic in filenames and file content
    fallback_results = []
    entity_words = entity_or_topic.lower().split()
    docs_root = PROJECT_ROOT / "baziforecaster" / "_docs"
    if docs_root.exists():
        for root, dirs, files in os.walk(docs_root):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                if f.endswith((".md", ".txt")):
                    fp = Path(root) / f
                    rel = _safe_relative(fp)
                    score = sum(1 for w in entity_words if w in fp.stem.lower() or w in f.lower())
                    if score > 0:
                        fallback_results.append({"file_path": rel, "match_score": score})
        fallback_results.sort(key=lambda x: x["match_score"], reverse=True)

    return {
        "success": True,
        "message": f"Found {len(fallback_results)} related docs (filename-based, graph not built). Run doc_graph.py --build for graph traversal.",
        "data": {"results": fallback_results[:max_results]},
    }


if __name__ == "__main__":
    if not run_preflight(["baziforecaster_docs", "baziforecaster_code"], "docs"):
        sys.exit(1)
    start_embedded_watcher(scope="docs", run_graph_build=False)

    mcp.run()
