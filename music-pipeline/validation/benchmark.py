"""Reproducible CLAP ranking, calibration, and 3D-quality benchmark."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from processing.positioning import UMAPPositioner
from .corpus import LABEL_RANK, LABELS, ValidationCorpus, load_corpus


def _normalize_embeddings(embeddings: np.ndarray) -> np.ndarray:
    values = np.asarray(embeddings, dtype=np.float32)
    if values.ndim != 2 or values.shape[0] < 2:
        raise ValueError("Embeddings must be a 2D matrix with at least two rows")
    if not np.isfinite(values).all():
        raise ValueError("Embeddings must be finite")
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if np.any(norms <= 0):
        raise ValueError("Embeddings must have non-zero norms")
    return values / norms


def load_embedding_artifact(path: str | Path, corpus: ValidationCorpus) -> tuple[np.ndarray, dict[str, Any]]:
    with np.load(Path(path), allow_pickle=False) as artifact:
        track_ids = tuple(str(value) for value in artifact["track_ids"].tolist())
        embeddings = np.asarray(artifact["embeddings"], dtype=np.float32)
        metadata = json.loads(str(artifact["metadata"].item()))
    if track_ids != corpus.track_ids:
        raise ValueError("Embedding artifact track order does not match the corpus manifest")
    if metadata.get("corpus_fingerprint") != corpus.fingerprint:
        raise ValueError("Embedding artifact was generated from another corpus manifest")
    if embeddings.shape[0] != len(corpus.tracks):
        raise ValueError("Embedding artifact row count does not match the corpus")
    return _normalize_embeddings(embeddings), metadata


def pair_samples(corpus: ValidationCorpus, embeddings: np.ndarray) -> list[dict[str, Any]]:
    vectors = _normalize_embeddings(embeddings)
    samples = []
    for left_index, left_id in enumerate(corpus.track_ids):
        for right_index in range(left_index + 1, len(corpus.track_ids)):
            right_id = corpus.track_ids[right_index]
            annotation = corpus.annotation_for(left_id, right_id)
            samples.append(
                {
                    "track_a": left_id,
                    "track_b": right_id,
                    "label": annotation.label,
                    "source": annotation.source,
                    "score": float(np.dot(vectors[left_index], vectors[right_index])),
                }
            )
    return samples


def _mean(values: Sequence[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def evaluate_retrieval(
    corpus: ValidationCorpus,
    embeddings: np.ndarray,
    precision_ks: Sequence[int] = (5, 10),
    recall_k: int = 10,
) -> dict[str, Any]:
    vectors = _normalize_embeddings(embeddings)
    similarity = vectors @ vectors.T
    relevance_floor = LABEL_RANK[str(corpus.annotation_protocol["relevance_floor"])]
    per_query = []
    false_positives = []

    for query_index, query_id in enumerate(corpus.track_ids):
        ranked_indices = [
            index
            for index in np.argsort(-similarity[query_index], kind="stable")
            if index != query_index
        ]
        relevant = {
            index
            for index in ranked_indices
            if LABEL_RANK[corpus.annotation_for(query_id, corpus.track_ids[index]).label] >= relevance_floor
        }
        query_metrics: dict[str, Any] = {
            "track_id": query_id,
            "relevant_count": len(relevant),
        }
        for k in precision_ks:
            effective_k = min(k, len(ranked_indices))
            hits = sum(index in relevant for index in ranked_indices[:effective_k])
            query_metrics[f"precision_at_{k}"] = hits / effective_k if effective_k else 0.0
        recall_slice = ranked_indices[: min(recall_k, len(ranked_indices))]
        query_metrics[f"recall_at_{recall_k}"] = (
            sum(index in relevant for index in recall_slice) / len(relevant) if relevant else 1.0
        )
        per_query.append(query_metrics)

        for rank, candidate_index in enumerate(recall_slice, start=1):
            candidate_id = corpus.track_ids[candidate_index]
            annotation = corpus.annotation_for(query_id, candidate_id)
            if annotation.label == "different":
                false_positives.append(
                    {
                        "query_id": query_id,
                        "candidate_id": candidate_id,
                        "rank": rank,
                        "score": float(similarity[query_index, candidate_index]),
                    }
                )

    aggregate = {
        f"precision_at_{k}": _mean([row[f"precision_at_{k}"] for row in per_query])
        for k in precision_ks
    }
    aggregate[f"recall_at_{recall_k}"] = _mean(
        [row[f"recall_at_{recall_k}"] for row in per_query]
    )
    return {
        "aggregate": aggregate,
        "per_query": per_query,
        "false_positives_at_10": sorted(
            false_positives,
            key=lambda row: (row["rank"], -row["score"], row["query_id"], row["candidate_id"]),
        ),
    }


def score_distributions(samples: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    grouped = {label: [] for label in LABELS}
    for sample in samples:
        grouped[str(sample["label"])].append(float(sample["score"]))
    distributions = {}
    for label, scores in grouped.items():
        if not scores:
            distributions[label] = {"count": 0}
            continue
        values = np.asarray(scores, dtype=np.float64)
        distributions[label] = {
            "count": len(scores),
            "min": float(values.min()),
            "p25": float(np.quantile(values, 0.25)),
            "median": float(np.median(values)),
            "p75": float(np.quantile(values, 0.75)),
            "max": float(values.max()),
            "mean": float(values.mean()),
        }
    return distributions


def _binary_metrics(samples: Sequence[Mapping[str, Any]], threshold: float, positive_floor: str) -> dict[str, float | int]:
    floor_rank = LABEL_RANK[positive_floor]
    true_positive = false_positive = true_negative = false_negative = 0
    for sample in samples:
        expected = LABEL_RANK[str(sample["label"])] >= floor_rank
        predicted = float(sample["score"]) >= threshold
        if expected and predicted:
            true_positive += 1
        elif expected:
            false_negative += 1
        elif predicted:
            false_positive += 1
        else:
            true_negative += 1
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    specificity = true_negative / (true_negative + false_positive) if true_negative + false_positive else 1.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "balanced_accuracy": (recall + specificity) / 2.0,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "true_negative": true_negative,
        "false_negative": false_negative,
    }


def _best_threshold(samples: Sequence[Mapping[str, Any]], positive_floor: str) -> tuple[float, dict[str, Any]]:
    scores = sorted({float(sample["score"]) for sample in samples})
    if not scores:
        raise ValueError("Cannot calibrate an empty sample set")
    candidates = [float(np.nextafter(scores[-1], np.inf)), *scores]
    best = None
    for threshold in candidates:
        metrics = _binary_metrics(samples, threshold, positive_floor)
        objective = (
            float(metrics["f1"]),
            float(metrics["balanced_accuracy"]),
            float(metrics["precision"]),
            threshold,
        )
        if best is None or objective > best[0]:
            best = (objective, threshold, metrics)
    assert best is not None
    return best[1], best[2]


def calibrate_thresholds(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    label_counts = {label: sum(sample["label"] == label for sample in samples) for label in LABELS}
    missing = [label for label, count in label_counts.items() if count == 0]
    if missing:
        raise ValueError(f"Calibration requires every label; missing: {', '.join(missing)}")

    thresholds = {}
    diagnostics = {}
    minimum = -1.0
    for label in ("related", "close", "very_close"):
        threshold, _ = _best_threshold(samples, label)
        threshold = max(minimum, threshold)
        thresholds[label] = float(threshold)
        diagnostics[label] = _binary_metrics(samples, threshold, label)
        minimum = threshold
    return {
        "thresholds": {
            "very_close": thresholds["very_close"],
            "close": thresholds["close"],
            "related": thresholds["related"],
        },
        "diagnostics": diagnostics,
        "label_counts": label_counts,
        "method": "nested_f1_with_monotonic_constraints_v1",
    }


def _position_quality(embeddings: np.ndarray, requested_k: int) -> dict[str, Any]:
    positioner = UMAPPositioner()
    positions = positioner.fit_transform(embeddings)
    metrics = positioner.quality_metrics(embeddings, positions, n_neighbors=requested_k)
    metrics["requested_k"] = requested_k
    return metrics


def run_benchmark(
    manifest_path: str | Path,
    embeddings_path: str | Path,
    output_path: str | Path,
    thresholds_path: str | Path,
) -> dict[str, Any]:
    corpus = load_corpus(manifest_path)
    embeddings, artifact_metadata = load_embedding_artifact(embeddings_path, corpus)
    samples = pair_samples(corpus, embeddings)
    retrieval = evaluate_retrieval(corpus, embeddings)
    calibration = calibrate_thresholds(samples)
    requested_k = int(corpus.annotation_protocol.get("neighbor_k", 10))
    position_quality = _position_quality(embeddings, requested_k)
    trust_target = float(corpus.annotation_protocol.get("minimum_trustworthiness", 0.90))
    recall_target = float(corpus.annotation_protocol.get("minimum_neighbor_recall", 0.70))
    acceptance = {
        "label_coverage": all(calibration["label_counts"].values()),
        "trustworthiness": position_quality["trustworthiness"] >= trust_target,
        "neighbor_recall": position_quality["neighbor_recall"] >= recall_target,
        "release_eligible_corpus": corpus.release_eligible,
    }
    acceptance["release_ready"] = all(acceptance.values())
    generated_at = datetime.now(timezone.utc).isoformat()
    calibration_seed = (
        f"{corpus.fingerprint}:{artifact_metadata.get('vector_sha256')}:{calibration['thresholds']}"
    )
    calibration_id = hashlib.sha256(calibration_seed.encode("utf-8")).hexdigest()[:16]
    report = {
        "schema_version": 1,
        "generated_at": generated_at,
        "corpus": {
            "id": corpus.corpus_id,
            "version": corpus.corpus_version,
            "fingerprint": corpus.fingerprint,
            "release_eligible": corpus.release_eligible,
            "track_count": len(corpus.tracks),
            "pair_count": len(samples),
            "annotation_protocol": corpus.annotation_protocol,
        },
        "embedding": artifact_metadata,
        "retrieval": retrieval,
        "score_distributions": score_distributions(samples),
        "calibration": {"id": calibration_id, **calibration},
        "positioning": position_quality,
        "targets": {
            "minimum_trustworthiness": trust_target,
            "minimum_neighbor_recall": recall_target,
        },
        "acceptance": acceptance,
        "pair_scores": samples,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    threshold_config = {
        "schema_version": 1,
        "calibration_id": calibration_id,
        "generated_at": generated_at,
        "active": bool(acceptance["release_ready"]),
        "activation_blockers": [key for key, passed in acceptance.items() if not passed],
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.corpus_version,
        "corpus_fingerprint": corpus.fingerprint,
        "model_name": artifact_metadata.get("model_name"),
        "model_version": artifact_metadata.get("model_version"),
        "vector_dimensions": artifact_metadata.get("vector_dimensions"),
        "thresholds": calibration["thresholds"],
        "method": calibration["method"],
    }
    threshold_output = Path(thresholds_path)
    threshold_output.parent.mkdir(parents=True, exist_ok=True)
    threshold_output.write_text(json.dumps(threshold_config, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="validation/corpus/v1/manifest.json")
    parser.add_argument("--embeddings", default="validation/artifacts/rebel-validation-synthetic-v1.clap.npz")
    parser.add_argument("--output", default="validation/reports/rebel-validation-synthetic-v1.json")
    parser.add_argument("--thresholds-output", default="config/similarity_thresholds.v1.json")
    args = parser.parse_args()
    report = run_benchmark(args.manifest, args.embeddings, args.output, args.thresholds_output)
    print(json.dumps({
        "retrieval": report["retrieval"]["aggregate"],
        "positioning": report["positioning"],
        "thresholds": report["calibration"]["thresholds"],
        "acceptance": report["acceptance"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
