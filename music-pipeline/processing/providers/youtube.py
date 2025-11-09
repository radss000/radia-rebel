"""YouTube Music preview adapter."""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

from .base import PreviewAdapter, PreviewAdapterError, PreviewFetchResult

logger = logging.getLogger(__name__)

_STREAM_HOST_HINTS = ("googlevideo.com", "youtube.googleapis.com")
_STREAM_EXT_HINTS = (".m4a", ".mp3", ".mp4", ".webm")


def _looks_like_direct_stream(url: str) -> bool:
    """Return True when the URL already points at a media stream."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    host = parsed.netloc.lower()
    if any(host.endswith(hint) for hint in _STREAM_HOST_HINTS):
        return True

    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in _STREAM_EXT_HINTS)


_YT_CLIENTS = ("android", "tv_embedded", "tvhtml5")
_YT_FORMAT = "bestaudio/best"


def _extract_best_stream(info):
    formats = info.get("formats") or []
    audio_formats = [
        fmt
        for fmt in formats
        if fmt.get("acodec") not in (None, "none")
        and fmt.get("url")
    ]
    if audio_formats:
        return max(audio_formats, key=lambda fmt: fmt.get("abr") or 0)
    if info.get("url"):
        return {"url": info["url"], "ext": info.get("ext", "m4a")}
    return None


class YouTubePreviewAdapter(PreviewAdapter):
    """Resolve YouTube audio streams via yt-dlp if available."""

    def resolve(self, *, source_url: str, preview_url: Optional[str], provider_track_id: Optional[str]) -> PreviewFetchResult:
        if preview_url and _looks_like_direct_stream(preview_url):
            candidate = preview_url
            extension = ".mp3" if candidate.endswith(".mp3") else ".m4a"
            track_id = provider_track_id or "youtube-music"
            return PreviewFetchResult(
                download_url=candidate,
                headers={},
                provider_track_id=track_id,
                file_extension=extension,
            )

        try:
            import yt_dlp  # type: ignore
        except ImportError as exc:
            raise PreviewAdapterError(
                "yt-dlp is required to resolve YouTube previews. Install yt-dlp "
                "and configure API/consent before enabling YouTube ingestion."
            ) from exc

        last_error: Optional[Exception] = None
        for client in _YT_CLIENTS:
            ydl_opts = {
                "format": _YT_FORMAT,
                "quiet": True,
                "skip_download": True,
                "extractor_args": {"youtube": {"player_client": [client]}},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[attr-defined]
                try:
                    info = ydl.extract_info(source_url, download=False)
                except Exception as exc:  # pragma: no cover - network path
                    last_error = exc
                    continue

            stream = _extract_best_stream(info)
            if stream and stream.get("url"):
                track_id = provider_track_id or info.get("id", "youtube-music")
                ext = stream.get("ext", info.get("ext", "m4a"))
                headers = info.get("http_headers") or {}
                return PreviewFetchResult(
                    download_url=stream["url"],
                    headers=headers,
                    provider_track_id=track_id,
                    file_extension=f".{ext}",
                )

        error_detail = last_error or RuntimeError("No playable YouTube formats available")
        raise PreviewAdapterError(f"Failed to resolve YouTube preview: {error_detail}")
