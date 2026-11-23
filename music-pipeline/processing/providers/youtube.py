"""YouTube preview adapter backed by yt-dlp."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from yt_dlp import YoutubeDL
import yt_dlp
from yt_dlp.utils import DownloadError

from .base import PreviewAdapter, PreviewAdapterError, PreviewFetchResult
from .youtube_utils import extract_video_id
from .cobalt_client import request_preview_url, CobaltAPIError

logger = logging.getLogger(__name__)

YTDLP_FORMAT = os.getenv("YTDLP_FORMAT", "bestaudio/best")
YTDLP_AUDIO_FORMAT = os.getenv("YTDLP_AUDIO_FORMAT", "mp3")
YTDLP_COOKIES_PATH = os.getenv("YTDLP_COOKIES_PATH")
YTDLP_COOKIES_FROM_BROWSER = os.getenv("YTDLP_COOKIES_FROM_BROWSER")
YTDLP_PROXY = os.getenv("YTDLP_PROXY")
YTDLP_USER_AGENT = os.getenv("YTDLP_USER_AGENT")
YTDLP_IMPERSONATE = os.getenv("YTDLP_IMPERSONATE")
YTDLP_PLAYER_CLIENTS = os.getenv("YTDLP_PLAYER_CLIENTS", "android")
YTDLP_REFERER = os.getenv("YTDLP_REFERER", "https://www.youtube.com/")
YTDLP_ORIGIN = os.getenv("YTDLP_ORIGIN", "https://www.youtube.com")
# Without a socket timeout a stalled YouTube connection blocks the worker until
# the RQ job timeout (or forever if the alarm cannot interrupt the read).
YTDLP_SOCKET_TIMEOUT = float(os.getenv("YTDLP_SOCKET_TIMEOUT", "30"))
YTDLP_RETRIES = int(os.getenv("YTDLP_RETRIES", "3"))
YOUTUBE_USE_COBALT = os.getenv("YOUTUBE_USE_COBALT", "false").strip().lower() in {"1", "true", "yes", "on"}

logger.info(
    "yt-dlp %s | format=%s | player_clients=%s",
    getattr(yt_dlp, "version", None) and yt_dlp.version.__version__,
    YTDLP_FORMAT,
    YTDLP_PLAYER_CLIENTS,
)

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
            def _attempt(retry_opts: dict, label: str) -> Optional[dict]:
                try:
                    with YoutubeDL(retry_opts) as ydl:
                        return ydl.extract_info(target_url, download=True)
                except DownloadError as retry_exc:
                    logger.warning("yt-dlp retry failed (%s): %s", label, retry_exc)
                    return None

            for fallback in FALLBACK_FORMATS:
                if ydl_opts.get("format") == fallback:
                    continue
                logger.warning("yt-dlp format unavailable, retrying with %s", fallback)
                retry_opts = dict(ydl_opts)
                retry_opts["format"] = fallback
                result = _attempt(retry_opts, f"format={fallback}")
                if result:
                    return result

            for fallback in FALLBACK_FORMATS:
                logger.warning("yt-dlp format unavailable, retrying without player_client using %s", fallback)
                retry_opts = dict(ydl_opts)
                retry_opts["format"] = fallback
                retry_opts.pop("extractor_args", None)
                result = _attempt(retry_opts, f"no player_client, format={fallback}")
                if result:
                    return result

            logger.warning("yt-dlp format unavailable, retrying with automatic format selection")
            retry_opts = dict(ydl_opts)
            retry_opts.pop("format", None)
            retry_opts.pop("extractor_args", None)
            result = _attempt(retry_opts, "auto format")
            if result:
                return result
            logger.warning("yt-dlp format unavailable, attempting format-id selection")
            probe_opts = dict(ydl_opts)
            probe_opts.pop("format", None)
            probe_opts.pop("extractor_args", None)
            probe_opts["skip_download"] = True
            try:
                with YoutubeDL(probe_opts) as ydl:
                    info = ydl.extract_info(target_url, download=False)
                formats = info.get("formats") or []
                audio_formats = [
                    fmt for fmt in formats
                    if fmt.get("vcodec") == "none" and fmt.get("acodec") not in (None, "none")
                ]
                if audio_formats:
                    audio_formats.sort(key=lambda f: (f.get("abr") or 0, f.get("filesize") or 0), reverse=True)
                    best_audio_id = audio_formats[0].get("format_id")
                    if best_audio_id:
                        retry_opts = dict(ydl_opts)
                        retry_opts["format"] = best_audio_id
                        retry_opts.pop("extractor_args", None)
                        result = _attempt(retry_opts, f"format_id={best_audio_id}")
                        if result:
                            return result
            except Exception as probe_exc:
                logger.warning("yt-dlp probe failed: %s", probe_exc)
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

        if YOUTUBE_USE_COBALT:
            try:
                cobalt_result = request_preview_url(target_url)
                return PreviewFetchResult(
                    download_url=cobalt_result["download_url"],
                    headers={},
                    provider_track_id=provider_track_id or video_id,
                    file_extension=cobalt_result["file_extension"] or ".mp3",
                    local_file_path=None,
                )
            except CobaltAPIError as exc:
                logger.warning("Cobalt API failed, falling back to yt-dlp: %s", exc)

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
            "socket_timeout": YTDLP_SOCKET_TIMEOUT,
            "retries": YTDLP_RETRIES,
            "fragment_retries": YTDLP_RETRIES,
        }
        if YTDLP_AUDIO_FORMAT:
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": YTDLP_AUDIO_FORMAT,
                }
            ]
        if YTDLP_COOKIES_FROM_BROWSER:
            cookies_from_browser = _parse_cookies_from_browser(YTDLP_COOKIES_FROM_BROWSER)
            if cookies_from_browser:
                ydl_opts["cookiesfrombrowser"] = cookies_from_browser
        elif YTDLP_COOKIES_PATH:
            cookie_path = _resolve_cookie_path(YTDLP_COOKIES_PATH)
            if not cookie_path.exists():
                logger.warning("yt-dlp cookies file not found: %s (continuing without cookies)", cookie_path)
            else:
                ydl_opts["cookiefile"] = str(cookie_path)
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
