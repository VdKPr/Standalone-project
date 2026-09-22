"""Block generators.

Each generator fills one floorplan box with Manhattan geometry in absolute nm
coordinates: ``gen(rng, box, params, library) -> Layout``. Callers clip the
result to the box.

| kind          | structure                                        | repetition            |
|---------------|--------------------------------------------------|-----------------------|
| logic         | standard-cell rows, mirrored, shared power rails | quasi-repeated        |
| sram          | mirrored bitcell array + periphery ring          | exactly periodic      |
| contact_array | regular contact grid on a diffusion plate        | exactly periodic      |
| routing       | M1 tracks with random-length segments and vias   | irregular (unique)    |
| marks         | alignment-mark-like crosses, frames, gratings    | unique                |
| fill          | dummy metal/active fill squares                  | exactly periodic      |
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from ..config import ProcessParams
from .cells import CellTemplate, Library
from .geometry import Layout, LayoutBuilder, mirror_x, mirror_y, rects, translate

Box = tuple[float, float, float, float]

PERIODIC_KINDS = frozenset({"sram", "contact_array", "fill"})


@dataclass(frozen=True)
class BlockResult:
    """Geometry of one block, plus its exact translational symmetry if it has one.

    ``lattice`` is the repeat spacing (nm) and ``interior`` the region over which
    that repeat actually holds: periphery rings, array edges and partial cells
    are excluded. Phase 3 uses both to derive the ambiguity set (Phase 0, D4)
    from the geometry instead of guessing it from pixels.
    """

    shapes: Layout
    lattice: tuple[float, float] | None = None
    interior: Box | None = None


def _ring(b: LayoutBuilder, layer: str, box: Box, width: float) -> None:
    x0, y0, x1, y1 = box
    b.add(layer, rects([x0, x0, x0, x1 - width], [y0, y1 - width, y0, y0],
                       [x1, x1, x0 + width, x1], [y0 + width, y1, y1, y1]))


def _place(b: LayoutBuilder, cell: CellTemplate, x: float, y: float, flip_y: bool) -> None:
    for layer, r in cell.shapes.items():
        if len(r):
            b.add(layer, translate(mirror_y(r, cell.height) if flip_y else r, x, y))


def logic_block(rng: np.random.Generator, box: Box, p: ProcessParams, lib: Library) -> BlockResult:
    """Rows of standard cells in random order; every other row is mirrored so rails are shared."""
    x0, y0, x1, y1 = box
    names = list(lib.cells)
    weights = np.array([lib.weights[n] for n in names])
    smallest = min(lib.cells.values(), key=lambda c: c.width)
    xs = np.ceil(x0 / p.cpp) * p.cpp  # cells sit on the global poly grid
    n_rows = int((y1 - y0) // p.cell_h)
    b = LayoutBuilder()
    x_end = xs
    for i in range(n_rows):
        ry, x = y0 + i * p.cell_h, xs
        while True:
            cell = lib.cells[names[rng.choice(len(names), p=weights)]]
            if x + cell.width > x1:
                cell = smallest
                if x + cell.width > x1:
                    break
            _place(b, cell, x, ry, flip_y=i % 2 == 1)
            x += cell.width
        x_end = x
    if n_rows:
        ys = y0 + np.arange(n_rows + 1) * p.cell_h
        b.add("M1", rects(xs, ys - p.rail_w / 2, x_end, ys + p.rail_w / 2))
    # Cell order is random, so rows repeat only approximately: no exact lattice.
    return BlockResult(b.build())


def sram_block(rng: np.random.Generator, box: Box, p: ProcessParams, lib: Library) -> BlockResult:
    """Bitcell array tiled with x/y mirroring (period 2w x 2h), surrounded by a periphery ring."""
    cell = lib.bitcell
    w, h = cell.width, cell.height
    x0, y0, x1, y1 = box
    ring = p.rail_w
    ax0, ay0 = x0 + 2 * ring, y0 + 2 * ring
    nx, ny = int((x1 - 2 * ring - ax0) // w), int((y1 - 2 * ring - ay0) // h)
    b = LayoutBuilder()
    if nx < 1 or ny < 1:
        return BlockResult(b.build())
    for layer, r in cell.shapes.items():
        if not len(r):
            continue
        variants = {(0, 0): r, (1, 0): mirror_x(r, w), (0, 1): mirror_y(r, h), (1, 1): mirror_y(mirror_x(r, w), h)}
        for (a, c), v in variants.items():
            ox, oy = ax0 + np.arange(a, nx, 2) * w, ay0 + np.arange(c, ny, 2) * h
            if not len(ox) or not len(oy):
                continue
            gx, gy = np.meshgrid(ox, oy)
            off = np.stack([gx.ravel(), gy.ravel(), gx.ravel(), gy.ravel()], axis=1)
            b.add(layer, (v[None, :, :] + off[:, None, :]).reshape(-1, 4))
    ax1, ay1 = ax0 + nx * w, ay0 + ny * h
    straps = p.sram_strap_every > 0
    if straps:
        ys = ay0 + np.arange(p.sram_strap_every, ny, p.sram_strap_every) * h
        b.add("M1", rects(ax0, ys - p.m1_w, ax1, ys + p.m1_w))
    _ring(b, "M1", (ax0 - 1.5 * ring, ay0 - 1.5 * ring, ax1 + 1.5 * ring, ay1 + 1.5 * ring), ring)
    # Mirrored tiling repeats every two cells; straps would break the y period.
    lattice = None if straps else (2 * w, 2 * h)
    return BlockResult(b.build(), lattice, (ax0, ay0, ax1, ay1))


def contact_array_block(rng: np.random.Generator, box: Box, p: ProcessParams, lib: Library) -> BlockResult:
    x0, y0, x1, y1 = box
    pc, s, ring = p.contact_array_pitch, p.contact_array_w, p.rail_w
    xs = np.arange(x0 + 2 * ring + pc / 2, x1 - 2 * ring - pc / 2 + 1e-9, pc)
    ys = np.arange(y0 + 2 * ring + pc / 2, y1 - 2 * ring - pc / 2 + 1e-9, pc)
    b = LayoutBuilder()
    if not len(xs) or not len(ys):
        return BlockResult(b.build())
    gx, gy = np.meshgrid(xs, ys)
    b.add("CONTACT", rects(gx - s / 2, gy - s / 2, gx + s / 2, gy + s / 2))
    plate = (xs[0] - pc / 2, ys[0] - pc / 2, xs[-1] + pc / 2, ys[-1] + pc / 2)
    b.add("ACTIVE", rects(*plate))
    _ring(b, "M1", (plate[0] - 1.5 * ring, plate[1] - 1.5 * ring, plate[2] + 1.5 * ring, plate[3] + 1.5 * ring), ring)
    # The uniform plate does not break the contact period; its edge does, hence interior = plate.
    return BlockResult(b.build(), (pc, pc), plate)


def routing_block(rng: np.random.Generator, box: Box, p: ProcessParams, lib: Library) -> BlockResult:
    """Unidirectional M1 routing: random-length segments on horizontal tracks, vias at some ends."""
    x0, y0, x1, y1 = box
    unit, half_w = p.cpp / 2, p.m1_w / 2
    b = LayoutBuilder()
    for y in np.arange(y0 + p.m1_pitch / 2, y1 - p.m1_pitch / 2 + 1e-9, p.m1_pitch):
        if rng.random() < 0.15:  # unused track
            continue
        x, segs = x0 + rng.integers(0, 8) * unit, []
        while True:
            length = rng.integers(3, 40) * unit
            if x + length > x1:
                break
            segs.append((x, x + length))
            x += length + rng.integers(2, 12) * unit
        if not segs:
            continue
        s = np.array(segs)
        b.add("M1", rects(s[:, 0], y - half_w, s[:, 1], y + half_w))
        vx = np.concatenate([s[rng.random(len(s)) < 0.3, 0] + half_w, s[rng.random(len(s)) < 0.3, 1] - half_w])
        b.add("CONTACT", rects(vx - half_w, y - half_w, vx + half_w, y + half_w))
    return BlockResult(b.build())


def _mark(rng: np.random.Generator, kind: str, s: float) -> Layout:
    """One mark in local coordinates [-s/2, s/2]^2."""
    b, e = LayoutBuilder(), s / 2
    t = s * rng.uniform(0.08, 0.2)
    if kind == "cross":
        b.add("M1", rects([-e, -t / 2], [-t / 2, -e], [e, t / 2], [t / 2, e]))
    elif kind == "box_in_box":
        _ring(b, "M1", (-e, -e, e, e), t)
        b.add("ACTIVE", rects(-0.18 * s, -0.18 * s, 0.18 * s, 0.18 * s))
    elif kind == "L":
        b.add("M1", rects([-e, -e], [e - t, -e], [e, -e + t], [e, e]))
    elif kind == "grating":
        n = int(rng.integers(4, 9))
        pitch = s / n
        c = -e + (np.arange(n) + 0.5) * pitch
        lines = rects(c - pitch / 4, -e, c + pitch / 4, e)
        b.add("M1", lines if rng.random() < 0.5 else lines[:, [1, 0, 3, 2]])
    elif kind == "open_frame":
        b.add("M1", rects([-e, -e, e - t], [-e, e - t, -e], [e, e, e], [-e + t, e, e]))
    shapes = b.build()
    # Random mirroring breaks the symmetry of L-shapes and open frames.
    fx, fy = rng.random() < 0.5, rng.random() < 0.5
    for layer, r in shapes.items():
        if fx:
            r = r[:, [2, 1, 0, 3]] * [-1, 1, -1, 1]
        if fy:
            r = r[:, [0, 3, 2, 1]] * [1, -1, 1, -1]
        shapes[layer] = r
    return shapes


MARK_KINDS = ("cross", "box_in_box", "L", "grating", "open_frame")


def marks_block(rng: np.random.Generator, box: Box, p: ProcessParams, lib: Library) -> BlockResult:
    """A few large, non-overlapping unique features (alignment-mark-like)."""
    x0, y0, x1, y1 = box
    b, placed = LayoutBuilder(), []
    target, clearance = int(rng.integers(2, 6)), 100.0
    for _ in range(200):
        if len(placed) == target:
            break
        s = rng.uniform(400.0, 1500.0)
        if x1 - x0 < s + 2 * clearance or y1 - y0 < s + 2 * clearance:
            continue
        cx = rng.uniform(x0 + s / 2 + clearance, x1 - s / 2 - clearance)
        cy = rng.uniform(y0 + s / 2 + clearance, y1 - s / 2 - clearance)
        bb = (cx - s / 2 - clearance, cy - s / 2 - clearance, cx + s / 2 + clearance, cy + s / 2 + clearance)
        if any(bb[0] < q[2] and q[0] < bb[2] and bb[1] < q[3] and q[1] < bb[3] for q in placed):
            continue
        placed.append(bb)
        for layer, r in _mark(rng, MARK_KINDS[rng.integers(len(MARK_KINDS))], s).items():
            b.add(layer, translate(r, cx, cy))
    return BlockResult(b.build())


def fill_block(rng: np.random.Generator, box: Box, p: ProcessParams, lib: Library) -> BlockResult:
    x0, y0, x1, y1 = box
    pf, s = p.fill_pitch, p.fill_w
    xs = np.arange(x0 + pf / 2, x1 - pf / 2 + 1e-9, pf)
    ys = np.arange(y0 + pf / 2, y1 - pf / 2 + 1e-9, pf)
    b = LayoutBuilder()
    if not len(xs) or not len(ys):
        return BlockResult(b.build())
    gx, gy = np.meshgrid(xs, ys)
    b.add("M1", rects(gx - s / 2, gy - s / 2, gx + s / 2, gy + s / 2))
    a = 0.3 * s  # staggered active fill between the metal squares
    b.add("ACTIVE", rects(gx[:-1, :-1] + pf / 2 - a, gy[:-1, :-1] + pf / 2 - a,
                          gx[:-1, :-1] + pf / 2 + a, gy[:-1, :-1] + pf / 2 + a))
    return BlockResult(b.build(), (pf, pf), (xs[0], ys[0], xs[-1], ys[-1]))


BLOCK_GENERATORS: dict[str, Callable[..., BlockResult]] = {
    "logic": logic_block,
    "sram": sram_block,
    "contact_array": contact_array_block,
    "routing": routing_block,
    "marks": marks_block,
    "fill": fill_block,
}
