# GeoGuider implementation audit

Audit of the repository performed before implementing GeoGuider (2026-10-10). Classification: **REUSE** (used as is), **REFACTOR** (small change), **ADD** (new), **REBUILD** (none were necessary).

## Existing architecture

| Layer | What exists |
|---|---|
| Frontend | Next.js 14 App Router, React 18, TypeScript, Tailwind, Zustand (`src/store/useAppStore.ts`), Recharts, Vitest + Testing Library, Playwright. Pages: `/dashboard /map /analyses /analyses/new /regions /changes /alerts /analytics /reports /settings /image-compare /admin/users`. Authenticated shell: `components/shell/AppShell.tsx`. |
| Maps | MapLibre GL (2D + compare slider) in `components/map/MapCanvas.tsx`, CesiumJS 3D globe in `GlobeView.tsx` (no Cesium ion token). Drawn rectangle (`drawBox.ts`), fly-to requests, weather layer, quick-compare overlay. |
| Backend | FastAPI, SQLAlchemy 2 async, GeoAlchemy2, Alembic (0001-0003 before this work), PostGIS 15. JWT auth with roles admin/user/viewer (`auth/dependencies.py`), per-project ownership (`services/access.py`). |
| Jobs | Postgres-as-queue worker (`jobs/runner.py`, `executor.py`); analysis statuses `queued → validating → acquiring_imagery → preprocessing → detecting_changes → polygonizing → evaluating_alerts → completed|failed|cancelled`; cancellation flag honoured at checkpoints. |
| Satellite | `providers/sentinel.py` (CDSE STAC + Sentinel Hub catalogue), `process_api.py` (imagery), `services/sentinel.py` (per-tile grouping, AOI coverage, selection rule, acquire-for-job), `/sentinel/search|acquire|preview|ml-changes`. |
| Raster / ML | `geo/` (rasterio/GDAL, pyproj, shapely, polygonize, geodesic area), learned Siamese models in `ML/` + `backend/models/registry.json` (`levir-cd-v1`, `s2looking-v1`, `second-v1`, `oscd-s2-v1`), `ml/registry.py`, `ml/detector.py`. |
| Results | `ChangeFeature` polygons, `analytics/queries.py` (deterministic operations), `analytics/nl.py` + `service.py` (question → approved operation), `services/exports.py` (GeoJSON/GPKG/CSV), `services/reports.py` (JSON/CSV/PDF). |
| Weather | OpenWeather Alerts integration (`providers/openweather.py`, `services/weather_alerts.py`, `/weather-alerts`), stored per AOI with dedup and an inbox. |
| LLM | `analytics/llm.py`: provider abstraction (`anthropic`, `openai_compatible`), settings `LLM_PROVIDER/LLM_API_KEY/LLM_MODEL/LLM_BASE_URL`; used only to map questions to approved operations and to narrate computed facts (numbers must be grounded). |
| Geocoding | **None.** |
| Chat UI / conversation storage | **None.** |

## Reusable components and services

| Module | Class | Used by GeoGuider for |
|---|---|---|
| `analytics/llm.py` (`_complete`, `llm_enabled`) | REUSE | intent extraction (same provider settings, no new SDK) |
| `analytics/service.run_query` | REUSE | answering "what changed the most / largest polygons / by region" from stored results |
| `analytics/queries.summarize_analysis / largest_changes` | REUSE | all statistics in result cards |
| `services/sentinel.py` (`group_scenes`, `window_bounds`) and `providers/sentinel.get_provider` | REUSE | real catalogue search, per-acquisition grouping, AOI coverage |
| `api/sentinel.acquire` | REUSE | creates the real analysis job (acquire → preprocess → model → polygons) |
| `services/analyses.request_cancel`, `services/access.*` | REUSE | cancellation and ownership checks |
| `services/exports`, `api/analyses export`, `reports` | REUSE | export links (GeoJSON/GPKG/CSV/PDF) |
| `services/weather_alerts.refresh_aoi`, `models.WeatherAlert` | REUSE | weather-alert tool |
| `ml/registry` | REUSE | model availability check and the model card's own limitations/metrics |
| `geo/aoi` (`bbox_polygon`, `finalize_aoi`) | REUSE | AOI validation and geodesic area |
| `providers/http.request` | REUSE | bounded, retried HTTP for the geocoder |
| Frontend `useAppStore` (fly requests, drawn box, active analysis, layers, left panel) | REUSE | map/globe synchronisation — GeoGuider drives the existing state instead of duplicating it |
| `api/client.ts` (`apiFetch`, `downloadFile`) | REUSE | typed API access and authenticated downloads |
| `AppShell` | REFACTOR | mounts the assistant on every authenticated page (one line) |
| `config.py`, `.env.example`, `models/__init__`, `api/__init__`, `tests/db/conftest` table list | REFACTOR | new settings, models, router, test cleanup |
| Geocoder provider, conversation tables, intent/workflow/tool registry/orchestrator, chat UI | ADD | missing capabilities |

## Missing capabilities (and what was done)

* Place search → **ADD** `providers/geocode.py` (Nominatim; server-side, cached, rate-limited, bounded).
* Conversation + workflow persistence → **ADD** tables `geoguider_conversations`, `geoguider_messages` (migration `0004`).
* Intent schema, tool registry, workflow state machine, orchestrator, API → **ADD** `backend/app/geoguider/`, `backend/app/api/geoguider.py`.
* Chat UI, action executor, store → **ADD** `src/components/geoguider/`, `src/lib/geoguiderActions.ts`, `src/store/useGeoGuider.ts`.
* **Not implemented** (reported honestly by the assistant): continuous multi-year trend analysis / temporal compositing; NDVI, rainfall, soil-moisture or air-quality *values* for an area (the layers panel shows catalogue layers only); streaming of tokens (replies are returned whole; job progress is polled).

## Integration points

`POST /api/v1/geoguider/chat` is the single conversational entry. Tools wrap the services above. UI instructions come back as typed actions (`navigate`, `show_aoi`, `open_analysis`, `track_analyses`, `zoom_to`, `show_weather`, `download_export`, `start_draw`) that the frontend validates against an allow-list and applies through the existing store.

## External dependencies and configuration

| Feature | Needs |
|---|---|
| Natural-language understanding beyond the built-in parser | `LLM_PROVIDER` (`anthropic` or `openai_compatible`), `LLM_API_KEY`, `LLM_MODEL` (server-side) |
| Place-name resolution | Outbound HTTPS to the configured geocoder (`GEOCODER_URL`, default OpenStreetMap Nominatim, usage policy applies; set `GEOCODER_USER_AGENT`) |
| Satellite search | `SENTINEL_PROVIDER` + CDSE / Sentinel Hub credentials |
| Imagery download + analysis | OAuth client credentials for imagery, PyTorch and the `oscd-s2-v1` checkpoint (`backend/models/`), running job worker (`JOB_RUNNER=embedded` or an external worker) |
| Weather alerts | `OPENWEATHER_API_KEY` with a plan that includes the Alerts API |

## Baseline test results (before GeoGuider)

* Backend: 205 passed, 1 skipped (earlier full run) — PostGIS test database on port 55432.
* Frontend: 93 tests passed, `tsc --noEmit` and `next lint` clean.

Results after implementation are in `docs/GEOGUIDER_IMPLEMENTATION.md` ("Verification").

## Implementation plan (followed)

1. Persistence + schemas + state machine. 2. Geocoder + tool registry (strict inputs, permissions, timeouts, audit). 3. Intent layer (LLM when configured, deterministic parser otherwise, same validated `Intent`). 4. Orchestrator for the AOI → period → catalogue → selection → confirmation → job → results workflow, plus results Q&A, export, weather, navigation. 5. API. 6. Chat UI + action executor. 7. Tests (unit, DB/API, frontend) and a real end-to-end run for Mumbai. 8. Documentation.
