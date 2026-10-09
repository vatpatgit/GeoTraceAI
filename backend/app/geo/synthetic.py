"""Deterministic synthetic bi-temporal scenes with exactly known ground-truth change.

Used by the unit tests, the demo seeder and the docs. The scenes are *synthetic*: they are not satellite
imagery, and everything derived from them must be labelled as demo data in any user interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from rasterio.transform import Affine
from scipy import ndimage

from app.geo.writers import write_geotiff

# Surface reflectances (blue, green, red, nir): typical orders of magnitude, not measured values.
SURFACES = {
    "vegetation": (0.04, 0.09, 0.05, 0.40),
    "soil": (0.16, 0.20, 0.22, 0.28),
    "built": (0.33, 0.34, 0.35, 0.33),
    "water": (0.06, 0.05, 0.03, 0.02),
}
BAND_ORDER = ("blue", "green", "red", "nir")


@dataclass
class ChangeSpec:
    kind: str  # vegetation_loss | vegetation_gain | built
    rows: tuple[int, int]
    cols: tuple[int, int]

    @property
    def area_px(self) -> int:
        return (self.rows[1] - self.rows[0]) * (self.cols[1] - self.cols[0])


DEFAULT_CHANGES = (
    ChangeSpec("vegetation_loss", (60, 120), (80, 160)),  # 60 x 80 px
    ChangeSpec("built", (200, 240), (300, 360)),  # 40 x 60 px
    ChangeSpec("vegetation_gain", (330, 380), (60, 110)),  # 50 x 50 px
    ChangeSpec("built", (400, 420), (400, 430)),  # 20 x 30 px
)


@dataclass
class SyntheticPair:
    before: Path
    after: Path
    truth_mask: np.ndarray
    changes: tuple[ChangeSpec, ...]
    transform: Affine
    crs: str
    pixel_size: float
    shape: tuple[int, int]
    meta: dict = field(default_factory=dict)


def _smooth_field(rng: np.random.Generator, shape: tuple[int, int], sigma: float) -> np.ndarray:
    f = ndimage.gaussian_filter(rng.standard_normal(shape), sigma=sigma, mode="reflect")
    return (f - f.min()) / (f.max() - f.min() + 1e-12)


def make_synthetic_pair(
    out_dir: str | Path,
    *,
    shape: tuple[int, int] = (512, 512),
    pixel_size: float = 10.0,
    origin: tuple[float, float] = (500000.0, 4500000.0),  # UTM easting/northing of the upper-left corner
    epsg: int = 32633,
    seed: int = 7,
    changes: tuple[ChangeSpec, ...] = DEFAULT_CHANGES,
    noise: float = 0.008,
    gain: float = 1.07,
    offset: float = 0.01,
    speckle: int = 25,
    dtype: str = "uint16",
    rgb_only: bool = False,
    name: str = "scene",
) -> SyntheticPair:
    """Create a before/after GeoTIFF pair with exactly known rectangular changes.

    * The *after* image has a global gain/offset (illumination difference) plus extra sensor noise.
    * ``speckle`` isolated 1-pixel outliers are added to the *after* image to exercise noise filtering.
    """
    rng = np.random.default_rng(seed)
    h, w = shape
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    veg_prob = _smooth_field(rng, shape, sigma=40)
    base_is_veg = veg_prob > 0.5
    surf = np.zeros((4, h, w), dtype=np.float32)
    for i in range(4):
        surf[i] = np.where(base_is_veg, SURFACES["vegetation"][i], SURFACES["soil"][i])
    yy, xx = np.ogrid[:h, :w]
    lake = (yy - int(h * 0.88)) ** 2 + (xx - int(w * 0.23)) ** 2 < 25**2  # permanent, identical in both dates
    for i in range(4):
        surf[i][lake] = SURFACES["water"][i]

    before = surf.copy()
    after = surf.copy()
    truth = np.zeros(shape, dtype=bool)
    for ch in changes:
        sl = (slice(*ch.rows), slice(*ch.cols))
        truth[sl] = True
        if ch.kind == "vegetation_loss":
            b, a = SURFACES["vegetation"], SURFACES["soil"]
        elif ch.kind == "vegetation_gain":
            b, a = SURFACES["soil"], SURFACES["vegetation"]
        elif ch.kind == "built":
            b, a = SURFACES["soil"], SURFACES["built"]
        else:
            raise ValueError(f"unknown change kind {ch.kind}")
        for i in range(4):
            before[i][sl] = b[i]
            after[i][sl] = a[i]

    after = after * gain + offset  # illumination / atmosphere difference
    before = before + rng.normal(0, noise, before.shape).astype(np.float32)
    after = after + rng.normal(0, noise * 1.3, after.shape).astype(np.float32)
    ys = rng.integers(0, h, speckle)
    xs = rng.integers(0, w, speckle)
    for y, x in zip(ys, xs):
        if not truth[max(0, y - 3): y + 4, max(0, x - 3): x + 4].any():
            after[:, y, x] = np.clip(after[:, y, x] + 0.25, 0, 1)
    before = np.clip(before, 0, 1)
    after = np.clip(after, 0, 1)

    if rgb_only:
        bands = ("red", "green", "blue")
    else:
        bands = BAND_ORDER
    idx = [BAND_ORDER.index(b) for b in bands]

    def to_dtype(a: np.ndarray) -> np.ndarray:
        a = a[idx]
        if dtype == "uint8":
            return (a * 255).round().astype(np.uint8)
        if dtype == "uint16":
            return (a * 10000).round().astype(np.uint16)
        return a.astype(np.float32)

    transform = Affine(pixel_size, 0, origin[0], 0, -pixel_size, origin[1])
    crs = f"EPSG:{epsg}"
    before_p = write_geotiff(out / f"{name}_before.tif", to_dtype(before), crs=crs, transform=transform,
                             descriptions=list(bands), tags={"synthetic": "true", "role": "before"})
    after_p = write_geotiff(out / f"{name}_after.tif", to_dtype(after), crs=crs, transform=transform,
                            descriptions=list(bands), tags={"synthetic": "true", "role": "after"})
    return SyntheticPair(
        before=before_p, after=after_p, truth_mask=truth, changes=changes, transform=transform,
        crs=crs, pixel_size=pixel_size, shape=shape,
        meta={"seed": seed, "dtype": dtype, "bands": list(bands), "gain": gain, "offset": offset},
    )
