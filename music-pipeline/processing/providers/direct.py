"""Adapter for audio reachable at a plain URL (artist uploads, Node API files).

``/api/tracks/ingest`` stores any URL that is not YouTube/Bandcamp/Discogs as
provider ``other``. Without an adapter for that provider the ``preview_fetch``
job failed with "No adapter registered", so the whole analysis chain stopped
for every direct upload.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Optional
from urllib.parse import urlparse

from .base import PreviewAdapterError, PreviewFetchResult

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".oga", ".m4a", ".aac", ".aif", ".aiff", ".opus", ".webm"}
_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


def _extension_from_url(url: str) -> str:
    suffix = os.path.splitext(urlparse(url).path)[1].lower()
    return suffix if suffix in AUDIO_EXTENSIONS else ".mp3"


def _storage_safe_id(provider_track_id: Optional[str], url: str) -> str:
    """Storage keys are built as ``<provider>/<id><ext>``: keep them path-safe."""
    if provider_track_id:
        cleaned = _SAFE_ID.sub("-", provider_track_id).strip("-.")
        if cleaned:
            return cleaned[:128]
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


class DirectURLPreviewAdapter:
    """Download the stored URL as-is (http/https only)."""

    def resolve(
        self,
        *,
        source_url: str,
        preview_url: Optional[str],
        provider_track_id: Optional[str],
    ) -> PreviewFetchResult:
        url = preview_url or source_url
        if not url:
            raise PreviewAdapterError("No URL stored for this audio asset")
        scheme = urlparse(url).scheme.lower()
        if scheme not in {"http", "https"}:
            raise PreviewAdapterError(f"Unsupported URL scheme '{scheme}' for direct download")
        return PreviewFetchResult(
            download_url=url,
            headers={},
            provider_track_id=_storage_safe_id(provider_track_id, url),
            file_extension=_extension_from_url(url),
        )


__all__ = ["DirectURLPreviewAdapter"]
