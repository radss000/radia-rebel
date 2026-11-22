"""Phase 1 check: audio_features -> CLAP embedding -> position, in one process.

Runs the same processing functions as the RQ worker (jobs/tasks.py), without
PostgreSQL/Redis/Qdrant, on a folder of audio files (or synthetic tones), and
reports resident memory after every round. The process should stay flat once
CLAP and numba are warm; steady growth means a leak in the worker chain.

Usage (from music-pipeline/):
    python scripts/phase1_worker_chain_check.py --audio-dir ~/Music/samples --rounds 3
    python scripts/phase1_worker_chain_check.py --synthetic 40          # no audio files needed
    python scripts/phase1_worker_chain_check.py --synthetic 40 --no-clap  # without the CLAP checkpoint

Exit code 1 if memory grows more than --max-growth-mb between the end of the
warm-up rounds and the end of the run.
"""

from __future__ import annotations

import argparse
import gc
import os
import resource
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:  # pragma: no cover - optional
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

from processing.audio_core_extractor import extract_core_segment  # noqa: E402
from processing.audio_features import extract_audio_features  # noqa: E402
from processing.positioning import UMAPPositioner  # noqa: E402

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif"}
SAMPLE_RATE = int(os.getenv("EMBEDDING_SAMPLE_RATE", "48000"))


def rss_mb() -> float:
    """Current resident set size in MB (falls back to peak RSS)."""
    try:
        import psutil  # type: ignore

        return psutil.Process().memory_info().rss / 1e6
    except Exception:
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak / 1e6 if sys.platform == "darwin" else peak / 1e3


def synthetic_tracks(count: int, folder: Path) -> list[Path]:
    import soundfile as sf

    rng = np.random.default_rng(0)
    paths = []
    sr = 44100
    for idx in range(count):
        seconds = 75 if idx % 3 == 0 else 20  # mix of core-extraction and full-track paths
        t = np.linspace(0, seconds, sr * seconds, endpoint=False)
        base = rng.uniform(80, 800)
        tone = sum(np.sin(2 * np.pi * base * h * t) / h for h in (1, 2, 3))
        beat = (np.sin(2 * np.pi * rng.uniform(1, 3) * t) > 0.95).astype(np.float32)
        audio = 0.3 * tone / 3 + 0.2 * beat + 0.02 * rng.normal(size=t.shape)
        path = folder / f"synthetic_{idx:03d}.wav"
        sf.write(path, np.clip(audio, -1, 1).astype(np.float32), sr, subtype="PCM_24")
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--audio-dir", type=Path, help="Folder of real audio files")
    parser.add_argument("--synthetic", type=int, default=0, help="Generate N synthetic tracks instead")
    parser.add_argument("--rounds", type=int, default=3, help="Passes over the track list (first 2 = warm-up when >= 3)")
    parser.add_argument("--no-clap", action="store_true", help="Use random 512-D vectors instead of CLAP")
    parser.add_argument("--max-growth-mb", type=float, default=150.0)
    args = parser.parse_args()

    tmp = None
    if args.audio_dir:
        tracks = sorted(p for p in args.audio_dir.expanduser().iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS)
    elif args.synthetic:
        tmp = tempfile.TemporaryDirectory()
        tracks = synthetic_tracks(args.synthetic, Path(tmp.name))
    else:
        parser.error("pass --audio-dir or --synthetic N")
    if len(tracks) < 5:
        parser.error("need at least 5 tracks (UMAP minimum)")

    clap = None
    if not args.no_clap:
        from processing.embeddings.clap_singleton import get_clap_model

        t0 = time.time()
        clap = get_clap_model()
        print(f"CLAP loaded in {time.time() - t0:.1f}s")

    positioner = UMAPPositioner()
    rng = np.random.default_rng(1)
    print(f"{len(tracks)} tracks x {args.rounds} rounds, start RSS {rss_mb():.0f} MB")

    # Numba/librosa caches keep filling during the first two passes; measure after them.
    warmup_rounds = 2 if args.rounds >= 3 else 1
    warm_rss = None
    timings = {"features": [], "embedding": [], "position": []}
    for round_idx in range(1, args.rounds + 1):
        embeddings = []
        for path in tracks:
            t0 = time.time()
            features = extract_audio_features(str(path))
            timings["features"].append(time.time() - t0)
            if not features:
                print(f"  ! features failed: {path.name}")

            t0 = time.time()
            audio, _meta = extract_core_segment(str(path), target_duration=30, sr=SAMPLE_RATE)
            if clap is not None:
                vector = clap.get_audio_embedding_from_data(x=[audio], use_tensor=False)[0]
            else:
                vector = rng.normal(size=512)
            vector = np.asarray(vector, dtype=np.float32)
            embeddings.append(vector / max(np.linalg.norm(vector), 1e-12))
            timings["embedding"].append(time.time() - t0)
            del audio, features

        t0 = time.time()
        matrix = np.stack(embeddings)
        coords = positioner.fit_transform(matrix)
        quality = positioner.quality_metrics(matrix, coords)
        timings["position"].append(time.time() - t0)
        if not np.isfinite(coords).all():
            print("  ! non-finite coordinates")
            return 1
        del matrix, coords, embeddings
        gc.collect()

        current = rss_mb()
        print(
            f"round {round_idx}: RSS {current:.0f} MB | trust={quality['trustworthiness']:.3f} "
            f"recall={quality['neighbor_recall']:.3f} | UMAP {timings['position'][-1]:.1f}s"
        )
        if round_idx == warmup_rounds:
            warm_rss = current

    growth = rss_mb() - (warm_rss or 0.0)
    print(
        "median per track: features {:.2f}s, core+embedding {:.2f}s".format(
            float(np.median(timings["features"])), float(np.median(timings["embedding"]))
        )
    )
    print(f"memory growth after warm-up: {growth:+.0f} MB (limit {args.max_growth_mb:.0f} MB)")
    if tmp:
        tmp.cleanup()
    if growth > args.max_growth_mb:
        print("FAIL: memory keeps growing across rounds")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
