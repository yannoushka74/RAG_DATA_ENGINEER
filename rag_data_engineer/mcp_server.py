"""MCP server exposing the RAG store as a `rag_search` tool.

Run as a stdio server (the format Claude Code / Claude Desktop expect):

    python -m rag_data_engineer.mcp_server

Required env vars:
    VOYAGE_API_KEY
    CHROMA_HTTP_HOST                 (e.g. chromadb.example.com)
    CHROMA_HTTP_PORT                 (default 8000)
    CHROMA_HTTP_SSL                  (true / false; default false)
    CHROMA_AUTH_TOKEN                (optional bearer token)
    CHROMA_COLLECTION                (default rag_data_engineer)
    EMBEDDING_MODEL                  (default voyage-3)

Register with Claude Code:
    claude mcp add rag-data-engineer -- python -m rag_data_engineer.mcp_server
"""
from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from .rag_query import RagQuery

logger = logging.getLogger("rag_data_engineer.mcp")

mcp = FastMCP("rag-data-engineer")

# Lazy singleton — built on first tool invocation so server boot doesn't fail
# if Chroma is briefly unreachable.
_query: RagQuery | None = None


def _get_query() -> RagQuery:
    global _query
    if _query is None:
        _query = RagQuery()
    return _query


@mcp.tool()
def rag_search(query: str, k: int = 5) -> str:
    """Search the data engineering RAG corpus and return the top-K matching chunks.

    Args:
        query: Natural language question or keywords to search for.
        k: Number of chunks to return (default 5, max 20).

    Returns:
        JSON-encoded list of hits with `text`, `file_name`, `chunk_index` and
        `distance` (cosine; lower is better).
    """
    k = max(1, min(int(k), 20))
    hits = _get_query().search(query, k=k)
    return json.dumps([h.to_dict() for h in hits], ensure_ascii=False, indent=2)


@mcp.tool()
def rag_stats() -> str:
    """Return basic statistics about the RAG collection (chunk count)."""
    q = _get_query()
    return json.dumps(
        {
            "collection": q.settings.chroma_collection,
            "embedding_model": q.settings.embedding_model,
            "chunk_count": q.collection_size(),
            "backend": "http" if q.settings.use_http_chroma else "persistent",
        },
        ensure_ascii=False,
        indent=2,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
