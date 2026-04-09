"""Centralised configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Best-effort: load .env from the current working directory if present.
# When the package is installed via pip, there is no project-local .env, so
# the caller (CLI script or Airflow DAG) is expected to populate the env.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    voyage_api_key: str
    google_service_account_file: str
    gdrive_folder_id: str
    chroma_persist_dir: str
    chroma_collection: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int

    @classmethod
    def from_env(cls) -> "Settings":
        required = {
            "VOYAGE_API_KEY": os.getenv("VOYAGE_API_KEY"),
            "GOOGLE_SERVICE_ACCOUNT_FILE": os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
            "GDRIVE_FOLDER_ID": os.getenv("GDRIVE_FOLDER_ID"),
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

        return cls(
            voyage_api_key=required["VOYAGE_API_KEY"],
            google_service_account_file=required["GOOGLE_SERVICE_ACCOUNT_FILE"],
            gdrive_folder_id=required["GDRIVE_FOLDER_ID"],
            chroma_persist_dir=os.getenv(
                "CHROMA_PERSIST_DIR", str(Path.cwd() / "chroma_db")
            ),
            chroma_collection=os.getenv("CHROMA_COLLECTION", "rag_data_engineer"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "voyage-3"),
            chunk_size=int(os.getenv("CHUNK_SIZE", "800")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "120")),
        )
