"""Bandcamp preview adapter."""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import requests

from .base import PreviewAdapter, PreviewAdapterError, PreviewFetchResult

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0 Safari/537.36"
)


class BandcampPreviewAdapter(PreviewAdapter):
    """Resolve Bandcamp streaming previews."""

    def resolve(self, *, source_url: str, preview_url: Optional[str], provider_track_id: Optional[str]) -> PreviewFetchResult:
        candidate_url = preview_url or self._scrape_preview(source_url)
        if not candidate_url:
            raise PreviewAdapterError(f"Unable to resolve Bandcamp preview for {source_url}")

        track_id = provider_track_id or self._extract_track_id(candidate_url) or "bandcamp-unknown"
        headers = {"User-Agent": _USER_AGENT, "Referer": source_url}
        return PreviewFetchResult(
            download_url=candidate_url,
            headers=headers,
            provider_track_id=track_id,
            file_extension=".mp3",
        )

    def _scrape_preview(self, source_url: str) -> Optional[str]:
        try:
            response = requests.get(source_url, timeout=15, headers={"User-Agent": _USER_AGENT})
            if response.status_code != 200:
                logger.warning("Bandcamp scrape failed (%s) for %s", response.status_code, source_url)
                return None
        except Exception as exc:
            logger.warning("Bandcamp scrape error for %s: %s", source_url, exc)
            return None

        html = response.text

        # Look for embedded JSON that exposes trackinfo with file urls
        match = re.search(r"data-tralbum=\"(.*?)\"", html)
        if match:
            try:
                json_blob = match.group(1)
                json_blob = json_blob.replace("&quot;", '"')
                data = json.loads(json_blob)
                trackinfo = data.get("trackinfo", [])
                for entry in trackinfo:
                    file_info = entry.get("file") or {}
                    mp3_url = file_info.get("mp3-128")
                    if mp3_url:
                        return mp3_url
            except Exception as exc:
                logger.debug("Bandcamp data-tralbum parse error: %s", exc)

        # Fallback: look for static MP3 URLs within the page
        mp3_match = re.search(r"https://t4\.bcbits\.com/stream/[^\"']+\.mp3", html)
        if mp3_match:
            return mp3_match.group(0)

        return None

    def _extract_track_id(self, preview_url: str) -> Optional[str]:
        match = re.search(r"/track/(\d+)", preview_url)
        if match:
            return match.group(1)
        return None
