"""Environmental / risk layer registry (source-backed, with honest availability).

Every layer here was checked against its provider's live service when it was added (see docs). Nothing is "real time" unless the
provider says so: the catalogue refreshes each layer's latest available date and probes a sample tile; if the probe fails the
layer is reported ``unavailable`` rather than silently shown.

Rendering: the browser fetches public tiles directly from the provider (no credentials involved). Analysis-derived layers
(Sentinel NDVI from the analysed imagery) are served by GeoTrace itself and are only available with a completed analysis.
"""
from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select

from app.database import async_session_maker
from app.models import LayerCatalog

logger = logging.getLogger(__name__)

GIBS_CAPS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml"
GIBS_WMTS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/{{time}}/{tms}/{{z}}/{{y}}/{{x}}.{ext}"
GIBS_WMS = ("https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={layer}&STYLES="
            "&FORMAT=image/png&TRANSPARENT=true&CRS=EPSG:3857&BBOX={{bbox-epsg-3857}}&WIDTH=256&HEIGHT=256&TIME={{time}}")
NS = {"w": "http://www.opengis.net/wmts/1.0", "ows": "http://www.opengis.net/ows/1.1"}


@dataclass
class LayerDef:
    id: str
    name: str
    group: str  # environmental | risk
    provider: str
    data_type: str  # observed | modelled | derived | static-hazard
    render_type: str  # raster_tiles | wms_raster | analysis_raster
    attribution: str
    legend: dict[str, Any] | None
    tile_template: str | None = None
    gibs_layer: str | None = None
    temporal_kind: str = "daily"  # daily | composite | monthly | static | analysis
    max_zoom: int | None = None
    default_opacity: float = 0.7
    limitations: list[str] = field(default_factory=list)
    requires_analysis: bool = False
    static_default_time: str | None = None


def _grad(unit: str, *stops: tuple[str, str]) -> dict[str, Any]:
    return {"kind": "gradient", "unit": unit, "stops": [{"value": v, "color": c} for v, c in stops]}


GIBS_ATTR = "NASA GIBS / ESDIS. Imagery provided by services of NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS)."

REGISTRY: list[LayerDef] = [
    LayerDef(
        id="ndvi-after", name="NDVI - after imagery (10 m)", group="environmental", provider="GeoTrace analysis (your imagery)",
        data_type="derived", render_type="analysis_raster", attribution="Computed by GeoTrace from the analysed imagery's red and NIR bands.",
        legend=_grad("NDVI", ("-0.2", "#8b4513"), ("0.2", "#e6d9a8"), ("0.5", "#7fbf5f"), ("0.9", "#0b6623")), temporal_kind="analysis", requires_analysis=True,
        limitations=["Only available for a completed analysis whose imagery has red and NIR bands.", "NDVI is a vegetation-vigour proxy; it is not corrected for atmosphere or cloud unless the source provides a quality mask."]),
    LayerDef(
        id="ndvi-before", name="NDVI - before imagery (10 m)", group="environmental", provider="GeoTrace analysis (your imagery)",
        data_type="derived", render_type="analysis_raster", attribution="Computed by GeoTrace from the analysed imagery's red and NIR bands.",
        legend=_grad("NDVI", ("-0.2", "#8b4513"), ("0.2", "#e6d9a8"), ("0.5", "#7fbf5f"), ("0.9", "#0b6623")), temporal_kind="analysis", requires_analysis=True,
        limitations=["Only available for a completed analysis whose imagery has red and NIR bands."]),
    LayerDef(
        id="ndvi", name="NDVI - global (MODIS, 16-day)", group="environmental", provider="NASA GIBS - MODIS Terra", data_type="observed",
        render_type="raster_tiles", gibs_layer="MODIS_Terra_L3_NDVI_16Day", temporal_kind="composite", max_zoom=9, attribution=GIBS_ATTR,
        legend=_grad("NDVI", ("-0.2", "#8b4513"), ("0.2", "#e6d9a8"), ("0.5", "#7fbf5f"), ("0.9", "#0b6623")),
        limitations=["250 m resolution, 16-day composite: regional context, not parcel-level evidence.", "Clouds are composited out, so very cloudy regions may show gaps or stale values."]),
    LayerDef(
        id="temperature", name="Land-surface temperature (MODIS, 8-day day)", group="environmental", provider="NASA GIBS - MODIS Terra / ASTER TES",
        data_type="observed", render_type="raster_tiles", gibs_layer="MODIS_Terra_L3_Land_Surface_Temp_8Day_Day_TES", temporal_kind="composite", max_zoom=7,
        attribution=GIBS_ATTR, legend=_grad("relative", ("cool", "#2c7bb6"), ("mild", "#ffffbf"), ("hot", "#d7191c")),
        limitations=["Land-SURFACE temperature (skin temperature), not air temperature.", "Clear-sky composite, ~1 km; undefined over water and persistent cloud.", "The colour scale is the provider's; values are not shown as numbers here."]),
    LayerDef(
        id="rainfall", name="Precipitation rate (GPM IMERG, daily)", group="environmental", provider="NASA GIBS - GPM IMERG", data_type="observed",
        render_type="raster_tiles", gibs_layer="IMERG_Precipitation_Rate", temporal_kind="daily", max_zoom=6, attribution=GIBS_ATTR,
        legend=_grad("mm/hr", ("0", "#e0f3f8"), ("5", "#4575b4"), ("20+", "#313695")),
        limitations=["Satellite precipitation estimate at ~10 km; local totals can differ from gauges.", "Near-real-time data may be revised later."]),
    LayerDef(
        id="soil-moisture", name="Root-zone soil moisture (SMAP L4)", group="environmental", provider="NASA GIBS - SMAP L4", data_type="modelled",
        render_type="raster_tiles", gibs_layer="SMAP_L4_Analyzed_Root_Zone_Soil_Moisture", temporal_kind="daily", max_zoom=6, attribution=GIBS_ATTR,
        legend=_grad("m3/m3", ("dry", "#8c510a"), ("moist", "#f6e8c3"), ("wet", "#01665e")),
        limitations=["Model-assimilated ROOT-ZONE moisture (~9 km), not surface moisture and not field-scale.", "Coarse relative to most analysis areas."]),
    LayerDef(
        id="air-quality", name="Air quality - tropospheric NO2 (OMI)", group="environmental", provider="NASA GIBS - OMI / Aura", data_type="observed",
        render_type="raster_tiles", gibs_layer="OMI_Nitrogen_Dioxide_Tropo_Column", temporal_kind="daily", max_zoom=6, attribution=GIBS_ATTR,
        legend=_grad("1e15 molec/cm2", ("low", "#f7fcb9"), ("mid", "#fd8d3c"), ("high", "#7a0177")),
        limitations=["Satellite column NO2 (an air-quality indicator), NOT surface concentration and NOT CAMS model output.", "~13 x 24 km pixels; gaps under cloud and for the OMI row anomaly."]),
    LayerDef(
        id="wildfire", name="Active-fire detections (VIIRS 375 m)", group="risk", provider="NASA GIBS / FIRMS - VIIRS S-NPP", data_type="observed",
        render_type="wms_raster", gibs_layer="VIIRS_SNPP_Thermal_Anomalies_375m_All", temporal_kind="daily", max_zoom=12, attribution=GIBS_ATTR + " Fire data: NASA FIRMS.",
        legend={"kind": "categorical", "stops": [{"value": "thermal anomaly (hotspot)", "color": "#ff4500"}]},
        limitations=["OBSERVED hotspots from the last overpasses; this is not a wildfire-risk forecast.", "Gas flares, volcanoes and industrial heat can appear as hotspots; clouds hide fires."]),
    LayerDef(
        id="flood-risk", name="Flood hazard frequency (1985-2003)", group="risk", provider="NASA GIBS - SEDAC NDH", data_type="static-hazard",
        render_type="raster_tiles", gibs_layer="NDH_Flood_Hazard_Frequency_Distribution_1985-2003", temporal_kind="static", max_zoom=7, attribution=GIBS_ATTR + " Data: SEDAC / Dartmouth Flood Observatory.",
        static_default_time="default", legend=_grad("hazard decile", ("low", "#ffffcc"), ("mid", "#41b6c4"), ("high", "#253494")),
        limitations=["Historical (1985-2003) flood-frequency hazard at ~5 km: a susceptibility indicator, not a forecast.", "Rainfall alone does not establish flood risk and this layer does not use rainfall."]),
    LayerDef(
        id="surface-water", name="Surface-water occurrence (JRC, 1984-2021)", group="risk", provider="JRC Global Surface Water (via Google Cloud Storage)", data_type="observed",
        render_type="raster_tiles", temporal_kind="static", max_zoom=13, attribution="Source: EC JRC / Google (Pekel et al., 2016, Nature). Global Surface Water v1.4.",
        tile_template="https://storage.googleapis.com/global-surface-water/tiles2021/occurrence/{z}/{x}/{y}.png", static_default_time="static",
        legend=_grad("% of time with water", ("rare", "#ffb3b3"), ("often", "#6a5acd"), ("always", "#0000ff")),
        limitations=["How often a 30 m pixel held water 1984-2021: useful flood-susceptibility context, not a hazard map or forecast."]),
    LayerDef(
        id="deforestation", name="Forest loss 2001-2024 (Hansen / UMD)", group="risk", provider="Hansen / UMD / Google / USGS / NASA (Global Forest Change v1.12)", data_type="observed",
        render_type="raster_tiles", temporal_kind="static", max_zoom=12, attribution="Hansen/UMD/Google/USGS/NASA. Hansen et al. (2013), Global Forest Change, Science 342.",
        tile_template="https://storage.googleapis.com/earthenginepartners-hansen/tiles/gfc_v1.12/loss_alpha/{z}/{x}/{y}.png", static_default_time="2001-2024",
        legend={"kind": "categorical", "stops": [{"value": "tree-cover loss (annual, 2001-2024)", "color": "#ff2d55"}]},
        limitations=["Stand-replacement tree-cover loss at 30 m, annual; it includes fire, logging and plantation harvest, so loss is not always deforestation.", "Updated yearly, so it cannot show recent clearing; use the analysis' dNDVI layer for current change."]),
]
BY_ID = {d.id: d for d in REGISTRY}


def _tile_url(d: LayerDef, ext: str = "png", tms: str | None = None) -> str | None:
    if d.tile_template:
        return d.tile_template
    if d.gibs_layer and d.render_type == "wms_raster":
        return GIBS_WMS.format(layer=d.gibs_layer)
    if d.gibs_layer:
        return GIBS_WMTS.format(layer=d.gibs_layer, tms=tms or f"GoogleMapsCompatible_Level{d.max_zoom or 6}", ext=ext)
    return None


async def _fetch_gibs_capabilities() -> dict[str, dict[str, Any]]:
    """Latest available date + matrix set for our GIBS layers (one ~6 MB request, cached by the caller)."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        resp = await client.get(GIBS_CAPS)
        resp.raise_for_status()
    root = ET.fromstring(resp.content)
    wanted = {d.gibs_layer for d in REGISTRY if d.gibs_layer}
    out: dict[str, dict[str, Any]] = {}
    for lyr in root.iter(f"{{{NS['w']}}}Layer"):
        ident = lyr.find("ows:Identifier", NS)
        if ident is None or ident.text not in wanted:
            continue
        tms = [t.find("w:TileMatrixSet", NS).text for t in lyr.findall("w:TileMatrixSetLink", NS)]
        dim = lyr.find("w:Dimension", NS)
        default = dim.find("w:Default", NS).text if dim is not None and dim.find("w:Default", NS) is not None else None
        fmt = [f.text for f in lyr.findall("w:Format", NS)]
        out[ident.text] = {"default": default, "tms": tms[0] if tms else None, "formats": fmt}
    return out


async def _probe(url: str, time: str | None) -> tuple[bool, str]:
    u = url.replace("{time}", time or "default").replace("{z}", "2").replace("{x}", "1").replace("{y}", "1").replace(
        "{bbox-epsg-3857}", "-10018754,-10018754,10018754,10018754")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0), follow_redirects=True) as client:
            r = await client.get(u)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/") and len(r.content) > 50:
            return True, "sample tile OK"
        return False, f"sample tile returned HTTP {r.status_code} ({r.headers.get('content-type', '?')})"
    except Exception as exc:
        return False, f"unreachable: {type(exc).__name__}"


def _row_values(d: LayerDef, availability: str, detail: str, default_time: str | None, tile_url: str | None, tms: str | None) -> dict[str, Any]:
    return dict(
        name=d.name, group=d.group, provider=d.provider, data_type=d.data_type, render_type=d.render_type, crs="EPSG:3857",
        config={"tile_url": tile_url, "gibs_layer": d.gibs_layer, "max_zoom": d.max_zoom, "tms": tms},
        legend=d.legend, temporal={"kind": d.temporal_kind, "default_time": default_time}, attribution=d.attribution,
        limitations=d.limitations, default_visible=False, default_opacity=d.default_opacity, availability=availability,
        availability_detail=detail,
    )


async def refresh_availability(probe: bool = True) -> list[dict[str, Any]]:
    """Update every layer's latest date + availability. Network failures degrade to 'unknown' (never fake 'available')."""
    caps: dict[str, dict[str, Any]] = {}
    caps_error = None
    if probe:
        try:
            caps = await _fetch_gibs_capabilities()
        except Exception as exc:
            caps_error = f"GIBS capabilities unavailable ({type(exc).__name__})"
            logger.warning(caps_error)
    now = datetime.now(timezone.utc)
    results = []
    probes = {}
    plan: dict[str, tuple[str | None, str | None, str | None]] = {}
    for d in REGISTRY:
        c = caps.get(d.gibs_layer or "", {})
        tms = c.get("tms")
        default_time = c.get("default") or d.static_default_time
        url = _tile_url(d, tms=tms)
        plan[d.id] = (default_time, url, tms)
        if probe and url and not d.requires_analysis:
            probes[d.id] = asyncio.create_task(_probe(url, default_time))
    async with async_session_maker() as db:
        for d in REGISTRY:
            default_time, url, tms = plan[d.id]
            if d.requires_analysis:
                availability, detail = "requires_analysis", "Needs a completed analysis with red + NIR bands."
            elif not probe:
                availability, detail = "unknown", "Not probed yet."
            else:
                ok, msg = await probes[d.id]
                availability = "available" if ok else "unavailable"
                detail = msg + (f"; {caps_error}" if caps_error else "")
                if d.gibs_layer and not caps.get(d.gibs_layer) and not caps_error:
                    detail += "; layer not found in the provider capabilities"
            row = await db.get(LayerCatalog, d.id)
            vals = _row_values(d, availability, detail, default_time, url, tms)
            if row is None:
                row = LayerCatalog(id=d.id, **vals)
                db.add(row)
            else:
                for k, v in vals.items():
                    setattr(row, k, v)
            row.last_checked_at = now
            if availability == "available":
                row.last_updated_at = now if row.last_updated_at is None else row.last_updated_at
            results.append({"id": d.id, "availability": availability})
        await db.commit()
    return results


async def sync_catalog() -> None:
    """Startup: make sure every layer has a row (instantly, offline-safe) then probe in the background."""
    async with async_session_maker() as db:
        existing = {r for (r,) in (await db.execute(select(LayerCatalog.id))).all()}
        for d in REGISTRY:
            if d.id not in existing:
                db.add(LayerCatalog(id=d.id, **_row_values(d, "requires_analysis" if d.requires_analysis else "unknown",
                                                           "Not probed yet.", d.static_default_time, _tile_url(d), None)))
        await db.commit()
    asyncio.create_task(_safe_refresh())


async def _safe_refresh() -> None:
    try:
        await refresh_availability(probe=True)
    except Exception:
        logger.exception("layer availability refresh failed")
