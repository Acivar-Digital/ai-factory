
# Read the main file
src_path = '/home/yapilwsl/arthityap/infra/codebase/mcp_codebase.py'
with open(src_path, 'r') as f:
    content = f.read()

additions = '''
# ============================================================================
# ADDED TOOLS - Index Repository, Delete Collection, Get Stats
# ============================================================================

@mcp.tool()
def index_repository(
    repo_name: Annotated[str, "Repository folder name under PROJECT_ROOT"],
    reset: Annotated[bool, "Drop and recreate collection"] = False,
    collection_name: Annotated[Optional[str], "Custom collection name"] = None,
) -\u003e Dict[str, Any]:
    """Index a repository into a Qdrant collection via BGEM3 embeddings."""
    collection = collection_name or repo_name
    hash_cache_path = PROJECT_ROOT / "infra" / "codebase" / f".file_hashes_{collection}.json"
    include_dirs = [f"{repo_name}/{d}" for d in STANDARD_DIRS]

    async def _run_index():
        from indexer_local import embed_with_retry as emb_fn
        client = _get_qdrant_client()
        existing = [c.name for c in client.get_collections().collections]
        if reset and collection in existing:
            client.delete_collection(collection)
            existing = []
            try:
                hash_cache_path.unlink()
            except:
                pass
        if collection not in existing:
            client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
        hash_cache = {}
        if hash_cache_path.exists():
            try:
                hash_cache = json.loads(hash_cache_path.read_text())
            except Exception:
                pass
        all_chunks = []
        files_to_delete = []
        new_hashes = {}
        for inc in include_dirs:
            dir_path = PROJECT_ROOT / inc
            if not dir_path.exists():
                continue
            for root, dirs, files in os.walk(dir_path):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for fname in files:
                    fp = Path(root) / fname
                    if fp.suffix not in INCLUDE_EXTENSIONS:
                        continue
                    try:
                        rel = str(fp.resolve().relative_to(PROJECT_ROOT))
                        cont = fp.read_text(encoding="utf-8")
                        h = hashlib.md5(cont.encode()).hexdigest()
                    except Exception:
                        continue
                    if hash_cache.get(rel) == h:
                        continue
                    if rel in hash_cache:
                        files_to_delete.append(rel)
                    chunks = process_file(fp, rel, h)
                    all_chunks.extend(chunks)
                    new_hashes[rel] = h
        if files_to_delete:
            client.delete(
                collection_name=collection,
                points_selector=Filter(must=[FieldCondition(
                    key="file_path", match=MatchAny(any=files_to_delete)
                )]),
            )
        if not all_chunks:
            return f"No new/changed files in '{collection}' (cached)."
        texts = [c["content"][:8000] for c in all_chunks]
        try:
            vectors = asyncio.run(emb_fn(texts))
        except Exception:
            async def _embed():
                model = _get_embedding_model()
                if model:
                    return list(model.embed(texts))
                import httpx
                resp = await httpx.AsyncClient(timeout=60.0).post(
                    BGEM3_URL, json=texts,
                    headers={"Authorization": f"Bearer {BGEM3_TOKEN}"}
                )
                resp.raise_for_status()
                d = resp.json()
                return d.get("embeddings", d) if isinstance(d, dict) else d
            vectors = asyncio.run(_embed())
        points = []
        for chunk, vec in zip(all_chunks, vectors):
            cid_str = f"{chunk['file_path']}:{chunk['start_line']}:{chunk['content'][:64]}"
            cid = int(hashlib.md5(cid_str.encode()).hexdigest()[:16], 16) % (2 ** 63)
            points.append(PointStruct(
                id=cid, vector=vec,
                payload={
                    "file_path": chunk["file_path"], "file_name": chunk["file_name"],
                    "start_line": chunk["start_line"], "chunk_type": chunk["chunk_type"],
                    "content": chunk["content"],
                },
            ))
        client.upsert(collection_name=collection, points=points)
        hash_cache.update(new_hashes)
        hash_cache_path.parent.mkdir(parents=True, exist_ok=True)
        hash_cache_path.write_text(json.dumps(hash_cache, indent=2))
        return f"Indexed {len(all_chunks)} chunks from {len(new_hashes)} files into '{collection}'."

    result = asyncio.run(_run_index())
    return {"success": True, "message": result}


@mcp.tool()
def delete_collection(collection: Annotated[str, "Collection to delete"]) -\u003e Dict[str, Any]:
    """Delete a collection from Qdrant and its hash cache."""
    client = _get_qdrant_client()
    existing = [c.name for c in client.get_collections().collections]
    if collection in existing:
        client.delete_collection(collection)
        cache = PROJECT_ROOT / "infra" / "codebase" / f".file_hashes_{collection}.json"
        if cache.exists():
            cache.unlink()
        return {"success": True, "message": f"Deleted '{collection}'"}
    return {"success": False, "message": f"Not found: {collection}"}


@mcp.tool()
def get_collection_stats_tool(collection: Annotated[str, "Collection name"]) -\u003e str:
    """Get statistics about a collection. Returns JSON."""
    client = _get_qdrant_client()
    count_res = client.count(collection_name=collection, count_filter=None)
    points, _ = client.scroll(
        collection_name=collection, limit=10000,
        with_payload=True, with_vectors=False,
    )
    chunk_types = {}
    files = set()
    for p in points:
        ct = p.payload.get("chunk_type", "unknown")
        chunk_types[ct] = chunk_types.get(ct, 0) + 1
        files.add(p.payload.get("file_path"))
    return json.dumps({
        "collection": collection, "total_points": count_res.count,
        "unique_files": len(files), "chunk_types": chunk_types,
    }, indent=2)


# ============================================================================
# MCP RESOURCES
# ============================================================================

@mcp.resource("codebase://collections/list")
def list_collections():
    """List all Qdrant collections with vector counts. Returns JSON."""
    client = _get_qdrant_client()
    cols = client.get_collections().collections
    result = {
        "collections": [
            {"name": c.name, "vectors_count": client.count(collection_name=c.name, count_filter=None).count}
            for c in cols
        ]
    }
    return json.dumps(result, indent=2)


@mcp.resource("codebase://files/{collection}")
def list_files_in_collection(collection: str):
    """List unique files in a collection. Returns JSON."""
    client = _get_qdrant_client()
    points, _ = client.scroll(
        collection_name=collection, limit=10000,
        with_payload=True, with_vectors=False,
    )
    files = {}
    for p in points:
        fp = p.payload.get("file_path")
        fn = p.payload.get("file_name")
        if fp and fp not in files:
            files[fp] = {"file_path": fp, "file_name": fn, "chunk_count": 1}
        elif fp:
            files[fp]["chunk_count"] += 1
    return json.dumps({"collection": collection, "total_files": len(files), "files": list(files.values())}, indent=2)


@mcp.resource("codebase://collections/{collection}/stats")
def get_collection_stats_resource(collection: str):
    """Get statistics about a collection. Returns JSON."""
    return get_collection_stats_tool(collection)


# ============================================================================
# MCP PROMPTS
# ============================================================================

@mcp.prompt()
def codebase_query(collection: str, question: str, search_limit: int = 5):
    """Generate a prompt for codebase Q/A with semantic search."""
    result = search_codebase(query=question, collection=collection, limit=search_limit, min_score=0.0)
    if result.get("success") and result.get("results"):
        parts = []
        for r in result["results"][:3]:
            parts.append(f"File: {r['file_path']} (score {r['score']})\\nChunk: {r['content'][:300]}")
        context = "\\n\\n".join(parts)
    else:
        context = "No relevant code found."
    return f"""You are an expert codebase assistant.

User question: {question}
Collection: {collection}

Relevant code context:
{context}

Answer the user's question based on the code context above.
"""


@mcp.prompt()
def file_analysis(collection: str, file_path: str, analysis_request: str):
    """Generate a prompt for analyzing a specific file."""
    result = read_file(relative_path=file_path)
    if result.get("success"):
        content_preview = result["data"]["content"][:2000]
    else:
        content_preview = "(Could not read file)"
    return f"""You are an expert code reviewer and analyzer.

Request: {analysis_request}
Collection: {collection}
File: {file_path}

File content (first 2000 chars):
{content_preview}

Analyze the file according to the request above.
"""

'''

content = content + additions

with open(src_path, 'w') as f:
    f.write(content)

print(f'Added missing tools, resources, prompts. Total lines: {len(content.split(chr(10)))}')
