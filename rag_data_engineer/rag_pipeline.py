"""End-to-end pipeline: Drive -> chunks -> embeddings -> Chroma."""
from __future__ import annotations

import logging

from .config import Settings
from .drive_loader import DriveLoader
from .rag_builder import RagBuilder

logger = logging.getLogger(__name__)


def run_pipeline(settings: Settings | None = None) -> dict:
    settings = settings or Settings.from_env()
    logger.info("Starting RAG pipeline for folder %s", settings.gdrive_folder_id)

    loader = DriveLoader(settings.google_service_account_file)
    builder = RagBuilder(
        voyage_api_key=settings.voyage_api_key,
        embedding_model=settings.embedding_model,
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.chroma_collection,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    known = builder.known_files()
    logger.info("Currently indexed: %d files", len(known))

    stats = builder.reconcile(loader.iter_files(settings.gdrive_folder_id), known)
    logger.info("Pipeline finished: %s", stats)
    return stats
