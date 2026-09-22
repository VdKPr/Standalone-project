# Phase 1 — Semiconductor / SEM Image Research and Synthetic Image Model

Status: draft v1, 2026-09-22. Builds on `phase0_spec_audit.md`.
Working defaults carried over from Phase 0, not yet confirmed by you:

- **AS2**: the whole reference FOV is the target.
- **Output point**: the target center.

**Citation status.** The references in §9 are recalled from memory and have **not** been checked online in this session. Every number marked "≈" is an approximate, public-domain order of magnitude. It is meant to set parameter ranges, not to claim that any specific process has that value. Verify before the final report.

---

## 1. The design constraint that dominates everything: two resolutions, one specimen

| | Reference R | Search S |
|---|---|---|
| Pixel pitch | ≈ 1 nm/px | ≈ 10 nm/px |
| Field of view | 1 µm × 1 µm | 10 µm × 10 µm |
| What is resolved | Line edges, edge roughness (LER), corner rounding, individual fins and contacts | Anything with a period of about 40 nm or more. Finer periodic detail aliases into texture or moiré. |
| Footprint of R inside S | — | ≈ 100 × 100 px |

Consequences:

1. **What makes the target unique has to survive at 10 nm/px.** Sub-20-nm pitch arrays (fins, DRAM lines, capacitors) turn into near-uniform texture in S. The features that can actually be matched are:
   - array/periphery boundaries,
   - cell-row boundaries and power rails,
   - irregular routing,
   - contact placement that varies from cell to cell,
   - larger pads and marks.

   The generator therefore has to produce structure on **several length scales at once**.
2. **LER, corner rounding and sub-pixel CD variation are visible only in R.** They make R look realistic, but they are *not* a matching cue. An algorithm that relies on them will fail.
3. **Render S from the world geometry at 10 nm/px.** Do not produce S by decimating R. R covers only 1 µm, so it cannot supply S's content anyway, and naive decimation creates aliasing that a real detector would not produce.

---

## 2. Layout geometry: what real structures look like

### 2.1 Manhattan geometry
- Layout polygons have edges only at 0° and 90°. Design rules fix minimum width, minimum spacing, pitch and enclosure.
- At advanced nodes, critical layers are **unidirectional**: each metal layer runs one way, poly is vertical, fins are horizontal. They are drawn on fixed tracks (gridded design rules).
- Real deviations from "perfect rectangles" come from lithography and etch, not from the design:
  - corner rounding,
  - line-end pullback,
  - edge roughness,
  - CD variation across the die.

### 2.2 Logic (standard-cell regions)
- Cells are placed in **horizontal rows**. The cell height is a fixed number of metal tracks, roughly 6–9 tracks times the M1 pitch.
- Power rails (wider M1 lines) run along the row boundaries. Every other row is **mirrored in y**, so rails are shared between neighbouring rows.
- Gates (poly) are vertical lines at the contacted poly pitch (CPP). Fins run horizontally underneath. Gate cuts and diffusion breaks split them.
- Cell *types* are drawn from a small library (INV, NAND, NOR, DFF, …) and placed in a non-periodic order. The result is **locally repetitive but globally unique**, which is ideal for targets that can be identified.
- Local routing in M1/M2 uses variable-length segments with vias at grid points. It is irregular.

### 2.3 Memory
- **SRAM**: a 6T bitcell tiled with mirroring in x and y, forming a perfectly periodic array. It is bounded by row decoders and sense amps. It is the canonical case of **repeated structure** (ambiguity stress).
- **DRAM (6F² buried-word-line cell)**:
  - Active regions are **tilted bars**, not Manhattan; the tilt is reported around 20° from the axis.
  - Word lines and bit lines are orthogonal lines.
  - Storage-node landing pads and capacitors form a **hexagonal (honeycomb) lattice**.
  - Half-pitch is below 20 nm at current nodes.

  DRAM is the one place where non-Manhattan and hexagonal geometry is physically justified.
- **Contact/via arrays** with regular pitch, and the **array edge**: the transition to dummy cells and then to periphery. The array edge is the most distinctive feature near memory.

### 2.4 FinFET structures (top-down view)
- Fins: long horizontal lines at the fin pitch, grouped in 2–4 fin sets per device, and cut at the cell edge.
- Gates: vertical lines crossing the fins at CPP, with gate cuts.
- Trench/source-drain contacts between the gates. Gate contacts on top.
- In a top-down SEM, the top-most exposed layer dominates. Underlying layers show through with reduced, blurred contrast.

### 2.5 Approximate public-order-of-magnitude pitch presets

| Preset | CPP (gate pitch) | M1 pitch | Fin pitch | Period in S (px) | Role |
|---|---|---|---|---|---|
| `mature` (≈65–90 nm class) | ≈ 200–250 nm | ≈ 180–200 nm | planar, no fins | 18–25 | Easy. Rich structure visible in S. |
| `intermediate` (≈16/14 nm class) | ≈ 70–90 nm | ≈ 52–64 nm | ≈ 42–48 nm | 4–9 | **Recommended default.** Realistic, and still resolvable in S. |
| `advanced` (≈5/3 nm class) | ≈ 45–51 nm | ≈ 23–30 nm | ≈ 25–30 nm | 2–5 | Aliasing stress test |
| `dram` | half-pitch ≈ 15–20 nm, capacitor hex pitch ≈ 40–50 nm | | | 3–5 | Periodic / aliasing stress |

Every size is specified in **nm** in the configuration. The pixel pitch is applied only at render time.

---

## 3. SEM image formation: what the images look like

### 3.1 Contrast (secondary electrons, top-down)
- **Edge effect.** Secondary-electron yield rises sharply where the beam meets a sidewall or edge. Line edges appear as **bright bands** a few nm wide, and flat tops and floors are mid-grey. The analytical line-scan model of Mack & Bunday captures this shape: a peak at the edge, decaying exponentially into the flat regions.
- **Material contrast.** Different materials have different base yields, so flat regions differ in grey level. Backscattered-electron and in-lens detectors emphasize this more.
- **Detector asymmetry.** With a side-mounted Everhart–Thornley detector, edges facing the detector look brighter, which gives a mild directional shading.
- **Buried layers.** Layers below the top one show through with lower contrast and extra blur.

### 3.2 Noise
- **Shot noise.** Secondary-electron emission is a counting process, so noise is Poisson and depends on the signal. The dose (beam current × dwell time) sets the SNR. Fast navigation scans are **low-dose and noisy**.
- **Detector gain noise.** Scintillator and photomultiplier gain adds excess noise, which is often modelled as compound Poisson or Poisson–Gaussian.
- **Electronic read noise.** Additive Gaussian.
- **Scan-line noise.** Row-to-row offset and gain fluctuations make horizontal streaks, because the fast scan runs along x.
- **Frame averaging and line integration** reduce noise by roughly √N, and the reference is typically acquired with more averaging. Poisson–Gaussian is therefore the right family, with *independent* parameters for R and S.

### 3.3 Charging (insulating films, resist, oxides)
All of these vary from acquisition to acquisition:
- **Low-frequency brightness gradients** across the field of view, and slow brightness drift from top to bottom, since the image is acquired over time.
- **Halos**: bright or dark rims around insulating features.
- **Scan-direction streaks.** After a strongly charging feature, the signal along the row recovers slowly, which acts like a **causal exponential tail in +x**.
- **Local beam deflection.** Small image displacements or distortion near charged regions.
- **Contrast reversal.** Severe charging can invert contrast. This supports the polarity risk DA7 from Phase 0.

### 3.4 Blur and focus
- **Probe size.** A roughly Gaussian PSF with σ ≈ 1–3 nm on high-resolution SEMs. In R (1 nm/px) that is 1–3 px. In S it is dominated by **pixel integration**: a 10 nm box.
- **Defocus.** The PSF widens (disk-to-Gaussian shape).
- **Astigmatism.** An elliptical, oriented Gaussian PSF that blurs one direction more than the other.

### 3.5 Distortion (SEM scanning is not an ideal camera)
- **Magnification calibration error** produces a scale error. This is the physical meaning of the ±20% scale study.
- **Scan rotation or stage rotation** gives the 1–3° relative rotation.
- **Drift during the frame.** Stage or thermal drift over the slow-scan time produces a **shear plus stretch/compression along y**.
- **Line jitter.** Vibration or stray field causes per-row x offsets, often sinusoidal with period tied to the 50/60 Hz mains frequency, plus random jitter.
- **Scan non-linearity.** Smooth, low-order field distortion, strongest near the frame edges.

### 3.6 Other real artifacts
- **Particles and defects**: bright blobs, bridges, missing contacts. These belong to the *specimen*, so they appear in both images.
- **Contamination.** Carbon deposition darkens a previously scanned area. **Leakage warning:** if S were acquired *after* R, S would contain a dark square exactly at the target, which would make the task trivial. In navigation the wide image comes first, so this artifact is **excluded by default**.
- **Detector settings**: brightness/contrast offset, gamma, saturation clipping, 8- or 16-bit quantization.

---

## 4. Shared vs independent factors

This split is what makes the synthetic data physically honest.

| Specimen properties: **shared** by R and S | Imaging properties: **independent** per image |
|---|---|
| Layout geometry, all layers | Pose: translation (navigation error), rotation, scale error |
| LER realization, CD variation, corner rounding, line-end pullback | PSF: probe, defocus, astigmatism |
| Defects, particles, material assignment | Noise: dose, gain, read noise, scan-line noise |
| Which layer sits on top, and buried-layer visibility | Charging realization: gradients, halos, streaks |
| | Drift, line jitter, field distortion |
| | Detector brightness/contrast/gamma, bit depth |

---

## 5. Augmentation taxonomy

### A. Physically motivated (primary; controlled by config; shared/independent status as in §4)

| Augmentation | Physical cause | Applied to | Controls |
|---|---|---|---|
| Translation | Navigation / stage error | S pose | Drift magnitude range; center or border cases |
| Rotation (±3°) | Stage or scan rotation | Relative R↔S | `max_deg` |
| Scale (±20%) | Magnification calibration | Relative R↔S | Band |
| Poisson–Gaussian noise | SE shot noise and electronics | Each image independently | Dose, gain, σ_read, frames averaged |
| Scan-line noise | Row gain/offset fluctuation | Each image | Amplitude |
| Charging: gradient, halo, streak tail, drift | Insulator charging | Each image | Amplitudes, decay length, orientation |
| Contrast inversion (rare) | Severe charging or detector change | One image | Probability |
| Gaussian / defocus / astigmatic PSF | Probe, focus, stigmator | Each image | σ, anisotropy, angle |
| Frame drift (shear/stretch in y) | Thermal or stage drift | Each image | Drift velocity |
| Line jitter | Vibration or stray field | Each image | Amplitude, frequency |
| Field distortion | Scan non-linearity | Each image | Polynomial coefficients |
| LER / CD variation / corner rounding | Lithography and etch | Specimen (shared) | 3σ LER, correlation length, radius |
| Particles and defects | Process defects | Specimen (shared) | Density, size |
| Brightness/contrast/gamma, clipping, quantization | Detector settings | Each image | Ranges |

### B. Generic computer-vision augmentations (acceptable as extra nuisance robustness, clearly labelled, never a substitute for A)
- Mild additive Gaussian noise, which stands in for unmodelled noise sources.
- Histogram shifts, mild gamma and local contrast change.
- Small random occlusion patches, as a proxy for local damage. Keep the size under about 10% of the footprint.
- **Flips and 90° rotations applied to the whole world, before both images are rendered.** These are legitimate because layouts contain mirrored cells. They are *not* legitimate when applied to just one image (see C).
- JPEG compression, only if the organizer's data turns out to be JPEG. SEM data is normally TIFF or PNG.

### C. Unrealistic augmentations to avoid

| Avoid | Why |
|---|---|
| Flipping or 90°-rotating **only R or only S** | No physical process mirrors one acquisition. It breaks the correspondence the task depends on. |
| Large rotations (≫ 5°) or arbitrary-angle rotations between R and S | Outside the stated physics; wastes model capacity |
| Perspective or projective warps | A top-down SEM image is essentially orthographic; no tilt is in scope |
| Large elastic or free-form deformations | Real SEM distortion is smooth and low-order, or row-wise |
| Hue/saturation jitter, colour-space tricks | SEM data is grayscale (see §8 for a physical meaning of RGB) |
| Mixup, CutMix, large random erasing, style transfer | Create image content that no instrument could record |
| Identical noise or charging in R and S | Violates independence (Phase 0, E6), and inflates correlation scores |
| Producing S by naive decimation of R, or of a higher-resolution render, without the imaging model | Aliasing no instrument produces; also impossible given the footprint sizes |
| Random non-Manhattan polygons or blobs as "layout" | Not justified by any design rule (the DRAM tilt and hex lattice are the only justified exceptions) |
| Generative-model images | Geometry and ground truth unknown (UD, Phase 0) |
| A contamination "burn mark" at the target in S | Leaks the answer (§3.6) |

---

## 6. Proposed synthetic image-generation model

### 6.1 Pipeline

```
 (1) Floorplan          world ≈ 14 × 14 µm (10 µm search FOV + margin for drift and rotation)
     └─ guillotine partition into blocks:  logic | SRAM | DRAM | contact array | routing | pads/marks | dummy fill
 (2) Block generators   each emits vector geometry in nm: axis-aligned rectangles on design grids,
                        per layer (e.g. FIN, POLY, CONTACT, M1, VIA), with explicit design-rule parameters
 (3) Specimen effects   (shared) CD bias per block, corner rounding, line-end pullback,
                        LER edge perturbation (Mack-style correlated random edges), defects/particles
 (4) Target selection   pick the target point ξ* by difficulty class (unique / near-boundary / periodic);
                        compute the equivalence set E from geometry → GT via the D4 rule, and the is_ambiguous flag
 (5) Per-image pose     R: centered on ξ*, pitch p_R, small rotation α_R
                        S: centered on ξ* + drift, pitch p_S·(1+ε_s), rotation α_S, distortion D_S
 (6) Rendering          for each output pixel v, sample the world at Γ(v) (distortion included),
                        with supersampling (≈4×4) for area coverage → per-layer coverage maps
 (7) SEM contrast       material base yield + edge-enhancement term (|∇ height| through a short
                        exponential kernel) + detector asymmetry + buried layers attenuated
 (8) Optics             PSF convolution (probe ⊗ defocus ⊗ astigmatism)
 (9) Charging           low-frequency gradient + halo (large-σ blur of insulator mask)
                        + causal exponential tail along +x + slow y brightness drift
(10) Noise              Poisson(dose · signal) · gain + N(0, σ_read) + row offsets; frames averaged
(11) Detector           brightness/contrast/gamma → clip → quantize to 8 or 16 bit
(12) Output             R.png, S.png, a metadata row (GT, all sampled parameters, seeds, flags)
```

### 6.2 Why this structure
- **Vector-first, in nm.** Ground truth is exact by construction, both images come from one specimen, and pitch changes are just a configuration change.
- **Render by sampling the world at distorted coordinates**, instead of warping a rendered image:
  - It avoids interpolation artifacts.
  - The GT is the analytic inverse of the pose map, `g = Γ_S⁻¹(ξ*)`. With distortion, the inverse is found by fixed-point iteration to better than 10⁻⁶ px.
  - This addresses the half-pixel risk DA3.
- **Only the needed windows are rendered.** R needs 1000² samples and S about 4000² with supersampling. We never rasterize the full 14 µm world at 1 nm (≈ 2·10⁸ px).
- **Seeds are split per stage** (floorplan, specimen, R-imaging, S-imaging). Each factor can be varied independently, and the Phase 9 train/test splits can hold out geometry separately from noise.

### 6.3 Target difficulty classes (controls the dataset mix)

| Class | Where the target is placed | Expected behaviour |
|---|---|---|
| `unique` | Irregular logic or routing, or near a block boundary | Well posed |
| `quasi_repeat` | Standard-cell rows with repeated cell types | Near-duplicates with small differences; tests discrimination |
| `periodic` | Inside SRAM, DRAM or contact arrays, away from edges | Exact repeats; tests the D4/D8 tie-break |
| `border` | GT near the S frame edge; the footprint may be clipped | Tests partial overlap |

### 6.4 Realism validation (to be run in Phase 2/3)

| Check | Pass criterion |
|---|---|
| Visual review | A grid of R and S images shows sensible Manhattan layouts, bright edges, noise |
| Line-scan profile | Average profile across a line in R shows edge peaks shaped like the Mack/Bunday model |
| Noise statistics | Variance vs mean is roughly linear (Poisson regime) at the configured dose |
| Radial power spectrum of S | Lattice peaks sit at the expected nm⁻¹; aliased presets show folding as predicted |
| GT check | A noise-free, rotation-free render gives an NCC peak within 0.1 px of GT |
| Determinism | Same seed → byte-identical files |
| Leakage | No artifact correlates with the GT position (e.g. mean intensity near GT vs elsewhere) |

---

## 7. Implications for the matching algorithm (fed forward to Phases 5–7)
1. **Polarity-robust and illumination-robust representations** (gradient or edge-based) are motivated by edge-effect contrast, charging and possible inversion.
2. **Pre-smooth R to S's resolution before matching.** R's fine detail (LER, fins in the `advanced` preset) is only noise with respect to S.
3. **Rotation/scale search or estimation is required** (Phase 0 §2.6).
4. **Row-wise artifacts** (line jitter, scan-line noise, charging streaks) are anisotropic. Robust refinement should allow a small shear along y.
5. **Periodic presets make repeats the norm, not the exception.** The candidate and tie-break design (Phase 0, D5–D8) is central, not an edge case.

---

## 8. RGB bonus: a physically meaningful interpretation
Real SEM data has no colour, but modern SEMs record **several detectors at the same time**:

- SE (Everhart–Thornley): topography and edges
- In-lens SE: high-resolution surface detail
- BSE: material contrast

Mapping these to three channels gives a physically honest RGB image. The generator can produce all three from the same geometry by changing only the contrast weights in step (7). The matcher can then use the channels jointly. This awaits the organizer's clarification on what "RGB" means (AM10).

---

## 9. References (from memory — verify before final documentation)
1. J. I. Goldstein et al., *Scanning Electron Microscopy and X-Ray Microanalysis*, 4th ed., Springer, 2018. SE/BSE contrast, edge effect, noise, charging.
2. L. Reimer, *Scanning Electron Microscopy: Physics of Image Formation and Microanalysis*, 2nd ed., Springer, 1998.
3. P. Cizmar, A. E. Vladár, B. Ming, M. T. Postek, "Simulated SEM images for resolution measurement," *Scanning* 30, 2008. NIST "Artimagen" SEM image simulator.
4. C. A. Mack, B. D. Bunday, "Analytical linescan model for SEM metrology," *Proc. SPIE* 9424, 2015.
5. C. A. Mack, "Generating random rough edges, surfaces, and volumes," *Applied Optics* 52(7), 2013.
6. J. S. Villarrubia et al., JMONSEL Monte Carlo SEM simulation, NIST (e.g. *Ultramicroscopy*, 2015).
7. M. T. Postek, A. E. Vladár, "Does your SEM really tell the truth? How would you know?" series, *Scanning*, 2013 onward. Charging, drift, calibration.
8. M. A. Sutton et al., "Scanning electron microscopy for quantitative small and large deformation measurements, Part I," *Experimental Mechanics* 47, 2007. SEM drift and spatial distortion.
9. IRDS, *More Moore* chapter (2022/2023 editions), and public node data, for the pitch presets in §2.5.
10. J. P. Lewis, "Fast normalized cross-correlation," *Vision Interface*, 1995.
11. C. D. Kuglin, D. C. Hines, "The phase correlation image alignment method," *Proc. IEEE Conf. Cybernetics and Society*, 1975.
12. B. S. Reddy, B. N. Chatterji, "An FFT-based technique for translation, rotation, and scale-invariant image registration," *IEEE Trans. Image Processing* 5(8), 1996.

---

## 10. Phase 1 exit criteria
- [ ] You accept the image model (§6.1) and the split between shared and independent factors (§4).
- [ ] You choose the default pitch preset. **Recommendation: `intermediate`**, with `mature`, `advanced` and `dram` kept as scenario families.
- [ ] You accept the augmentation taxonomy (§5), especially the exclusion list C.
- [ ] Optional: I verify the references online before they go into the final methodology document.

Next: **Phase 2**, the layout generator (steps 1–3 of §6.1), with visual inspection outputs.
