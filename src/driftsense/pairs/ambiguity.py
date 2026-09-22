"""Ambiguity set of a target (Phase 0, D4).

If the target sits inside a periodic block, its reference footprint is
*identical* at every lattice translation that stays within the periodic
interior. Image content alone cannot tell those positions apart, so the
specification's rule applies: the ground truth is the one nearest the search
image center.

These positions come from the generator's own geometry (each block reports its
repeat spacing), not from comparing rendered pixels: the spacing is exact,
whereas a pixel comparison would need an arbitrary similarity cutoff and would
be confused by sub-pixel phase differences between copies.

Quasi-repeats (a standard-cell row whose neighbours look alike) are deliberately
*not* included. They are similar, not identical, so they stay a matcher
robustness problem rather than a labelling one.
"""
from __future__ import annotations

import numpy as np

from ..layout.render import Window
from ..layout.world import World

MAX_EQUIVALENTS = 10_000


def _containing_block(world: World, x: float, y: float):
    for blk in world.blocks:
        bx0, by0, bx1, by1 = blk.box
        if bx0 <= x < bx1 and by0 <= y < by1:
            return blk
    return None


def equivalent_locations(world: World, point: tuple[float, float], footprint_nm: float,
                         window: Window) -> list[tuple[float, float]]:
    """World positions inside ``window`` whose footprint content equals the target's.

    Always contains ``point`` itself. A position qualifies only if its whole
    footprint lies inside the periodic interior (so it excludes array edges and
    periphery rings) and inside the search window.
    """
    x, y = point
    half = footprint_nm / 2
    blk = _containing_block(world, x, y)
    if blk is None or blk.lattice is None or blk.interior is None:
        return [point]

    ix0, iy0, ix1, iy1 = blk.interior
    if not (ix0 + half <= x <= ix1 - half and iy0 + half <= y <= iy1 - half):
        return [point]  # the target's own footprint already crosses the periodic region's edge

    wx0, wy0, wx1, wy1 = window.bounds_nm
    lo_x, hi_x = max(ix0, wx0) + half, min(ix1, wx1) - half
    lo_y, hi_y = max(iy0, wy0) + half, min(iy1, wy1) - half
    lx, ly = blk.lattice
    xs = x + np.arange(np.ceil((lo_x - x) / lx), np.floor((hi_x - x) / lx) + 1) * lx
    ys = y + np.arange(np.ceil((lo_y - y) / ly), np.floor((hi_y - y) / ly) + 1) * ly
    if len(xs) * len(ys) > MAX_EQUIVALENTS:  # pathological lattice; fall back to the true position
        return [point]
    gx, gy = np.meshgrid(xs, ys)
    return [(float(a), float(b)) for a, b in zip(gx.ravel(), gy.ravel())]


def ground_truth_location(world: World, point: tuple[float, float], footprint_nm: float,
                          window: Window) -> tuple[tuple[float, float], int]:
    """Apply rule D4: of the indistinguishable positions, take the one nearest the image center.

    Returns the chosen world position and the size of the ambiguity set.
    """
    candidates = equivalent_locations(world, point, footprint_nm, window)
    cx, cy = window.center_x_nm, window.center_y_nm
    best = min(candidates, key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, p[1], p[0]))
    return best, len(candidates)
