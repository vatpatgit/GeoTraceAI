"""Sub-pixel translation estimate between two co-gridded images (misregistration check)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage


@dataclass
class ShiftEstimate:
    dx_px: float  # shift (in full-resolution pixels) that must be applied to ``b`` to match ``a`` (+x = right)
    dy_px: float  # (+y = down)
    peak: float  # normalised correlation peak in [0, 1]; low => estimate unreliable
    decimation: int

    @property
    def magnitude_px(self) -> float:
        return float(np.hypot(self.dx_px, self.dy_px))


def _edges(img: np.ndarray) -> np.ndarray:
    sm = ndimage.gaussian_filter(img.astype(np.float32), 1.0)
    gx = ndimage.sobel(sm, axis=1)
    gy = ndimage.sobel(sm, axis=0)
    return np.hypot(gx, gy)


def estimate_shift(a: np.ndarray, b: np.ndarray, valid: np.ndarray | None = None, *, max_dim: int = 1024) -> ShiftEstimate:
    """Phase correlation on edge-magnitude images (robust to radiometric differences between dates)."""
    if a.shape != b.shape:
        raise ValueError("images must share a shape")
    step = max(1, int(np.ceil(max(a.shape) / max_dim)))
    a_s = a[::step, ::step].astype(np.float32)
    b_s = b[::step, ::step].astype(np.float32)
    if valid is not None:
        v = valid[::step, ::step].astype(bool)
        fill_a = float(a_s[v].mean()) if v.any() else 0.0
        fill_b = float(b_s[v].mean()) if v.any() else 0.0
        a_s = np.where(v, a_s, fill_a)
        b_s = np.where(v, b_s, fill_b)
    ea, eb = _edges(a_s), _edges(b_s)
    if ea.std() < 1e-9 or eb.std() < 1e-9:
        return ShiftEstimate(0.0, 0.0, 0.0, step)
    ea = (ea - ea.mean()) / ea.std()
    eb = (eb - eb.mean()) / eb.std()
    win = np.outer(np.hanning(ea.shape[0]), np.hanning(ea.shape[1])).astype(np.float32)
    fa, fb = np.fft.fft2(ea * win), np.fft.fft2(eb * win)
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-9
    corr = np.fft.ifft2(cross).real
    iy, ix = np.unravel_index(int(np.argmax(corr)), corr.shape)
    peak = float(corr[iy, ix])
    h, w = corr.shape

    def refine(c: np.ndarray, i: int, n: int, axis: int) -> float:
        prev = c[(i - 1) % n, ix] if axis == 0 else c[iy, (i - 1) % n]
        nxt = c[(i + 1) % n, ix] if axis == 0 else c[iy, (i + 1) % n]
        mid = c[iy, ix]
        denom = prev - 2 * mid + nxt
        return 0.0 if abs(denom) < 1e-12 else 0.5 * (prev - nxt) / denom

    dy = iy + refine(corr, iy, h, 0)
    dx = ix + refine(corr, ix, w, 1)
    if dy > h / 2:
        dy -= h
    if dx > w / 2:
        dx -= w
    return ShiftEstimate(float(dx * step), float(dy * step), peak, step)
