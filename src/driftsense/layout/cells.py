"""Reusable cell templates: a small standard-cell library and one SRAM bitcell.

Templates are generated once per world from their own random stream, so every
instance of a cell type is geometrically identical. Standard-cell rows are
therefore locally repetitive but globally unique (cell order is random), while
SRAM arrays are exactly periodic.

Cell-local coordinates: origin at the top-left corner, fins/M1 horizontal,
poly vertical, power rails centered on the top and bottom cell edges.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import ProcessParams
from .geometry import Layout, LayoutBuilder, rects

# name, width in contacted poly pitches, placement weight
STANDARD_CELLS = (
    ("INV_X1", 2, 0.14),
    ("INV_X2", 3, 0.07),
    ("NAND2_X1", 3, 0.13),
    ("NOR2_X1", 3, 0.11),
    ("AOI21_X1", 4, 0.10),
    ("OAI21_X1", 4, 0.08),
    ("XOR2_X1", 5, 0.06),
    ("MUX2_X1", 6, 0.07),
    ("DFF_X1", 10, 0.08),
    ("FILL_X1", 1, 0.09),
    ("FILL_X2", 2, 0.07),
)


@dataclass(frozen=True)
class CellTemplate:
    name: str
    width: float
    height: float
    shapes: Layout  # rectangles relative to the cell origin


@dataclass(frozen=True)
class Library:
    cells: dict[str, CellTemplate]
    weights: dict[str, float]
    bitcell: CellTemplate


def _diffusion_regions(p: ProcessParams) -> tuple[tuple[float, float], tuple[float, float]]:
    """NMOS (upper half) and PMOS (lower half) regions between the power rails."""
    h, keep, gap = p.cell_h, p.rail_w / 2 + p.m1_pitch / 2, p.m1_pitch / 2
    return (keep, h / 2 - gap), (h / 2 + gap, h - keep)


def _active(x0: float, x1: float, ya: float, yb: float, p: ProcessParams) -> np.ndarray:
    """Fins on the fin grid inside [ya, yb], or one planar active rectangle."""
    if p.fin_pitch > 0:
        ys = np.arange(np.ceil(ya / p.fin_pitch), np.floor(yb / p.fin_pitch) + 1) * p.fin_pitch
        return rects(x0, ys - p.fin_w / 2, x1, ys + p.fin_w / 2)
    return rects(x0, ya, x1, yb)


def build_standard_cell(rng: np.random.Generator, name: str, n_cpp: int, p: ProcessParams) -> CellTemplate:
    cpp, h = p.cpp, p.cell_h
    w = n_cpp * cpp
    filler = name.startswith("FILL")
    regions = _diffusion_regions(p)
    b = LayoutBuilder()

    # Active is pulled back from the cell edge: a diffusion break separates neighbours.
    if not filler:
        for ya, yb in regions:
            b.add("ACTIVE", _active(0.25 * cpp, w - 0.25 * cpp, ya, yb, p))

    # One gate per poly pitch; some gates are split by a gate cut at mid-cell.
    gate_y0 = p.rail_w / 2 + p.m1_pitch / 4
    gate_y1 = h - gate_y0
    cut = max(1.5 * p.gate_w, p.m1_pitch / 2)
    uncut = []
    for k in range(n_cpp):
        x = (k + 0.5) * cpp
        xa, xb = x - p.gate_w / 2, x + p.gate_w / 2
        if not filler and rng.random() < 0.3:
            b.add("POLY", rects(xa, [gate_y0, h / 2 + cut / 2], xb, [h / 2 - cut / 2, gate_y1]))
        else:
            b.add("POLY", rects(xa, gate_y0, xb, gate_y1))
            uncut.append(x)
    if filler:
        return CellTemplate(name, w, h, b.build())

    # Trench (source/drain) contacts between gates.
    for k in range(1, n_cpp):
        for ya, yb in regions:
            if rng.random() < 0.6:
                yc, half = (ya + yb) / 2, 0.3 * (yb - ya)
                b.add("CONTACT", rects(k * cpp - p.contact_w / 2, yc - half, k * cpp + p.contact_w / 2, yc + half))
    # Gate contact on one uncut gate, between the diffusion regions.
    if uncut and rng.random() < 0.7:
        x, s = rng.choice(uncut), p.contact_w
        b.add("CONTACT", rects(x - s / 2, h / 2 - s / 2, x + s / 2, h / 2 + s / 2))

    # Local M1 routing on the horizontal tracks (tracks 0 and cell_tracks are the rails).
    tracks = np.arange(1, p.cell_tracks)
    grid = np.arange(2 * n_cpp + 1) * cpp / 2
    grid = grid[(grid >= 0.25 * cpp) & (grid <= w - 0.25 * cpp)]
    if len(grid) >= 2:
        n_seg = min(len(tracks), int(rng.integers(1, 4)))
        for t in rng.choice(tracks, size=n_seg, replace=False):
            i, j = np.sort(rng.choice(len(grid), size=2, replace=False))
            y = t * p.m1_pitch
            b.add("M1", rects(grid[i], y - p.m1_w / 2, grid[j], y + p.m1_w / 2))
    return CellTemplate(name, w, h, b.build())


def build_bitcell(rng: np.random.Generator, p: ProcessParams) -> CellTemplate:
    """One SRAM bitcell. Arrays tile it with x/y mirroring, as in real SRAM macros.

    Some features touch the cell edge on purpose: after mirroring they join the
    neighbour's copy (shared contacts, continuous active), which is what real
    bitcells do.
    """
    w, h = p.sram_cell_w, p.sram_cell_h
    q = w / 4
    b = LayoutBuilder()

    if p.fin_pitch > 0:
        ys = np.arange(1, int(h // p.fin_pitch)) * p.fin_pitch
        n = min(len(ys), int(rng.integers(2, 5)))
        for y in rng.choice(ys, size=n, replace=False):
            x0, x1 = rng.choice([0.0, q]), rng.choice([3 * q, w])
            b.add("ACTIVE", rects(x0, y - p.fin_w / 2, x1, y + p.fin_w / 2))
    else:
        b.add("ACTIVE", rects([0.0, 0.4 * w], [0.1 * h, 0.6 * h], [0.6 * w, w], [0.4 * h, 0.9 * h]))

    for x in (q, 3 * q):
        ya, yb = rng.uniform(0.0, 0.3) * h, rng.uniform(0.6, 1.0) * h
        b.add("POLY", rects(x - p.gate_w / 2, ya, x + p.gate_w / 2, yb))

    sites = np.array([(0, 0.25), (0, 0.75), (0.5, 0.2), (0.5, 0.5), (0.5, 0.8), (1, 0.5)]) * [w, h]
    s = p.contact_w
    for cx, cy in sites[rng.choice(len(sites), size=int(rng.integers(3, 5)), replace=False)]:
        b.add("CONTACT", rects(cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2))

    tracks = (np.arange(int(h // p.m1_pitch)) + 0.5) * p.m1_pitch
    for y in rng.choice(tracks, size=min(2, len(tracks)), replace=False):
        x0, x1 = rng.choice([0.0, q]), rng.choice([3 * q, w])
        b.add("M1", rects(x0, y - p.m1_w / 2, x1, y + p.m1_w / 2))
    return CellTemplate("SRAM_BITCELL", w, h, b.build())


def build_library(rng: np.random.Generator, p: ProcessParams) -> Library:
    cells = {name: build_standard_cell(rng, name, n, p) for name, n, _ in STANDARD_CELLS}
    total = sum(wt for *_, wt in STANDARD_CELLS)
    weights = {name: wt / total for name, _, wt in STANDARD_CELLS}
    return Library(cells, weights, build_bitcell(rng, p))
