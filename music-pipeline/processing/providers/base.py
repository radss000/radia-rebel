"""Abstract base classes and helpers for preview provider adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Protocol


@dataclass
class PreviewFetchResult:
    """Resolved information required to download an audio preview."""

    download_url: str
    headers: Dict[str, str]
    provider_track_id: str
    file_extension: str = ".mp3"
    license_name: Optional[str] = None
    license_url: Optional[str] = None
    license_notes: Optional[str] = None


class PreviewAdapterError(RuntimeError):
    """Raised when a provider adapter cannot resolve a preview."""


class PreviewAdapter(Protocol):
    """Protocol for provider adapters."""

    def resolve(self, *, source_url: str, preview_url: Optional[str], provider_track_id: Optional[str]) -> PreviewFetchResult:
        """Resolve a preview fetch result.

        Args:
            source_url: Canonical public URL to the track page.
            preview_url: Direct preview URL if already stored.
            provider_track_id: Provider specific identifier when available.
        """


_ADAPTER_REGISTRY: Dict[str, PreviewAdapter] = {}


def register_adapter(provider_type: str, adapter: PreviewAdapter) -> None:
    """Register an adapter instance for a given provider type."""
    provider_key = provider_type.lower()
    _ADAPTER_REGISTRY[provider_key] = adapter


def get_adapter(provider_type: str) -> PreviewAdapter:
    """Retrieve an adapter for a provider type."""
    provider_key = provider_type.lower()
    adapter = _ADAPTER_REGISTRY.get(provider_key)
    if not adapter:
        raise PreviewAdapterError(f"No adapter registered for provider '{provider_type}'")
    return adapter
