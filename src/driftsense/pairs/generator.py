"""Reference/search pair generation (Phase 3).

Both images are rendered from the *same* world geometry, each at its own pixel
pitch. The search image is never a resampled copy of the reference (Phase 1, 1).

Pose model implemented here:
  * navigation drift: the search window is centered on target + drift
  * magnification error: search pitch = nominal * (1 + scale_error), default 0

Deliberately not here (Phase 4): rotation, scan distortion, blur, noise,
charging, edge roughness.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np

from ..layout.render import Window, composite, rasterize
from ..layout.world import World, generate_world
from .ambiguity import ground_truth_location


@dataclass(frozen=True)
class PairSample:
    sample_id: str
    seed: int
    preset: str
    scenario: str
    reference: np.ndarray          # float32 in [0, 1], (size, size)
    search: np.ndarray
    reference_window: Window
    search_window: Window
    gt_x: float                    # ground truth in SEARCH image pixels
    gt_y: float
    gt_x_nm: float                 # same point in world nm, after the D4 tie-break
    gt_y_nm: float
    target_x_nm: float             # where the generator actually placed the target
    target_y_nm: float
    drift_nm: tuple[float, float]
    scale_error: float
    n_equivalent: int
    target_class: str
    block_kind: str | None
    world: World

    @property
    def is_ambiguous(self) -> bool:
        return self.n_equivalent > 1


def max_drift_nm(cfg: dict) -> float:
    return max(float(s["drift_nm"][1]) for s in cfg["scenarios"].values())


def _pick_scenario(rng: np.random.Generator, scenarios: dict) -> str:
    names = list(scenarios)
    w = np.array([scenarios[n]["weight"] for n in names], dtype=float)
    return names[rng.choice(len(names), p=w / w.sum())]


def _sample_drift(rng: np.random.Generator, drift_range, max_component: float) -> tuple[float, float]:
    """Uniform direction, radius inside the scenario's range, both components in range."""
    lo, hi = float(drift_range[0]), float(drift_range[1])
    for _ in range(1000):
        r, a = rng.uniform(lo, hi), rng.uniform(0, 2 * np.pi)
        dx, dy = r * np.cos(a), r * np.sin(a)
        if abs(dx) <= max_component and abs(dy) <= max_component:
            return float(np.round(dx)), float(np.round(dy))
    raise ValueError(f"drift range {drift_range} cannot fit inside +/-{max_component} nm per axis")


def generate_pair(cfg: dict, layout_cfg: dict, seed: int, index: int = 0, preset: str | None = None,
                  target_class: str | None = None, scenario: str | None = None,
                  drift_nm: tuple[float, float] | None = None) -> PairSample:
    """Build one (reference, search) pair with its ground truth."""
    ref_cfg, search_cfg = cfg["reference"], cfg["search"]
    size = int(search_cfg["size_px"])
    ref_size, ref_pitch = int(ref_cfg["size_px"]), float(ref_cfg["pitch_nm"])
    ref_fov = ref_size * ref_pitch

    # Pose randomness is a stream of its own, so changing the pose leaves the layout untouched.
    rng = np.random.default_rng(np.random.SeedSequence([seed, 0x9051]))
    eps = float(search_cfg.get("scale_error", 0.0))
    pitch = float(search_cfg["nominal_pitch_nm"]) * (1.0 + eps)
    fov = size * pitch

    # The world must contain the search window at maximum drift, and the target's
    # own footprint must stay inside the search window.
    layout_cfg = copy.deepcopy(layout_cfg)
    layout_cfg["world"]["size_nm"] = float(cfg["world_size_nm"])
    max_fov = size * float(search_cfg["nominal_pitch_nm"]) * (1.0 + float(search_cfg.get("max_scale_error", eps)))
    limit = (layout_cfg["world"]["size_nm"] - max_fov) / 2 - max_drift_nm(cfg)
    world = generate_world(layout_cfg, seed, preset, target_class, target_limit_nm=limit)

    scenario = scenario or _pick_scenario(rng, cfg["scenarios"])
    if drift_nm is None:
        drift_nm = _sample_drift(rng, cfg["scenarios"][scenario]["drift_nm"], fov / 2 - ref_fov / 2)
    tx, ty = world.target.x_nm, world.target.y_nm

    search_window = Window(tx + drift_nm[0], ty + drift_nm[1], pitch, size)
    reference_window = Window(tx, ty, ref_pitch, ref_size)
    order, levels = layout_cfg["render"]["layer_order"], layout_cfg["render"]["gray_levels"]
    search = composite(rasterize(world.layout, search_window, int(search_cfg["supersample"])), order, levels)
    reference = composite(rasterize(world.layout, reference_window, int(ref_cfg["supersample"])), order, levels)

    (gx_nm, gy_nm), n_eq = (((tx, ty), 1) if not cfg.get("ambiguity", {}).get("enabled", True)
                            else ground_truth_location(world, (tx, ty), ref_fov, search_window))
    gt_x, gt_y = search_window.world_to_pixel(gx_nm, gy_nm)

    if reference.shape != (ref_size, ref_size) or search.shape != (size, size):
        raise AssertionError(f"image size {reference.shape} / {search.shape} != {(ref_size, ref_size)} / {(size, size)}")
    return PairSample(
        sample_id=f"pair_{index:03d}", seed=seed, preset=world.preset, scenario=scenario,
        reference=reference, search=search, reference_window=reference_window, search_window=search_window,
        gt_x=float(gt_x), gt_y=float(gt_y), gt_x_nm=gx_nm, gt_y_nm=gy_nm, target_x_nm=tx, target_y_nm=ty,
        drift_nm=drift_nm, scale_error=eps, n_equivalent=n_eq,
        target_class=world.target.target_class, block_kind=world.target.block_kind, world=world,
    )
