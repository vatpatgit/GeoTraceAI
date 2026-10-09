"""Typed, serialisable configuration for the geospatial pipeline.

Every threshold the pipeline applies is a field here (nothing is hard-coded in algorithms) and the effective
configuration is persisted with each analysis for reproducibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from typing import Any, Literal

DetectionMethod = Literal["auto", "spectral_cva", "ndvi_diff", "learned_siamese"]
ThresholdMethod = Literal["robust_sigma", "otsu", "fixed"]


def _from_dict(cls, data: dict[str, Any] | None):
    data = data or {}
    names = {f.name for f in fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise ValueError(f"Unknown {cls.__name__} option(s): {sorted(unknown)}")
    return cls(**data)


@dataclass
class PreprocessConfig:
    pixel_size_m: float | None = None  # None => coarser of the two inputs (never invent detail)
    max_pixels: int = 64_000_000  # hard cap on the aligned grid (memory guard)
    min_overlap_fraction: float = 0.10  # of the smaller footprint; below this the pair is rejected
    cloud_scl_invalid: tuple[int, ...] = (0, 1, 3, 8, 9, 10)  # Sentinel-2 SCL classes treated as invalid
    registration_warn_px: float = 1.0
    registration_min_peak: float = 0.08

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PreprocessConfig":
        if data and "cloud_scl_invalid" in data:
            data = {**data, "cloud_scl_invalid": tuple(data["cloud_scl_invalid"])}
        return _from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cloud_scl_invalid"] = list(self.cloud_scl_invalid)
        return d


@dataclass
class DetectionConfig:
    method: DetectionMethod = "auto"
    threshold_method: ThresholdMethod = "robust_sigma"
    sigma_k: float = 4.0  # robust z-score cut-off for robust_sigma
    fixed_threshold: float | None = None  # used when threshold_method == "fixed" (z-score units; |dNDVI| for ndvi_diff)
    ndvi_delta: float = 0.20  # |dNDVI| threshold for ndvi_diff
    smoothing_sigma_px: float = 0.0  # optional gaussian pre-smoothing of the magnitude surface (blurs edges; off by default)
    model_id: str | None = None  # learned model registry id (None => registry default)
    model_threshold: float | None = None  # None => threshold stored with the checkpoint
    target_gsd_m: float | None = None  # GSD the learned model is fed; None => the resolution the checkpoint was trained at
    tile_size: int = 256
    tile_overlap: int = 64
    device: Literal["auto", "cpu", "cuda"] = "auto"
    band_map: dict[str, int] | None = None  # explicit {role: 1-based band index} override for BOTH images

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DetectionConfig":
        return _from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PostprocessConfig:
    opening_radius_px: int = 1  # removes isolated pixels / thin spurs (0 disables)
    closing_radius_px: int = 1  # bridges 1-px gaps inside a change (0 disables)
    fill_holes_max_px: int = 16  # holes smaller than this are filled
    min_area_px: int = 4  # components smaller than this many pixels are dropped
    min_area_m2: float | None = None  # additional absolute floor; the stricter of the two wins
    simplify_tolerance_px: float = 0.5  # Douglas-Peucker tolerance (in pixels) for output polygons; 0 disables
    max_features: int = 50_000  # keep the largest N if exceeded (flagged in the report)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PostprocessConfig":
        return _from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SeverityConfig:
    """Documented, heuristic priority rules. NOT a calibrated probability or an impact estimate.

    Base tier from area, optionally escalated one tier for high magnitude and/or proximity to a monitored boundary.
    """

    area_m2_medium: float = 2_500.0  # 0.25 ha
    area_m2_high: float = 10_000.0  # 1 ha
    area_m2_critical: float = 50_000.0  # 5 ha
    magnitude_escalation: float = 0.85  # magnitude (0..1) at/above which the tier is bumped by one
    proximity_escalation_m: float = 1_000.0  # within this distance of a monitored boundary => bump by one
    escalate_on_proximity: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SeverityConfig":
        return _from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineConfig:
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    postprocess: PostprocessConfig = field(default_factory=PostprocessConfig)
    severity: SeverityConfig = field(default_factory=SeverityConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PipelineConfig":
        data = data or {}
        unknown = set(data) - {"preprocess", "detection", "postprocess", "severity"}
        if unknown:
            raise ValueError(f"Unknown pipeline config section(s): {sorted(unknown)}")
        return cls(
            preprocess=PreprocessConfig.from_dict(data.get("preprocess")),
            detection=DetectionConfig.from_dict(data.get("detection")),
            postprocess=PostprocessConfig.from_dict(data.get("postprocess")),
            severity=SeverityConfig.from_dict(data.get("severity")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "preprocess": self.preprocess.to_dict(),
            "detection": self.detection.to_dict(),
            "postprocess": self.postprocess.to_dict(),
            "severity": self.severity.to_dict(),
        }
