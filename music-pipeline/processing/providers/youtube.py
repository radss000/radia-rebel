"""YouTube preview adapter backed by yt-dlp."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .base import PreviewAdapter, PreviewAdapterError, PreviewFetchResult
from .youtube_utils import extract_video_id

logger = logging.getLogger(__name__)

YTDLP_FORMAT = os.getenv("YTDLP_FORMAT", "best")
YTDLP_AUDIO_FORMAT = os.getenv("YTDLP_AUDIO_FORMAT", "mp3")
YTDLP_COOKIES_PATH = os.getenv("YTDLP_COOKIES_PATH")
YTDLP_COOKIES_FROM_BROWSER = os.getenv("YTDLP_COOKIES_FROM_BROWSER")
YTDLP_PROXY = os.getenv("YTDLP_PROXY")
YTDLP_USER_AGENT = os.getenv("YTDLP_USER_AGENT")
YTDLP_IMPERSONATE = os.getenv("YTDLP_IMPERSONATE")
YTDLP_PLAYER_CLIENTS = os.getenv("YTDLP_PLAYER_CLIENTS", "android")
YTDLP_REFERER = os.getenv("YTDLP_REFERER", "https://www.youtube.com/")
YTDLP_ORIGIN = os.getenv("YTDLP_ORIGIN", "https://www.youtube.com")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FALLBACK_FORMATS = ["bestaudio/best", "best"]


def _parse_cookies_from_browser(value: str):
    raw = value.strip()
    if not raw:
        return None
    if ":" in raw:
        browser, profile = [part.strip() for part in raw.split(":", 1)]
        return (browser, profile) if browser else None
    return (raw,)


def _resolve_cookie_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _run_yt_dlp(target_url: str, ydl_opts: dict) -> dict:
    try:
        with YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(target_url, download=True)
    except DownloadError as exc:
        message = str(exc)
        if "Requested format is not available" in message:
            for fallback in FALLBACK_FORMATS:
                if ydl_opts.get("format") == fallback:
                    continue
                logger.warning("yt-dlp format unavailable, retrying with %s", fallback)
                retry_opts = dict(ydl_opts)
                retry_opts["format"] = fallback
                with YoutubeDL(retry_opts) as ydl:
                    return ydl.extract_info(target_url, download=True)
        raise

class YouTubePreviewAdapter(PreviewAdapter):
    """Resolve YouTube previews via yt-dlp."""

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

        download_dir = Path(tempfile.mkdtemp(prefix="yt-dlp-"))
        output_template = str(download_dir / "%(id)s.%(ext)s")
        ydl_opts = {
            "format": YTDLP_FORMAT,
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "overwrites": True,
            "restrictfilenames": True,
        }
        if YTDLP_AUDIO_FORMAT:
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": YTDLP_AUDIO_FORMAT,
                }
            ]
        if YTDLP_COOKIES_PATH:
            cookie_path = _resolve_cookie_path(YTDLP_COOKIES_PATH)
            if not cookie_path.exists():
                raise PreviewAdapterError(f"yt-dlp cookies file not found: {cookie_path}")
            ydl_opts["cookiefile"] = str(cookie_path)
        elif YTDLP_COOKIES_FROM_BROWSER:
            cookies_from_browser = _parse_cookies_from_browser(YTDLP_COOKIES_FROM_BROWSER)
            if cookies_from_browser:
                ydl_opts["cookiesfrombrowser"] = cookies_from_browser
        if YTDLP_PROXY:
            ydl_opts["proxy"] = YTDLP_PROXY
        if YTDLP_USER_AGENT:
            ydl_opts["user_agent"] = YTDLP_USER_AGENT
        if YTDLP_IMPERSONATE:
            ydl_opts["impersonate"] = YTDLP_IMPERSONATE
        if YTDLP_PLAYER_CLIENTS:
            clients = [client.strip() for client in YTDLP_PLAYER_CLIENTS.split(",") if client.strip()]
            if clients:
                ydl_opts["extractor_args"] = {"youtube": {"player_client": clients}}
        if YTDLP_REFERER or YTDLP_ORIGIN:
            headers = {}
            if YTDLP_REFERER:
                headers["Referer"] = YTDLP_REFERER
            if YTDLP_ORIGIN:
                headers["Origin"] = YTDLP_ORIGIN
            ydl_opts["http_headers"] = headers

        try:
            info = _run_yt_dlp(target_url, ydl_opts)
        except DownloadError as exc:
            raise PreviewAdapterError(f"yt-dlp download failed: {exc}") from exc
        except Exception as exc:
            raise PreviewAdapterError(f"yt-dlp error: {exc}") from exc

        candidate_files = [
            path
            for path in download_dir.iterdir()
            if path.is_file()
            and not path.name.endswith(".part")
            and not path.name.endswith(".ytdl")
            and not path.name.endswith(".info.json")
        ]
        if not candidate_files:
            raise PreviewAdapterError("yt-dlp did not produce a preview file")

        best_file = max(candidate_files, key=lambda path: path.stat().st_size)
        track_id = provider_track_id or info.get("id") or video_id or hashlib.sha256(target_url.encode("utf-8")).hexdigest()
        fallback_extension = f".{YTDLP_AUDIO_FORMAT}" if YTDLP_AUDIO_FORMAT else ".mp3"
        file_extension = best_file.suffix or fallback_extension

        return PreviewFetchResult(
            download_url=None,
            headers={},
            provider_track_id=track_id,
            file_extension=file_extension,
            local_file_path=str(best_file),
        )
