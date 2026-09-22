"""World assembly: floorplan -> blocks -> layout, plus target selection.

Randomness is split into independent streams (floorplan, cell library, one
stream per block, target) derived from a single seed with ``SeedSequence``.
Consequently, requesting a different target class for the same seed yields the
identical layout with a different target.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import ProcessParams, process_params
from .blocks import BLOCK_GENERATORS, PERIODIC_KINDS
from .cells import build_library
from .geometry import Layout, LayoutBuilder, clip

TARGET_CLASSES = ("unique", "quasi_repeat", "periodic")


@dataclass(frozen=True)
class Block:
    kind: str
    box: tuple[float, float, float, float]
    lattice: tuple[float, float] | None = None       # exact repeat spacing (nm), if the block has one
    interior: tuple[float, float, float, float] | None = None  # region where that repeat holds


@dataclass(frozen=True)
class Target:
    x_nm: float
    y_nm: float
    target_class: str            # heuristic class, see classify_point
    requested_class: str
    block_kind: str | None       # block containing the target point (None = isolation gap)
    boundary_distance_nm: float  # distance from the target point to its block's edge


@dataclass(frozen=True)
class World:
    seed: int
    preset: str
    params: ProcessParams
    size_nm: float
    fov_nm: float
    reference_fov_nm: float
    blocks: tuple[Block, ...]
    layout: Layout
    target: Target

    @property
    def center(self) -> tuple[float, float]:
        return self.size_nm / 2, self.size_nm / 2

    @property
    def n_rects(self) -> int:
        return sum(len(r) for r in self.layout.values())


def floorplan(rng: np.random.Generator, wcfg: dict) -> list[Block]:
    """Guillotine partition of the square world into blocks of random kind."""
    size, lo, hi = wcfg["size_nm"], wcfg["min_block_nm"], wcfg["max_block_nm"]
    kinds = list(wcfg["block_weights"])
    weights = np.array([wcfg["block_weights"][k] for k in kinds], dtype=float)
    weights /= weights.sum()
    leaves: list[tuple[float, float, float, float]] = []

    def split(box):
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        axes = [a for a, length in ((0, w), (1, h)) if length >= 2 * lo]
        if not axes or (max(w, h) <= hi and rng.random() < wcfg["stop_split_prob"]):
            leaves.append(box)
            return
        axis = 0 if 0 in axes and (w >= h or 1 not in axes) else 1
        start, length = (x0, w) if axis == 0 else (y0, h)
        cut = start + round(rng.uniform(lo, length - lo) / 10) * 10
        if axis == 0:
            split((x0, y0, cut, y1)), split((cut, y0, x1, y1))
        else:
            split((x0, y0, x1, cut)), split((x0, cut, x1, y1))

    split((0.0, 0.0, float(size), float(size)))
    g = wcfg["block_gap_nm"] / 2  # isolation spacing between blocks
    return [Block(kinds[rng.choice(len(kinds), p=weights)], (x0 + g, y0 + g, x1 - g, y1 - g))
            for x0, y0, x1, y1 in leaves]


def classify_point(x: float, y: float, blocks: tuple[Block, ...] | list[Block], half_footprint: float):
    """Heuristic difficulty class of a reference footprint centered at (x, y).

    - footprint crosses a block boundary or gap         -> unique
    - inside a periodic block (sram/contact_array/fill) -> periodic
    - inside logic                                      -> quasi_repeat
    - inside routing/marks                              -> unique

    For a periodic block the test uses its *interior* (the region where the
    repeat actually holds), not the block box: a footprint overlapping the
    array edge or periphery ring is unique, however deep inside the block it
    sits. Phase 3 derives the exact ambiguity set (Phase 0, D4) from the same
    geometry, so the label and the ground truth agree.
    """
    for blk in blocks:
        x0, y0, x1, y1 = blk.box
        if x0 <= x < x1 and y0 <= y < y1:
            rx0, ry0, rx1, ry1 = (blk.interior if blk.kind in PERIODIC_KINDS and blk.interior else blk.box)
            d = min(x - rx0, rx1 - x, y - ry0, ry1 - y)
            if d < half_footprint:
                return "unique", blk, d
            if blk.kind in PERIODIC_KINDS:
                return "periodic", blk, d
            if blk.kind == "logic":
                return "quasi_repeat", blk, d
            return "unique", blk, d
    return "unique", None, 0.0


def select_target(rng: np.random.Generator, blocks, tcfg: dict, center, fov_nm: float,
                  reference_fov_nm: float, wanted: str | None = None,
                  limit_nm: float | None = None) -> Target:
    """Rejection-sample a target point whose whole reference footprint lies inside the search FOV.

    ``limit_nm`` overrides how far from the world center the target may sit. Pair
    generation (Phase 3) passes a smaller limit so that a *drifted* search window
    still falls inside the world.
    """
    if wanted is None:
        classes = list(tcfg["class_weights"])
        w = np.array([tcfg["class_weights"][c] for c in classes], dtype=float)
        wanted = classes[rng.choice(len(classes), p=w / w.sum())]
    if wanted not in TARGET_CLASSES:
        raise ValueError(f"unknown target class {wanted!r}")
    half = reference_fov_nm / 2
    lim = fov_nm / 2 - half - tcfg["margin_nm"] if limit_nm is None else limit_nm
    if lim <= 0:
        raise ValueError(f"target limit {lim} nm leaves no room; enlarge the world or reduce the drift")
    for _ in range(tcfg["max_tries"]):
        # Integer-nm target points keep reference renders free of edge ties.
        x = float(np.round(center[0] + rng.uniform(-lim, lim)))
        y = float(np.round(center[1] + rng.uniform(-lim, lim)))
        cls, blk, d = classify_point(x, y, blocks, half)
        if cls == wanted:
            break
    # If the class is infeasible for this floorplan the last sample is kept and
    # its actual class is recorded, so the metadata never lies.
    return Target(x, y, cls, wanted, blk.kind if blk else None, float(d))


def generate_world(cfg: dict, seed: int, preset: str | None = None, target_class: str | None = None,
                   target_limit_nm: float | None = None) -> World:
    preset_name, p = process_params(cfg, preset)
    wcfg = cfg["world"]
    s_floor, s_lib, s_blocks, s_target = np.random.SeedSequence(seed).spawn(4)

    plan = floorplan(np.random.default_rng(s_floor), wcfg)
    lib = build_library(np.random.default_rng(s_lib), p)
    builder = LayoutBuilder()
    blocks = []
    for blk, s in zip(plan, s_blocks.spawn(len(plan))):
        result = BLOCK_GENERATORS[blk.kind](np.random.default_rng(s), blk.box, p, lib)
        for layer, r in result.shapes.items():
            builder.add(layer, clip(r, blk.box))
        blocks.append(Block(blk.kind, blk.box, result.lattice, result.interior))

    size = float(wcfg["size_nm"])
    target = select_target(np.random.default_rng(s_target), blocks, cfg["target"], (size / 2, size / 2),
                           wcfg["fov_nm"], wcfg["reference_fov_nm"], target_class, target_limit_nm)
    return World(seed, preset_name, p, size, wcfg["fov_nm"], wcfg["reference_fov_nm"],
                 tuple(blocks), builder.build(), target)
