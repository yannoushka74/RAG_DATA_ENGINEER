"""Obsidian-specific markdown preprocessing for better RAG chunking."""
from __future__ import annotations

import re
import yaml


def extract_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and return (metadata_dict, body_text).

    Returns an empty dict if no frontmatter is found.
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    try:
        meta = yaml.safe_load(raw)
        if not isinstance(meta, dict):
            meta = {}
    except yaml.YAMLError:
        meta = {}
    return meta, body


def clean_obsidian_markdown(text: str) -> str:
    """Strip Obsidian-specific syntax for cleaner embeddings."""
    # [[link|alias]] → alias
    text = re.sub(r"\[\[([^]|]+)\|([^]]+)\]\]", r"\2", text)
    # [[link]] → link
    text = re.sub(r"\[\[([^]]+)\]\]", r"\1", text)
    # ![[embedded note]] → (embedded: note)
    text = re.sub(r"!\[\[([^]]+)\]\]", r"(embedded: \1)", text)
    # Callouts: > [!type] title → title
    text = re.sub(r"^>\s*\[!(\w+)\]\s*", "", text, flags=re.MULTILINE)
    # Tags in body: #tag → tag (but not ## headings)
    text = re.sub(r"(?<!\w)#(?!#)(\w[\w/-]*)", r"\1", text)
    return text


def preprocess_obsidian(text: str) -> tuple[str, dict]:
    """Full Obsidian preprocessing pipeline.

    Returns (cleaned_text, extra_metadata) where extra_metadata contains
    tags and aliases extracted from frontmatter.
    """
    meta, body = extract_frontmatter(text)
    cleaned = clean_obsidian_markdown(body)

    extra: dict = {}
    tags = meta.get("tags")
    if isinstance(tags, list):
        extra["tags"] = ", ".join(str(t) for t in tags)
    elif isinstance(tags, str):
        extra["tags"] = tags

    aliases = meta.get("aliases")
    if isinstance(aliases, list):
        extra["aliases"] = ", ".join(str(a) for a in aliases)

    folder_path = meta.get("folder")
    if folder_path:
        extra["folder_path"] = str(folder_path)

    return cleaned, extra
