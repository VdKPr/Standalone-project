"""Generate example layouts with known target coordinates and save inspection images.

For each sample this writes:
  images/<id>_search.png     1000x1000 clean layout at search pitch (10 nm/px), centered on the world
  images/<id>_reference.png  1000x1000 clean layout at reference pitch (1 nm/px), centered on the target
  viz/<id>.png               search view with block outlines + footprint, reference view, layer view
plus metadata.csv (ground truth in search-image pixels) and contact_sheet.png.

No imaging effects (noise, blur, rotation, scale error, drift) are applied: that is Phase 3/4.

Usage:
    python scripts/generate_layout_examples.py
    python scripts/generate_layout_examples.py --n 10 --presets intermediate,mature,advanced --out data/processed/layout_presets
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import numpy as np
from PIL import Image

from driftsense.config import load_config
from driftsense.layout import TARGET_CLASSES, Window, colorize, composite, generate_world, rasterize
from driftsense.viz import plot_contact_sheet, plot_layout_sample


def to_uint8(img: np.ndarray) -> np.ndarray:
    return np.clip(np.round(img * 255), 0, 255).astype(np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="configs/layout_v1.yaml")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=None, help="base seed (default: config seed); sample i uses seed+i")
    ap.add_argument("--presets", default=None, help="comma-separated presets, cycled (default: config preset)")
    ap.add_argument("--out", default="data/processed/layout_v1")
    args = ap.parse_args()

    cfg = load_config(args.config)
    base_seed = cfg["seed"] if args.seed is None else args.seed
    presets = args.presets.split(",") if args.presets else [cfg["preset"]]
    rc = cfg["render"]
    n, order = rc["size_px"], rc["layer_order"]

    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "viz").mkdir(parents=True, exist_ok=True)

    rows, sheet = [], []
    for i in range(args.n):
        seed = base_seed + i
        preset = presets[i % len(presets)]
        wanted = TARGET_CLASSES[i % len(TARGET_CLASSES)]

        t0 = time.perf_counter()
        world = generate_world(cfg, seed, preset, wanted)
        t1 = time.perf_counter()
        t = world.target
        cx, cy = world.center
        swin = Window(cx, cy, rc["search_pitch_nm"], n)
        rwin = Window(t.x_nm, t.y_nm, rc["reference_pitch_nm"], n)
        zwin = Window(t.x_nm, t.y_nm, 3.0, n)
        search = composite(rasterize(world.layout, swin, rc["search_supersample"]), order, rc["gray_levels"])
        reference = composite(rasterize(world.layout, rwin, rc["reference_supersample"]), order, rc["gray_levels"])
        t2 = time.perf_counter()
        gx, gy = swin.world_to_pixel(t.x_nm, t.y_nm)

        sid = f"layout_{i:03d}"
        search_rel, ref_rel = f"images/{sid}_search.png", f"images/{sid}_reference.png"
        Image.fromarray(to_uint8(search)).save(out / search_rel)
        Image.fromarray(to_uint8(reference)).save(out / ref_rel)
        zoom = colorize(rasterize(world.layout, zwin, 2), order)
        plot_layout_sample(world, search, reference, zoom, swin, zwin, out / "viz" / f"{sid}.png")

        half = world.reference_fov_nm / 2 / swin.pitch_nm
        sheet.append((search, (gx, gy), half, f"{sid} {preset}\n{t.target_class} in {t.block_kind}"))
        rows.append({
            "sample_id": sid, "seed": seed, "preset": preset,
            "reference_image": ref_rel, "search_image": search_rel,
            "ground_truth_x": f"{gx:.4f}", "ground_truth_y": f"{gy:.4f}",
            "target_x_nm": t.x_nm, "target_y_nm": t.y_nm,
            "target_class": t.target_class, "requested_class": t.requested_class,
            "block_kind": t.block_kind, "boundary_distance_nm": f"{t.boundary_distance_nm:.1f}",
            "search_center_x_nm": cx, "search_center_y_nm": cy,
            "search_pitch_nm": swin.pitch_nm, "reference_pitch_nm": rwin.pitch_nm,
            "n_rects": world.n_rects, "gen_s": f"{t1 - t0:.3f}", "render_s": f"{t2 - t1:.3f}",
        })
        print(f"{sid} seed={seed} {preset:12s} {t.target_class:12s} (req {t.requested_class:12s}) "
              f"block={str(t.block_kind):13s} GT=({gx:7.2f},{gy:7.2f}) rects={world.n_rects:6d} "
              f"gen={t1 - t0:.2f}s render={t2 - t1:.2f}s")

    with open(out / "metadata.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    plot_contact_sheet(sheet, out / "contact_sheet.png")
    print(f"wrote {len(rows)} samples to {out}")


if __name__ == "__main__":
    main()
