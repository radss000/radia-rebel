"""CLAP model singleton for RQ workers."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from types import MethodType
from typing import Optional


_CLAP_MODEL = None


def _patch_clap_state_dict_loader(model) -> None:
    """Strip incompatible keys before laion-clap loads checkpoints."""
    if getattr(model, "_patched_state_dict_loader", False):
        return

    original_loader = model.model.load_state_dict

    def _safe_load_state_dict(self, state_dict, strict=True):
        if "text_branch.embeddings.position_ids" in state_dict:
            state_dict = dict(state_dict)
            state_dict.pop("text_branch.embeddings.position_ids", None)
        return original_loader(state_dict, strict=strict)

    model.model.load_state_dict = MethodType(_safe_load_state_dict, model.model)
    setattr(model, "_patched_state_dict_loader", True)


def _detect_device() -> str:
    forced = os.getenv("CLAP_DEVICE")
    if forced:
        return forced.lower()

    try:
        import torch
    except ImportError:  # pragma: no cover - optional dependency
        return "cpu"

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _load_clap_from_config():
    try:
        from laion_clap import CLAP_Module  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("laion-clap not installed; pip install laion-clap to enable embeddings") from exc

    clap_amodel = os.getenv("CLAP_AMODEL", "HTSAT-base")
    clap_enable_fusion = os.getenv("CLAP_ENABLE_FUSION", "false").lower() == "true"
    clap_checkpoint_path = os.getenv("CLAP_CHECKPOINT_PATH")

    if not clap_checkpoint_path:
        raise ValueError("CLAP_CHECKPOINT_PATH non défini — voir INSTALL.md")

    ckpt_path = Path(clap_checkpoint_path).expanduser()
    if not ckpt_path.exists():
        raise FileNotFoundError(f"CLAP checkpoint introuvable: {ckpt_path}")

    model = CLAP_Module(enable_fusion=clap_enable_fusion, amodel=clap_amodel)
    _patch_clap_state_dict_loader(model)
    model.load_ckpt(str(ckpt_path))

    device = _detect_device()
    if device == "cpu":
        return model, device

    try:
        model.to(device)
    except Exception:  # pragma: no cover - device move optional
        device = "cpu"

    logging.info("CLAP checkpoint: %s", ckpt_path.name)
    return model, device


def get_clap_model():
    global _CLAP_MODEL
    if _CLAP_MODEL is None:
        t0 = time.time()
        model, device = _load_clap_from_config()
        _CLAP_MODEL = model
        dt_ms = int((time.time() - t0) * 1000)
        logging.info("CLAP model loaded on %s in %dms", device, dt_ms)
        logging.info("CLAP ready on %s", device)
    return _CLAP_MODEL
