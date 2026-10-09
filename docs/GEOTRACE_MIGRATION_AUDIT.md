# GeoTrace Migration Audit (TerraTrack → GeoTrace)

Audit date: 2026-10-09. Method: every claim below was verified by reading the source and/or running it.
Nothing here is taken from the legacy blueprint docs (`PROJECT_SUMMARY.md`, `IMPLEMENTATION_*.md`,
`UI_UX_ANALYSIS.md`), which describe a mock-data prototype and are **not** a reliable description of the code.

## 1. Verified architecture and stack (before migration)

| Layer | What is actually in the repo |
|---|---|
| Frontend | Next.js 14.2.5 (App Router), React 18, TypeScript (strict), Tailwind 3, Zustand 4, MapLibre GL 5.5, Recharts, framer-motion, Vitest, Playwright. Routes: `/dashboard`, `/regions`, `/alerts`, `/admin/users`, `/settings`, plus `/analytics`, `/reports`, `/changes` which are **empty placeholders** (`RoutePlaceholder`). |
| Backend | FastAPI 0.115, SQLAlchemy 2 (async, asyncpg), GeoAlchemy2, Pydantic 2, python-jose JWT, bcrypt, httpx. Routers: auth, users, regions, changes, alerts, analytics, sentinel. Docker Compose: `postgis/postgis:15-3.4` + API. **No Alembic migrations** (alembic is in `requirements.txt` but unused); schema is created by `Base.metadata.create_all` + `migrations/init_postgis.sql`. |
| ML | `ML/terratrack/` package: Siamese ResNet50 shared encoder → multi-scale `|F1−F2|` → U-Net decoder (43.9 M params), BCE+Soft-Dice loss, adapters for LEVIR-CD / S2Looking / SECOND / SYSU-CD, trainer, metrics, `scripts/train.py|predict.py`. Three trained checkpoints exist in `ML/experiments/`. |
| Infra | Docker is installed (28.5.2). Python 3.13.7. RTX 3050 Laptop (4 GB) with CUDA torch 2.13+cu126 in the *global* interpreter. No local Postgres/Redis/GDAL CLI. |
| Geospatial libs | **None installed** (no rasterio, geopandas, pyogrio). Shapely/pyproj exist globally. |
| Sentinel | `SentinelHubService` (Sentinel Hub Process / Catalog / Statistics APIs) returning **PNG** imagery. No GeoTIFF acquisition, no analysis path. |

## 2. Baseline results (before any change)

| Check | Result |
|---|---|
| `npx tsc --noEmit` | 1 error: `src/lib/sentinelApi.test.ts(85)` (test object not assignable to `SentinelApiError`). |
| `npx vitest run src` | 4 files / 15 tests pass. |
| `npx next lint` | 1 warning (`MapViewer.tsx` hook deps). |
| ML smoke (`scripts/test_pipeline.py`, CPU venv) | Pass (dataset → forward → loss). |
| Checkpoint load | `torch.load(..., weights_only=True)` succeeds; `load_state_dict(strict=True)` matches all keys. |
| Backend tests | **Could not run**: neither `venv` nor `.venv` contains the backend requirements (no httpx, geoalchemy2, asyncpg…). A clean environment is created in Phase 1. |

### Reproduced ML metrics (this audit, `ML/scripts/evaluate.py`, CUDA, 256×256, checkpoint's own threshold, no tuning)

| Checkpoint | Split | Threshold | Precision | Recall | F1 | Change IoU |
|---|---|---|---|---|---|---|
| `levir-cd_baseline` (epoch 18) | val (64) | 0.7 | 0.700 | 0.766 | 0.731 | 0.577 |
| `levir-cd_baseline` | **test (128)** | 0.7 | 0.707 | 0.746 | **0.726** | 0.570 |
| `s2looking_baseline` (epoch 20) | **test (1000)** | 0.6 | 0.605 | 0.549 | **0.575** | 0.404 |
| `second_baseline` (epoch 14) | **test (1694)** | 0.4 | 0.662 | 0.717 | **0.688** | 0.525 |

Notes: `metrics.json` in the experiment folders is computed on the *validation* split that was also used to pick the
epoch and threshold, so it is optimistic; the numbers above are the honest held-out ones (the LEVIR val number
reproduces the recorded 0.7315 to 3 decimals). All three models were trained on **RGB 0.5–1 m aerial/VHR imagery
down-sampled to 256×256 (effective ≈2 m)**. They have **not** been validated on Sentinel-2 (10 m) imagery; the UI and
API must say so.

## 3. Reuse assessment

Legend: REUSE (keep), REFACTOR (keep & improve), REBUILD (replace), ADD (missing).

### Frontend
| Subsystem | Verdict | Notes |
|---|---|---|
| Next.js App Router / TS config / Tailwind / Vitest / Playwright | REUSE | |
| Zustand store (`useAppStore`) | REFACTOR | Keep auth slice; replace region/mock-centric map slice with analysis-centric shared geographic state (active analysis, selected feature, filters, layer visibility, dates). |
| Auth (`ProtectedRoute`, `AuthMock` login form, `routeAccess`, `usersApi`, `/admin/users`) | REUSE (rename) | `AuthMock` is a real login form despite the name. Keep, tested by e2e. |
| MapLibre `BaseMap` + layer components | REFACTOR | Working MapLibre integration; coupled to mock data and region demo. Rewritten around the canonical analysis state; style/tile sources/attribution services reused. |
| Layer registry/manager | REFACTOR | Good idea; all env/risk layers are `enabled:false` placeholders. Replaced by a registry that is backed by `/api/v1/layers` metadata. |
| `lib/mockApi.ts` | **REBUILD** | `requestBackend()` **silently falls back to `/public/mocks` on any network error** — violates the "no silent mock fallback" rule. Replaced by a typed API client with explicit error states. |
| `lib/mockData.ts`, `public/mocks/*`, `AIInsightsPanel`, `AnalyticsPanel` (mock parts), `MapViewer.tsx` | REBUILD / delete | `generateInsights()` fabricates "AI insights"; `MapViewer` is dead code (imported nowhere). |
| `Header` | REBUILD | Hard-coded green "Live" badge; hard-coded alert list behaviour. |
| `Sidebar` | REBUILD | Hard-coded "Online" status rows for API / Satellite Feed / AI Detection (not checked against anything). |
| `settings/page.tsx` | REBUILD | Displays a **fake hard-coded "live" Copernicus client secret** and fake admin email; controls are not persisted. |
| `ReportDownloader` | REBUILD | "PDF" is a text string wrapped in an `application/pdf` Blob (not a PDF). |
| `AlertConfigurator`, `AlertPanel` | REFACTOR | Real API calls but model is `confidence ≥ threshold` only. Re-pointed to the new rule/incident model. |
| UI primitives (`DataDisplay/*`) | REUSE | Badge, Card, Modal, Tabs, Tooltip, Progress, Select, EmptyState, ErrorBoundary. |
| `/changes`, `/analytics`, `/reports` | ADD | Currently empty placeholders. |
| 3D globe | ADD | "Globe" today is MapLibre's globe *projection* of the same mock data. A CesiumJS globe is added (PRD §8, App. A). |
| Before/after comparison | ADD | A `comparisonMode` flag exists in the store but nothing implements it. |
| Upload wizard, Sentinel search UI, job progress, detection list, intelligence panel, export UI | ADD | |

### Backend
| Subsystem | Verdict | Notes |
|---|---|---|
| FastAPI app, `/api/v1` prefix, config via pydantic-settings | REFACTOR | `/health` returns a hard-coded `"database": "connected"` — replaced by a real readiness probe. CORS is origin-list based (OK) but `allow_methods/headers=["*"]`. |
| JWT + RBAC (`auth/*`, `api/auth.py`, `api/users.py`) | REUSE | Correct, tested (last-admin protection etc.). Minor hardening only. |
| `Region` model/API | REFACTOR | Becomes "monitored region" + the proximity target for alert rules. `calculate_area_km2` uses `deg² × 12321` (wrong away from the equator) → replaced with geodesic/equal-area calc. |
| `ChangeEvent` + `/changes` | **REBUILD** | Region-centric, `confidence` NOT NULL (forces a made-up number), area in km² computed by the caller, no analysis/provenance. Replaced by analysis-linked `ChangeFeature`. |
| `AlertConfig`/`AlertHistory`/`AlertEngine` | **REBUILD** | Only `confidence ≥ threshold`; severity derived from confidence; no dedup (a retry creates duplicates); evaluated only in an admin-only POST. Replaced by rule/incident engine run on analysis completion with uniqueness constraints. |
| Sentinel Hub client | REFACTOR | OAuth + token cache OK; but "API key as Bearer" headers are not a Sentinel Hub concept, no retries/backoff, no GeoTIFF output, cloud filter built on `eo:cloud_cover` with a non-CQL2-typed filter, `max_cloud_cover*100` unit mismatch. Rebuilt as provider abstraction (§ Phase 5). |
| Analytics endpoints | REBUILD | Aggregates over the old events table. |
| `init_db()` = `create_all`, SQL seed file | **REBUILD** | Replaced by Alembic migrations. |
| Tests (`tests/*`) | REUSE | Auth/user tests kept; DB-startup test revisited. |
| Background jobs, rasters, storage, uploads, exports, layers, AI analytics | ADD | |

### ML
| Subsystem | Verdict | Notes |
|---|---|---|
| `SiameseResNetUNet` (+ encoder/decoder, losses, metrics, trainer, dataset adapters) | REUSE | Verified architecture, checkpoints load strictly. |
| Inference path | REBUILD | `scripts/predict.py` resizes a whole image to 256×256 and uses PNG/PIL — no georeferencing, no tiling, no GPU/CPU policy, `torch.load` without `weights_only`. Replaced by tiled, overlap-blended, georeferenced inference in the backend (`app/ml`). |
| Checkpoint management | REFACTOR | 527 MB training checkpoints (incl. optimizer state) → export 176 MB weights-only files + a JSON card with *verified* metrics (`scripts/export_for_backend.py` was an empty file). |
| `train_eurosat_baseline.py`, `train_change_detection.py` (empty), `models/siamese_unet.py` (empty) | Leave | Out of scope; empty files noted. |

## 4. Defects / risks found

1. **Silent mock fallback** in the frontend API client (data-integrity violation).
2. **Fake "Live" indicator and fake service-status rows**; **fake "live" Copernicus secret** shown in Settings; fake PDF; fabricated "AI insights".
3. `/health` always reports the database as connected.
4. Area calculation `deg² × 12321 km²` is wrong everywhere except the equator.
5. Alert engine is non-idempotent (no unique constraint → duplicate alerts on retry) and severity is derived from confidence only.
6. Auth token stored in `localStorage` (XSS-exposed). Accepted for the prototype; documented. Refresh/HttpOnly cookie is a hardening item.
7. `SENTINEL_HUB_*_API_KEY` variables are placed in the **frontend** `.env.local` (not exposed by Next since they lack `NEXT_PUBLIC_`, but they do not belong there and they are not Sentinel Hub concepts — all Sentinel Hub APIs use the OAuth client-credentials token). Real credentials exist in `backend/.env` (never printed in this audit).
8. No schema migrations; `create_all` at startup.
9. ML checkpoints are domain-specific (see §2): applying them to 10 m Sentinel-2 is out-of-distribution.
10. Repository hygiene: two virtualenvs committed to the working tree (`venv/`, `.venv/`), stray `bits.py`, `.dist/`.

## 5. Planned migrations and compatibility

* `users`, auth endpoints, `/users/*` unchanged (wire-compatible). `regions` kept (adds nothing breaking).
* Alembic baseline revision reproduces the current schema; later revisions add projects, AOIs, imagery assets,
  acquisitions, analysis jobs, change features, layers, alert rules/incidents, exports. Legacy `alert_configs` rows are copied to
  `alert_rules`; legacy `change_events`/`alert_history` (only seed data exists) are dropped in a separate, reversible revision.
* Legacy `/changes` and `/alerts/config|history` endpoints are removed in the same change that ships their replacements and updated UI.
* Frontend routes `/dashboard`, `/regions`, `/alerts`, `/admin/users`, `/settings` are preserved; `/map`, `/analyses`, `/analytics`, `/reports` are added.

## 6. Implementation sequence

1. Environment + audit (this document) → 2. geospatial pipeline (validation, baseline CD, polygonization, exports) with synthetic-GeoTIFF tests →
3. learned-model inference integration → 4. DB models + Alembic + job runner + API → 5. frontend shell, upload, 2D map + compare, details →
6. Sentinel acquisition → 7. Cesium globe + layer registry (NDVI, deforestation first) → 8. alerts + analytics (+ optional LLM narration) →
9. reports, hardening, docs, demo data.

## 7. Known environmental / credential dependencies

| Dependency | Status |
|---|---|
| PostgreSQL + PostGIS | Provided via Docker (`postgis/postgis:15-3.4`). No local install. |
| Sentinel credentials | `backend/.env` has a client id/secret; provider/endpoint match to be verified in Phase 5 (client-id format suggests a Copernicus Data Space Ecosystem client). Live acquisition tested only if the credentials work; otherwise mocked tests only and reported. |
| Trained checkpoints | Present locally (gitignored `*.pth`); a missing checkpoint must not break the baseline path. |
| CUDA | Optional. 4 GB GPU is sufficient for tiled inference at 256×256. |
| LLM provider | Optional (`LLM_PROVIDER`/key); deterministic analytics always available. |
| Environmental layer providers (NASA GIBS / FIRMS, Hansen GFC, CAMS…) | Public tile services need no key where used; FIRMS hotspots need a free MAP_KEY. Verified per-provider in Phase 7. |

## 8. Outcome (end of implementation)

### 8.1 Status of the defects in §4

| # | Defect | Status |
|---|---|---|
| 1 | Silent mock fallback in the API client | **Removed.** `src/lib/api/client.ts` has no fallback; a failed request is an `ApiError` and the UI shows an explicit error. Covered by `client.test.ts` and an e2e test ("unreachable backend is reported, never replaced by sample data"). `public/mocks/` deleted. |
| 2 | Fake "Live" indicator, fake service rows, fake secret, fake PDF, fabricated "AI insights" | **Removed / replaced.** Status comes from `/system/status` (database, storage, runner, model files, provider credentials). Reports are real PDF/CSV/JSON built from stored results. Analytics are computed operations; LLM wording (optional) is discarded if it contains an ungrounded figure. |
| 3 | `/health` always "connected" | `/ready` performs a real database round-trip and storage check. |
| 4 | Wrong area formula | Area is computed geodesically (WGS 84 ellipsoid) from polygon coordinates; `tests/geo/test_exports.py` re-computes each exported polygon's area with `geodesic_area_m2` and requires it to match the stored value (rel. 1e-4). |
| 5 | Non-idempotent alert engine | `UNIQUE(rule_id, feature_id)` + `ON CONFLICT DO NOTHING`; optional spatial de-duplication; severity is a configurable heuristic over area, magnitude and proximity (not confidence). |
| 6 | Token in `localStorage` | **Unchanged (documented).** Needs an HttpOnly-cookie/refresh design; listed in the README limitations. |
| 7 | Sentinel keys in the frontend `.env.local` | The new code does not read them. The legacy `.env.local` in the working tree still contains `SENTINEL_HUB_*` values; it is git-ignored and unused, and should be deleted or rotated by its owner. `.env.example` no longer lists them. |
| 8 | `create_all` at startup | Alembic migrations (`0001` baseline stamping for legacy databases, `0002` GeoTrace schema). `AUTO_MIGRATE` is refused in production; the test suite builds its schema through the migrations. |
| 9 | Checkpoints are domain-specific | Reproduced and now stated on every model card, in the UI and in the README. Automatic method selection prefers the spectral baseline for coarse or non-RGB imagery. |
| 10 | Repository hygiene | Stale blueprint documents, `bits.py`, legacy mock data and legacy components removed. `venv/` and `.venv/` remain untracked local environments (git-ignored). |

### 8.2 Findings made during implementation

* **Sentinel credentials.** The client id in `backend/.env` has the `sh-<uuid>` form of a *Copernicus Data Space Ecosystem* OAuth client; it is not accepted by the commercial Sentinel Hub endpoints the legacy service called. The new provider layer supports both services (`SENTINEL_PROVIDER=cdse|sentinel_hub|auto`). Live search and retrieval were exercised against CDSE with those credentials (an opt-in test, `tests/integration/test_sentinel_live.py`, repeats this); all other Sentinel tests use mocked HTTP.
* **Docker image check.** Building the API image and importing every `app.*` module inside it exposed two problems a developer machine hides: a missing dependency (`geojson`, installed implicitly locally) and a missing system library (`libexpat1`, needed by rasterio's bundled GDAL on `python:3.12-slim`). Both are fixed; after the fix all modules import in the image. The full compose stack (API + worker + PostGIS) was not started end to end.
* **Job-state race.** A progress write that was already in flight when a job failed could re-open the finished job (last-writer-wins). Progress writes are now conditional `UPDATE … WHERE status NOT IN (terminal states)`.
* **Detector calibration.** Median/MAD radiometric normalisation left a residual on dark pixels (water false positives); replaced by a Tukey-bisquare IRLS fit, with a dark-pixel mask for NDVI.

### 8.3 Verified test results (final run)

| Suite | Command | Result |
|---|---|---|
| Backend (geo, ML, providers, PostGIS API/workflow/authz/alerts/analytics/layers) | `python -m pytest -q` (PostGIS test container) | 164 passed, 1 skipped (opt-in live Sentinel test), 0 failed |
| Frontend unit/component | `npm test` | 56 tests passed (8 files) |
| Browser, API stubbed | `npx playwright test e2e/access.spec.ts` | 11 passed |
| Browser acceptance, real backend | `npx playwright test e2e/acceptance.spec.ts` (see README) | 1 passed (upload → detect → select → GeoJSON export → alert → PDF report) |
| Static | `npx tsc --noEmit`, `npx next lint`, `npm run build` | clean |

Not covered by automated tests: the Cesium globe rendering itself (selecting a detection from the list on the globe was verified manually in a browser: the camera flies to it and the intelligence panel shows its measured attributes), Sentinel retrieval over large AOIs, and any load/performance testing.

### 8.4 ML model improvement (Sentinel-2)

* **Problem:** the shipped checkpoints were trained on 0.5-2 m aerial imagery; on 10 m Sentinel-2 they flagged clouds and noise (zero-shot F1 0.30 on OSCD).
* **Data:** OSCD (Onera Satellite Change Detection; 24 real Sentinel-2 city pairs, RGB, 10 m) via the Hugging Face mirror `blanchon/OSCD_RGB` (38 MB, downloaded with the user's approval; the mirror's licence field says "unknown", the original dataset is academic: confirm terms before redistribution).
* **Method:** `ML/scripts/finetune_oscd.py` fine-tunes the LEVIR-CD checkpoint on 11 training pairs (random 256 px crops biased to changed pixels, flips/rotations, date swap, independent radiometric jitter per date), picks the epoch and threshold on 3 validation pairs, and evaluates the 10 official test pairs once.
* **Result (whole-image, pixel-level, test pairs):** fine-tuned F1 0.52 / IoU 0.35 / P 0.68 / R 0.42 vs. starting checkpoint F1 0.30 (fed at 10 m or 2 m) vs. spectral change-vector baseline F1 0.24. Validation F1 peaked at epoch 5 (0.69) and fell afterwards (over-fitting: 11 pairs), so the epoch-5 weights are shipped. Per-scene test F1 ranges 0.06-0.71.
* **Honest limits:** tiny training set; 10-scene test set (differences of a few points are noise); labels cover urban change only; no validation on vegetation, flood or fire change; no calibration; no validation on user areas. In the Compare tool a rural Rondonia box produced 0 detections (expected: no new buildings) where the previous model flagged clouds; a Mumbai-sized area (1,540 km2) took ~50 s.
* **Product:** Compare-dates ML switch uses `oscd-s2-v1`; `POST /sentinel/ml-changes` returns GeoJSON + statistics; "Save as analysis" stores the result through the normal job pipeline with this model.
