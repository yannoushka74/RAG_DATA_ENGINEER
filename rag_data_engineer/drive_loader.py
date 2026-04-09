"""Google Drive loader: lists and downloads files from a folder using a service account."""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Iterator

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Google Workspace native MIME types -> export format
EXPORT_MIME_MAP = {
    "application/vnd.google-apps.document": (
        "text/plain",
        ".txt",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "text/csv",
        ".csv",
    ),
    "application/vnd.google-apps.presentation": (
        "text/plain",
        ".txt",
    ),
}

# Binary MIME types we know how to parse downstream
SUPPORTED_BINARY_MIMES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

# Treat any text/* and application/*-script as plain text by default.
TEXT_PREFIXES = ("text/",)
TEXT_LIKE_MIMES = {
    "application/json",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
    "application/x-sh",
    "application/x-python",
    "application/javascript",
    "application/sql",
    "application/octet-stream",  # tentative; we'll try to decode as utf-8
}


@dataclass
class DriveFile:
    id: str
    name: str
    mime_type: str
    modified_time: str  # RFC3339 string
    content: bytes
    effective_mime: str  # mime after export (e.g., text/plain for gdocs)


class DriveLoader:
    def __init__(self, service_account_file: str):
        creds = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=SCOPES
        )
        self.service = build("drive", "v3", credentials=creds, cache_discovery=False)

    def list_folder(self, folder_id: str) -> list[dict]:
        """List all files (recursively) under the given folder ID."""
        files: list[dict] = []
        stack = [folder_id]
        while stack:
            current = stack.pop()
            page_token = None
            while True:
                resp = (
                    self.service.files()
                    .list(
                        q=f"'{current}' in parents and trashed = false",
                        fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                        pageSize=1000,
                        pageToken=page_token,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                    .execute()
                )
                for f in resp.get("files", []):
                    if f["mimeType"] == "application/vnd.google-apps.folder":
                        stack.append(f["id"])
                    else:
                        files.append(f)
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        return files

    def download(self, file_meta: dict) -> DriveFile | None:
        """Download a single file, exporting Google-native formats to text."""
        file_id = file_meta["id"]
        mime = file_meta["mimeType"]

        if mime in EXPORT_MIME_MAP:
            export_mime, _ext = EXPORT_MIME_MAP[mime]
            request = self.service.files().export_media(
                fileId=file_id, mimeType=export_mime
            )
            effective_mime = export_mime
        elif mime in SUPPORTED_BINARY_MIMES:
            request = self.service.files().get_media(fileId=file_id)
            effective_mime = mime
        elif mime.startswith(TEXT_PREFIXES) or mime in TEXT_LIKE_MIMES:
            # Source code, configs, JSON, YAML, etc. — treat as plain text.
            request = self.service.files().get_media(fileId=file_id)
            effective_mime = "text/plain"
        else:
            logger.info("Skipping unsupported file %s (%s)", file_meta["name"], mime)
            return None

        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _status, done = downloader.next_chunk()

        return DriveFile(
            id=file_id,
            name=file_meta["name"],
            mime_type=mime,
            modified_time=file_meta["modifiedTime"],
            content=buf.getvalue(),
            effective_mime=effective_mime,
        )

    def iter_files(self, folder_id: str) -> Iterator[DriveFile]:
        for meta in self.list_folder(folder_id):
            df = self.download(meta)
            if df is not None:
                yield df
