"""Runtime configuration shared by pipeline entrypoints."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def configure_numba_cache() -> Path | None:
    """Configure a writable Numba cache without disabling JIT compilation."""
    configured_path = os.getenv("NUMBA_CACHE_DIR")
    cache_dir = (
        Path(configured_path).expanduser()
        if configured_path
        else Path(tempfile.gettempdir()) / "rebel-numba-cache"
    )
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Unable to create Numba cache directory %s: %s", cache_dir, exc)
        return None
    os.environ["NUMBA_CACHE_DIR"] = str(cache_dir)
    return cache_dir


__all__ = ["configure_numba_cache"]
