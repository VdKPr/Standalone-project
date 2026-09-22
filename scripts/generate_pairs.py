"""Generate a (reference, search) pair dataset with automatic ground truth.

Writes, under --out:
  images/<id>_reference.png   1000x1000, 1 nm/px, centered on the target
  images/<id>_search.png      1000x1000, 10 nm/px, offset by the navigation drift
  viz/<id>.png                reference next to search, with the footprint, GT and drift
  metadata.csv                reference_path, search_path, ground_truth_x, ground_truth_y, + provenance
  contact_sheet.png

Usage:
    python scripts/generate_pairs.py
    python scripts/generate_pairs.py --n 36 --out data/processed/pairs_v1
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import numpy as np
from PIL import Image

from driftsense.config import load_config
from driftsense.layout import TARGET_CLASSES
from driftsense.pairs import generate_pair
from driftsense.viz import plot_contact_sheet, plot_pair

FIELDS = ["reference_path", "search_path", "ground_truth_x", "ground_truth_y",
          "sample_id", "seed", "preset", "scenario", "target_class", "block_kind",
          "drift_x_nm", "drift_y_nm", "drift_nm", "scale_error", "search_pitch_nm", "reference_pitch_nm",
          "n_equivalent", "is_ambiguous", "target_x_nm", "target_y_nm", "gt_x_nm", "gt_y_nm",
          "search_center_x_nm", "search_center_y_nm", "image_width", "image_height", "gen_s"]


def to_uint8(img: np.ndarray) -> np.ndarray:
    return np.clip(np.round(img * 255), 0, 255).astype(np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="configs/pairs_v1.yaml")
    ap.add_argument("--n", type=int, default=None, help="number of pairs (default: config n_pairs)")
    ap.add_argument("--seed", type=int, default=None, help="base seed; pair i uses seed+i")
    ap.add_argument("--presets", default=None, help="comma-separated presets, cycled")
    ap.add_argument("--out", default="data/processed/pairs_v1")
    ap.add_argument("--no-viz", action="store_true", help="skip figures (faster)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    layout_cfg = load_config(cfg["layout_config"])
    n = args.n if args.n is not None else int(cfg["n_pairs"])
    base_seed = cfg["seed"] if args.seed is None else args.seed
    presets = args.presets.split(",") if args.presets else list(cfg["presets"])

    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    if not args.no_viz:
        (out / "viz").mkdir(parents=True, exist_ok=True)

    rows, sheet = [], []
    for i in range(n):
        t0 = time.perf_counter()
        s = generate_pair(cfg, layout_cfg, seed=base_seed + i, index=i,
                          preset=presets[i % len(presets)], target_class=TARGET_CLASSES[i % len(TARGET_CLASSES)])
        dt = time.perf_counter() - t0

        ref_rel, search_rel = f"images/{s.sample_id}_reference.png", f"images/{s.sample_id}_search.png"
        Image.fromarray(to_uint8(s.reference)).save(out / ref_rel)
        Image.fromarray(to_uint8(s.search)).save(out / search_rel)
        if not args.no_viz:
            plot_pair(s, out / "viz" / f"{s.sample_id}.png")
        sheet.append((s.search, (s.gt_x, s.gt_y), s.world.reference_fov_nm / 2 / s.search_window.pitch_nm,
                      f"{s.sample_id} {s.scenario}\n{s.target_class} in {s.block_kind}"
                      f"{' (x%d)' % s.n_equivalent if s.is_ambiguous else ''}"))

        dx, dy = s.drift_nm
        rows.append({
            "reference_path": ref_rel, "search_path": search_rel,
            "ground_truth_x": f"{s.gt_x:.4f}", "ground_truth_y": f"{s.gt_y:.4f}",
            "sample_id": s.sample_id, "seed": s.seed, "preset": s.preset, "scenario": s.scenario,
            "target_class": s.target_class, "block_kind": s.block_kind,
            "drift_x_nm": f"{dx:.1f}", "drift_y_nm": f"{dy:.1f}", "drift_nm": f"{np.hypot(dx, dy):.1f}",
            "scale_error": s.scale_error, "search_pitch_nm": s.search_window.pitch_nm,
            "reference_pitch_nm": s.reference_window.pitch_nm,
            "n_equivalent": s.n_equivalent, "is_ambiguous": int(s.is_ambiguous),
            "target_x_nm": s.target_x_nm, "target_y_nm": s.target_y_nm,
            "gt_x_nm": s.gt_x_nm, "gt_y_nm": s.gt_y_nm,
            "search_center_x_nm": s.search_window.center_x_nm, "search_center_y_nm": s.search_window.center_y_nm,
            "image_width": s.search.shape[1], "image_height": s.search.shape[0], "gen_s": f"{dt:.2f}",
        })
        print(f"{s.sample_id} seed={s.seed} {s.preset:12s} {s.scenario:11s} {s.target_class:12s} "
              f"drift=({dx:6.0f},{dy:6.0f}) nm  GT=({s.gt_x:7.2f},{s.gt_y:7.2f})  "
              f"eq={s.n_equivalent:4d}  {dt:.2f}s")

    with open(out / "metadata.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    if not args.no_viz:
        plot_contact_sheet(sheet, out / "contact_sheet.png", cols=6)
    print(f"wrote {len(rows)} pairs to {out}")


if __name__ == "__main__":
    main()
