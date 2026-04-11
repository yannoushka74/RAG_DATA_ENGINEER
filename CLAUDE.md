# RAG_DATA_ENGINEER

## What this project does

Python package (`rag-data-engineer`) that ingests a Google Drive folder, extracts text from PDF/DOCX/PPTX/source code, chunks by tokens, embeds with Voyage AI (`voyage-3`), and persists into ChromaDB. Includes an MCP server for querying the RAG from Claude Desktop / Claude Code.

## Architecture

- **Ingest path**: Google Drive → `drive_loader.py` → `rag_builder.py` (extract + chunk + embed + upsert) → ChromaDB HTTP server
- **Query path**: Claude (MCP) → `mcp_server.py` → `rag_query.py` → ChromaDB HTTP server
- **Orchestration**: Airflow DAG in a separate repo (`airflow-local-setup`) installs this package via pip and calls `run_pipeline()`
- **ChromaDB**: standalone k8s Deployment exposed via Tailscale ingress at `chromadb.tail430f32.ts.net`

## Key design decisions

- **Incremental reconciliation**: `reconcile()` compares Drive `modifiedTime` with Chroma metadata — only new/modified files are re-embedded, deleted files are removed
- **HTTP Chroma backend**: `make_chroma_client()` factory switches between `PersistentClient` (local dev) and `HttpClient` (production) based on `CHROMA_HTTP_HOST` env var
- **Drive credentials optional**: `Settings.from_env(require_drive=False)` allows query-only consumers (MCP server) to bootstrap without GCP credentials
- **Token-based chunking**: uses `tiktoken` (`cl100k_base`) for consistent chunk sizes relative to embedding model token limits

## Common commands

```bash
# Dev install
pip install -e ".[mcp]"

# Run ingest locally
python -m rag_data_engineer

# Run MCP server (stdio)
python -m rag_data_engineer.mcp_server

# Quick query test
python -c "from rag_data_engineer.rag_query import RagQuery; q=RagQuery(); print(q.search('your query', k=3))"
```

## Environment variables

Required for ingest: `VOYAGE_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_FILE`, `GDRIVE_FOLDER_ID`
Required for query only: `VOYAGE_API_KEY`, `CHROMA_HTTP_HOST`, `CHROMA_AUTH_TOKEN`
Optional: `CHROMA_HTTP_PORT` (8000), `CHROMA_HTTP_SSL` (false), `CHROMA_COLLECTION` (rag_data_engineer), `EMBEDDING_MODEL` (voyage-3), `CHUNK_SIZE` (800), `CHUNK_OVERLAP` (120)

## Code conventions

- Python 3.10+, `from __future__ import annotations` in every module
- Relative imports within the package (`from .config import Settings`)
- Lazy imports for heavy optional deps (`from docx import Document`, `from pptx import Presentation`)
- `make_chroma_client()` is the single factory for Chroma clients — never instantiate `PersistentClient` or `HttpClient` directly
- Errors on a single file during reconcile are logged and counted as `failed` — they never crash the whole batch

## Files that should NEVER be committed

- `.env`, `service_account*.json`, `chroma_db/`, `.venv/`
- These are all covered by `.gitignore`
