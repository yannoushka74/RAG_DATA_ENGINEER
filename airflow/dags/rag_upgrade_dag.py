"""Airflow DAG that re-syncs the RAG vector store from Google Drive.

Drop this file into your AIRFLOW_HOME/dags/ folder.

Required Airflow Variables (Admin > Variables) OR env vars on the worker:
    VOYAGE_API_KEY
    GOOGLE_SERVICE_ACCOUNT_FILE   (absolute path on the worker)
    GDRIVE_FOLDER_ID
    CHROMA_PERSIST_DIR            (worker-writable, ideally a shared volume)
    RAG_PROJECT_PATH              (absolute path to the RAG_DATA_ENGINEER repo)
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

log = logging.getLogger(__name__)


def _resolve(name: str, default: str | None = None) -> str | None:
    """Read from Airflow Variable first, then env, then default."""
    try:
        val = Variable.get(name, default_var=None)
        if val:
            return val
    except Exception:
        pass
    return os.getenv(name, default)


def upgrade_rag(**_context) -> dict:
    project_path = _resolve("RAG_PROJECT_PATH")
    if not project_path:
        raise RuntimeError("RAG_PROJECT_PATH is not configured")
    if project_path not in sys.path:
        sys.path.insert(0, project_path)

    # Propagate config into the env so Settings.from_env() picks it up.
    for key in (
        "VOYAGE_API_KEY",
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        "GDRIVE_FOLDER_ID",
        "CHROMA_PERSIST_DIR",
        "CHROMA_COLLECTION",
        "EMBEDDING_MODEL",
        "CHUNK_SIZE",
        "CHUNK_OVERLAP",
    ):
        val = _resolve(key)
        if val is not None:
            os.environ[key] = val

    from src.rag_pipeline import run_pipeline  # imported after sys.path tweak

    stats = run_pipeline()
    log.info("RAG upgrade finished: %s", stats)
    return stats


default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="rag_data_engineer_upgrade",
    description="Incrementally re-sync the RAG vector store from a Google Drive folder",
    default_args=default_args,
    start_date=datetime(2026, 4, 9),
    schedule="@hourly",  # change to "@daily", a cron, or None for manual only
    catchup=False,
    max_active_runs=1,
    tags=["rag", "drive", "embeddings"],
) as dag:
    PythonOperator(
        task_id="upgrade_rag_from_drive",
        python_callable=upgrade_rag,
    )
