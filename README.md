# GeoTrace

Bi-temporal satellite change detection for rapid urban-encroachment and disaster-impact assessment
(FUSION 2026, problem GEOAI 04). GeoTrace takes a *before* and an *after* image of the same place — uploaded GeoTIFFs or
Sentinel-2 scenes retrieved server-side — aligns them, detects what changed, turns the result into georeferenced
polygons, and lets an analyst explore, review, alert on, query and export those changes on a 3D globe, a 2D map or a
swipe-compare view.

GeoTrace was rebuilt from the earlier *TerraTrack* prototype. What was reused, refactored, rebuilt and added is recorded
in [docs/GEOTRACE_MIGRATION_AUDIT.md](docs/GEOTRACE_MIGRATION_AUDIT.md).

> **Integrity rules the product follows.** Nothing is simulated silently: the API client has no mock fallback; seeded demo
> data is always badged *DEMO* (and flagged inside exports/reports); a baseline detector has no confidence (the UI says
> "n/a"); a learned-model score is labelled *uncalibrated*; severity is a configurable heuristic tier, never a probability;
> categories are labelled by how they were inferred; AI answers are computed from stored records and any language-model
> wording is discarded if it contains a figure that is not in those records.

## Architecture

```
Browser (Next.js 14, React 18, TypeScript, Tailwind, Zustand, Recharts)
  ├─ 2D map + compare  — MapLibre GL        ┐ one shared store: selection, filters, layers,
  ├─ 3D globe          — CesiumJS (no ion)  ┘ camera requests, server-filtered detections
  └─ pages: overview · map · analyses · changes · regions · alerts · analytics · reports · settings · admin
        │  REST (JWT bearer)
FastAPI (SQLAlchemy 2 async, GeoAlchemy2, Alembic migrations) ─────────────── PostgreSQL 15 + PostGIS
  ├─ app/geo        validated GeoTIFF I/O → pair validation → metric-grid alignment (rasterio/WarpedVRT) → registration
  │                 check → detectors (robust CVA, ΔNDVI, learned Siamese ResNet50-UNet) → MMU/morphology → polygons
  │                 (geodesic area) → severity heuristic → GeoJSON / GeoPackage / CSV
  ├─ app/jobs       Postgres-as-queue (SELECT … FOR UPDATE SKIP LOCKED); embedded or separate worker; cancel, retry,
  │                 stale-job recovery, ordered progress events
  ├─ app/providers  Sentinel-2: Copernicus Data Space (STAC + Process API) or Sentinel Hub; OAuth server-side only
  ├─ app/layers     NASA GIBS / Hansen / JRC layer registry with real availability probing
  ├─ app/analytics  approved query operations + deterministic NL parser + optional LLM wording (grounded)
  └─ app/services   access control (admin/user/viewer, private/shared projects), alerts engine, reports (JSON/CSV/PDF)
```

Long geospatial work never runs inside a request handler: `POST /analyses` enqueues a job and returns `202`.

## Requirements

* Node.js 18+ and npm
* Python 3.12 (3.10+ works) with GDAL wheels from PyPI (`rasterio` ships its own GDAL)
* Docker (for PostGIS) — or any PostgreSQL 15+ with the PostGIS extension
* Optional: an NVIDIA GPU + CUDA PyTorch for faster learned-model inference (CPU works)

## Install and run (development)

### 1. Database

```bash
docker run -d --name geotrace-db -p 55432:5432 -e POSTGRES_USER=geotrace -e POSTGRES_PASSWORD=geotrace_dev -e POSTGRES_DB=geotrace_dev postgis/postgis:15-3.4
```

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows;  source .venv/bin/activate on Linux/macOS
pip install -r requirements-dev.txt
pip install -r requirements-ml.txt  # optional: PyTorch for the learned model (add --extra-index-url for CUDA/CPU wheels)
cp .env.example .env              # then edit: JWT_SECRET_KEY, DATABASE settings
```

Minimum `.env` for the database above (generate a real secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`):

```
JWT_SECRET_KEY=<at least 32 random characters>
DATABASE_URL=postgresql+asyncpg://geotrace:geotrace_dev@localhost:55432/geotrace_dev
CORS_ORIGINS=http://localhost:3000
JOB_RUNNER=embedded
```

```bash
python -m app.migrate                                   # apply Alembic migrations (the schema is never created implicitly in production)
python -m app.cli create-user --email you@example.com --name "Your Name" --role admin   # prompts for a password (>= 12 chars)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Interactive API docs: <http://127.0.0.1:8000/docs>. Health: `/health`, readiness (database + storage): `/ready`.

### 3. Frontend

```bash
npm install
cp .env.example .env.local        # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
npm run dev                       # http://localhost:3000  (copies CesiumJS assets to public/cesium first)
```

Production build: `npm run build && npm start`.

### 4. Try it without your own imagery (optional, clearly labelled demo)

```bash
cd backend
DEMO_MODE=true python -m app.demo.seed --owner-email you@example.com      # add --reset to rebuild
```

This creates two synthetic scene pairs (rectangles + noise with *known* changes over Rondônia coordinates), runs the real
pipeline on them, and adds a demo reserve region and alert rule. Everything is flagged `is_demo` and shown with a DEMO badge.
It is not satellite data.

### Using it

1. **Analyses → New analysis → Upload GeoTIFFs.** The server verifies the file *content* (not the extension), reports CRS,
   resolution, bands and footprint (there is no date field: uploaded imagery is compared by footprint, not by date).
   The pair is validated (overlap, CRS, resolution, bands) before you can run it.
   *or* **Search Sentinel-2:** draw/enter an AOI and two date windows; GeoTrace queries the catalogue, selects the least
   cloudy acquisition per window by a published rule, retrieves the bands and records provenance (provider, product id, time,
   cloud cover). Retrieval needs server credentials (below); without them the UI says so and uploads still work.
2. Pick a detector: *Automatic*, *Spectral baseline* (robust change-vector analysis, any sensor), *NDVI difference*
   (needs red + NIR) or the *learned model* (see limitations).
3. Watch job progress; open the globe / map / compare view. Detections are selectable from the list, the map and the globe
   (shared selection); filters and exports apply server-side to exactly what you see.
4. Review detections (confirm / reject), create alert rules, ask questions in **Analytics**, download **Reports** and exports.

## Configuration (backend `.env`)

See [backend/.env.example](backend/.env.example) for every variable. The important ones:

| Variable | Purpose |
|---|---|
| `JWT_SECRET_KEY` | **Required**, ≥ 32 chars. Never commit it. |
| `DATABASE_URL` or `POSTGRES_*` | PostGIS connection. |
| `ENV` | `development` / `test` / `production`. Production refuses unsafe settings (weak secret, auto-migrate, demo mode). |
| `JOB_RUNNER` | `embedded` (in-process), `external` (run `python -m app.jobs.worker`), `off`. |
| `SENTINEL_PROVIDER` + `SENTINEL_HUB_CLIENT_ID/SECRET` | Sentinel-2 retrieval. `cdse` for Copernicus Data Space OAuth clients (`sh-<uuid>` ids), `sentinel_hub` for the commercial service. Server-side only. |
| `MODEL_DIR`, `ML_ROOT`, `ML_DEVICE` | Learned-model weights (see below). |
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` | Optional wording for analytics answers. Analytics works without it. |
| `FIRMS_MAP_KEY` | Optional NASA FIRMS key for active-fire hotspots. |
| `OPENWEATHER_API_KEY` | Optional. Enables weather alerts. The Alerts product is a separate OpenWeather offering: the key's plan must include it (otherwise the provider answers HTTP 401). Server-side only. |
| `WEATHER_LOOKAHEAD_HOURS`, `WEATHER_MAX_AOI_KM2`, `WEATHER_MAX_VERTICES`, `WEATHER_MIN_REFRESH_S`, `WEATHER_REFRESH_MINUTES`, `OPENWEATHER_TIMEOUT_S` | Weather-alert window (default 48 h, provider supports ~5 days), AOI limits, refresh guard, scheduled refresh interval (0 = off) and request timeout. |

Frontend: only `NEXT_PUBLIC_API_BASE_URL` (a URL, not a secret).

### Compare dates + ML changes

Instead of typing coordinates you can click the **rectangle** tool (or *Select area on the map*), drag a box on the 2D map or the 3D globe, and the
West/South/East/North fields are filled in automatically (Esc cancels; editing the fields redraws the box). Maximum 0.5° per side.

Map page -> calendar icon: enter a box (or pick a monitored region) and two dates; GeoTrace retrieves one Sentinel-2 image per date and shows
them in the slider / side-by-side compare view. The **ML changes** switch runs the fine-tuned model on the two images (cloud, shadow and
no-data pixels are masked first), outlines the flagged areas on the after image and shows statistics (count, area, share of the compared
area, size classes). **Save as analysis** re-runs the same model on the full-quality scenes as a stored analysis (polygons, severity,
alerts, exports, reports, analytics).

### Compare two ordinary images (PNG, JPEG, WebP, BMP, GIF)

The same upload slots also take ordinary images. They carry no coordinates, so they stay in your browser (only sent to the model endpoint), are compared **without a
map** at `/image-compare` (slider or side by side, shared zoom and pan), and are assumed to show the same area framed identically (proportions must match within 3%;
a slightly different size is resized with a notice). The **ML changes** switch runs the same models via `POST /imagery/plain-ml-changes` (files are checked by content,
not by extension) and draws the detections in image-pixel space on the after image. Without the optional **Pixel size (m)** the model sees the image at its native scale
and areas are reported as a share of the image, never as invented square metres; with it, the aerial or Sentinel-2 model is chosen from the resolution and m2 areas
are reported. Two GeoTIFFs or two ordinary images work; mixing a GeoTIFF with an ordinary image is refused (one has coordinates, the other does not). Saving as a stored
analysis is only available for GeoTIFFs. Plain TIFFs without georeferencing are not supported here (browsers cannot display them).

### Compare two uploaded GeoTIFFs

Analyses -> New analysis -> Upload GeoTIFFs: as soon as both images are uploaded and the pair validates, the app opens the comparison **by itself** (no button; a **Compare side by side** button remains for re-opening it). It renders both
over their common area on one pixel grid (`GET /imagery/{id}/render`) and opens the compare view (slider or side by side). The **ML changes** switch runs the
learned model on the pair (`POST /imagery/ml-changes`): the aerial-trained `levir-cd-v1` for imagery finer than ~5 m/px, the Sentinel-2 fine-tune `oscd-s2-v1`
for coarser imagery (the choice and reason are returned and shown). Uploaded imagery has no cloud mask (only no-data is excluded) and the model sees an 8-bit RGB
rendering of your bands. **Save as analysis** stores the same detection as a normal analysis. Works for any pair that passes validation (same area, overlapping, RGB).

### Weather alerts (OpenWeather Alerts API)

Alerts page -> **Weather alerts (OpenWeather)**: pick a saved AOI (or add one from a monitored region), choose **Get alerts**, and inspect what
the provider returns: title, description, tags, source, severity / urgency / certainty, event time, affected area, last-retrieved time. **Map** fits
the map to the alert area and opens a detail card; alert areas are drawn as dashed severity-coloured outlines on the 2D map and 3D globe, in their own
layer ("Weather alerts (provider)") that is separate from imagery and change-detection polygons. The area is the provider's indicative alert geometry,
not satellite-derived and not the extent of damage.

* Backend: `POST /weather-alerts/refresh`, `GET /weather-alerts`, `GET /weather-alerts/events`, `POST /weather-alerts/events/read`,
  `PATCH /weather-alerts/aois/{id}/monitoring`, `GET /weather-alerts/status`. The key (`OPENWEATHER_API_KEY`) is read only by the server; the AOI polygon
  is validated (single WGS84 Polygon, valid ring, vertex / area limits) and sent as the `location` GeoJSON parameter.
* Stored per AOI (`weather_alerts`, unique per provider alert id) with change detection: an alert that is new or materially changed (title, description,
  tags, severity, urgency, certainty, times, geometry) creates one in-app notification event; an unchanged re-fetch creates none. Alerts the provider no longer
  returns are marked `expired` only after a successful fetch (an empty answer is valid; a failed fetch never expires anything).
* Refresh is on demand, rate-guarded per AOI (`WEATHER_MIN_REFRESH_S`, default 300 s; "Force refresh" overrides). Scheduled refresh is opt-in: switch
  **Monitor** on for an AOI and set `WEATHER_REFRESH_MINUTES` (>= 15) with `JOB_RUNNER=embedded`; AOIs are refreshed sequentially with a pause between calls.
* Viewers can read stored alerts; only analysts/admins can call the provider (it is a metered service).

### Re-training the Sentinel-2 model

```bash
# data: ML/datasets/OSCD_RGB (parquet mirror of OSCD, https://huggingface.co/datasets/blanchon/OSCD_RGB; check the upstream licence before redistributing)
python ML/scripts/finetune_oscd.py --epochs 60          # ~20 min on a 4 GB laptop GPU; writes ML/experiments/oscd_finetune/results.json
python ML/scripts/export_for_backend.py                 # weights-only .pt + model card (metrics, baselines, limitations) into backend/models
```

### Learned model weights

The Siamese ResNet50-UNet checkpoints are not committed (`*.pt`/`*.pth` are git-ignored). Export weights-only files and
model cards (with the verified held-out metrics and limitations) for the backend:

```bash
python ML/scripts/export_for_backend.py --out backend/models
```

If no weights are present the learned detector is simply unavailable; the baseline detectors are unaffected.

## Tests

Backend (needs a throw-away PostGIS database whose name contains `test`; the suite rebuilds its schema through the real
migrations and refuses to run against any other database name):

```bash
docker run -d --name geotrace-test-db -p 55432:5432 -e POSTGRES_USER=geotrace -e POSTGRES_PASSWORD=geotrace_test -e POSTGRES_DB=geotrace_test postgis/postgis:15-3.4
cd backend
python -m pytest -q                       # DB tests are skipped (not passed) if the database is unreachable
python -m pytest tests/geo tests/ml -q    # geospatial / ML tests need no database
```

Optional live-provider test (opt-in, uses real credentials and network): `tests/integration/test_sentinel_live.py`.

Frontend:

```bash
npm test                  # Vitest + Testing Library (store, API client, components, pages)
npm run lint && npm run typecheck && npm run build
npx playwright install chromium           # once
npx playwright test e2e/access.spec.ts    # browser tests with the API stubbed (auth gating, error/empty states, no dead links)
```

Acceptance workflow in a real browser against a real backend (sign in → upload → detect → explore → export → alert → report):

```bash
python backend/scripts/make_e2e_fixtures.py .e2e-fixtures        # writes a synthetic before/after pair
# backend running with CORS_ORIGINS including the frontend origin, frontend running (npm run dev)
E2E_BASE_URL=http://localhost:3000 E2E_EMAIL=<user> E2E_PASSWORD=<password> E2E_FIXTURE_DIR=$PWD/.e2e-fixtures npx playwright test e2e/acceptance.spec.ts
```

The acceptance test is **skipped** when those variables or the backend are missing.

## Docker (API + worker + PostGIS)

```bash
cd backend
cp .env.example .env              # set POSTGRES_PASSWORD and JWT_SECRET_KEY
docker compose up --build -d
docker compose exec api python -m app.migrate
```

`docker-compose.yml` runs the API with an external worker (`JOB_RUNNER=external`); the dev override
(`docker-compose.override.yml`, loaded automatically) switches to hot-reload with an embedded worker.

## API surface (all under `/api/v1`, bearer-token authenticated unless noted)

`auth/login` · `auth/me` · `users/*` (admin) · `projects` + `projects/{id}/aois` · `imagery/upload|validate-pair|{id}|{id}/tiles` ·
`analyses` (create 202, list, get, events, cancel, retry, delete, `features` incl. GeoJSON + server-side filters, `features/{id}/review`,
`export` GeoJSON/GeoPackage/CSV, `artifacts/{name}`, `tiles/{layer}/{z}/{x}/{y}.png`, `evaluate-alerts`) · `alerts` + `alerts/rules` ·
`sentinel/status|search|acquire|preview` · `layers` · `regions` · `analytics/query|overview` · `reports/analyses/{id}?format=json|csv|pdf` ·
`system/status` · `/health`, `/ready` (unauthenticated).

Roles: **admin** (everything, user management, regions), **user** (own projects, analyses, rules), **viewer** (read-only).
Projects are `private` or `shared`; hidden resources return `404`, not `403`.

## Known limitations (read before relying on results)

* **Learned models.** The three original checkpoints were trained on 0.5-2 m aerial RGB building-change data and are **not validated on
  Sentinel-2**. For Sentinel-2 the Compare-dates tool uses `oscd-s2-v1`, the LEVIR-CD checkpoint fine-tuned on real Sentinel-2 pairs
  (OSCD, RGB, 10 m). On the 10 official OSCD test scenes it reaches F1 0.52 (IoU 0.35, precision 0.68, recall 0.42) versus F1 0.30 for the
  starting checkpoint and 0.24 for a spectral change-vector baseline (threshold and epoch chosen on 3 separate validation scenes; per-scene F1
  ranges 0.06-0.71). It was fine-tuned on only 11 image pairs, detects *urban* change (new buildings/roads), and is not validated on your area.
  Generic analyses keep their previous default (`levir-cd-v1` / spectral baseline); `learned_siamese` with `model_id: oscd-s2-v1` selects the new model.
* **Baseline detectors flag any radiometric/vegetation change** — including seasonal, atmospheric, shadow and harvest effects.
  Categories (`vegetation_decrease`, …) are index-based inferences; only `building_change`/`land_cover_change` come from a model.
  Nothing is human-verified until a user confirms it.
* **Severity** is a configurable heuristic (area, magnitude, proximity to monitored boundaries). On the synthetic demo data most
  polygons are large and therefore land in the top tier — that reflects the heuristic, not a measured hazard level.
* **Sentinel-2:** one scene per date window (least-cloud rule, scene-classification masking); no multi-scene mosaicking or
  atmospheric correction beyond the provider's L2A product. Tiled retrieval is capped by `MAX_AOI_KM2`.
* **Environmental/risk layers** are third-party observations at coarse resolution, probed for availability at run time and shown
  with their limitations; they are context, not part of detection. A layer that cannot be reached is shown as unavailable.
* **Weather alerts:** the OpenWeather documentation does not publish the full example response, rate limits or the plan required, so the parser accepts
  several plausible shapes and stores only what is present (missing severity/urgency/certainty are shown as "unknown"); a 401 may mean the plan lacks the Alerts product.
  Only single Polygon AOIs are supported (the provider accepts Point or Polygon). Alert geometry is whatever the provider returns; it is not validated against reality.
  Notifications are in-app only (no e-mail/SMS/webhook). Clicking an alert polygon on the 3D globe is not wired (select from the list or on the 2D map).
* **Compare/globe rendering** uses the same server-rendered raster tiles as the 2D map; very large AOIs are limited by tile
  rendering time. Tiles are rendered on demand and cached only by the browser (private `Cache-Control` + ETag); there is no server-side tile cache.
* **Auth tokens** are kept in browser `localStorage` (documented trade-off of the inherited auth design); there is no refresh-token flow,
  rate limiting or audit log UI. Put the API behind TLS and a reverse proxy with rate limits in production.
* **Retention:** uploaded imagery and artifacts are kept until the owner deletes the analysis/asset; there is no automatic expiry yet.
* Scale tested: synthetic 512×512 scenes and the Sentinel AOIs described in the audit. Not load-tested.

## Repository layout

```
src/app            Next.js routes (map, analyses, changes, regions, alerts, analytics, reports, settings, admin)
src/components     shell/, map/ (MapLibre, Cesium, compare), panels/, analyses/, pages/, analytics/, ui/
src/store          Zustand stores (shared map/selection/filter/layer state)
src/lib/api        typed API client (no mock fallback)
backend/app        api/, geo/, jobs/, providers/, layers/, analytics/, services/, models/, schemas/, demo/, ml/
backend/alembic    migrations (0001 TerraTrack baseline, 0002 GeoTrace schema)
backend/tests      geo/, ml/, db/ (PostGIS), providers/, integration/ (opt-in live)
ML/                training code, evaluation and export scripts (datasets and checkpoints are git-ignored)
e2e/               Playwright specs
docs/              migration audit
```
