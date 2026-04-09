"""Query helper for the RAG store. Used by the CLI and the MCP server."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import voyageai

from .config import Settings
from .rag_builder import make_chroma_client

logger = logging.getLogger(__name__)


@dataclass
class Hit:
    text: str
    file_name: str
    file_id: str
    chunk_index: int
    distance: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "file_name": self.file_name,
            "file_id": self.file_id,
            "chunk_index": self.chunk_index,
            "distance": self.distance,
        }


class RagQuery:
    """Embeds a query with Voyage and runs a similarity search on Chroma."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env(require_drive=False)
        self._voyage = voyageai.Client(api_key=self.settings.voyage_api_key)
        self._chroma = make_chroma_client(
            persist_dir=self.settings.chroma_persist_dir,
            http_host=self.settings.chroma_http_host,
            http_port=self.settings.chroma_http_port,
            http_ssl=self.settings.chroma_http_ssl,
            auth_token=self.settings.chroma_auth_token,
        )
        self._collection = self._chroma.get_collection(
            name=self.settings.chroma_collection
        )

    def search(self, query: str, k: int = 5) -> list[Hit]:
        if not query.strip():
            return []
        qvec = self._voyage.embed(
            texts=[query],
            model=self.settings.embedding_model,
            input_type="query",
        ).embeddings[0]
        res = self._collection.query(
            query_embeddings=[qvec],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[Hit] = []
        docs = res["documents"][0] if res.get("documents") else []
        metas = res["metadatas"][0] if res.get("metadatas") else []
        dists = res["distances"][0] if res.get("distances") else []
        for doc, meta, dist in zip(docs, metas, dists):
            hits.append(
                Hit(
                    text=doc,
                    file_name=meta.get("file_name", "?"),
                    file_id=meta.get("file_id", "?"),
                    chunk_index=int(meta.get("chunk_index", -1)),
                    distance=float(dist),
                )
            )
        return hits

    def collection_size(self) -> int:
        return self._collection.count()
