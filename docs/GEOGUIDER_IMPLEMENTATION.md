# GeoGuider: the conversational control layer for GeoTraceAI

GeoGuider lets a user operate GeoTraceAI in plain language: resolve a place, choose a period, search **real** Sentinel-2 acquisitions, pick scenes, run the **real** learned change-detection pipeline as a background job, see polygons on the 2D map / 3D globe, read evidence-based summaries, ask follow-up questions, and export. It is an orchestration layer over existing services, not a separate chatbot.

## Architecture

```
Browser                                        FastAPI                                         Services
┌──────────────────────────┐   POST /geoguider/chat    ┌──────────────────────────────┐
│ GeoGuider panel (React)  │ ───────────────────────▶  │ api/geoguider.py             │
│  - chat, cards, buttons  │ ◀───────────────────────  │  rate limit · ownership ·    │
│  - polls workflow status │   messages+blocks+actions │  row lock per conversation   │
│ useGeoGuider (Zustand)   │                           └──────────────┬───────────────┘
│ geoguiderActions.ts      │                                          │
│  allow-list → useAppStore│                           ┌──────────────▼───────────────┐
└──────────────────────────┘                           │ geoguider/engine.py (Turn)   │
                                                       │  interpret → workflow step   │
                                                       └───┬──────────┬───────────┬───┘
                                        intent.py          │          │           │ workflow.py
                              (LLM if configured, else     │          │           │ (validated state machine)
                               deterministic rules)        │          │
                                                  ┌────────▼──────────▼───────┐
                                                  │ tools.py registry          │  strict input models, permission
                                                  │ (validate → authorise →    │  levels, timeouts, audit trail
                                                  │  bounded run → audit)      │
                                                  └─┬────┬─────┬─────┬────┬───┘
                          Nominatim ◀──────────────┘    │     │     │    └──▶ analytics (summaries, Q&A)
                          CDSE / Sentinel Hub catalogue ◀┘     │     └──────▶ exports / reports
                          api.sentinel.acquire → job queue ◀───┘  (download → preprocess → model → polygons → PostGIS)
```

* **The LLM never is a source of truth.** When `LLM_PROVIDER` is configured it only converts a message into an `Intent` (validated by Pydantic; invalid output is discarded, dates are recomputed by code). Satellite availability, geocoding, areas, model output and job state all come from tools. Without an LLM a deterministic parser handles the supported requests and the UI says so.
* **One orchestrator, a typed state machine, a small tool registry** — no multi-agent framework.

## Request lifecycle

1. The UI posts `{conversation_id?, message | choice, ui:{page, active_analysis_id, drawn_bbox}}`.
2. The API checks authentication, rate limit (default 30/min/user) and message size (1000 chars), creates or loads the user's conversation, **commits the user message**, then takes a row lock on the conversation for the whole turn (concurrent requests cannot double-start or double-announce).
3. `Turn.message()` interprets the text (confirm/cancel/navigate short-circuits, slot filling for a pending question, then LLM or rules → `Intent`). `Turn.choose()` handles button clicks and verifies the `pending_id`/`option_id` against the server-side pending record.
4. The step runs tools through the registry, advances the workflow via `workflow.advance()` (invalid transitions raise), and returns text + **blocks** (cards) + **actions** (UI instructions).
5. The assistant message, the new workflow JSON and an audit list of tool calls (tool, permission, ok/code, ms, input summary with long values truncated) are stored.
6. While a job runs the UI polls `GET /conversations/{id}/workflow`; the server derives the workflow state from the **real job rows** (`PREPROCESSING` for queued/validating/acquiring/preprocessing, `ANALYZING` for detecting/polygonizing...), and when every job is terminal it posts the results message exactly once.

## Workflow state machine

`IDLE → INTENT_RESOLVED → AOI_CONFIRMED → SCENES_FOUND → SCENES_SELECTED → PREPROCESSING → ANALYZING → RESULTS_READY → COMPLETED`, plus `FAILED` (retry returns to `SCENES_SELECTED` with the kept selection) and `CANCELLED`. Allowed transitions are the table in `geoguider/workflow.py`; neither the model nor the client can set a state. A new request starts a fresh workflow (an analysis that is still running must be cancelled or finished first). `Pending` records which question is open (`location`, `period`, `place_choice`, `aoi_size`, `mode_choice`, `scene_choice`, `confirm_plan`, `area_on_map`).

## The Mumbai ten-year workflow

1. **Intent/period**: "past 10 years" is resolved from *today's* date (`periods.resolve_period`; tested against several "today" values) and the exact dates are shown in the reply.
2. **AOI**: the place is resolved through Nominatim. If the boundary is larger than `GEOGUIDER_MAX_AOI_KM2` (400 km²; Mumbai ≈ 1,193 km²) GeoGuider asks: central 10 × 10 km, central 20 × 20 km, or select on the map (it switches on the rectangle tool; "use it" then picks up the drawn box). Ambiguous names (several comparably important matches) produce a choice. The AOI is stored (`areas_of_interest`, source `geoguider`) and shown on the map/globe.
3. **Catalogue search**: the period is split into ≤ 12 sub-periods (`GEOGUIDER_SEARCH_WINDOWS`), each searched in the real catalogue (3 concurrent, bounded timeouts); the coverage table (scenes and lowest cloud per sub-period, failures and 100-result truncation flagged) is shown. Nothing is downloaded at this stage.
4. **Modes**: two-date comparison (default) and a *series of separate pairwise comparisons* (for "year-by-year/trend/multi-period" requests; ≤ `GEOGUIDER_MAX_PAIRS`). GeoGuider states that it does **not** produce a continuous trend model.
5. **Recommended pairs**: ranked by cloud cover, AOI coverage and **seasonal alignment** (same time of year) with a minimum separation of 3 days; three genuinely different alternatives are offered. "Run it" accepts the recommended pair; scenes are never substituted silently (`select_satellite_scenes` validates each pair server-side).
6. **Confirmation card** (area, dates, scenes, mode, model, number of analyses, outputs) — nothing runs before "Start analysis".
7. **Run**: `run_change_detection` calls the existing `/sentinel/acquire` logic, which queues a job: scene download, CRS/alignment/no-data/cloud (SCL) preprocessing, the `oscd-s2-v1` learned model (checkpoint required), postprocessing and polygonisation with geodesic areas, persisted in PostGIS. If the model or credentials are missing the tool fails with an explicit message and the workflow ends in `FAILED`.
8. **Results**: statistics come from `analytics.queries`; the card has five labelled sections — *Observed input data, Computed metrics, Model predictions, Interpretation (hypotheses), Limitations* — with positions ("north-eastern part of the area") computed from stored centroids. Limitations include the model card's own metrics note and caveats. No causal claims are made.
9. **Map**: the `open_analysis` action loads the analysis through the existing store, so the polygons, statistics and detection list appear on the 2D map and 3D globe exactly as for any analysis; `show_aoi` draws the AOI rectangle on both.
10. **Q&A / export**: follow-ups use the existing analytics engine (approved operations, grounded numbers); exports reuse the existing endpoints (GeoJSON/GPKG/CSV/PDF) with authorisation.

## Tool registry (`GET /api/v1/geoguider/tools` returns the schemas)

| Tool | Permission | Purpose |
|---|---|---|
| `resolve_location` | read | Nominatim candidates, or parse a "lat, lon" pair |
| `create_or_update_aoi` | write | save a bbox as the user's AOI (size-limited per purpose; reuses an identical one) |
| `get_aoi_metadata` | read | name/bounds/area of an AOI the user can read |
| `search_satellite_scenes` | read | real catalogue search per sub-period |
| `select_satellite_scenes` | read | validate a chosen pair (order, ≥ 3 days, coverage, cloud, imagery configured) |
| `run_change_detection` | **expensive** | queue real analysis jobs (≤ 3 pairs; needs model + credentials) |
| `get_analysis_status` | read | real job state (access-checked) |
| `get_change_statistics` | read | summary of a completed analysis |
| `get_detected_features` | read | largest polygons with centroid + position |
| `query_analysis_results` | read | existing analytics engine |
| `get_analysis_history` | read | latest analyses |
| `get_weather_alerts` | read | stored alerts, optional refresh when OpenWeather is configured |
| `export_analysis_results` | read | authorise a GeoJSON/GPKG/CSV/PDF download |
| `navigate_to_page` | read | validated route key |

Every call: strict Pydantic input → role check (`write`/`expensive` need a non-viewer role) → ownership checks inside the tool → `asyncio.wait_for` timeout → structured `ToolResult` with a user-safe message → audit entry. Unknown tools are refused; unexpected exceptions are logged and replaced by a generic message (no stack traces or internals reach the user).

## API (all under `/api/v1/geoguider`, all authenticated and user-scoped)

| Endpoint | Purpose |
|---|---|
| `GET /status` | LLM mode, geocoder, satellite, weather, model readiness, capability flags |
| `GET /tools` | tool catalogue |
| `POST /chat` | one turn (message or choice) |
| `GET /conversations`, `GET /conversations/{id}`, `DELETE /conversations/{id}` | history |
| `GET /conversations/{id}/workflow` | live workflow + jobs; advances the state from job rows and returns any newly posted messages |
| `POST /conversations/{id}/workflow/confirm` | start the confirmed plan (409 if nothing is waiting, so a double click cannot start two jobs) |
| `POST /conversations/{id}/workflow/cancel` | request cancellation of running jobs |

Streaming of tokens is **not** implemented (replies are returned whole; long work is a background job with polled progress).

## Frontend

`src/components/geoguider/` (panel + cards), `src/store/useGeoGuider.ts`, `src/lib/geoguiderActions.ts`, mounted in `AppShell`. Floating launcher, dialog with labelled input, Enter to send, Escape to close, live regions for messages and progress, responsive (full-width on narrow screens), stale choice cards become inert, errors with Retry, conversation id kept in `sessionStorage` and restored on reload. Actions are applied only after validation: route **keys** map to fixed paths; UUIDs, bboxes and export paths are pattern-checked; anything else is dropped.

## Configuration

Reuses the existing settings (`backend/.env.example`):

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` (`none` \| `anthropic` \| `openai_compatible`), `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` | optional language understanding. Gemini or other providers: use their OpenAI-compatible endpoint with `openai_compatible`. Keys live only in the server environment. |
| `GEOGUIDER_ENABLED`, `GEOGUIDER_MAX_AOI_KM2` (400), `GEOGUIDER_MAX_PAIRS` (3), `GEOGUIDER_SEARCH_WINDOWS` (12), `GEOGUIDER_MODEL_ID` (`oscd-s2-v1`), `GEOGUIDER_RATE_PER_MIN` (30), `GEOGUIDER_MAX_MESSAGE_CHARS` (1000) | limits |
| `GEOCODER_PROVIDER` (`nominatim`\|`none`), `GEOCODER_URL`, `GEOCODER_USER_AGENT`, `GEOCODER_TIMEOUT_S` | place search (OSM policy: ≤ 1 req/s — enforced and cached in-process; set a real contact in the user agent) |
| `SENTINEL_*`, `OPENWEATHER_API_KEY`, `JOB_RUNNER` | as before |

Without an LLM key the chat works with the built-in parser (common phrasings; not free-form language) and the header says so.

## Run locally

```bash
# database (PostGIS) and migrations
cd backend && python -m app.migrate            # applies 0004 (geoguider_conversations / geoguider_messages)
# backend
python -m uvicorn app.main:app --port 8010
# frontend (repo root)
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010/api/v1 npm run dev -- -p 3000
```

Open http://localhost:3000, sign in, click **GeoGuider** (bottom right), and type e.g. *Show me past 10 years changes in Mumbai.*

## Tests

```bash
cd backend && python -m pytest tests/geoguider tests/db/test_geoguider_api.py   # unit + API (needs the PostGIS test DB on :55432)
cd backend && python -m pytest                                                   # everything
npx vitest run src && npx tsc --noEmit && npx next lint                          # frontend
```

**Mocks versus real**: `tests/geoguider` are pure unit tests. `tests/db/test_geoguider_api.py` runs the real API and PostGIS but **mocks** the geocoder, the Sentinel catalogue, model availability and job creation/completion — it proves orchestration, validation, authorisation, isolation and persistence, not live satellite access. The real end-to-end run below used the live services.

## Verification performed

* **Real end-to-end (live services, no mocks)** against the development database: "Show me past 10 years changes in Mumbai." → Nominatim resolved Mumbai (boundary ≈ 1,193 km² → size question) → central 10 km AOI (100.2 km²) created → the real CDSE catalogue returned **401 scenes in 11 sub-periods (≤ 30% cloud)** → recommended pair 14 Nov 2016 → 17 Nov 2025 → confirmation → real job (download, alignment, `oscd-s2-v1` inference) → **490 change polygons, 6.52 km² (6.51% of the analysed area)**, severity split and the five largest polygons with computed positions → results posted into the chat and opened on the map (screenshots were checked). Export links and follow-up questions (largest polygons, limitations, export) were answered from the stored analysis.
* Live checks of the other scenarios: navigation (`navigate` action to the map with the Compare-dates panel), clarification ("Analyze changes." asks for the place and creates nothing), "Explain my latest analysis", weather alerts (reports that `OPENWEATHER_API_KEY` is not configured instead of inventing alerts), year-by-year trend (explains that only pairwise comparison exists and offers a series of pairwise comparisons).
* Automated results are listed in the final summary of the work (backend, frontend, lint, type-check).

## Security

Authentication and role checks on every route; conversations, AOIs and analyses are user-scoped in the query itself (other users get 404, the same as "missing"); the LLM key never leaves the server; tool allow-list with strict schemas; no LLM-generated SQL/code/shell/URLs are executed (the only outbound URLs are the configured geocoder and satellite providers); navigation uses route keys and the UI re-validates every action; message size and rate limits; geocoder/provider/scene text is sanitised (control characters stripped, lengths bounded) and treated as data — it is never fed back to the LLM as instructions (the LLM only sees the user's message and a tiny state hint); secrets are not logged; the audit trail truncates inputs; errors shown to users are generic for unexpected failures; per-conversation row locks and the state check make confirm/cancel idempotent.

## Known limitations

* No continuous multi-year trend model or temporal compositing; "series" mode is separate two-date analyses (≤ 3).
* No token streaming; progress is polled every 4 s while a job runs.
* Imagery is Sentinel-2 L2A at 10 m; the model `oscd-s2-v1` detects *urban* change (fine-tuned on a small dataset, F1 0.52 on its test set) — the results card states this. Different seasons/dates produce false positives.
* Environmental *values* (NDVI, rainfall, soil moisture, air quality) are not queried by GeoGuider; weather alerts require an OpenWeather plan with the Alerts API.
* Place boundaries come from Nominatim's bounding box (not the exact administrative polygon) and are never larger than the limit without the user choosing a smaller area.
* Without an LLM the built-in parser understands the listed phrasings only; with one, intent extraction is better but still validated.
* The in-process rate limiter and geocoder cache are per API process (use an external limiter if you run several workers).
* Catalogue results are capped at 100 per sub-period query; truncation is shown.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Built-in command parser (no LLM configured)" | set `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` on the server |
| "No satellite catalogue is configured" / "Imagery retrieval is not configured" | configure `SENTINEL_PROVIDER` and the OAuth client credentials |
| "model ... is not available on this server" | install PyTorch (`requirements-ml.txt`) and place the `oscd-s2-v1` checkpoint in `backend/models/` |
| "Place search is disabled" / lookups failing | `GEOCODER_PROVIDER`/`GEOCODER_URL`; outbound HTTPS; Nominatim rate limits |
| Job stays queued | the worker is off: `JOB_RUNNER=embedded` (or run an external worker) |
| 404 on `/geoguider/*` | `GEOGUIDER_ENABLED=false`, or the conversation belongs to another user |
| 429 | rate limit (`GEOGUIDER_RATE_PER_MIN`) |
