"""Helpers for working with YouTube URLs without requiring OAuth."""

from __future__ import annotations

import re
from typing import Optional

YOUTUBE_VIDEO_ID_RE = re.compile(
    r"(?:v=|\/)([0-9A-Za-z_-]{11})",
    re.IGNORECASE,
)


def extract_video_id(url: str) -> Optional[str]:
    """Extract the canonical 11-character YouTube video id from a URL."""
    if not url:
        return None
    if "youtu.be/" in url:
        return url.rstrip("/").split("/")[-1].split("?")[0]
    match = YOUTUBE_VIDEO_ID_RE.search(url)
    if match:
        return match.group(1)
    return None


__all__ = ["extract_video_id"]
