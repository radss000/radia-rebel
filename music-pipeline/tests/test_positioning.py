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


def test_nearest_neighbor_filters_invalid_and_negative_candidates():
    positioner = UMAPPositioner()
    new_embedding = np.array([1.0, 0.0], dtype=np.float32)
    existing_embeddings = np.array(
        [
            [1.0, 0.0],
            [0.8, 0.2],
            [-1.0, 0.0],
            [1.0, 0.0],
        ],
        dtype=np.float32,
    )
    existing_positions = np.array(
        [
            [10.0, 0.0, 0.0],
            [20.0, 0.0, 0.0],
            [-100.0, 0.0, 0.0],
            [np.nan, 0.0, 0.0],
        ],
        dtype=np.float32,
    )

    result = positioner.nearest_neighbor_position_with_details(
        new_embedding,
        existing_embeddings,
        existing_positions,
        k=3,
        min_similarity=0.1,
        min_neighbors=2,
    )

    assert result.neighbor_indices.tolist() == [0, 1]
    assert np.all(result.similarities > 0)
    assert 10.0 <= result.position[0] <= 20.0


def test_nearest_neighbor_rejects_insufficient_neighbors():
    positioner = UMAPPositioner()

    with np.testing.assert_raises_regex(ValueError, "Not enough valid neighbors"):
        positioner.nearest_neighbor_position(
            np.array([1.0, 0.0]),
            np.array([[1.0, 0.0], [-1.0, 0.0]]),
            np.array([[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]),
            min_similarity=0.1,
            min_neighbors=2,
        )


def test_anchor_alignment_recovers_existing_frame():
    positioner = UMAPPositioner()
    rng = np.random.default_rng(12)
    coords = rng.normal(size=(20, 3)).astype(np.float32)
    reflection = np.diag([-1.0, 1.0, 1.0]).astype(np.float32)
    target = coords @ reflection * 2.5 + np.array([10.0, -5.0, 3.0])
    anchor_indices = np.arange(12)

    aligned = positioner.align_to_anchors(coords, anchor_indices, target[anchor_indices])

    assert np.sqrt(np.mean((aligned[anchor_indices] - target[anchor_indices]) ** 2)) < 1e-4


def test_quality_metrics_report_local_topology():
    embeddings, _, _ = _make_cluster_embeddings()
    positioner = UMAPPositioner()
    positions = positioner.fit_transform(embeddings)

    metrics = positioner.quality_metrics(embeddings, positions, n_neighbors=5)

    assert metrics["trustworthiness"] >= 0.9
    assert metrics["neighbor_recall"] >= 0.5
    assert metrics["quality_k"] == 5


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
