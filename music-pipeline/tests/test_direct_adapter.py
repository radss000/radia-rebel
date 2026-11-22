import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from processing.providers import PreviewAdapterError, get_adapter


def test_other_provider_has_an_adapter():
    adapter = get_adapter("other")
    result = adapter.resolve(
        source_url="https://cdn.example.com/uploads/track-123.flac",
        preview_url=None,
        provider_track_id="mongo-abc123",
    )
    assert result.download_url == "https://cdn.example.com/uploads/track-123.flac"
    assert result.file_extension == ".flac"
    assert result.provider_track_id == "mongo-abc123"


def test_preview_url_wins_and_ids_are_path_safe():
    result = get_adapter("other").resolve(
        source_url="https://example.com/page",
        preview_url="http://127.0.0.1:8765/a/b.wav?sig=1",
        provider_track_id="../../etc/passwd",
    )
    assert result.download_url.startswith("http://127.0.0.1:8765/a/b.wav")
    assert result.file_extension == ".wav"
    assert "/" not in result.provider_track_id and not result.provider_track_id.startswith(".")


def test_unknown_extension_and_missing_id_fall_back():
    result = get_adapter("other").resolve(source_url="https://example.com/stream", preview_url=None, provider_track_id=None)
    assert result.file_extension == ".mp3"
    assert len(result.provider_track_id) == 64


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/a.mp3", ""])
def test_rejects_non_http_urls(url):
    with pytest.raises(PreviewAdapterError):
        get_adapter("other").resolve(source_url=url, preview_url=None, provider_track_id="x")
