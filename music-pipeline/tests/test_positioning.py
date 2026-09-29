import time

import numpy as np
from sklearn.metrics import silhouette_score

from processing.positioning import UMAPPositioner


def _make_cluster_embeddings() -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    np.random.seed(42)
    cluster_centers = [np.random.randn(512) for _ in range(3)]
    embeddings = []
    labels = []
    for i, center in enumerate(cluster_centers):
        for _ in range(10):
            embeddings.append(center + np.random.randn(512) * 0.1)
            labels.append(i)
    embeddings = np.array(embeddings)
    embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    labels = np.array(labels)
    return embeddings, labels, cluster_centers


def test_umap_topology_and_normalization():
    embeddings, labels, _ = _make_cluster_embeddings()

    positioner = UMAPPositioner()
    positions = positioner.fit_transform(embeddings)

    score = silhouette_score(positions, labels)
    assert score > 0.3, f"Coherence too low: silhouette={score:.3f}"

    assert positions.min() >= -50.0
    assert positions.max() <= 50.0
    for axis in range(3):
        spread = positions[:, axis].max() - positions[:, axis].min()
        assert spread > 20.0, f"Axis {axis} too compressed: spread={spread:.1f}"


def test_umap_reproducibility():
    embeddings, _, _ = _make_cluster_embeddings()

    positioner = UMAPPositioner()
    pos1 = positioner.fit_transform(embeddings)
    pos2 = positioner.fit_transform(embeddings)
    assert np.allclose(pos1, pos2, atol=1e-5), "UMAP not reproducible"


def test_nearest_neighbor_consistency():
    embeddings, labels, cluster_centers = _make_cluster_embeddings()
    positioner = UMAPPositioner()
    positions = positioner.fit_transform(embeddings)

    new_emb = cluster_centers[0] + np.random.randn(512) * 0.05
    new_emb = new_emb / np.linalg.norm(new_emb)
    approx_pos = positioner.nearest_neighbor_position(new_emb, embeddings, positions)
    cluster0_center_pos = positions[labels == 0].mean(axis=0)
    dist = np.linalg.norm(approx_pos - cluster0_center_pos)
    assert dist < 20.0, f"Approx position too far: dist={dist:.1f}"


def test_umap_performance():
    positioner = UMAPPositioner()

    big_embeddings = np.random.randn(1000, 512)
    big_embeddings = big_embeddings / np.linalg.norm(big_embeddings, axis=1, keepdims=True)
    t0 = time.time()
    positioner.fit_transform(big_embeddings)
    assert time.time() - t0 < 60.0, "UMAP too slow (>60s)"

    t0 = time.time()
    positioner.nearest_neighbor_position(
        big_embeddings[0],
        big_embeddings[1:],
        np.random.randn(999, 3),
    )
    assert time.time() - t0 < 1.0, "Nearest-neighbor too slow (>1s)"
