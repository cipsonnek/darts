"""Colour-space helpers. Optical blur, defocus and pixel integration mix *linear light*;
cameras then apply a (roughly sRGB) transfer curve. Sub-pixel edge models must therefore
be evaluated in linear space, otherwise every bright/dark edge is biased."""

from __future__ import annotations

import numpy as np

_LUT_LINEAR = None


def srgb_to_linear(v: np.ndarray | float) -> np.ndarray:
    """sRGB-encoded values in [0, 255] → linear light in [0, 1]."""
    c = np.asarray(v, dtype=np.float32) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(v: np.ndarray) -> np.ndarray:
    """Linear light in [0, 1] → sRGB-encoded values in [0, 255] (float, unclipped above)."""
    c = np.clip(np.asarray(v, dtype=np.float32), 0.0, None)
    out = np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return (out * 255.0).astype(np.float32)


def linearize_u8(image: np.ndarray) -> np.ndarray:
    """uint8 image → float32 linear light scaled to [0, 100] (lookup table)."""
    global _LUT_LINEAR
    if _LUT_LINEAR is None:
        _LUT_LINEAR = srgb_to_linear(np.arange(256)) * 100.0
    return _LUT_LINEAR[image]
