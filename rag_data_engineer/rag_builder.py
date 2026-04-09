"""Document parsing, chunking, embedding and Chroma persistence."""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Iterable

import chromadb
import tiktoken
import voyageai
from chromadb.config import Settings as ChromaSettings
from pypdf import PdfReader

from .drive_loader import DriveFile

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    text: str
    metadata: dict
    chunk_id: str


def extract_text(file: DriveFile) -> str:
    mime = file.effective_mime
    if mime == "application/pdf":
        if not file.content:
            return ""
        reader = PdfReader(io.BytesIO(file.content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if mime in {"text/plain", "text/markdown", "text/csv"}:
        return file.content.decode("utf-8", errors="replace")
    if (
        mime
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        from docx import Document  # lazy import

        doc = Document(io.BytesIO(file.content))
        return "\n".join(p.text for p in doc.paragraphs)
    if (
        mime
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ):
        from pptx import Presentation  # lazy import

        prs = Presentation(io.BytesIO(file.content))
        parts: list[str] = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text:
                    parts.append(shape.text)
        return "\n".join(parts)
    logger.warning("No extractor for mime %s (file %s)", mime, file.name)
    return ""


def chunk_text(text: str, chunk_size: int, overlap: int, encoder) -> list[str]:
    """Token-based chunking with overlap. Stable and embedding-friendly."""
    if not text.strip():
        return []
    tokens = encoder.encode(text)
    chunks: list[str] = []
    step = max(chunk_size - overlap, 1)
    for start in range(0, len(tokens), step):
        window = tokens[start : start + chunk_size]
        if not window:
            break
        chunks.append(encoder.decode(window))
        if start + chunk_size >= len(tokens):
            break
    return chunks


class RagBuilder:
    def __init__(
        self,
        voyage_api_key: str,
        embedding_model: str,
        persist_dir: str,
        collection_name: str,
        chunk_size: int,
        chunk_overlap: int,
    ):
        self.client = voyageai.Client(api_key=voyage_api_key)
        self.embedding_model = embedding_model
        self.chroma = chromadb.PersistentClient(
            path=persist_dir, settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection = self.chroma.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        # Voyage doesn't expose tiktoken-compatible tokenizers; cl100k_base
        # is a close-enough approximation for chunk-size budgeting.
        self.encoder = tiktoken.get_encoding("cl100k_base")

    # ---- state helpers --------------------------------------------------

    def known_files(self) -> dict[str, str]:
        """Return {file_id: modified_time} already indexed."""
        # We store one Chroma metadata 'file_id' + 'modified_time' per chunk.
        # A single get() returns all metadata.
        out: dict[str, str] = {}
        offset = 0
        page = 1000
        while True:
            res = self.collection.get(limit=page, offset=offset, include=["metadatas"])
            metas = res.get("metadatas") or []
            if not metas:
                break
            for m in metas:
                fid = m.get("file_id")
                mt = m.get("modified_time")
                if fid and mt and out.get(fid, "") < mt:
                    out[fid] = mt
            if len(metas) < page:
                break
            offset += page
        return out

    def delete_file(self, file_id: str) -> None:
        self.collection.delete(where={"file_id": file_id})

    # ---- ingestion ------------------------------------------------------

    def _embed(self, texts: list[str]) -> list[list[float]]:
        # Voyage allows up to 128 inputs per request for voyage-3 family.
        out: list[list[float]] = []
        for i in range(0, len(texts), 128):
            batch = texts[i : i + 128]
            resp = self.client.embed(
                texts=batch,
                model=self.embedding_model,
                input_type="document",
            )
            out.extend(resp.embeddings)
        return out

    def upsert_file(self, file: DriveFile) -> int:
        text = extract_text(file)
        chunks = chunk_text(
            text, self.chunk_size, self.chunk_overlap, self.encoder
        )
        if not chunks:
            return 0

        # Replace any prior version of this file.
        self.delete_file(file.id)

        ids = [f"{file.id}::{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "file_id": file.id,
                "file_name": file.name,
                "mime_type": file.mime_type,
                "modified_time": file.modified_time,
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]
        embeddings = self._embed(chunks)
        self.collection.upsert(
            ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings
        )
        return len(chunks)

    def reconcile(
        self, files: Iterable[DriveFile], known: dict[str, str]
    ) -> dict[str, int]:
        """Add new / update modified / leave untouched. Returns counters."""
        stats = {"added": 0, "updated": 0, "skipped": 0, "chunks": 0, "failed": 0}
        seen_ids: set[str] = set()
        for f in files:
            seen_ids.add(f.id)
            prev = known.get(f.id)
            if prev == f.modified_time:
                stats["skipped"] += 1
                continue
            try:
                n = self.upsert_file(f)
            except Exception as exc:  # noqa: BLE001 — never fail the whole batch
                logger.warning(
                    "Failed to ingest %s (%s): %s", f.name, f.id, exc
                )
                stats["failed"] += 1
                continue
            stats["chunks"] += n
            if prev is None:
                stats["added"] += 1
            else:
                stats["updated"] += 1
        # Delete files removed from Drive
        deleted = 0
        for fid in known.keys() - seen_ids:
            self.delete_file(fid)
            deleted += 1
        stats["deleted"] = deleted
        return stats
