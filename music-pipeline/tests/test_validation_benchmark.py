from pathlib import Path

import numpy as np

from validation.benchmark import (
    calibrate_thresholds,
    evaluate_retrieval,
    pair_samples,
    score_distributions,
)
from validation.corpus import LABELS, load_corpus
from validation.fixtures import synthesize_track, write_wav


MANIFEST = Path(__file__).resolve().parents[1] / "validation" / "corpus" / "v1" / "manifest.json"


def _structured_embeddings(corpus):
    family_axis = {"pulse": 0, "ambient": 1, "pluck": 2, "experimental": 3}
    identity_axis = {}
    close_axis = {}
    vectors = []
    for track in corpus.tracks:
        vector = np.zeros(40, dtype=np.float32)
        vector[family_axis[track.family]] = 1.0
        close_index = close_axis.setdefault(track.close_group, len(close_axis))
        identity_index = identity_axis.setdefault(track.identity_group, len(identity_axis))
        vector[4 + close_index] = 0.28
        vector[24 + identity_index] = 0.12
        vectors.append(vector)
    return np.asarray(vectors, dtype=np.float32)


def test_corpus_materializes_every_pair_and_every_label():
    corpus = load_corpus(MANIFEST)

    assert len(corpus.tracks) == 13
    assert len(corpus.annotations) == 78
    assert {annotation.label for annotation in corpus.annotations.values()} == set(LABELS)
    assert corpus.annotation_for("pulse_core", "pulse_core_gain").label == "very_close"
    assert corpus.annotation_for("pulse_core", "pulse_core_detuned").label == "close"
    assert corpus.annotation_for("pulse_core", "pulse_bright").label == "related"
    assert corpus.annotation_for("pulse_core", "ambient_core").label == "different"
    assert corpus.release_eligible is False


def test_fixture_generation_is_byte_reproducible(tmp_path):
    corpus = load_corpus(MANIFEST)
    track = corpus.tracks[0]
    first_audio = synthesize_track(track, sample_rate=8000, duration_seconds=0.5)
    second_audio = synthesize_track(track, sample_rate=8000, duration_seconds=0.5)

    first_hash = write_wav(tmp_path / "first.wav", first_audio, 8000)
    second_hash = write_wav(tmp_path / "second.wav", second_audio, 8000)

    assert first_hash == second_hash
    assert np.array_equal(first_audio, second_audio)


def test_ranking_metrics_and_calibration_follow_annotations():
    corpus = load_corpus(MANIFEST)
    embeddings = _structured_embeddings(corpus)
    samples = pair_samples(corpus, embeddings)
    retrieval = evaluate_retrieval(corpus, embeddings)
    calibration = calibrate_thresholds(samples)
    distributions = score_distributions(samples)

    assert retrieval["aggregate"]["precision_at_5"] > 0.55
    assert retrieval["aggregate"]["recall_at_10"] == 1.0
    assert calibration["thresholds"]["very_close"] >= calibration["thresholds"]["close"]
    assert calibration["thresholds"]["close"] >= calibration["thresholds"]["related"]
    assert all(distributions[label]["count"] > 0 for label in LABELS)


def test_calibration_rejects_missing_annotation_classes():
    samples = [
        {"label": "very_close", "score": 0.95},
        {"label": "close", "score": 0.8},
        {"label": "different", "score": 0.2},
    ]

    try:
        calibrate_thresholds(samples)
    except ValueError as error:
        assert "related" in str(error)
    else:
        raise AssertionError("Calibration should require every label")
