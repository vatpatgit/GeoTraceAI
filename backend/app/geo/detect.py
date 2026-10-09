"""Non-learned change detectors (the always-available baseline).

Every detector writes a float32 ``change_score.tif`` in [0, 1] on the aligned grid plus the score threshold
that separates "changed" from "unchanged". Learned models (``app.ml``) produce the same artefact, so post-processing
and polygonization are method-agnostic.

Score definitions (documented user-facing semantics):
  * spectral_cva : robust change-vector magnitude m (in noise-sigma units); score = min(1, m / (3 * threshold)).
  * ndvi_diff    : score = min(1, |dNDVI| / (3 * ndvi_delta)).
  * learned      : score = sigmoid probability (uncalibrated).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window
from scipy import ndimage

from app.geo.config import DetectionConfig
from app.geo.errors import PairIncompatibleError
from app.geo.preprocess import AlignedPair, BLOCK_ROWS
from app.geo.writers import default_profile

ProgressFn = Callable[[float, str], None]
SCORE_NODATA = -1.0


@dataclass
class DetectionOutput:
    method: str
    score_path: str
    score_threshold: float  # in score space; mask = score >= score_threshold
    category_basis: str  # observed_difference | spectral_index | model_inferred
    default_category: str
    magnitude_kind: str
    confidence_kind: str | None  # None => no meaningful confidence for this method
    delta_ndvi_path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def robust_stats(x: np.ndarray) -> tuple[float, float]:
    """Median and 1.4826*MAD (a robust sigma estimate)."""
    if x.size == 0:
        return 0.0, 1.0
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    return med, 1.4826 * mad


def robust_linear_fit(x: np.ndarray, y: np.ndarray, iters: int = 20, max_samples: int = 1_000_000) -> tuple[float, float]:
    """Fit y ~ a*x + b with Tukey-bisquare iteratively re-weighted least squares.

    Real change pixels are outliers w.r.t. the global radiometric relationship, so they get (near-)zero weight and the
    fit describes the unchanged majority: the standard relative radiometric normalisation used before change detection.
    """
    if x.size > max_samples:
        sel = np.linspace(0, x.size - 1, max_samples).astype(np.int64)
        x, y = x[sel], y[sel]
    x = x.astype(np.float64)
    y = y.astype(np.float64)
    sx = robust_stats(x)[1]
    sy = robust_stats(y)[1]
    a = (sy / sx) if sx > 1e-12 else 1.0
    b = float(np.median(y) - a * np.median(x))
    for _ in range(iters):
        r = y - (a * x + b)
        s = 1.4826 * float(np.median(np.abs(r))) + 1e-12
        u = r / (4.685 * s)
        w = np.where(np.abs(u) < 1.0, (1.0 - u * u) ** 2, 0.0)
        sw = w.sum()
        if sw < 10:
            break
        mx, my = (w * x).sum() / sw, (w * y).sum() / sw
        sxx = (w * (x - mx) ** 2).sum()
        if sxx < 1e-18:
            break
        a_new = (w * (x - mx) * (y - my)).sum() / sxx
        b_new = my - a_new * mx
        converged = abs(a_new - a) < 1e-9 and abs(b_new - b) < 1e-9 * (1 + abs(b))
        a, b = float(a_new), float(b_new)
        if converged:
            break
    return a, b


def _decimated_shape(h: int, w: int, max_px: int = 4_000_000) -> tuple[int, int]:
    step = max(1, int(math.ceil(math.sqrt(h * w / max_px))))
    return max(1, h // step), max(1, w // step)


def _read_decimated(path: str, shape: tuple[int, int]) -> np.ndarray:
    with rasterio.open(path) as ds:
        return ds.read(out_shape=(ds.count, *shape), resampling=Resampling.nearest).astype(np.float32)


def _score_profile(aligned: AlignedPair) -> dict:
    return default_profile(count=1, dtype="float32", width=aligned.width, height=aligned.height,
                           crs=aligned.crs_wkt, transform=aligned.affine, nodata=SCORE_NODATA)


def _smooth_masked(arr: np.ndarray, valid: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian smoothing that does not bleed invalid pixels into valid ones (normalised convolution)."""
    if sigma <= 0:
        return arr
    num = ndimage.gaussian_filter(np.where(valid, arr, 0.0).astype(np.float32), sigma)
    den = ndimage.gaussian_filter(valid.astype(np.float32), sigma)
    return np.where(den > 1e-3, num / np.maximum(den, 1e-3), 0.0).astype(np.float32)


def _otsu(values: np.ndarray, bins: int = 256) -> float:
    hist, edges = np.histogram(values, bins=bins)
    hist = hist.astype(np.float64)
    centers = (edges[:-1] + edges[1:]) / 2.0
    w0 = np.cumsum(hist)
    w1 = hist.sum() - w0
    m0 = np.cumsum(hist * centers) / np.maximum(w0, 1e-12)
    m1 = (np.sum(hist * centers) - np.cumsum(hist * centers)) / np.maximum(w1, 1e-12)
    between = w0 * w1 * (m0 - m1) ** 2
    return float(centers[int(np.argmax(between))])


def _choose_threshold(sample: np.ndarray, cfg: DetectionConfig) -> tuple[float, dict[str, Any]]:
    if cfg.threshold_method == "fixed":
        if cfg.fixed_threshold is None:
            raise PairIncompatibleError("threshold_method 'fixed' requires fixed_threshold.", code="bad_config")
        return float(cfg.fixed_threshold), {"method": "fixed"}
    if cfg.threshold_method == "otsu":
        hi = float(np.percentile(sample, 99.9))
        thr = _otsu(sample[sample <= hi])
        return thr, {"method": "otsu"}
    med, sig = robust_stats(sample)
    thr = med + cfg.sigma_k * sig
    return float(thr), {"method": "robust_sigma", "median": med, "robust_sigma": sig, "k": cfg.sigma_k}


def _load_valid(aligned: AlignedPair) -> np.ndarray:
    with rasterio.open(aligned.valid_mask_path) as ds:
        return ds.read(1).astype(bool)


def detect_spectral_cva(aligned: AlignedPair, cfg: DetectionConfig, out_dir: str | Path,
                        progress: ProgressFn | None = None) -> DetectionOutput:
    """Robust change-vector analysis over all common optical bands.

    1. Robustly (Tukey-bisquare IRLS) fit each *after* band to the *before* band so global illumination /
       atmosphere differences do not read as change.
    2. Per-band difference, standardised by its own robust spread (noise units).
    3. Magnitude = RMS across bands; smoothed with a validity-aware Gaussian; thresholded.
    """
    report = progress or (lambda f, m: None)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    roles = aligned.roles
    nb = len(roles)
    valid = _load_valid(aligned)
    h, w = valid.shape
    dshape = _decimated_shape(h, w)
    vmask_s = _read_decimated(aligned.valid_mask_path, dshape)[0] > 0
    if vmask_s.sum() < 100:
        raise PairIncompatibleError("Too few valid pixels to estimate change statistics.", code="insufficient_valid_pixels")

    sb = _read_decimated(aligned.before_path, dshape)
    sa = _read_decimated(aligned.after_path, dshape)
    gain = np.ones(nb)
    offset = np.zeros(nb)
    for i in range(nb):
        gain[i], offset[i] = robust_linear_fit(sa[i][vmask_s], sb[i][vmask_s])  # before ~ gain * after + offset
    d_s = sa * gain[:, None, None] + offset[:, None, None] - sb
    med_d = np.zeros(nb); sig_d = np.ones(nb)
    for i in range(nb):
        med_d[i], sig_d[i] = robust_stats(d_s[i][vmask_s])
    sig_d = np.maximum(sig_d, 1e-6)
    report(0.15, "Change statistics estimated")

    m = np.zeros((h, w), dtype=np.float32)
    n_blocks = math.ceil(h / BLOCK_ROWS)
    with rasterio.open(aligned.before_path) as db, rasterio.open(aligned.after_path) as da:
        for bi in range(n_blocks):
            r0 = bi * BLOCK_ROWS
            win = Window(0, r0, w, min(BLOCK_ROWS, h - r0))
            b = db.read(window=win).astype(np.float32)
            a = da.read(window=win).astype(np.float32)
            a = a * gain[:, None, None] + offset[:, None, None]
            z = (a - b - med_d[:, None, None]) / sig_d[:, None, None]
            m[r0:r0 + win.height] = np.sqrt(np.mean(z * z, axis=0))
            report(0.15 + 0.5 * (bi + 1) / n_blocks, "Computing change magnitude")

    m = _smooth_masked(m, valid, cfg.smoothing_sigma_px)
    sample = m[valid][:: max(1, int(valid.sum() // 2_000_000))]
    thr, thr_info = _choose_threshold(sample, cfg)
    degenerate = thr <= 1e-6
    if degenerate:
        # Identical (or constant) images: there is nothing to detect. Report it instead of dividing by zero.
        thr, thr_info = 1.0, {**thr_info, "degenerate": True}
        m = np.zeros_like(m)
    score = np.clip(m / (3.0 * thr), 0.0, 1.0).astype(np.float32)
    score[~valid] = SCORE_NODATA
    score_path = out / "change_score.tif"
    _write_score(score_path, score, aligned)

    delta_ndvi_path = None
    notes = ["A robust per-band linear radiometric normalisation of the after image to the before image was applied."]
    if degenerate:
        notes.append("The two images are statistically identical; no change can be detected.")
    if "red" in roles and "nir" in roles:
        delta_ndvi_path = str(_write_delta_ndvi(aligned, valid, out / "delta_ndvi.tif"))
        notes.append("Components are labelled using the sign of the mean dNDVI (red + NIR bands present).")
    report(0.95, "Baseline detection complete")
    return DetectionOutput(
        method="spectral_cva", score_path=str(score_path), score_threshold=1.0 / 3.0,
        category_basis="observed_difference", default_category="unclassified_change",
        magnitude_kind="robust_change_vector_magnitude", confidence_kind=None,
        delta_ndvi_path=delta_ndvi_path,
        details={"threshold_zscore": thr, "threshold": thr_info, "bands": roles,
                 "band_match": {"gain": gain.tolist(), "offset": offset.tolist(), "diff_sigma": sig_d.tolist()},
                 "smoothing_sigma_px": cfg.smoothing_sigma_px, "ndvi_label_threshold": cfg.ndvi_delta},
        notes=notes,
    )


def _ndvi_block(arr: np.ndarray, roles: list[str]) -> np.ndarray:
    red = arr[roles.index("red")].astype(np.float32)
    nir = arr[roles.index("nir")].astype(np.float32)
    den = nir + red
    return np.where(np.abs(den) > 1e-6, (nir - red) / np.where(np.abs(den) > 1e-6, den, 1.0), 0.0).astype(np.float32)


DARK_PIXEL_FRACTION = 0.25  # NDVI is unreliable where (red+NIR) is below this fraction of the scene median (water, shadow)


def _write_delta_ndvi(aligned: AlignedPair, valid: np.ndarray, path: Path) -> Path:
    """dNDVI = NDVI_after - NDVI_before; NaN where invalid or where either date is too dark for a stable ratio."""
    h, w = valid.shape
    ri, ni = aligned.roles.index("red"), aligned.roles.index("nir")
    dshape = _decimated_shape(h, w)
    vs = _read_decimated(aligned.valid_mask_path, dshape)[0] > 0
    sums = []
    for p_ in (aligned.before_path, aligned.after_path):
        dec = _read_decimated(p_, dshape)
        sums.append((dec[ri] + dec[ni])[vs])
    floor = DARK_PIXEL_FRACTION * float(np.median(np.concatenate(sums))) if vs.any() else 0.0
    prof = default_profile(count=1, dtype="float32", width=w, height=h, crs=aligned.crs_wkt, transform=aligned.affine, nodata=np.nan)
    with rasterio.open(aligned.before_path) as db, rasterio.open(aligned.after_path) as da, rasterio.open(path, "w", **prof) as dst:
        for r0 in range(0, h, BLOCK_ROWS):
            win = Window(0, r0, w, min(BLOCK_ROWS, h - r0))
            b, a = db.read(window=win).astype(np.float32), da.read(window=win).astype(np.float32)
            bright = ((b[ri] + b[ni]) >= floor) & ((a[ri] + a[ni]) >= floor)
            d = _ndvi_block(a, aligned.roles) - _ndvi_block(b, aligned.roles)
            d = np.where(valid[r0:r0 + win.height] & bright, d, np.nan).astype(np.float32)
            dst.write(d[np.newaxis], window=win)
    return path


def _write_score(path: Path, score: np.ndarray, aligned: AlignedPair) -> None:
    with rasterio.open(path, "w", **_score_profile(aligned)) as dst:
        dst.write(score[np.newaxis])
        dst.set_band_description(1, "change_score")
    with rasterio.open(path, "r+") as ds:
        if min(ds.width, ds.height) >= 512:
            ds.build_overviews([2, 4, 8, 16], Resampling.average)


def detect_ndvi_diff(aligned: AlignedPair, cfg: DetectionConfig, out_dir: str | Path,
                     progress: ProgressFn | None = None) -> DetectionOutput:
    """|dNDVI| thresholding; only valid when the aligned pair has red and NIR bands."""
    roles = aligned.roles
    if "red" not in roles or "nir" not in roles:
        raise PairIncompatibleError(
            "NDVI change detection needs red and near-infrared bands, but this pair only has "
            f"{roles}. Choose the spectral change-vector method instead.", code="ndvi_bands_missing")
    report = progress or (lambda f, m: None)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    valid = _load_valid(aligned)
    report(0.1, "Computing dNDVI")
    dpath = _write_delta_ndvi(aligned, valid, out / "delta_ndvi.tif")
    with rasterio.open(dpath) as ds:
        d = ds.read(1)
    thr = float(cfg.fixed_threshold if cfg.threshold_method == "fixed" and cfg.fixed_threshold else cfg.ndvi_delta)
    mag = np.abs(np.nan_to_num(d, nan=0.0))
    mag = _smooth_masked(mag, valid, cfg.smoothing_sigma_px)
    score = np.clip(mag / (3.0 * thr), 0.0, 1.0).astype(np.float32)
    score[~valid] = SCORE_NODATA
    score_path = out / "change_score.tif"
    _write_score(score_path, score, aligned)
    report(0.95, "dNDVI detection complete")
    return DetectionOutput(
        method="ndvi_diff", score_path=str(score_path), score_threshold=1.0 / 3.0,
        category_basis="spectral_index", default_category="vegetation_change",
        magnitude_kind="abs_delta_ndvi", confidence_kind=None, delta_ndvi_path=str(dpath),
        details={"ndvi_delta_threshold": thr, "smoothing_sigma_px": cfg.smoothing_sigma_px},
        notes=["NDVI is only a proxy for vegetation vigour; a drop may be loss of cover, senescence, flooding or cloud."],
    )


def ndvi_scene_means(aligned: AlignedPair) -> dict[str, float] | None:
    """Scene-mean NDVI before/after over valid, reasonably bright pixels (None without red + NIR)."""
    if "red" not in aligned.roles or "nir" not in aligned.roles:
        return None
    h, w = aligned.height, aligned.width
    shape = _decimated_shape(h, w)
    vs = _read_decimated(aligned.valid_mask_path, shape)[0] > 0
    if not vs.any():
        return None
    ri, ni = aligned.roles.index("red"), aligned.roles.index("nir")
    vals = {}
    sums = []
    arrs = {}
    for k, p in (("before", aligned.before_path), ("after", aligned.after_path)):
        a = _read_decimated(p, shape)
        arrs[k] = a
        sums.append((a[ri] + a[ni])[vs])
    floor = DARK_PIXEL_FRACTION * float(np.median(np.concatenate(sums)))
    keep = vs & ((arrs["before"][ri] + arrs["before"][ni]) >= floor) & ((arrs["after"][ri] + arrs["after"][ni]) >= floor)
    if not keep.any():
        return None
    for k in ("before", "after"):
        vals[f"{k}_mean"] = float(np.mean(_ndvi_block(arrs[k], aligned.roles)[keep]))
    return vals
