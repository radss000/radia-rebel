"""Shared audio feature utilities."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import numpy as np


def normalise_feature(value: float, min_val: float, max_val: float) -> float:
    if value is None or np.isnan(value):
        return 0.5
    return float(np.clip((value - min_val) / (max_val - min_val + 1e-9), 0.0, 1.0))


def _convert_to_wav(source_path: str, sample_rate: int) -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg binary not found on PATH; install ffmpeg to decode .m4a previews.")

    tmp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_file.close()
    try:
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                source_path,
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                tmp_file.name,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        os.unlink(tmp_file.name)
        raise RuntimeError(f"ffmpeg failed to convert preview: {exc}") from exc

    return tmp_file.name


def _load_audio_with_fallback(audio_path: str, sample_rate: int):
    import librosa

    try:
        return librosa.load(audio_path, sr=sample_rate, mono=True)
    except Exception:
        converted_path = _convert_to_wav(audio_path, sample_rate)
        try:
            return librosa.load(converted_path, sr=sample_rate, mono=True)
        except Exception as exc:
            raise RuntimeError(f"Audio decode failed even after ffmpeg conversion: {exc}") from exc
        finally:
            if os.path.exists(converted_path):
                os.unlink(converted_path)


def _features_source(explicit: str | None) -> str:
    value = (explicit or os.getenv("AUDIO_FEATURES_SOURCE", "full")).strip().lower()
    return value if value in {"full", "core"} else "full"


def extract_audio_features(audio_path: str, source: str | None = None):
    """Descriptive features (tempo, energy, ...) used by the UI and fallback positions.

    ``source`` (or env ``AUDIO_FEATURES_SOURCE``): ``full`` analyses the whole file
    (historical behaviour, default); ``core`` analyses the same 30 s central
    segment as the CLAP embedding, roughly 4-8x faster on full-length tracks.
    Values differ between the two modes: do not mix them in one catalogue
    without re-running audio_features for every track.
    """
    try:
        import librosa

        y, sr = _load_audio_with_fallback(audio_path, sample_rate=22050)
        if not len(y):
            raise ValueError("Audio buffer empty")
        full_duration = librosa.get_duration(y=y, sr=sr)
        if _features_source(source) == "core":
            from processing.audio_core_extractor import extract_core_segment_from_array

            y, _meta = extract_core_segment_from_array(y, sr, target_duration=30)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        rms = librosa.feature.rms(y=y)[0]
        zcr = librosa.feature.zero_crossing_rate(y=y)[0]
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)[0]
        duration = full_duration

        energy = normalise_feature(np.mean(rms) * 4, 0, 1.5)
        danceability = normalise_feature(np.mean(zcr) * 5, 0, 2.5)
        brightness = normalise_feature(np.mean(spectral_centroid), 500, 7000)
        bass = normalise_feature(1.0 / (np.mean(rolloff) + 1e-9), 0, 0.001)
        acousticness = normalise_feature(np.mean(spectral_bandwidth), 500, 4000)
        valence = normalise_feature(np.var(y), 0.01, 0.2)

        return {
            "tempo": float(np.clip(tempo, 40, 200)),
            "energy": energy,
            "danceability": danceability,
            "brightness": brightness,
            "bass": bass,
            "acousticness": acousticness,
            "valence": valence,
            "duration_sec": int(duration),
        }
    except Exception as exc:
        raise RuntimeError(f"Audio feature extraction failed: {exc}") from exc


def derive_position(features: dict):
    energy = features.get("energy", 0.5)
    dance = features.get("danceability", 0.5)
    brightness = features.get("brightness", 0.5)
    valence = features.get("valence", 0.5)

    x = (energy - 0.5) * 400
    y = (brightness - 0.5) * 400
    z = (dance - 0.5) * 400

    color = (
        float(np.clip(energy, 0, 1)),
        float(np.clip(brightness, 0, 1)),
        float(np.clip(valence, 0, 1)),
    )

    size = 1.5 + energy * 1.5
    emissive = 0.2 + brightness * 0.8

    return (x, y, z), color, size, emissive


def load_audio_mono(audio_path: str, sample_rate: int = 22050):
    """Load mono audio at the requested sample rate with ffmpeg fallback."""
    return _load_audio_with_fallback(audio_path, sample_rate=sample_rate)


__all__ = ["extract_audio_features", "derive_position", "normalise_feature", "load_audio_mono"]
