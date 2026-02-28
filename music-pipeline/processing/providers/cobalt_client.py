"""Lightweight client for the cobalt API."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


def _env_bool(var_name: str, default: bool) -> bool:
    raw = os.getenv(var_name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


COBALT_API_URL = os.getenv("COBALT_API_URL", "http://127.0.0.1:9000/")
COBALT_API_TIMEOUT = int(os.getenv("COBALT_API_TIMEOUT", "60"))
COBALT_DOWNLOAD_MODE = os.getenv("COBALT_DOWNLOAD_MODE", "audio")
COBALT_AUDIO_FORMAT = os.getenv("COBALT_AUDIO_FORMAT", "mp3")
COBALT_AUDIO_BITRATE = os.getenv("COBALT_AUDIO_BITRATE", "128")
COBALT_ALWAYS_PROXY = _env_bool("COBALT_ALWAYS_PROXY", True)
COBALT_LOCAL_PROCESSING = os.getenv("COBALT_LOCAL_PROCESSING", "disabled")
COBALT_AUTH_SCHEME = os.getenv("COBALT_API_AUTH_SCHEME", "Api-Key")
COBALT_API_KEY = os.getenv("COBALT_API_KEY")


class CobaltAPIError(RuntimeError):
    """Raised when the cobalt API returns an error response."""


def _build_headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if COBALT_API_KEY:
        scheme = COBALT_AUTH_SCHEME.strip() if COBALT_AUTH_SCHEME else "Api-Key"
        headers["Authorization"] = f"{scheme} {COBALT_API_KEY}"
    return headers


def _derive_extension(filename: Optional[str], mime_type: Optional[str]) -> str:
    if filename:
        ext = Path(filename).suffix
        if ext:
            return ext
    if mime_type == "audio/mpeg":
        return ".mp3"
    if mime_type == "audio/webm":
        return ".webm"
    if mime_type == "audio/mp4":
        return ".m4a"
    return ".mp3"


def request_preview_url(source_url: str) -> Dict[str, Optional[str]]:
    """Call cobalt's API and return the resolved download URL."""
    payload = {
        "url": source_url,
        "downloadMode": COBALT_DOWNLOAD_MODE,
        "audioFormat": COBALT_AUDIO_FORMAT,
        "audioBitrate": COBALT_AUDIO_BITRATE,
        "alwaysProxy": COBALT_ALWAYS_PROXY,
        "localProcessing": COBALT_LOCAL_PROCESSING,
    }
    api_endpoint = f"{COBALT_API_URL.rstrip('/')}/"
    try:
        response = requests.post(
            api_endpoint,
            headers=_build_headers(),
            data=json.dumps(payload),
            timeout=COBALT_API_TIMEOUT,
        )
    except requests.RequestException as exc:  # pragma: no cover - network failure path
        raise CobaltAPIError(f"Cobalt API request failed: {exc}") from exc

    if response.status_code >= 400:
        snippet = response.text[:200]
        raise CobaltAPIError(f"Cobalt API HTTP {response.status_code}: {snippet}")

    try:
        data = response.json()
    except ValueError as exc:
        raise CobaltAPIError("Cobalt API returned non-JSON response") from exc

    status = data.get("status")
    if status not in {"tunnel", "redirect"}:
        if status == "error":
            error = data.get("error") or {}
            code = error.get("code") or "unknown"
            raise CobaltAPIError(f"Cobalt API error: {code}")
        raise CobaltAPIError(f"Unsupported cobalt status: {status!r}")

    download_url = data.get("url")
    if not download_url:
        raise CobaltAPIError("Cobalt response missing download URL")

    filename = data.get("filename")
    mime_type = (data.get("output") or {}).get("type") if isinstance(data.get("output"), dict) else data.get("type")
    file_extension = _derive_extension(filename, mime_type)
    return {
        "download_url": download_url,
        "filename": filename,
        "mime_type": mime_type,
        "file_extension": file_extension,
    }


__all__ = ["request_preview_url", "CobaltAPIError"]
