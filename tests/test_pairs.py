"""Phase 3 validation: pair geometry, ground truth, ambiguity rule, determinism, dataset contract."""
from pathlib import Path

import numpy as np
import pytest

from driftsense.config import load_config
from driftsense.layout import Window, composite, rasterize
from driftsense.pairs import equivalent_locations, generate_pair

ROOT = Path(__file__).resolve().parents[1]
PAIRS_CFG = ROOT / "configs" / "pairs_v1.yaml"


@pytest.fixture(scope="module")
def cfgs():
    cfg = load_config(PAIRS_CFG)
    return cfg, load_config(ROOT / cfg["layout_config"])


def _pair(cfgs, **kw):
    cfg, layout_cfg = cfgs
    return generate_pair(cfg, layout_cfg, **kw)


@pytest.mark.parametrize("seed", [101, 202, 303])
def test_images_are_1000x1000_and_in_range(cfgs, seed):
    s = _pair(cfgs, seed=seed)
    for img in (s.reference, s.search):
        assert img.shape == (1000, 1000)
        assert img.dtype == np.float32
        assert 0.0 <= img.min() and img.max() <= 1.0


def test_reference_is_centered_on_the_target(cfgs):
    s = _pair(cfgs, seed=404)
    assert s.reference_window.world_to_pixel(s.target_x_nm, s.target_y_nm) == (499.5, 499.5)


def test_search_content_at_ground_truth_matches_the_target_neighbourhood(cfgs):
    """With a whole-pixel drift the two renders share a grid, so the crop at GT must match exactly.

    This is the end-to-end check that the stored ground truth really points at
    the target: a half-pixel error or an x/y swap breaks it.
    """
    cfg, layout_cfg = cfgs
    # An ambiguous target would move the GT to an equivalent copy, which this test is not about.
    for seed in range(505, 545):
        s = _pair(cfgs, seed=seed, drift_nm=(250.0, -430.0))  # 25 px, -43 px at 10 nm/px
        if not s.is_ambiguous:
            break
    else:
        pytest.skip("no unambiguous sample found")
    pitch = s.search_window.pitch_nm
    assert (s.gt_x, s.gt_y) == pytest.approx((499.5 - 250.0 / pitch, 499.5 + 430.0 / pitch))

    # Render the target's own neighbourhood on the search grid and compare with the crop at GT.
    size = 100
    win = Window(s.target_x_nm, s.target_y_nm, pitch, size)
    patch = composite(rasterize(s.world.layout, win, int(cfg["search"]["supersample"])),
                      layout_cfg["render"]["layer_order"], layout_cfg["render"]["gray_levels"])
    x0, y0 = int(round(s.gt_x - (size - 1) / 2)), int(round(s.gt_y - (size - 1) / 2))
    crop = s.search[y0:y0 + size, x0:x0 + size]
    assert np.array_equal(crop, patch)


def test_drift_moves_the_target_off_center(cfgs):
    s = _pair(cfgs, seed=606, scenario="large_drift")
    offset = np.hypot(s.gt_x - 499.5, s.gt_y - 499.5)
    assert offset > 100  # >= 1500 nm of drift at 10 nm/px, minus any tie-break correction


def test_footprint_stays_inside_the_search_image(cfgs):
    half = 1000 * 1.0 / 2 / 10.0
    for seed in range(20):
        s = _pair(cfgs, seed=seed)
        assert half - 0.5 <= s.gt_x <= 999.5 - half
        assert half - 0.5 <= s.gt_y <= 999.5 - half


def test_same_seed_is_reproducible(cfgs):
    a, b = _pair(cfgs, seed=777), _pair(cfgs, seed=777)
    assert np.array_equal(a.search, b.search) and np.array_equal(a.reference, b.reference)
    assert (a.gt_x, a.gt_y, a.drift_nm, a.n_equivalent) == (b.gt_x, b.gt_y, b.drift_nm, b.n_equivalent)


def test_periodic_target_reports_equivalents_and_applies_the_center_rule(cfgs):
    """On a periodic target the ground truth is the equivalent position nearest the image center."""
    found = False
    for seed in range(40):
        s = _pair(cfgs, seed=seed, target_class="periodic", scenario="large_drift")
        if not s.is_ambiguous:
            continue
        found = True
        eq = equivalent_locations(s.world, (s.target_x_nm, s.target_y_nm),
                                  s.world.reference_fov_nm, s.search_window)
        d = [np.hypot(x - s.search_window.center_x_nm, y - s.search_window.center_y_nm) for x, y in eq]
        chosen = np.hypot(s.gt_x_nm - s.search_window.center_x_nm, s.gt_y_nm - s.search_window.center_y_nm)
        assert chosen == pytest.approx(min(d))
        assert np.hypot(s.gt_x - 499.5, s.gt_y - 499.5) <= np.hypot(
            *np.subtract(s.search_window.world_to_pixel(s.target_x_nm, s.target_y_nm), 499.5))
        break
    assert found, "no ambiguous periodic sample in 40 seeds"


def test_unique_target_has_a_single_ground_truth(cfgs):
    s = _pair(cfgs, seed=909, target_class="unique")
    if s.target_class == "unique":  # the class is a heuristic; only assert when it held
        assert s.n_equivalent == 1
        assert (s.gt_x_nm, s.gt_y_nm) == (s.target_x_nm, s.target_y_nm)


def test_scale_error_changes_the_search_pitch(cfgs):
    cfg, layout_cfg = cfgs
    scaled = {**cfg, "search": {**cfg["search"], "scale_error": 0.15}}
    s = generate_pair(scaled, layout_cfg, seed=1111, drift_nm=(0.0, 0.0))
    assert s.search_window.pitch_nm == pytest.approx(11.5)
    assert (s.gt_x, s.gt_y) == pytest.approx((499.5, 499.5))  # no drift: the target sits at the center


def test_validator_accepts_a_generated_dataset_and_rejects_a_wrong_size(tmp_path, cfgs):
    import csv as _csv

    from PIL import Image

    from scripts_validate import validate  # thin import shim, see conftest

    s = _pair(cfgs, seed=1212)
    (tmp_path / "images").mkdir()
    ref, search = "images/a_reference.png", "images/a_search.png"
    Image.fromarray((s.reference * 255).astype(np.uint8)).save(tmp_path / ref)
    Image.fromarray((s.search * 255).astype(np.uint8)).save(tmp_path / search)
    row = {"reference_path": ref, "search_path": search, "sample_id": "a",
           "ground_truth_x": f"{s.gt_x:.4f}", "ground_truth_y": f"{s.gt_y:.4f}",
           "reference_pitch_nm": 1.0, "search_pitch_nm": 10.0}
    with open(tmp_path / "metadata.csv", "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=list(row))
        w.writeheader()
        w.writerow(row)
    assert validate(tmp_path, min_samples=1) == []

    Image.fromarray(np.zeros((999, 1000), np.uint8)).save(tmp_path / search)
    assert any("999" in e for e in validate(tmp_path, min_samples=1))
