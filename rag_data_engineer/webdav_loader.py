"""WebDAV loader: lists and downloads files from a Nextcloud folder via WebDAV."""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import urllib.parse
from dataclasses import dataclass
from typing import Iterator
from xml.etree import ElementTree as ET

import requests

from .drive_loader import DriveFile

logger = logging.getLogger(__name__)

# Namespaces used in WebDAV PROPFIND responses
DAV_NS = "DAV:"

# File extensions we can process
SUPPORTED_EXTENSIONS = {
    ".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".xml",
    ".py", ".sql", ".sh", ".js", ".ts",
    ".pdf", ".docx", ".pptx",
}


class WebdavLoader:
    """List and download files from a WebDAV endpoint (Nextcloud compatible)."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (username, password)

    def _propfind(self, path: str, depth: str = "1") -> list[dict]:
        """PROPFIND a path and return file/folder metadata."""
        url = f"{self.base_url}/{urllib.parse.quote(path, safe='/')}"
        resp = self.session.request("PROPFIND", url, headers={"Depth": depth})
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        items = []
        for response in root.findall(f"{{{DAV_NS}}}response"):
            href = response.findtext(f"{{{DAV_NS}}}href", "")
            propstat = response.find(f"{{{DAV_NS}}}propstat")
            if propstat is None:
                continue
            prop = propstat.find(f"{{{DAV_NS}}}prop")
            if prop is None:
                continue

            is_collection = prop.find(f"{{{DAV_NS}}}resourcetype/{{{DAV_NS}}}collection") is not None
            last_modified = prop.findtext(f"{{{DAV_NS}}}getlastmodified", "")
            content_length = prop.findtext(f"{{{DAV_NS}}}getcontentlength", "0")
            etag = prop.findtext(f"{{{DAV_NS}}}getetag", "")

            # Decode the href to get the filename
            decoded = urllib.parse.unquote(href)

            items.append({
                "href": decoded,
                "is_folder": is_collection,
                "modified": last_modified,
                "size": int(content_length) if content_length else 0,
                "etag": etag.strip('"'),
            })
        return items

    def list_folder(self, path: str = "") -> list[dict]:
        """Recursively list all files under a path."""
        files: list[dict] = []
        stack = [path]
        while stack:
            current = stack.pop()
            try:
                items = self._propfind(current)
            except Exception as e:
                logger.warning("PROPFIND failed for %s: %s", current, e)
                continue

            for item in items:
                # Skip the folder itself
                item_path = item["href"]
                # Extract relative path from the full href
                # href looks like /remote.php/dav/files/admin/Obsidian/subfolder/file.md
                if item["is_folder"]:
                    # Don't recurse into the current folder again
                    rel = item_path.rstrip("/")
                    current_rel = f"{self.base_url}/{urllib.parse.quote(current, safe='/')}".rstrip("/")
                    if rel != current_rel and not rel.endswith(f"/{current.rstrip('/')}"):
                        # Extract path relative to base_url
                        # Find the base path in the href
                        base_path = urllib.parse.urlparse(self.base_url).path
                        if base_path in rel:
                            sub = rel[len(base_path):].strip("/")
                            if sub and sub != current.strip("/"):
                                stack.append(sub)
                else:
                    # It's a file
                    base_path = urllib.parse.urlparse(self.base_url).path
                    if base_path in item_path:
                        rel_path = item_path[len(base_path):].strip("/")
                    else:
                        rel_path = item_path.strip("/")

                    name = rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path
                    files.append({
                        "path": rel_path,
                        "name": name,
                        "modified": item["modified"],
                        "size": item["size"],
                        "etag": item["etag"],
                    })
        return files

    def download(self, file_meta: dict) -> DriveFile | None:
        """Download a single file from WebDAV."""
        path = file_meta["path"]
        name = file_meta["name"]

        # Skip renamed junk
        if name.startswith(("_DOUBLON_", "_VIDE_", "_KEEP_JUNK_")):
            return None

        # Check extension
        ext = ""
        if "." in name:
            ext = "." + name.rsplit(".", 1)[-1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            logger.info("Skipping unsupported file %s", name)
            return None

        # Guess MIME type
        mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"

        url = f"{self.base_url}/{urllib.parse.quote(path, safe='/')}"
        resp = self.session.get(url)
        if resp.status_code != 200:
            logger.warning("GET %s → %s", path, resp.status_code)
            return None

        # Use etag as stable file ID, fallback to hash of path
        file_id = file_meta.get("etag") or hashlib.md5(path.encode()).hexdigest()

        return DriveFile(
            id=file_id,
            name=name,
            mime_type=mime_type,
            modified_time=file_meta["modified"],
            content=resp.content,
            effective_mime=mime_type,
        )

    def iter_files(self, path: str = "") -> Iterator[DriveFile]:
        """Iterate over all supported files, yielding DriveFile objects."""
        for meta in self.list_folder(path):
            df = self.download(meta)
            if df is not None:
                yield df
