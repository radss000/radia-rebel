"""YouTube preview adapter backed by the cobalt API."""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

from .base import PreviewAdapter, PreviewAdapterError, PreviewFetchResult
from .cobalt_client import CobaltAPIError, request_preview_url
from .youtube_utils import extract_video_id

logger = logging.getLogger(__name__)


class YouTubePreviewAdapter(PreviewAdapter):
    """Resolve YouTube previews via the cobalt API."""

    def resolve(
        self,
        *,
        source_url: str,
        preview_url: Optional[str],
        provider_track_id: Optional[str],
    ) -> PreviewFetchResult:
        target_url = preview_url or source_url
        video_id = extract_video_id(target_url)
        if not video_id:
            raise PreviewAdapterError("Unable to extract video id from provided YouTube URL")

        try:
            cobalt_result = request_preview_url(target_url)
        except CobaltAPIError as exc:
            raise PreviewAdapterError(str(exc)) from exc

        track_id = provider_track_id or video_id or hashlib.sha256(target_url.encode("utf-8")).hexdigest()
        file_extension = cobalt_result.get("file_extension") or ".mp3"
        download_url = cobalt_result.get("download_url")
        if not download_url:
            raise PreviewAdapterError("Cobalt response missing download URL")

        return PreviewFetchResult(
            download_url=download_url,
            headers={},
            provider_track_id=track_id,
            file_extension=file_extension,
        )
