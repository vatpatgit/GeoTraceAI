"""Mask clean-up: invalid-pixel masking, morphology, hole filling and component area filtering."""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from scipy import ndimage

from app.geo.config import PostprocessConfig
from app.geo.preprocess import AlignedPair
from app.geo.writers import default_profile

EIGHT = np.ones((3, 3), dtype=bool)
MASK_NODATA = 255


@dataclass
class PostprocessReport:
    raw_changed_px: int
    final_changed_px: int
    components_before_filter: int
    components_after_filter: int
    removed_small_components: int
    min_area_px_effective: int
    holes_filled: int
    opening_radius_px: int
    closing_radius_px: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _disk(radius: int) -> np.ndarray:
    y, x = np.ogrid[-radius: radius + 1, -radius: radius + 1]
    return (x * x + y * y) <= radius * radius


def clean_mask(score: np.ndarray, valid: np.ndarray, score_threshold: float, cfg: PostprocessConfig,
               pixel_size_m: float) -> tuple[np.ndarray, PostprocessReport]:
    """Return the cleaned boolean change mask and a report of what each step removed."""
    mask = (score >= score_threshold) & valid
    raw = int(mask.sum())
    if cfg.opening_radius_px > 0:
        mask = ndimage.binary_opening(mask, structure=_disk(cfg.opening_radius_px))
    if cfg.closing_radius_px > 0:
        # Pad so closing does not erode features touching the edge; never extend into invalid pixels.
        mask = ndimage.binary_closing(mask, structure=_disk(cfg.closing_radius_px), border_value=0) & valid

    holes_filled = 0
    if cfg.fill_holes_max_px > 0 and mask.any():
        inv_labels, n_inv = ndimage.label(~mask, structure=ndimage.generate_binary_structure(2, 1))
        if n_inv:
            sizes = np.bincount(inv_labels.ravel(), minlength=n_inv + 1)
            border = np.unique(np.concatenate([inv_labels[0], inv_labels[-1], inv_labels[:, 0], inv_labels[:, -1]]))
            small = (sizes <= cfg.fill_holes_max_px)
            small[0] = False
            small[border] = False
            fill = small[inv_labels] & valid  # only fill valid pixels
            holes_filled = int(small.sum())
            mask = mask | fill

    labels, n = ndimage.label(mask, structure=EIGHT)
    min_px = cfg.min_area_px
    if cfg.min_area_m2:
        min_px = max(min_px, int(math.ceil(cfg.min_area_m2 / (pixel_size_m ** 2))))
    removed = 0
    if n:
        sizes = np.bincount(labels.ravel(), minlength=n + 1)
        keep = sizes >= max(min_px, 1)
        keep[0] = False
        removed = int((~keep[1:]).sum())
        mask = keep[labels]
    n_after = n - removed
    report = PostprocessReport(
        raw_changed_px=raw, final_changed_px=int(mask.sum()), components_before_filter=int(n),
        components_after_filter=int(n_after), removed_small_components=removed, min_area_px_effective=int(min_px),
        holes_filled=holes_filled, opening_radius_px=cfg.opening_radius_px, closing_radius_px=cfg.closing_radius_px,
    )
    return mask, report


def write_mask(path: str | Path, mask: np.ndarray, valid: np.ndarray, aligned: AlignedPair) -> Path:
    out = np.where(valid, mask.astype(np.uint8), MASK_NODATA).astype(np.uint8)
    prof = default_profile(count=1, dtype="uint8", width=aligned.width, height=aligned.height,
                           crs=aligned.crs_wkt, transform=aligned.affine, nodata=MASK_NODATA)
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(out[np.newaxis])
        dst.set_band_description(1, "change_mask")
        dst.update_tags(values="0=unchanged,1=changed,255=invalid")
    return Path(path)
