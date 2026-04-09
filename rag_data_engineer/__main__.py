"""Module entry point: `python -m rag_data_engineer` or `rag-build` CLI."""
from __future__ import annotations

import logging

from .rag_pipeline import run_pipeline


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    stats = run_pipeline()
    print("RAG pipeline stats:", stats)


if __name__ == "__main__":
    main()
