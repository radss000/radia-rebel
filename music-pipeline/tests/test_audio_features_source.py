import os
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from processing.audio_features import extract_audio_features


def _write(path, seconds, sr=22050):
    t = np.linspace(0, seconds, sr * seconds, endpoint=False)
    sf.write(path, 0.3 * np.sin(2 * np.pi * 220 * t).astype(np.float32), sr)


def test_core_mode_keeps_full_duration_and_same_keys(monkeypatch):
    monkeypatch.delenv("AUDIO_FEATURES_SOURCE", raising=False)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "long.wav")
        _write(path, 90)
        full = extract_audio_features(path)
        core = extract_audio_features(path, source="core")
    assert set(full) == set(core)
    assert full["duration_sec"] == core["duration_sec"] == 90


def test_env_selects_mode_and_invalid_values_fall_back(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "short.wav")
        _write(path, 5)
        monkeypatch.setenv("AUDIO_FEATURES_SOURCE", "core")
        assert extract_audio_features(path)["duration_sec"] == 5
        monkeypatch.setenv("AUDIO_FEATURES_SOURCE", "nonsense")
        assert extract_audio_features(path)["duration_sec"] == 5
