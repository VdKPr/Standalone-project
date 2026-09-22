"""Window definition (the single source of the pixel-coordinate convention) and rasterization.

Convention (Phase 0, section 1): pixel column c has its center at
``x = center_x + (c - (size - 1) / 2) * pitch`` and covers ``pitch / 2`` on
either side, and the same holds for rows and y. Consequently, the
geometric image center is ``((size - 1) / 2, (size - 1) / 2) = (499.5, 499.5)``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import Layout

LAYER_COLORS = {
    "ACTIVE": (0.20, 0.70, 0.30),
    "POLY": (0.85, 0.20, 0.20),
    "CONTACT": (1.00, 0.85, 0.10),
    "M1": (0.25, 0.45, 0.95),
}


@dataclass(frozen=True)
class Window:
    """A square image window onto the world."""

    center_x_nm: float
    center_y_nm: float
    pitch_nm: float
    size_px: int = 1000

    def world_to_pixel(self, x_nm, y_nm):
        h = (self.size_px - 1) / 2
        return (x_nm - self.center_x_nm) / self.pitch_nm + h, (y_nm - self.center_y_nm) / self.pitch_nm + h

    def pixel_to_world(self, x_px, y_px):
        h = (self.size_px - 1) / 2
        return self.center_x_nm + (x_px - h) * self.pitch_nm, self.center_y_nm + (y_px - h) * self.pitch_nm

    @property
    def bounds_nm(self) -> tuple[float, float, float, float]:
        """Outer edges (left, top, right, bottom) of the window."""
        half = self.size_px * self.pitch_nm / 2
        return (self.center_x_nm - half, self.center_y_nm - half,
                self.center_x_nm + half, self.center_y_nm + half)


def rasterize(layout: Layout, window: Window, supersample: int = 4) -> dict[str, np.ndarray]:
    """Per-layer area coverage in [0, 1], shape (size_px, size_px), float32.

    Each pixel is split into supersample x supersample sub-pixels. A sub-pixel
    is inside a rectangle if its center satisfies x0 <= x < x1 (and likewise
    for y). Coverage is the mean over sub-pixels, i.e. a box-filtered area
    estimate. It is exact when edges fall on the sub-pixel grid and otherwise
    off by at most half a sub-pixel per edge.
    """
    n = window.size_px * supersample
    step = window.pitch_nm / supersample
    left, top, right, bottom = window.bounds_nm
    out = {}
    for layer, r in layout.items():
        mask = np.zeros((n, n), dtype=bool)
        if len(r):
            r = r[(r[:, 2] > left) & (r[:, 0] < right) & (r[:, 3] > top) & (r[:, 1] < bottom)]
            # sub-pixel j has center left + (j + 0.5) * step
            c0 = np.clip(np.ceil((r[:, 0] - left) / step - 0.5), 0, n).astype(np.int64)
            c1 = np.clip(np.ceil((r[:, 2] - left) / step - 0.5), 0, n).astype(np.int64)
            r0 = np.clip(np.ceil((r[:, 1] - top) / step - 0.5), 0, n).astype(np.int64)
            r1 = np.clip(np.ceil((r[:, 3] - top) / step - 0.5), 0, n).astype(np.int64)
            for a, b, c, d in zip(r0, r1, c0, c1):
                mask[a:b, c:d] = True
        s = window.size_px
        out[layer] = mask.reshape(s, supersample, s, supersample).mean(axis=(1, 3), dtype=np.float32)
    return out


def composite(coverage: dict[str, np.ndarray], layer_order, gray_levels: dict[str, float]) -> np.ndarray:
    """Grayscale layout image: layers painted bottom-to-top, alpha = coverage.

    This is a clean *layout* rendering, not an SEM image. SEM contrast, blur
    and noise come in Phase 3/4.
    """
    shape = next(iter(coverage.values())).shape
    img = np.full(shape, gray_levels["background"], dtype=np.float32)
    for layer in layer_order:
        a = coverage[layer]
        img = img * (1 - a) + gray_levels[layer] * a
    return img


def colorize(coverage: dict[str, np.ndarray], layer_order, background=(0.08, 0.08, 0.10), alpha: float = 0.75) -> np.ndarray:
    """Layout-editor style RGB view for inspection."""
    shape = next(iter(coverage.values())).shape
    img = np.empty((*shape, 3), dtype=np.float32)
    img[:] = background
    for layer in layer_order:
        a = (alpha * coverage[layer])[..., None]
        img = img * (1 - a) + np.asarray(LAYER_COLORS[layer], dtype=np.float32) * a
    return img
