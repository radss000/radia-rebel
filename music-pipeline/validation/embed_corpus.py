"""Generate versioned CLAP embeddings for an offline validation corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
import numpy as np

from processing.audio_core_extractor import extract_core_segment
from processing.embeddings.clap_singleton import get_clap_model
from .corpus import load_corpus
from .fixtures import generate_fixtures

PIPELINE_ROOT = Path(__file__).resolve().parents[1]


def _configure_environment(allow_model_downloads: bool = False) -> None:
    load_dotenv(PIPELINE_ROOT / ".env", override=False)
    if not allow_model_downloads:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    checkpoint = os.getenv("CLAP_CHECKPOINT_PATH")
    if checkpoint and not Path(checkpoint).is_absolute():
        os.environ["CLAP_CHECKPOINT_PATH"] = str((PIPELINE_ROOT / checkpoint).resolve())


def embed_corpus(
    manifest_path: str | Path,
    output_path: str | Path,
    batch_size: int = 4,
    allow_model_downloads: bool = False,
) -> dict:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    _configure_environment(allow_model_downloads=allow_model_downloads)
    corpus = load_corpus(manifest_path)
    audio_hashes = generate_fixtures(corpus)
    sample_rate = int(corpus.embedding_spec.get("sample_rate", 48000))
    target_duration = int(corpus.embedding_spec.get("segment_duration_seconds", 30))

    audio_buffers = []
    segment_metadata = {}
    for track in corpus.tracks:
        audio, metadata = extract_core_segment(
            str(corpus.audio_path(track)),
            target_duration=target_duration,
            sr=sample_rate,
        )
        if audio is None or not len(audio):
            raise ValueError(f"Empty audio fixture: {track.id}")
        audio_buffers.append(audio)
        segment_metadata[track.id] = metadata

    try:
        model = get_clap_model()
    except OSError as exc:
        raise RuntimeError(
            "CLAP validation runs offline by default, but required tokenizer files are not cached. "
            "Pre-cache bert-base-uncased, roberta-base and facebook/bart-base, or rerun with "
            "--allow-model-downloads when a connection is available."
        ) from exc
    vectors = []
    for start in range(0, len(audio_buffers), batch_size):
        batch = audio_buffers[start : start + batch_size]
        result = model.get_audio_embedding_from_data(x=batch, use_tensor=False)
        vectors.extend(np.asarray(result, dtype=np.float32))
    embeddings = np.asarray(vectors, dtype=np.float32)
    if embeddings.ndim != 2 or embeddings.shape[0] != len(corpus.tracks):
        raise ValueError(f"Unexpected CLAP embedding shape: {embeddings.shape}")
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    if not np.isfinite(embeddings).all() or np.any(norms <= 0):
        raise ValueError("CLAP returned invalid embeddings")
    embeddings = embeddings / norms

    vector_hash = hashlib.sha256(embeddings.tobytes()).hexdigest()
    metadata = {
        "schema_version": 1,
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.corpus_version,
        "corpus_fingerprint": corpus.fingerprint,
        "model_name": os.getenv("CLAP_MODEL_NAME", corpus.embedding_spec.get("model_name", "clap-htsat-base")),
        "model_version": os.getenv("CLAP_MODEL_VERSION", corpus.embedding_spec.get("model_version", "1.0")),
        "checkpoint": Path(os.environ["CLAP_CHECKPOINT_PATH"]).name,
        "sample_rate": sample_rate,
        "segment_strategy": corpus.embedding_spec.get("segment_strategy", "full_short_fixture"),
        "vector_dimensions": int(embeddings.shape[1]),
        "vector_sha256": vector_hash,
        "audio_sha256": audio_hashes,
        "segments": segment_metadata,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        track_ids=np.asarray(corpus.track_ids),
        embeddings=embeddings,
        metadata=np.asarray(json.dumps(metadata, sort_keys=True)),
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="validation/corpus/v1/manifest.json")
    parser.add_argument("--output", default="validation/artifacts/rebel-validation-synthetic-v1.clap.npz")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--allow-model-downloads", action="store_true")
    args = parser.parse_args()
    metadata = embed_corpus(
        args.manifest,
        args.output,
        batch_size=args.batch_size,
        allow_model_downloads=args.allow_model_downloads,
    )
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
