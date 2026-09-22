"""Manhattan layout geometry.

World coordinates are in nm with x to the right and y *downward* (the same
orientation as image rows), so the world -> pixel map never flips an axis.
Every shape is an axis-aligned rectangle ``(x0, y0, x1, y1)`` with x0 < x1 and
y0 < y1; a set of shapes is an ``(N, 4)`` float64 array.
"""
from __future__ import annotations

import numpy as np

LAYERS = ("ACTIVE", "POLY", "CONTACT", "M1")

Layout = dict[str, np.ndarray]  # layer name -> (N, 4) rectangles


def rects(x0, y0, x1, y1) -> np.ndarray:
    """Build an (N, 4) rectangle array; scalar and array arguments broadcast."""
    cols = np.broadcast_arrays(*(np.asarray(v, dtype=np.float64) for v in (x0, y0, x1, y1)))
    return np.stack([c.ravel() for c in cols], axis=1)


def translate(r: np.ndarray, dx: float, dy: float) -> np.ndarray:
    return r + np.array([dx, dy, dx, dy])


def mirror_x(r: np.ndarray, width: float) -> np.ndarray:
    """Mirror shapes about the vertical center line of a cell of the given width."""
    return np.column_stack([width - r[:, 2], r[:, 1], width - r[:, 0], r[:, 3]])


def mirror_y(r: np.ndarray, height: float) -> np.ndarray:
    """Mirror shapes about the horizontal center line of a cell of the given height."""
    return np.column_stack([r[:, 0], height - r[:, 3], r[:, 2], height - r[:, 1]])


def clip(r: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    """Clip shapes to a box and drop the ones that vanish."""
    x0, y0, x1, y1 = box
    out = np.column_stack([
        np.maximum(r[:, 0], x0), np.maximum(r[:, 1], y0),
        np.minimum(r[:, 2], x1), np.minimum(r[:, 3], y1),
    ])
    return out[(out[:, 2] > out[:, 0]) & (out[:, 3] > out[:, 1])]


class LayoutBuilder:
    """Accumulates rectangle arrays per layer."""

    def __init__(self) -> None:
        self._parts: dict[str, list[np.ndarray]] = {name: [] for name in LAYERS}

    def add(self, layer: str, r: np.ndarray) -> None:
        r = np.asarray(r, dtype=np.float64).reshape(-1, 4)
        if len(r):
            self._parts[layer].append(r)

    def add_layout(self, layout: Layout) -> None:
        for layer, r in layout.items():
            self.add(layer, r)

    def build(self) -> Layout:
        return {k: np.concatenate(v) if v else np.empty((0, 4)) for k, v in self._parts.items()}
