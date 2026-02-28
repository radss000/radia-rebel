"""Preview provider adapters for fetching audio previews.

This package exposes a registry-based interface that maps provider types
(`provider_type` stored in `audio_assets`) to adapter implementations capable
of resolving the actual preview download URL plus any request metadata (headers,
cookies, etc.).

Adapters currently implemented:
    - ``bandcamp``: scrape track pages to extract the preview MP3 URL, falling
      back to the stored ``provider_preview_url`` when available.

Additional adapters (e.g. Bandcamp, YouTube via yt-dlp) can be
registered via ``register_adapter``.
"""

from .base import PreviewAdapter, PreviewAdapterError, PreviewFetchResult, register_adapter, get_adapter
from .bandcamp import BandcampPreviewAdapter
from .youtube import YouTubePreviewAdapter

# Register default adapters at import time
register_adapter("bandcamp", BandcampPreviewAdapter())
register_adapter("discogs", BandcampPreviewAdapter())  # Discogs often links to Bandcamp previews
register_adapter("youtube_music", YouTubePreviewAdapter())

__all__ = [
    "PreviewAdapter",
    "PreviewAdapterError",
    "PreviewFetchResult",
    "register_adapter",
    "get_adapter",
]
