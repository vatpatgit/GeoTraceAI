# Live hazard alerts

Real-time alerts for earthquakes, fire hotspots and storm events near the user's saved areas of interest (AOIs), built on the OSIRIS public API
(`https://osirisai.live/api/...`). It is a separate alert source from satellite change detection and from OpenWeather weather alerts, and the UI says so.

## What the feed provides (checked live on 2026-10-09)

| Endpoint | Content | Used? |
|---|---|---|
| `/earthquakes` | USGS events (id, lat/lng, magnitude, depth, place, time in ms, tsunami flag) | **yes** |
| `/fires` | NASA FIRMS thermal anomalies, ~2,000 global records (lat/lng, FRP, confidence, date, time) | **yes** (satellite hotspots, not confirmed fires) |
| `/weather` | NASA EONET events (storms, severity, date, source link) | **yes** |
| `/air-quality` | returned `{"stations":[]}` — no records, so the schema could not be verified | **no** (nothing is guessed) |
| `/radar` | country-level internet outages (IODA) at country centroids | **no** (cannot be matched to an AOI meaningfully) |

The endpoints are undocumented and belong to a third party: they may change, be rate limited or disappear. Parsing is defensive (unknown records are skipped),
all text is sanitised, and a feed that fails is reported as *unknown*, never as "no alerts". Check the provider's terms before relying on it commercially.

## How it works

* `providers/hazards.py` fetches the three feeds concurrently (fixed, configured base URL; bounded timeout and retries; one failing feed does not stop the others).
* `services/hazards.py` matches events to every AOI by **geodesic distance to the nearest edge of the AOI** (0 when inside):
  earthquakes ≥ `HAZARD_QUAKE_MIN_MAG` within `HAZARD_QUAKE_RADIUS_KM` (and ≤ `HAZARD_MAX_AGE_HOURS` old); fire hotspots (low confidence dropped) within
  `HAZARD_FIRE_RADIUS_KM`, **aggregated per AOI and UTC day**; storm events within `HAZARD_STORM_RADIUS_KM`. Severity is a heuristic tier computed from the figures
  (magnitude; hotspot count / radiative power; the feed's own severity for storms) and is stored with the evidence in `details`.
* Alerts are stored in `hazard_alerts` (migration `0005`), unique per (AOI, kind, external id). A re-fetch never duplicates; changed data updates the row; **a worse
  severity (or a returning alert) makes it unread again**; alerts no longer reported expire (but a kind whose fetch failed is left alone).
* One upstream fetch is shared (`HAZARD_MIN_REFRESH_S`, default 60 s) however many users or AOIs ask.
* **Real time**: `HAZARD_REFRESH_MINUTES` (≥ 2) starts an embedded scheduler on the server; the web app also checks every 2 minutes while open and shows a single
  summary toast for new unread alerts. The Alerts page has a *Live hazard alerts* section with type filter, "Check now", mark-as-read and "Show on map".

## API (`/api/v1/hazard-alerts`, authenticated, user-scoped)

`GET /status` · `GET /` (`kind`, `unread`, `include_expired`, `limit`) · `POST /refresh` (`{force}`; read-only roles cannot force) · `POST /read` (`{ids}` or `{all:true}`).
Users only ever see alerts for AOIs in projects they can read.

## Configuration (`backend/.env.example`)

`HAZARD_FEED_PROVIDER` (`osiris`|`none`), `HAZARD_FEED_URL`, `HAZARD_TIMEOUT_S`, `HAZARD_REFRESH_MINUTES` (0 = no scheduler), `HAZARD_MIN_REFRESH_S`, `HAZARD_QUAKE_MIN_MAG`,
`HAZARD_QUAKE_RADIUS_KM`, `HAZARD_FIRE_RADIUS_KM`, `HAZARD_STORM_RADIUS_KM`, `HAZARD_MAX_AGE_HOURS`, `HAZARD_STORM_MAX_AGE_HOURS`.

## Verification

* Live: a temporary AOI placed next to the strongest quake in the feed (an M7.7 Panama sequence) produced 16 earthquake alerts with correct distances, the second refresh
  created nothing (cache + dedup), mark-read worked, and the temporary AOI was deleted. A real fire-hotspot alert also appeared for an existing demo AOI.
* A real bug was found and fixed this way: millisecond timestamps were rejected by an over-strict numeric guard (earthquakes parsed as 0 records).
* Automated: `backend/tests/db/test_hazard_alerts.py` (10 tests: parsing incl. hostile fields, thresholds, aggregation, geodesic distance, dedup / re-notify / expiry,
  failed-feed safety, isolation, outage reporting) and `src/components/pages/HazardAlerts.test.tsx` (6 tests). These use **mocked feed payloads**; the live check above is manual.

## Limitations

* Proximity is not impact: an alert means an event was reported near the area, not that the area was affected.
* Fire hotspots are thermal anomalies (VIIRS), including industrial heat and false detections.
* No air-quality or internet-outage alerts (see table). No push/email delivery; notifications are in-app (toast + inbox).
* The shared cache and scheduler are per API process.
