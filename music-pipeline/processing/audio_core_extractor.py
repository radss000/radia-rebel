"""Extract a representative core segment from an audio track."""

from __future__ import annotations

import logging
from typing import Dict, Tuple

import numpy as np

logger = logging.getLogger(__name__)

WINDOW_SEC = 5
LONG_TRACK_SEC = 20 * 60


class AudioLoadError(RuntimeError):
    """Raised when librosa cannot load an audio file."""


def _load_audio_mono(audio_path: str, sr: int) -> np.ndarray:
    """Load audio as mono float32 at ``sr``.

    Mirrors ``librosa.load(path, sr=sr, mono=True)`` (soundfile decode, channel
    mean, soxr "HQ" resampling) without importing librosa, so WAV/FLAC/OGG
    (any bit depth) load fast and produce the same samples as the librosa path.
    Formats libsndfile cannot decode fall back to librosa/audioread.
    """
    try:
        import soundfile as sf

        audio, file_sr = sf.read(audio_path, dtype="float32", always_2d=True)
    except Exception:
        import librosa

        audio, _ = librosa.load(audio_path, sr=sr, mono=True)
        return np.asarray(audio, dtype=np.float32)

    audio = audio.mean(axis=1) if audio.shape[1] > 1 else audio[:, 0]
    if file_sr != sr and audio.size > 1:
        import soxr

        target_len = int(np.ceil(audio.shape[0] * (float(sr) / file_sr)))
        audio = soxr.resample(audio, file_sr, sr, quality="HQ")
        # Same length convention as librosa.resample (ceil + pad/trim).
        if audio.shape[0] < target_len:
            audio = np.pad(audio, (0, target_len - audio.shape[0]))
        audio = audio[:target_len]
    return np.ascontiguousarray(audio, dtype=np.float32)


def extract_core_segment(
    audio_path: str,
    target_duration: int = 30,
    sr: int = 48000,
) -> Tuple[np.ndarray, Dict[str, float | str]]:
    try:
        audio = _load_audio_mono(audio_path, sr)
    except Exception as exc:
        raise AudioLoadError(f"Cannot load audio: {audio_path}") from exc
    return extract_core_segment_from_array(audio, sr, target_duration=target_duration)


def extract_core_segment_from_array(
    audio: np.ndarray,
    sr: int,
    target_duration: int = 30,
) -> Tuple[np.ndarray, Dict[str, float | str]]:
    total_samples = int(len(audio))
    total_sec = float(total_samples) / float(sr) if sr else 0.0
    if total_sec <= 0.0:
        metadata = {
            "start_sec": 0.0,
            "end_sec": 0.0,
            "rms_score": 0.0,
            "method": "full_track",
        }
        logger.info("Core segment: 0.0s-0.0s (score=0.000, method=full_track)")
        return audio, metadata

    if total_sec < 60.0:
        metadata = {
            "start_sec": 0.0,
            "end_sec": total_sec,
            "rms_score": 0.0,
            "method": "full_track",
        }
        logger.info(
            "Core segment: %.1fs-%.1fs (score=0.000, method=full_track)",
            metadata["start_sec"],
            metadata["end_sec"],
        )
        return audio, metadata

    window_samples = int(WINDOW_SEC * sr)
    if window_samples <= 0:
        raise ValueError("Invalid sample rate for core extraction")

    window_count = total_samples // window_samples
    if window_count == 0:
        metadata = {
            "start_sec": 0.0,
            "end_sec": total_sec,
            "rms_score": 0.0,
            "method": "full_track",
        }
        logger.info(
            "Core segment: %.1fs-%.1fs (score=0.000, method=full_track)",
            metadata["start_sec"],
            metadata["end_sec"],
        )
        return audio, metadata

    trimmed = audio[: window_count * window_samples]
    frames = trimmed.reshape(window_count, window_samples)
    rms_values = np.sqrt(np.mean(frames * frames, axis=1))

    rms_max_global = float(np.max(rms_values)) if rms_values.size else 0.0
    if rms_max_global <= 0.0:
        rms_max_global = 1e-8

    valid_start_sec = total_sec * 0.1
    valid_end_sec = total_sec * 0.9
    candidate_duration = float(target_duration)
    if valid_end_sec - valid_start_sec < candidate_duration:
        metadata = {
            "start_sec": 0.0,
            "end_sec": total_sec,
            "rms_score": 0.0,
            "method": "full_track",
        }
        logger.info(
            "Core segment: %.1fs-%.1fs (score=0.000, method=full_track)",
            metadata["start_sec"],
            metadata["end_sec"],
        )
        return audio, metadata

    start_window_min = int(np.ceil(valid_start_sec / WINDOW_SEC))
    start_window_max = int(np.floor((valid_end_sec - candidate_duration) / WINDOW_SEC))
    if start_window_max < start_window_min:
        metadata = {
            "start_sec": 0.0,
            "end_sec": total_sec,
            "rms_score": 0.0,
            "method": "full_track",
        }
        logger.info(
            "Core segment: %.1fs-%.1fs (score=0.000, method=full_track)",
            metadata["start_sec"],
            metadata["end_sec"],
        )
        return audio, metadata

    windows_per_candidate = max(1, int(np.ceil(candidate_duration / WINDOW_SEC)))
    step_sec = 30 if total_sec > LONG_TRACK_SEC else WINDOW_SEC
    step_windows = max(1, int(round(step_sec / WINDOW_SEC)))

    candidates: list[tuple[int, float, float]] = []
    for start_window in range(start_window_min, start_window_max + 1, step_windows):
        end_window = start_window + windows_per_candidate
        if end_window > len(rms_values):
            break
        window_rms = rms_values[start_window:end_window]
        if window_rms.size == 0:
            continue
        candidates.append(
            (start_window, float(np.mean(window_rms)), float(np.std(window_rms)))
        )

    if not candidates:
        metadata = {
            "start_sec": 0.0,
            "end_sec": total_sec,
            "rms_score": 0.0,
            "method": "full_track",
        }
        logger.info(
            "Core segment: %.1fs-%.1fs (score=0.000, method=full_track)",
            metadata["start_sec"],
            metadata["end_sec"],
        )
        return audio, metadata

    rms_std_max_global = max(std for _, _, std in candidates)
    if rms_std_max_global <= 0.0:
        rms_std_max_global = 1e-8

    best_start = candidates[0][0]
    best_score = -1.0
    for start_window, rms_mean, rms_std in candidates:
        rms_norm = rms_mean / rms_max_global
        variance_norm = rms_std / (rms_std_max_global + 1e-8)
        score = 0.7 * rms_norm + 0.3 * (1.0 - variance_norm)
        if score > best_score:
            best_score = score
            best_start = start_window

    start_sec = float(best_start * WINDOW_SEC)
    end_sec = min(start_sec + candidate_duration, total_sec)
    start_sample = int(start_sec * sr)
    end_sample = int(end_sec * sr)
    segment = audio[start_sample:end_sample]
    metadata = {
        "start_sec": start_sec,
        "end_sec": end_sec,
        "rms_score": float(best_score),
        "method": "rms_core",
    }
    logger.info(
        "Core segment: %.1fs-%.1fs (score=%.3f, method=%s)",
        start_sec,
        end_sec,
        best_score,
        metadata["method"],
    )
    return segment, metadata
