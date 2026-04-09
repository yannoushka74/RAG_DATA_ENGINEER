"""CLI entry point: python scripts/build_rag.py"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Allow running as a script without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag_pipeline import run_pipeline  # noqa: E402


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    stats = run_pipeline()
    print("RAG pipeline stats:", stats)


if __name__ == "__main__":
    main()
