import os
import sys
import tempfile
import time
import wave

import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from processing.audio_core_extractor import (
    extract_core_segment,
    extract_core_segment_from_array,
)


def _write_wav(path: str, audio: np.ndarray, sr: int) -> None:
    audio_clipped = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio_clipped * 32767).astype(np.int16)
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(audio_int16.tobytes())


def test_short_track_returns_full_audio():
    sample_rate = 8000
    audio = np.zeros(int(45 * sample_rate), dtype=np.float32)
    segment, meta = extract_core_segment_from_array(audio, sample_rate)
    assert meta["method"] == "full_track"
    assert len(segment) == len(audio)


def test_intro_silence_avoided():
    sample_rate = 8000
    rng = np.random.default_rng(42)
    audio = np.concatenate(
        [
            np.zeros(120 * sample_rate, dtype=np.float32),
            rng.standard_normal(240 * sample_rate, dtype=np.float32) * 0.1,
        ]
    ).astype(np.float32)
    segment, meta = extract_core_segment_from_array(audio, sample_rate)
    assert meta["start_sec"] > 60, f"Attendu > 60s, obtenu {meta['start_sec']}"
    assert meta["rms_score"] > 0.1
    assert len(segment) > 0


def test_determinism_on_same_file():
    sr = 8000
    rng = np.random.default_rng(123)
    audio = rng.standard_normal(sr * 180, dtype=np.float32) * 0.05
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        _write_wav(tmp_path, audio, sr)
        _, meta1 = extract_core_segment(tmp_path, sr=sr)
        _, meta2 = extract_core_segment(tmp_path, sr=sr)
        assert abs(meta1["start_sec"] - meta2["start_sec"]) < 1.0
    finally:
        os.unlink(tmp_path)


def test_long_track_performance():
    sample_rate = 8000
    rng = np.random.default_rng(7)
    audio = rng.standard_normal(25 * 60 * sample_rate, dtype=np.float32) * 0.1
    t0 = time.time()
    extract_core_segment_from_array(audio, sample_rate)
    assert time.time() - t0 < 10.0, "Trop lent sur track longue"


def test_audio_modules_do_not_disable_numba_jit():
    import numba

    assert os.getenv("NUMBA_DISABLE_JIT") not in {"1", "true", "True"}
    assert numba.config.DISABLE_JIT == 0
