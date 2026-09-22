# Phase 0 — Specification Audit

Project: Drift Sense — AI-Powered Navigation Error (Applied Materials hackathon)
Status: draft v1, 2026-09-22. This file replaces the assumptions register from the kickoff discussion.
Scope: specification only. No implementation.

Source labels used below:

- **PS**: problem statement, as you relayed it from the webinar. It is second-hand, so it is not authoritative.
- **UD**: your own directive for this project. Binding on us, but not on the organizer.
- **OFF**: the official AMAT statement or scoring utility. We don't have it yet.

---

## 1. Notation and conventions

| Symbol | Meaning |
|---|---|
| `I[r, c]` | Image array; `r` = row (0…999, top→bottom), `c` = column (0…999, left→right) |
| `(x, y)` | Continuous image coordinates, **x = column direction, y = row direction**, origin top-left |
| Pixel-center convention | Pixel `[r, c]` covers the square `[c−½, c+½] × [r−½, r+½]`, so its center is `(c, r)`. The image's continuous extent is `[−½, 999.5]²`. This matches OpenCV and scikit-image. |
| `c_img` | Geometric image center = `(499.5, 499.5)` under this convention |
| `p_R`, `p_S` | Pixel pitch of reference and search images, in nm/px (nominal 1 and 10) |
| `s₀` | Nominal scale ratio `p_R / p_S ≈ 0.1` (a reference pixel spans 0.1 search pixels) |
| `ξ` | Physical position on the specimen (stage/world frame), in nm |

---

## 2. Formal mathematical formulation

### 2.1 Imaging model

The specimen surface is a planar intensity field `W(ξ)`, with `ξ ∈ ℝ²` measured in nm. Each image maps its pixel coordinates to world coordinates:

```
Γ_R(u) = o_R + p_R · Q(α_R) · u              u ∈ reference pixel coords
Γ_S(v) = o_S + p_S · Q(α_S) · D_S(v)         v ∈ search pixel coords
```

- `o_R`, `o_S`: world position of pixel (0, 0). Stage position and navigation error enter here.
- `Q(α)`: 2-D rotation by the scan/stage angle `α`.
- `D_S`: a small, smooth non-rigid distortion (scan non-linearity, drift during the scan). `D_S ≈ identity`.

Observed images:

```
R[r,c] = 𝒩_R( (h_R ∗ W)(Γ_R(c, r)) )
S[r,c] = 𝒩_S( (h_S ∗ W)(Γ_S(c, r)) )
```

- `h_R`, `h_S`: point-spread functions (focus/blur). `h_S` also includes the anti-aliasing from the coarser sampling.
- `𝒩_R`, `𝒩_S`: noise, charging, contrast and quantization operators. **They are independent realizations with different parameters** (UD).

### 2.2 The reference→search mapping

Ignoring `D_S`, the map from reference pixel coordinates to search pixel coordinates is a similarity transform:

```
φ(u) = Γ_S⁻¹(Γ_R(u)) = s · Rθ · u + t
    s = s₀ · (1 + ε_s),   ε_s ∈ [−0.2, +0.2]   (scale robustness band, PS)
    θ = α_R − α_S,        |θ| ≤ 3°             (PS)
    t ∈ ℝ²                                     (navigation error, unbounded a priori)
```

### 2.3 Ground truth

The target point is `c_R`, the reference center `(499.5, 499.5)` (assumption AS2). Its true location in the search image is:

```
g = (x_gt, y_gt) = φ(c_R)
```

**Drift interpretation.** The stage was commanded to put the target at the center of the search image. The navigation error is therefore:

```
d_px = g − c_img            (search pixels)
d_nm = p_S · d_px           (nm)
```

This explains the product name, and it is why the center-tie-break rule is a sensible prior: small drift is more likely than large drift.

### 2.4 Estimation problem

Hypothesis space:

```
H = { h = (x, y, s, θ) : x, y ∈ [−½, 999.5],  s ∈ s₀·[0.8, 1.2],  θ ∈ [−3°, 3°] }
```

We choose a similarity functional `J(h; R, S) ∈ ℝ` that is higher for better matches. Examples are NCC, phase-correlation peak height, and inlier ratio. `J` compares `S` near `(x, y)` with `R` after it has been low-pass filtered, resampled by `s`, and rotated by `θ`.

The estimator produces `ĝ` using the candidate and tie-break procedure defined in §3.

### 2.5 Identifiability

If `W` is periodic with lattice `Λ` over a region larger than the reference footprint, then `J` is (approximately) invariant under shifts in `Λ / p_S`. **In that case `g` cannot be identified from image content alone.** The PS tie-break rule is exactly what makes the answer unique. As a consequence, the ground truth *our generator writes* must follow the same rule (see D4). Otherwise our dataset contradicts the specification.

### 2.6 Numbers that drive the design

| Quantity | Value | Consequence |
|---|---|---|
| Reference footprint in S | `1000 · s ≈ 100 px` (80–120 px over the ±20% band) | The effective template is only about 100×100 px |
| Downsampling factor | 10 reference px per search px | Structure with a period below about 2·`p_S` = 20 nm cannot be represented in S (Nyquist). Realistically we need a period of 40 nm or more. Fine FinFET fin pitch (about 30–50 nm) is barely resolved or aliased in S. Matching must rely on coarser structure. |
| Rotation displacement at template corner | `70.7 px · θ` ≈ 1.2 px at 1°, 3.7 px at 3° | Ignoring rotation smears the correlation peak. Rotation must be searched or estimated. |
| Scale displacement at template edge | `50 px · 0.2` = 10 px at ±20% | Scale must be searched. A hardcoded `s₀` is not enough. |
| Physical cost of 1 px error | 10 nm | success@1px means sub-10-nm navigation accuracy |
| GT range if the target must be fully visible | about [60, 940] per axis | Targets beyond this range are partially clipped (AM7) |

---

## 3. Precise definitions

**D1 — Reference image `R`.** A 1000×1000 image at pitch `p_R ≈ 1 nm/px`. It shows a 1 µm × 1 µm patch of the specimen centered on the target point, and it is acquired independently of `S` (own noise, blur and charging). **The whole reference field of view is the template** (assumption AS2, open question AM1).

**D2 — Search image `S`.** A 1000×1000 image at pitch `p_S ≈ 10 nm/px`. It shows a 10 µm × 10 µm patch of the same specimen. The stage intended this patch to be centered on the target point, but it is offset by the unknown navigation error. `S` may contain structures that repeat the target.

**D3 — Target point.** The world point `ξ* = Γ_R(c_R)`, i.e. the physical location imaged at the reference center.

**D4 — Ground truth `g`.**
- If the target's neighbourhood is unique within `S`, then `g = φ(c_R)`, taken from the generator's known geometry. It is not measured from pixels.
- If there are exact repeats, then `g` is the member of the equivalence set `E` nearest to `c_img`. `E` is the set of search locations whose reference-footprint neighbourhood is geometrically identical to the target's.

The generator computes `E` from the layout geometry, not from rendered pixels. It stores `is_ambiguous = |E| > 1` in the CSV.

**D5 — Candidate.** A tuple `k = (x, y, s, θ, J)`, where `(x, y) = φ_h(c_R)` is the **predicted location of the reference center under hypothesis h**.

- This is **not** the top-left corner of the matching window.
- Candidates are the local maxima of `J` over `H`, after non-maximum suppression with radius `r_nms = ½ · footprint ≈ 50 px`. Two matches closer than half a template overlap, so they are not distinct instances.

**D6 — Score map.** `J` evaluated on a grid over `H`, with optional sub-pixel refinement around each peak. Every method (classical or learned) must expose its score map, for explainability.

**D7 — Valid candidate set.**

```
V = { k ∈ C : J(k) ≥ τ_abs  and  J(k) ≥ J_max − δ }
```

- `τ_abs` is the absolute acceptance threshold. It rejects non-matches.
- `δ` is the indistinguishability margin. It equals the spread of `J` across true duplicates that is caused by noise.
- Both are **calibrated on a synthetic calibration split and frozen** before any test evaluation.
- If `V = ∅`, the output is **abstain** (⊥) internally. Whether ⊥ may be emitted is decided by the API adapter (AM6).

**D8 — Center-based tie-break.**

```
ĝ = argmin_{k ∈ V} ‖(x_k, y_k) − c_img‖₂
```

- Secondary key: higher `J`. Tertiary keys: smaller `y`, then smaller `x`, so the result is fully deterministic.
- When `|V| = 1`, this reduces to plain argmax.
- `c_img = (499.5, 499.5)` by our convention. If the organizer uses (500, 500), distances change by at most 0.71 px, which only matters for exact equidistant ties.

**D9 — Localization error.** `e = ‖ĝ − g‖₂`, measured in search pixels as a float with no rounding. We also report:
- Signed per-axis errors `e_x = x̂ − x_gt` and `e_y = ŷ − y_gt`, to detect systematic bias such as half-pixel or axis-swap bugs.
- Physical error `e · p_S` in nm.

**D10 — Success, precision and recall at threshold N.**

For each pair, with `ĝ ∈ {point, ⊥}`:

- `success@N = 1[ĝ ≠ ⊥ ∧ e ≤ N]`
- TP: `ĝ ≠ ⊥ ∧ e ≤ N`
- FP: `ĝ ≠ ⊥ ∧ e > N`
- FN: `ĝ = ⊥`, or `e > N`. The second case assumes the detection convention where a wrong location counts as both FP and FN. To be confirmed (AM6).

**If the system never abstains, then P = R = F1 = success@N.** P/R/F1 therefore only carry extra information if we output a confidence. In that case we sweep a confidence threshold to get a PR curve.

**D11 — Failure.** A pair with `e > N_fail`, with `N_fail = 5 px` by default (configurable), or an abstention on a pair whose target is present.

---

## 4. Explicit requirements (stated, not inferred)

| ID | Requirement | Source |
|---|---|---|
| E1 | Input: one reference image and one search image, both 1000×1000 | PS |
| E2 | Output: `(x, y)` pixel coordinate of the target in the search image, origin top-left | PS |
| E3 | Reference ≈ 1 nm/px (100×), search ≈ 10 nm/px (10×) | PS ("approximate") |
| E4 | If several visually valid matches exist, choose the one closest to the center of the search image | PS |
| E5 | Robust to translation, rotation (1–3°), scale (±20%, as a robustness study), grayscale/SEM noise, charging and edge artifacts, distortion, blur, repeated structures, partial ambiguity, and combinations of these | PS |
| E6 | Reference and search noise are not identical | PS/UD |
| E7 | Scoring ≈ 30% dataset, 50% localization, 10% explainability, 10% failure analysis; RGB earns a bonus; runtime is a secondary criterion | PS ("approximate") |
| E8 | If deep learning is used, document the architecture, weights, parameter count, training method and time, inference time, data and preprocessing | PS |
| E9 | Synthetic, literature-grounded geometry with ground truth known by construction. No generative-model images of unknown geometry. | UD |
| E10 | At least 30 diverse samples; CSV with the reference path, search path, `ground_truth_x`, `ground_truth_y` | UD |
| E11 | Every step reproducible from a seed; every important parameter configurable | UD |
| E12 | The official scoring utility is authoritative; do not invent its API | UD |

---

## 5. Working assumptions (adopted; each is a config parameter or an adapter concern)

| ID | Assumption | Rationale | Where it can be changed |
|---|---|---|---|
| AS1 | The core pipeline is single-channel float32. RGB input is reduced to one channel at the adapter, or used as extra channels in the bonus path. | SEM data is inherently grayscale; RGB is a bonus | Input adapter |
| AS2 | The target point is the reference center; the whole reference FOV is the template | Most direct reading of E1/E2 | `target_point` config |
| AS3 | In the core set, the target footprint lies fully inside `S`. Clipped targets form a separate stress subset. | Keeps the core ground truth unambiguous | Generator config |
| AS4 | `s₀ = 0.1` is only the *center* of a searched scale band. It is never hardcoded as exact. | E3 says "approximate" | `scale.nominal`, `scale.band` |
| AS5 | Geometry is a similarity transform plus small smooth distortion. No flips, no 90° rotations, no perspective. | Physics of a planar specimen under an SEM | Generator and search config |
| AS6 | `𝒩_R` and `𝒩_S` are independent. Typically the search image is noisier per pixel, and the reference is more exposed to charging at high magnification. | E6 and SEM physics (confirmed in Phase 1) | Augmentation config |
| AS7 | The reference is an SEM-like image, not a CAD/layout render. The generator can produce both. | "High-resolution reference image" | Generator `reference_mode` |
| AS8 | Every pair contains the target at least once. The ground truth follows D4. | E4 implies at least one match | Generator config |
| AS9 | Output is float `(x, y)` with the pixel-center convention | Preserves sub-pixel information | Output adapter |
| AS10 | The evaluator uses Euclidean distance in search-image pixels | Most common choice | Evaluation config |
| AS11 | Inputs may be 8-bit or 16-bit, grayscale or color. They are read without truncation and normalized internally. | Real SEM files are often 16-bit TIFF | I/O layer |
| AS12 | Runtime is measured per pair on CPU, reported both with and without file I/O and one-time setup | Hardware unknown | Benchmark script |

---

## 6. Open ambiguities

| ID | Question | Plausible readings | Impact |
|---|---|---|---|
| AM1 | What exactly is "the target" in the reference? | (a) the whole reference FOV; (b) a marked sub-ROI or feature inside it; (c) a specific structural feature such as a via or line end | Determines the template and the meaning of `(x, y)`. **High.** |
| AM2 | Which point does `(x, y)` denote? | Target center, top-left of the matched region, or a feature point | A wrong choice gives a systematic error of about 71 px. **Critical.** |
| AM3 | Is the scale ratio fixed at 10× and identical for every pair? Is ±20% a real-data range or only a stress study? | Fixed / per-sample / study-only | Search cost versus robustness |
| AM4 | Which image carries the rotation and the distortion, and what kind of distortion? | Stage rotation versus scan rotation; smooth lens-like distortion versus line jitter/shear from drift during the scan | Refinement model (rigid versus local) |
| AM5 | How does the organizer label ground truth on repeated structures, and what counts as "visually valid"? | Nearest-center among exact repeats; or the true inserted location; or any repeat is accepted | Decides whether D4/D7 match the evaluator |
| AM6 | What do precision, recall, F1 and the confusion matrix mean for a single-point output? Is abstaining allowed? | Per-threshold correctness; detection-style with confidence; box-based (IoU) if YOLO-style outputs are expected | Output contract, and whether a confidence score is required |
| AM7 | Can the target be partially outside `S`, or missing entirely? | Never / sometimes | Need for masked or partial-overlap scoring and for abstention |
| AM8 | Is the center (500, 500) or (499.5, 499.5)? | Either | Negligible except for exact ties |
| AM9 | Do "100×" and "10×" mean magnification settings or pitch ratios? | SEM magnification figures depend on the display; nm/px is the real invariant | We rely on nm/px |
| AM10 | What does "RGB support" mean? | Color-mapped SEM; optical microscope images (cross-modal matching against SEM); multi-detector channels | A cross-modal case would change the method substantially |
| AM11 | Can contrast polarity differ between R and S (SE versus BSE detector, charging reversal)? | Same polarity / sometimes inverted | Plain NCC breaks under inversion |
| AM12 | Is our submitted dataset itself the "30% dataset" deliverable? | Our dataset and generator; or only our augmentation practice | Effort allocation |
| AM13 | Runtime measurement: which hardware, is model loading included, is there a per-pair limit? | Unknown | Method choice, especially for deep learning |

---

## 7. Dangerous assumptions (risk of mismatch with the organizer's evaluator)

Ranked by severity × likelihood. Each one has a mitigation we will build in *now*, before the official utility arrives.

| # | Dangerous assumption | What goes wrong if it is false | Error size | Mitigation built now |
|---|---|---|---|---|
| DA1 | Returning the **top-left corner** of the matched window (the default output of `cv2.matchTemplate`) instead of the target point | Constant offset of half the footprint | ≈ 50 px per axis, ≈ 71 px Euclidean, on every pair | The localizer returns `φ_h(c_R)` by definition (D5). A unit test uses a known ground truth with the target off-center. |
| DA2 | **(x, y) vs (row, col)** order | Axes swapped | `√2·|x−y|`; invisible when x ≈ y | CSV columns are named explicitly. Every test uses `x ≠ y` and very different values. |
| DA3 | **Half-pixel convention** and resampling offsets. `cv2.resize` maps `u → (u + ½)·s − ½`; a naive `u·s` is biased by 0.45 px at s = 0.1. A corner-based evaluator shifts results by a further 0.5 px. | Systematic sub-pixel bias | 0.45–0.7 px, enough to wreck success@1px | Coordinate transforms are derived analytically. The generator and the localizer are implemented **independently**, so a shared bug cannot cancel out. Signed per-axis bias is reported (D9). |
| DA4 | Rounding the output to integers | Quantization error | Up to 0.71 px | Output a float. Round only if the evaluator requires it. |
| DA5 | Scale is exactly `s₀` | The NCC peak collapses on fine-pitch patterns when scale is off by 10–20% | Gross failures | Search a scale band (AS4) |
| DA6 | The organizer labels repeats with our D4/D8 rule | Correct answers on periodic patterns are scored as wrong, or the reverse | Gross, and concentrated on the ambiguous subset | `is_ambiguous` flag in the CSV. Metrics reported with and without ambiguous pairs. The tie-break is a switchable module. |
| DA7 | R and S have the same contrast polarity | NCC goes to −1 at the true location | Gross | Polarity-robust representations (gradient/edge magnitude, or \|NCC\| as an option). Inversion is included as an augmentation. |
| DA8 | Always emitting a point is acceptable | If P/R penalize confident wrong answers, forced guesses cost precision | Metric-dependent | Keep a confidence score internally (D7). The adapter chooses between forced output and abstention. |
| DA9 | Good results on our synthetic data carry over | The generator and the algorithm share assumptions (same blur family, same pattern grammar), so the numbers are optimistic | Unknown generalization gap | Test splits hold out whole pattern families and augmentation types (Phase 9). Some augmentation families are never used during tuning. |
| DA10 | The target is always fully inside `S` | Full-template matching fails near image borders | Gross, for large drift | Border and clipped cases go into the stress set. Masked or partial-overlap scoring is a Phase 7 option. |
| DA11 | The reference is SEM-like | If the reference is a CAD render (binary edges, no noise), the appearance gap changes | Moderate | The generator supports `reference_mode = sem | cad`. Both are evaluated. |
| DA12 | 8-bit grayscale input | A 16-bit TIFF read with default flags is truncated; color files are loaded as BGR | Silent quality loss | I/O reads files unchanged, then normalizes explicitly. |
| DA13 | Runtime is measured our way | A cold start (imports, model load) dominates on their machine | Ranking penalty | Light dependencies. Report cold and warm timings separately. |

---

## 8. Parameters to replace once official information arrives

| Parameter | Current default | Replaced by |
|---|---|---|
| `p_R`, `p_S`, `s₀` | 1 nm/px, 10 nm/px, 0.1 | Official pitch or metadata |
| `scale.band` | ±20% | Real-data range (AM3) |
| `rotation.max_deg` | 3° | Official range |
| `target_point` | Reference center | AM1/AM2 answer |
| `center` | (499.5, 499.5) | Evaluator's definition (AM8) |
| `output.dtype` / rounding | float, no rounding | Evaluator contract |
| `output.order` | (x, y) | Evaluator contract |
| `success_thresholds_px` | 1, 2, 3, 5, 10 | Evaluator thresholds |
| `allow_abstain` | false (forced output) | AM6 answer |
| `tie_break.mode` | nearest-center among `V` | AM5 answer |
| `N_fail` | 5 px | Evaluator's pass/fail threshold |
| API signature | `locate_pattern(reference_image, search_image) -> (x, y)` | Evaluator's call convention |

---

## 9. Phase 0 exit criteria

1. You confirm or override **AS2 / AM1 / AM2**. These define the target and the meaning of the output point.
2. You accept the conventions in §1 (x = column, pixel-center, float output) as internal conventions. The output adapter translates them to whatever the evaluator expects.
3. You accept that the generator's ground truth follows D4 on repeated patterns and flags ambiguous pairs.

Next phase: Phase 1 (literature and image-model research).
