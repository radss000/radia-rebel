"""UMAP-based positioning helpers for the Sonic Map."""

from __future__ import annotations

import logging
import numpy as np
import umap

logger = logging.getLogger(__name__)

UMAP_PARAMS = {
    "n_components": 3,
    "n_neighbors": 15,
    "min_dist": 0.1,
    "metric": "cosine",
    "random_state": 42,
}


class UMAPPositioner:
    """Reduce CLAP embeddings to 3D positions with UMAP."""

    def __init__(self) -> None:
        self._umap_device = self._detect_umap_device()
        logger.info("UMAP device: %s", self._umap_device)

    def fit_transform(self, embeddings: np.ndarray) -> np.ndarray:
        """Fit UMAP and return normalized coordinates."""
        if embeddings.ndim != 2:
            raise ValueError("Embeddings must be a 2D array")
        num_tracks = embeddings.shape[0]
        if num_tracks < 5:
            raise ValueError("UMAP requires at least 5 tracks")

        params = dict(UMAP_PARAMS)
        if num_tracks < params["n_neighbors"]:
            params["n_neighbors"] = max(2, num_tracks - 1)

        reducer = umap.UMAP(**params)
        coords = reducer.fit_transform(embeddings)
        coords = np.asarray(coords, dtype=np.float32)
        return self.normalize_coords(coords)

    def normalize_coords(self, coords: np.ndarray) -> np.ndarray:
        """Normalize each axis independently into [-50, 50]."""
        coords = np.asarray(coords, dtype=np.float32)
        mins = coords.min(axis=0)
        maxs = coords.max(axis=0)
        spreads = maxs - mins
        coords_norm = np.zeros_like(coords, dtype=np.float32)
        for axis in range(coords.shape[1]):
            if spreads[axis] == 0:
                coords_norm[:, axis] = 0.0
            else:
                coords_norm[:, axis] = (coords[:, axis] - mins[axis]) / spreads[axis] * 100.0 - 50.0
        return coords_norm.astype(np.float32)

    def nearest_neighbor_position(
        self,
        new_embedding: np.ndarray,
        existing_embeddings: np.ndarray,
        existing_positions: np.ndarray,
        k: int = 5,
    ) -> np.ndarray:
        """Approximate a position via weighted cosine similarity."""
        if existing_embeddings.ndim != 2 or existing_positions.ndim != 2:
            raise ValueError("Existing embeddings/positions must be 2D arrays")
        if existing_embeddings.shape[0] == 0:
            raise ValueError("Existing embeddings cannot be empty")
        if existing_embeddings.shape[0] != existing_positions.shape[0]:
            raise ValueError("Embeddings and positions must have the same length")

        existing_embeddings = np.asarray(existing_embeddings, dtype=np.float32)
        existing_positions = np.asarray(existing_positions, dtype=np.float32)
        new_embedding = np.asarray(new_embedding, dtype=np.float32)

        k = min(k, existing_embeddings.shape[0])

        new_norm = np.linalg.norm(new_embedding)
        existing_norms = np.linalg.norm(existing_embeddings, axis=1)
        denom = existing_norms * new_norm
        sims = np.divide(
            existing_embeddings @ new_embedding,
            denom,
            out=np.zeros_like(existing_norms),
            where=denom > 0,
        )

        if k == existing_embeddings.shape[0]:
            top_idx = np.arange(existing_embeddings.shape[0])
        else:
            top_idx = np.argpartition(-sims, k - 1)[:k]

        weights = sims[top_idx]
        positions = existing_positions[top_idx]
        weight_sum = weights.sum()
        if weight_sum == 0:
            position = positions.mean(axis=0)
        else:
            position = np.sum(positions * weights[:, None], axis=0) / weight_sum
        return position.astype(np.float32)

    def _detect_umap_device(self) -> str:
        """Return the active UMAP device hint."""
        if _gpu_available():
            return "gpu"
        return "cpu"


def _gpu_available() -> bool:
    try:
        import cuml  # type: ignore  # noqa: F401

        return True
    except Exception:
        pass
    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except Exception:
        return False
