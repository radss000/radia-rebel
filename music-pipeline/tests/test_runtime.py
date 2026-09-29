import os

from processing.runtime import configure_numba_cache


def test_configure_numba_cache_creates_writable_directory(tmp_path, monkeypatch):
    cache_dir = tmp_path / "numba-cache"
    monkeypatch.setenv("NUMBA_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("NUMBA_DISABLE_JIT", raising=False)

    configured = configure_numba_cache()

    assert configured == cache_dir
    assert cache_dir.is_dir()
    assert os.access(cache_dir, os.W_OK)
    assert os.getenv("NUMBA_DISABLE_JIT") is None
