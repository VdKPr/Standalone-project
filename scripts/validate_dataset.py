"""Validate a generated pair dataset against the Phase 0 contract.

Checks, over every row of metadata.csv:
  * the four required columns exist and parse
  * both image files exist, are exactly 1000x1000, 8-bit, single channel
  * the ground truth is finite and inside the search image
  * the whole reference footprint lies inside the search image
  * sample ids are unique and the dataset holds at least --min-samples rows

Usage:
    python scripts/validate_dataset.py data/processed/pairs_v1
Exit code 0 = PASS, 1 = FAIL.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

from PIL import Image

REQUIRED = ("reference_path", "search_path", "ground_truth_x", "ground_truth_y")
EXPECTED_SIZE = (1000, 1000)


def validate(root: Path, min_samples: int, expected_size=EXPECTED_SIZE) -> list[str]:
    errors: list[str] = []
    meta = root / "metadata.csv"
    if not meta.exists():
        return [f"missing {meta}"]

    with open(meta, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return [f"{meta} has no rows"]
    missing = [c for c in REQUIRED if c not in rows[0]]
    if missing:
        return [f"metadata.csv is missing required columns: {missing}"]
    if len(rows) < min_samples:
        errors.append(f"only {len(rows)} samples, expected at least {min_samples}")

    seen: set[str] = set()
    for i, row in enumerate(rows):
        tag = row.get("sample_id") or f"row {i}"
        if tag in seen:
            errors.append(f"{tag}: duplicate sample_id")
        seen.add(tag)

        for col in ("reference_path", "search_path"):
            path = root / row[col]
            if not path.exists():
                errors.append(f"{tag}: {col} not found: {path}")
                continue
            with Image.open(path) as im:
                if im.size != expected_size:
                    errors.append(f"{tag}: {col} is {im.size[0]}x{im.size[1]}, expected "
                                  f"{expected_size[0]}x{expected_size[1]}")
                if im.mode != "L":
                    errors.append(f"{tag}: {col} mode is {im.mode!r}, expected 8-bit grayscale 'L'")

        try:
            gx, gy = float(row["ground_truth_x"]), float(row["ground_truth_y"])
        except ValueError:
            errors.append(f"{tag}: ground truth is not numeric")
            continue
        w, h = expected_size
        if not (math.isfinite(gx) and math.isfinite(gy)):
            errors.append(f"{tag}: ground truth is not finite")
        elif not (-0.5 <= gx <= w - 0.5 and -0.5 <= gy <= h - 0.5):
            errors.append(f"{tag}: ground truth ({gx:.2f}, {gy:.2f}) is outside the search image")
        else:
            # The reference footprint must be fully visible: half of 1 um at the search pitch.
            try:
                half = (1000 * float(row["reference_pitch_nm"])) / 2 / float(row["search_pitch_nm"])
            except (KeyError, ValueError, ZeroDivisionError):
                half = None
            if half is not None and not (half - 0.5 <= gx <= w - 0.5 - half and half - 0.5 <= gy <= h - 0.5 - half):
                errors.append(f"{tag}: footprint (+/-{half:.0f} px) around ({gx:.1f}, {gy:.1f}) "
                              f"extends outside the search image")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default="data/processed/pairs_v1")
    ap.add_argument("--min-samples", type=int, default=30)
    args = ap.parse_args()

    root = Path(args.root)
    errors = validate(root, args.min_samples)
    if errors:
        print(f"FAIL: {len(errors)} problem(s) in {root}")
        for e in errors[:50]:
            print("  -", e)
        if len(errors) > 50:
            print(f"  ... and {len(errors) - 50} more")
        return 1
    print(f"PASS: {root} satisfies the Phase 0 dataset contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
