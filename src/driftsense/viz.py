"""Inspection figures. Image axes use the pixel-center convention (pixel c spans c +/- 0.5)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

BLOCK_COLORS = {
    "logic": "#4c9be8",
    "sram": "#e8744c",
    "contact_array": "#e8c14c",
    "routing": "#6cc070",
    "marks": "#c46ce8",
    "fill": "#9aa0a6",
}


def _footprint(ax, cx, cy, half, color="red"):
    ax.add_patch(Rectangle((cx - half, cy - half), 2 * half, 2 * half, fill=False, ec=color, lw=1.8))
    ax.plot(cx, cy, "+", color=color, ms=14, mew=2)


def _frame(ax, n):
    ax.set_xlim(-0.5, n - 0.5)
    ax.set_ylim(n - 0.5, -0.5)


def plot_layout_sample(world, search_img, reference_img, zoom_rgb, search_win, zoom_win, out_path: str | Path) -> None:
    t = world.target
    n = search_win.size_px
    gx, gy = search_win.world_to_pixel(t.x_nm, t.y_nm)
    fig, axes = plt.subplots(1, 3, figsize=(19, 6.8))

    ax = axes[0]
    ax.imshow(search_img, cmap="gray", vmin=0, vmax=1, interpolation="antialiased")
    for blk in world.blocks:
        # Block edges are world positions; world_to_pixel maps them straight onto the image axes.
        x0, y0 = search_win.world_to_pixel(blk.box[0], blk.box[1])
        x1, y1 = search_win.world_to_pixel(blk.box[2], blk.box[3])
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=BLOCK_COLORS[blk.kind], lw=1.2))
    _footprint(ax, gx, gy, world.reference_fov_nm / 2 / search_win.pitch_nm)
    _frame(ax, n)
    ax.set_title(f"search scale ({search_win.pitch_nm:g} nm/px)   GT = ({gx:.2f}, {gy:.2f}) px")
    ax.legend(handles=[Line2D([], [], color=c, label=k) for k, c in BLOCK_COLORS.items()],
              loc="lower right", fontsize=7, framealpha=0.8)

    ax = axes[1]
    ax.imshow(reference_img, cmap="gray", vmin=0, vmax=1, interpolation="antialiased")
    ax.plot((n - 1) / 2, (n - 1) / 2, "r+", ms=14, mew=2)
    _frame(ax, n)
    ax.set_title(f"reference scale ({world.reference_fov_nm / n:g} nm/px), centered on target")

    ax = axes[2]
    ax.imshow(zoom_rgb, interpolation="antialiased")
    zx, zy = zoom_win.world_to_pixel(t.x_nm, t.y_nm)
    _footprint(ax, zx, zy, world.reference_fov_nm / 2 / zoom_win.pitch_nm)
    _frame(ax, n)
    ax.set_title(f"layer view ({zoom_win.pitch_nm:g} nm/px): ACTIVE green, POLY red, CONTACT yellow, M1 blue",
                 fontsize=9)

    fig.suptitle(f"seed={world.seed}  preset={world.preset}  class={t.target_class} "
                 f"(requested {t.requested_class})  block={t.block_kind}  "
                 f"target=({t.x_nm:.0f}, {t.y_nm:.0f}) nm  rects={world.n_rects}")
    fig.tight_layout()
    fig.savefig(out_path, dpi=80)
    plt.close(fig)


def plot_pair(sample, out_path: str | Path) -> None:
    """Reference next to search, with the footprint, the ground truth and the drift vector."""
    n = sample.search.shape[0]
    win = sample.search_window
    half = sample.world.reference_fov_nm / 2 / win.pitch_nm
    cx = cy = (n - 1) / 2
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 7.2))

    ax = axes[0]
    ax.imshow(sample.reference, cmap="gray", vmin=0, vmax=1, interpolation="antialiased")
    ax.plot(cx, cy, "r+", ms=14, mew=2)
    _frame(ax, sample.reference.shape[0])
    ax.set_title(f"reference  {sample.reference_window.pitch_nm:g} nm/px "
                 f"({sample.reference.shape[0] * sample.reference_window.pitch_nm / 1000:g} um FOV)")

    ax = axes[1]
    ax.imshow(sample.search, cmap="gray", vmin=0, vmax=1, interpolation="antialiased")
    # Positions that are indistinguishable from the target (Phase 0, D4).
    if sample.is_ambiguous:
        from .pairs.ambiguity import equivalent_locations
        eq = equivalent_locations(sample.world, (sample.target_x_nm, sample.target_y_nm),
                                  sample.world.reference_fov_nm, win)
        ex, ey = zip(*[win.world_to_pixel(x, y) for x, y in eq])
        ax.plot(ex, ey, ".", color="deepskyblue", ms=4, label=f"equivalent x{len(eq)}")
    ax.plot(cx, cy, "o", mfc="none", mec="lime", ms=10, mew=1.6, label="image center (commanded)")
    ax.annotate("", xy=(sample.gt_x, sample.gt_y), xytext=(cx, cy),
                arrowprops=dict(arrowstyle="->", color="yellow", lw=1.5))
    _footprint(ax, sample.gt_x, sample.gt_y, half)
    _frame(ax, n)
    dx, dy = sample.drift_nm
    ax.set_title(f"search  {win.pitch_nm:g} nm/px   GT = ({sample.gt_x:.2f}, {sample.gt_y:.2f}) px")
    ax.legend(loc="lower right", fontsize=8, framealpha=0.85)

    fig.suptitle(f"{sample.sample_id}  seed={sample.seed}  preset={sample.preset}  scenario={sample.scenario}  "
                 f"class={sample.target_class} in {sample.block_kind}  "
                 f"drift=({dx:.0f}, {dy:.0f}) nm = ({dx / win.pitch_nm:.1f}, {dy / win.pitch_nm:.1f}) px  "
                 f"equivalents={sample.n_equivalent}")
    fig.tight_layout()
    fig.savefig(out_path, dpi=80)
    plt.close(fig)


def plot_contact_sheet(entries, out_path: str | Path, cols: int = 5) -> None:
    """entries: list of (search_img, (gx, gy), half_footprint_px, title)."""
    rows = (len(entries) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 4.3 * rows), squeeze=False)
    for ax in axes.flat:
        ax.axis("off")
    for ax, (img, (gx, gy), half, title) in zip(axes.flat, entries):
        ax.imshow(img, cmap="gray", vmin=0, vmax=1, interpolation="antialiased")
        _footprint(ax, gx, gy, half)
        _frame(ax, img.shape[0])
        ax.set_title(title, fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=80)
    plt.close(fig)
