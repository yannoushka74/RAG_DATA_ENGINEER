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
    chroma_collection: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int

    # Drive ingestion only — optional when the package is used in query-only
    # mode (e.g. an MCP server that just reads from Chroma).
    google_service_account_file: str | None = None
    gdrive_folder_id: str | None = None

    # Chroma backend: either a local PersistentClient on disk OR a remote
    # HttpClient. If `chroma_http_host` is set, HTTP mode wins.
    chroma_persist_dir: str = "./chroma_db"
    chroma_http_host: str | None = None
    chroma_http_port: int = 8000
    chroma_http_ssl: bool = False
    chroma_auth_token: str | None = None

    @property
    def use_http_chroma(self) -> bool:
        return bool(self.chroma_http_host)

    @classmethod
    def from_env(cls, *, require_drive: bool = True) -> "Settings":
        if not os.getenv("VOYAGE_API_KEY"):
            raise RuntimeError("Missing required env var: VOYAGE_API_KEY")

        if require_drive:
            for var in ("GOOGLE_SERVICE_ACCOUNT_FILE", "GDRIVE_FOLDER_ID"):
                if not os.getenv(var):
                    raise RuntimeError(f"Missing required env var: {var}")

        return cls(
            voyage_api_key=os.environ["VOYAGE_API_KEY"],
            google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
            gdrive_folder_id=os.getenv("GDRIVE_FOLDER_ID"),
            chroma_persist_dir=os.getenv(
                "CHROMA_PERSIST_DIR", str(Path.cwd() / "chroma_db")
            ),
            chroma_http_host=os.getenv("CHROMA_HTTP_HOST") or None,
            chroma_http_port=int(os.getenv("CHROMA_HTTP_PORT", "8000")),
            chroma_http_ssl=os.getenv("CHROMA_HTTP_SSL", "false").lower()
            in ("1", "true", "yes"),
            chroma_auth_token=os.getenv("CHROMA_AUTH_TOKEN") or None,
            chroma_collection=os.getenv("CHROMA_COLLECTION", "rag_data_engineer"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "voyage-3"),
            chunk_size=int(os.getenv("CHUNK_SIZE", "800")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "120")),
        )
