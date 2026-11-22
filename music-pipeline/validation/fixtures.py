"""Deterministic offline WAV fixture generation for the validation corpus."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import wave

import numpy as np

from .corpus import CorpusTrack, ValidationCorpus, load_corpus


def _pulse(time_axis: np.ndarray, sample_rate: int, recipe: dict) -> np.ndarray:
    bpm = float(recipe.get("bpm", 120.0))
    frequency = float(recipe.get("frequency", 110.0))
    brightness = float(recipe.get("brightness", 0.35))
    beat_phase = np.mod(time_axis * bpm / 60.0, 1.0)
    envelope = np.exp(-beat_phase * (8.0 + brightness * 8.0))
    carrier = np.sin(2.0 * np.pi * frequency * time_axis)
    carrier += brightness * 0.55 * np.sin(2.0 * np.pi * frequency * 2.0 * time_axis)
    carrier += brightness * 0.25 * np.sin(2.0 * np.pi * frequency * 3.0 * time_axis)
    click_samples = max(1, int(sample_rate * 0.008))
    click = (beat_phase < click_samples / sample_rate * bpm / 60.0).astype(np.float32)
    return carrier * envelope + click * (0.08 + brightness * 0.08)


def _ambient(time_axis: np.ndarray, recipe: dict) -> np.ndarray:
    root = float(recipe.get("frequency", 146.83))
    motion = float(recipe.get("motion", 0.12))
    frequencies = (root, root * 1.25, root * 1.5, root * 2.0)
    signal = sum(
        np.sin(2.0 * np.pi * frequency * time_axis + index * 0.7) / (index + 1)
        for index, frequency in enumerate(frequencies)
    )
    modulation = 0.58 + 0.42 * np.sin(2.0 * np.pi * motion * time_axis) ** 2
    return signal * modulation


def _pluck(time_axis: np.ndarray, recipe: dict) -> np.ndarray:
    bpm = float(recipe.get("bpm", 90.0))
    frequency = float(recipe.get("frequency", 196.0))
    phase = np.mod(time_axis * bpm / 60.0, 1.0)
    envelope = np.exp(-phase * float(recipe.get("decay", 7.0)))
    signal = sum(
        np.sin(2.0 * np.pi * frequency * harmonic * time_axis) / (harmonic ** 1.35)
        for harmonic in range(1, 6)
    )
    return signal * envelope


def _experimental(time_axis: np.ndarray, recipe: dict) -> np.ndarray:
    seed = int(recipe.get("seed", 1701))
    rng = np.random.default_rng(seed)
    start = float(recipe.get("frequency", 80.0))
    sweep = float(recipe.get("sweep", 620.0))
    phase = 2.0 * np.pi * (start * time_axis + sweep * time_axis * time_axis / (2.0 * time_axis[-1]))
    gated = (np.sin(2.0 * np.pi * 3.7 * time_axis) > 0.45).astype(np.float32)
    return np.sin(phase) * gated * 0.7 + rng.normal(0.0, 0.16, len(time_axis))


def synthesize_track(track: CorpusTrack, sample_rate: int, duration_seconds: float) -> np.ndarray:
    recipe = dict(track.fixture)
    sample_count = int(round(sample_rate * duration_seconds))
    time_axis = np.arange(sample_count, dtype=np.float32) / float(sample_rate)
    fixture_type = recipe.get("type")
    if fixture_type == "pulse":
        signal = _pulse(time_axis, sample_rate, recipe)
    elif fixture_type == "ambient":
        signal = _ambient(time_axis, recipe)
    elif fixture_type == "pluck":
        signal = _pluck(time_axis, recipe)
    elif fixture_type == "experimental":
        signal = _experimental(time_axis, recipe)
    else:
        raise ValueError(f"Unsupported fixture type for {track.id}: {fixture_type}")
    gain = float(recipe.get("gain", 0.72))
    fade_samples = min(int(sample_rate * 0.03), max(1, sample_count // 2))
    fade = np.ones(sample_count, dtype=np.float32)
    fade[:fade_samples] = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
    fade[-fade_samples:] = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
    return np.clip(np.asarray(signal, dtype=np.float32) * gain * fade, -0.98, 0.98)


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_fixtures(corpus: ValidationCorpus, force: bool = False) -> dict[str, str]:
    sample_rate = int(corpus.embedding_spec.get("sample_rate", 48000))
    duration = float(corpus.embedding_spec.get("fixture_duration_seconds", 6.0))
    hashes = {}
    for track in corpus.tracks:
        output_path = corpus.audio_path(track)
        if force or not output_path.exists():
            audio = synthesize_track(track, sample_rate, duration)
            hashes[track.id] = write_wav(output_path, audio, sample_rate)
        else:
            hashes[track.id] = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="validation/corpus/v1/manifest.json")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    corpus = load_corpus(args.manifest)
    hashes = generate_fixtures(corpus, force=args.force)
    print(f"Generated {len(hashes)} deterministic fixtures for {corpus.corpus_id}@{corpus.corpus_version}")


if __name__ == "__main__":
    main()
