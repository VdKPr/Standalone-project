"""Phase 2 validation: coordinate convention, exact ground truth, determinism, geometry, repetition."""
from pathlib import Path

import numpy as np
import pytest

from driftsense.config import load_config, process_params
from driftsense.layout import LAYERS, Window, generate_world, rasterize, rects
from driftsense.layout.blocks import BLOCK_GENERATORS
from driftsense.layout.cells import build_library

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "layout_v1.yaml"


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG)


def _single(layer_rects, layer="M1"):
    return {k: (layer_rects if k == layer else np.empty((0, 4))) for k in LAYERS}


def _centroid(cov):
    m = cov.sum()
    return (np.arange(cov.shape[1]) * cov.sum(0)).sum() / m, (np.arange(cov.shape[0]) * cov.sum(1)).sum() / m


def test_window_convention_center_and_roundtrip():
    w = Window(1234.0, 5678.0, 10.0, 1000)
    assert w.world_to_pixel(1234.0, 5678.0) == (499.5, 499.5)
    x, y = w.pixel_to_world(*w.world_to_pixel(1500.3, 4000.7))
    assert x == pytest.approx(1500.3) and y == pytest.approx(4000.7)
    # pixel 0 spans [left, left + pitch]: its center is half a pitch inside the left edge
    left, top, _, _ = w.bounds_nm
    assert w.pixel_to_world(0, 0) == pytest.approx((left + 5.0, top + 5.0))


def test_rasterized_rect_centroid_matches_world_to_pixel():
    """A pixel-aligned rectangle must land exactly where world_to_pixel says (no half-pixel bias, x/y not swapped)."""
    w = Window(1000.0, 2000.0, 10.0, 100)  # left edge 500 nm, top edge 1500 nm
    cov = rasterize(_single(rects(1100.0, 2300.0, 1180.0, 2420.0)), w, supersample=4)["M1"]
    ex, ey = w.world_to_pixel(1140.0, 2360.0)
    assert _centroid(cov) == pytest.approx((ex, ey), abs=1e-9)
    assert (ex, ey) == (63.5, 85.5)


def test_subpixel_rect_area_is_exact_on_subgrid():
    w = Window(1000.0, 2000.0, 10.0, 100)
    # edges on the 2.5 nm sub-pixel grid
    cov = rasterize(_single(rects(1102.5, 2300.0, 1180.0, 2412.5)), w, supersample=4)["M1"]
    assert cov.sum() == pytest.approx(77.5 * 112.5 / 100.0)


def test_target_ground_truth_matches_rendered_marker(cfg):
    """A marker drawn at the generated target point lands at the stored search-image GT.

    The marker is rendered on a fine 1.25 nm grid, deliberately not centered on it,
    so its centroid is exact to half a fine pixel (0.0625 search px). That is far
    below the 0.5 px offsets this test exists to catch.
    """
    world = generate_world(cfg, seed=7)
    t = world.target
    search = Window(*world.center, 10.0, 1000)
    gx, gy = search.world_to_pixel(t.x_nm, t.y_nm)
    fine = Window(t.x_nm + 3.7, t.y_nm - 2.1, 1.25, 64)
    marker = _single(rects(t.x_nm - 15, t.y_nm - 15, t.x_nm + 15, t.y_nm + 15))
    fx, fy = _centroid(rasterize(marker, fine, supersample=1)["M1"])
    mx, my = search.world_to_pixel(*fine.pixel_to_world(fx, fy))
    assert (mx, my) == pytest.approx((gx, gy), abs=0.07)
    assert abs(gx - gy) > 1  # this seed must not hide an x/y swap


def test_same_seed_is_identical_and_different_seed_differs(cfg):
    a, b, c = generate_world(cfg, 11), generate_world(cfg, 11), generate_world(cfg, 12)
    assert a.target == b.target and a.blocks == b.blocks
    assert all(np.array_equal(a.layout[k], b.layout[k]) for k in LAYERS)
    assert any(len(a.layout[k]) != len(c.layout[k]) or not np.array_equal(a.layout[k], c.layout[k]) for k in LAYERS)


def test_target_class_does_not_change_layout(cfg):
    a = generate_world(cfg, 21, target_class="unique")
    b = generate_world(cfg, 21, target_class="periodic")
    assert all(np.array_equal(a.layout[k], b.layout[k]) for k in LAYERS)


@pytest.mark.parametrize("preset", ["mature", "intermediate", "advanced"])
def test_geometry_is_valid_manhattan_and_inside_blocks(cfg, preset):
    world = generate_world(cfg, 3, preset=preset)
    for layer, r in world.layout.items():
        assert np.all(r[:, 2] > r[:, 0]) and np.all(r[:, 3] > r[:, 1]), layer
        assert np.all(r >= 0) and np.all(r <= world.size_nm), layer
    assert world.n_rects > 200  # coarse presets legitimately hold far fewer shapes


@pytest.mark.parametrize("seed", range(5))
def test_target_footprint_inside_search_fov(cfg, seed):
    world = generate_world(cfg, seed)
    t = world.target
    lo = world.size_nm / 2 - world.fov_nm / 2 + world.reference_fov_nm / 2
    hi = world.size_nm / 2 + world.fov_nm / 2 - world.reference_fov_nm / 2
    assert lo <= t.x_nm <= hi and lo <= t.y_nm <= hi


def test_requested_classes_are_achieved(cfg):
    hits = 0
    for seed in range(12):
        cls = ("unique", "quasi_repeat", "periodic")[seed % 3]
        hits += generate_world(cfg, seed, target_class=cls).target.target_class == cls
    assert hits >= 10  # a floorplan may occasionally lack a suitable block; that case is recorded, not hidden


def _block(cfg, kind, size=6000.0):
    _, p = process_params(cfg, "intermediate")
    lib = build_library(np.random.default_rng(0), p)
    return p, BLOCK_GENERATORS[kind](np.random.default_rng(1), (0.0, 0.0, size, size), p, lib)


def test_sram_is_exactly_periodic(cfg):
    p, lay = _block(cfg, "sram")
    a = rasterize(lay, Window(3000.0, 3000.0, 1.0, 1000), 1)
    b = rasterize(lay, Window(3000.0 + 2 * p.sram_cell_w, 3000.0 + 2 * p.sram_cell_h, 1.0, 1000), 1)
    assert all(np.array_equal(a[k], b[k]) for k in LAYERS)


def test_logic_is_not_periodic(cfg):
    p, lay = _block(cfg, "logic")
    a = rasterize(lay, Window(3000.0, 3000.0, 1.0, 1000), 1)
    b = rasterize(lay, Window(3000.0, 3000.0 + 2 * p.cell_h, 1.0, 1000), 1)
    assert not all(np.array_equal(a[k], b[k]) for k in LAYERS)
