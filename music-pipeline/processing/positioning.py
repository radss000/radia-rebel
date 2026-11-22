"""UMAP-based positioning helpers for the Sonic Map."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
import os
import numpy as np

logger = logging.getLogger(__name__)

UMAP_PARAMS = {
    "n_components": 3,
    "n_neighbors": 15,
    "min_dist": 0.1,
    "metric": "cosine",
    "random_state": 42,
}


def umap_params_for_count(num_tracks: int) -> dict[str, object]:
    params = dict(UMAP_PARAMS)
    if num_tracks < params["n_neighbors"]:
        params["n_neighbors"] = max(2, num_tracks - 1)
    return params


@dataclass(frozen=True)
class NeighborPositionResult:
    position: np.ndarray
    neighbor_indices: np.ndarray
    similarities: np.ndarray


class UMAPPositioner:
    """Reduce CLAP embeddings to 3D positions with UMAP."""

    def __init__(self, **umap_overrides: object) -> None:
        unknown = set(umap_overrides).difference(UMAP_PARAMS)
        if unknown:
            raise TypeError(f"Unsupported UMAP parameters: {', '.join(sorted(unknown))}")
        self._umap_overrides = dict(umap_overrides)
        self._umap_device = self._detect_umap_device()
        logger.info("UMAP device: %s", self._umap_device)

    def fit_transform(self, embeddings: np.ndarray) -> np.ndarray:
        """Fit UMAP and return normalized coordinates."""
        if embeddings.ndim != 2:
            raise ValueError("Embeddings must be a 2D array")
        num_tracks = embeddings.shape[0]
        if num_tracks < 5:
            raise ValueError("UMAP requires at least 5 tracks")

        params = umap_params_for_count(num_tracks)
        params.update(self._umap_overrides)
        from umap import UMAP

        reducer = UMAP(**params)
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
        min_similarity: float = 0.0,
        min_neighbors: int = 1,
    ) -> np.ndarray:
        """Approximate a position via weighted cosine similarity."""
        result = self.nearest_neighbor_position_with_details(
            new_embedding,
            existing_embeddings,
            existing_positions,
            k=k,
            min_similarity=min_similarity,
            min_neighbors=min_neighbors,
        )
        return result.position

    def nearest_neighbor_position_with_details(
        self,
        new_embedding: np.ndarray,
        existing_embeddings: np.ndarray,
        existing_positions: np.ndarray,
        k: int = 5,
        min_similarity: float = 0.0,
        min_neighbors: int = 1,
    ) -> NeighborPositionResult:
        """Return a weighted position using valid positive-similarity neighbors."""
        if existing_embeddings.ndim != 2 or existing_positions.ndim != 2:
            raise ValueError("Existing embeddings/positions must be 2D arrays")
        if existing_embeddings.shape[0] == 0:
            raise ValueError("Existing embeddings cannot be empty")
        if existing_embeddings.shape[0] != existing_positions.shape[0]:
            raise ValueError("Embeddings and positions must have the same length")

        existing_embeddings = np.asarray(existing_embeddings, dtype=np.float32)
        existing_positions = np.asarray(existing_positions, dtype=np.float32)
        new_embedding = np.asarray(new_embedding, dtype=np.float32)

        if existing_positions.shape[1] != 3:
            raise ValueError("Existing positions must contain three coordinates")
        if new_embedding.ndim != 1 or new_embedding.shape[0] != existing_embeddings.shape[1]:
            raise ValueError("New embedding dimensions must match existing embeddings")
        if k < 1 or min_neighbors < 1:
            raise ValueError("k and min_neighbors must be positive")

        valid_rows = np.isfinite(existing_embeddings).all(axis=1) & np.isfinite(existing_positions).all(axis=1)
        valid_indices = np.flatnonzero(valid_rows)
        if not len(valid_indices):
            raise ValueError("No valid positioned embeddings are available")
        valid_embeddings = existing_embeddings[valid_indices]
        valid_positions = existing_positions[valid_indices]

        new_norm = np.linalg.norm(new_embedding)
        if not np.isfinite(new_norm) or new_norm <= 0:
            raise ValueError("New embedding must have a non-zero finite norm")
        existing_norms = np.linalg.norm(valid_embeddings, axis=1)
        denom = existing_norms * new_norm
        sims = np.divide(
            valid_embeddings @ new_embedding,
            denom,
            out=np.zeros_like(existing_norms),
            where=denom > 0,
        )

        eligible = np.flatnonzero(np.isfinite(sims) & (sims > max(0.0, min_similarity)))
        if len(eligible) < min_neighbors:
            raise ValueError(
                f"Not enough valid neighbors: required {min_neighbors}, found {len(eligible)}"
            )
        ordered = eligible[np.argsort(-sims[eligible], kind="stable")]
        selected = ordered[: min(k, len(ordered))]
        if len(selected) < min_neighbors:
            raise ValueError(
                f"Not enough neighbors after top-k selection: required {min_neighbors}, found {len(selected)}"
            )

        weights = sims[selected]
        positions = valid_positions[selected]
        position = np.sum(positions * weights[:, None], axis=0) / weights.sum()
        return NeighborPositionResult(
            position=position.astype(np.float32),
            neighbor_indices=valid_indices[selected].astype(np.int64),
            similarities=weights.astype(np.float32),
        )

    def align_to_anchors(
        self,
        coords: np.ndarray,
        anchor_indices: np.ndarray,
        anchor_positions: np.ndarray,
    ) -> np.ndarray:
        """Align a new projection to existing anchor positions with Procrustes."""
        coords = np.asarray(coords, dtype=np.float32)
        anchor_indices = np.asarray(anchor_indices, dtype=np.int64)
        anchor_positions = np.asarray(anchor_positions, dtype=np.float32)
        if coords.ndim != 2 or coords.shape[1] != 3:
            raise ValueError("Coordinates must be a two-dimensional array with three axes")
        if anchor_positions.shape != (len(anchor_indices), 3):
            raise ValueError("Anchor indices and positions must have matching shapes")
        if len(anchor_indices) < 3:
            return coords.copy()
        if not np.isfinite(anchor_positions).all():
            raise ValueError("Anchor positions must be finite")

        source = coords[anchor_indices]
        source_center = source.mean(axis=0)
        target_center = anchor_positions.mean(axis=0)
        source_centered = source - source_center
        target_centered = anchor_positions - target_center
        source_energy = float(np.sum(source_centered * source_centered))
        if source_energy <= 1e-12:
            return coords.copy()

        covariance = source_centered.T @ target_centered
        left, singular_values, right_t = np.linalg.svd(covariance)
        rotation = left @ right_t
        scale = float(np.sum(singular_values) / source_energy)
        aligned = (coords - source_center) @ rotation * scale + target_center
        return aligned.astype(np.float32)

    def quality_metrics(
        self,
        embeddings: np.ndarray,
        positions: np.ndarray,
        n_neighbors: int = 10,
    ) -> dict[str, float | int]:
        """Measure local-neighbor preservation between CLAP and 3D spaces."""
        embeddings = np.asarray(embeddings, dtype=np.float32)
        positions = np.asarray(positions, dtype=np.float32)
        if embeddings.ndim != 2 or positions.ndim != 2 or positions.shape[1] != 3:
            raise ValueError("Embeddings and positions must be compatible 2D arrays")
        if len(embeddings) != len(positions):
            raise ValueError("Embeddings and positions must contain the same number of tracks")
        if len(embeddings) < 5:
            raise ValueError("Quality metrics require at least 5 tracks")
        if not np.isfinite(embeddings).all() or not np.isfinite(positions).all():
            raise ValueError("Quality metrics require finite values")

        max_neighbors = max(1, (len(embeddings) - 1) // 2)
        quality_k = min(max(1, n_neighbors), max_neighbors)
        from sklearn.manifold import trustworthiness
        from sklearn.neighbors import NearestNeighbors

        trust = float(
            trustworthiness(
                embeddings,
                positions,
                n_neighbors=quality_k,
                metric="cosine",
            )
        )

        high_neighbors = NearestNeighbors(
            n_neighbors=quality_k + 1,
            metric="cosine",
            algorithm="brute",
        ).fit(embeddings)
        low_candidate_count = min(len(embeddings) - 1, max(quality_k, math.ceil(quality_k * 1.5)))
        low_neighbors = NearestNeighbors(
            n_neighbors=low_candidate_count + 1,
            metric="euclidean",
        ).fit(positions)
        high_indices = high_neighbors.kneighbors(embeddings, return_distance=False)[:, 1:]
        low_indices = low_neighbors.kneighbors(positions, return_distance=False)[:, 1:]
        recalls = [
            len(set(high_row).intersection(low_row)) / quality_k
            for high_row, low_row in zip(high_indices, low_indices)
        ]
        return {
            "trustworthiness": trust,
            "neighbor_recall": float(np.mean(recalls)),
            "quality_k": quality_k,
            "neighbor_candidate_count": low_candidate_count,
        }

    def _detect_umap_device(self) -> str:
        """Return the active UMAP device hint."""
        configured = os.getenv("UMAP_DEVICE", "cpu").strip().lower()
        if configured not in {"cpu", "auto", "gpu"}:
            logger.warning("Unsupported UMAP_DEVICE=%s; using cpu", configured)
            return "cpu"
        if configured in {"auto", "gpu"} and _gpu_available():
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


# Backward-compatible name retained for callers created during phase 6.
SonicPositioner = UMAPPositioner


__all__ = [
    "NeighborPositionResult",
    "SonicPositioner",
    "UMAP_PARAMS",
    "UMAPPositioner",
    "umap_params_for_count",
]
