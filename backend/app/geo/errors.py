from __future__ import annotations


class GeoProcessingError(Exception):
    """Base class for expected, user-presentable geospatial failures."""

    code = "geo_error"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        if code:
            self.code = code
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": str(self), "details": self.details}


class RasterValidationError(GeoProcessingError):
    code = "invalid_raster"


class PairIncompatibleError(GeoProcessingError):
    code = "incompatible_pair"
