# Frontend & Local API Architecture

The desktop-style web app is a **presentation layer** over the existing Python engine. No scientific
algorithm is re-implemented in TypeScript; every metric, finding, hypothesis and report comes from
`src/deepmodel_inspector`.

```
browser (React SPA) ──fetch /api──▶ FastAPI (127.0.0.1:8765) ──import──▶ deepmodel_inspector engine
        ▲                                    │                                (analyzers, rootcause, render)
        └──── static frontend/dist ◀─────────┘           workspace/ (projects.json, settings.json, reports/*.json)
```

## Backend (`backend/`)

| Module | Role |
|---|---|
| `api/main.py` | FastAPI app factory, routes, error mapping (403 security, 404, 422), TrustedHost + restricted CORS, static SPA serving |
| `schemas/models.py` | Typed Pydantic request/response models (status, settings, projects, experiments, jobs, report metadata) |
| `services/store.py` | Local JSON persistence (`workspace/` or `DMI_APP_HOME`); settings validation (authorized roots) |
| `services/jobs.py` | Thread pool (2 workers) with real step progress and cooperative cancellation; consolidates results with `rootcause.consolidate` |
| `services/analysis.py` | Expands experiment items with the engine inventory (`scan`/`classify`), dispatches engine analyzers, exposes chart data (`training.extract_series`), length histograms (engine parsers) and redacted record previews (`redact`, `repetition_rate`) |

Endpoints: `GET /api/status`, `GET|PUT /api/settings`, `GET /api/fs/list`, `GET|POST /api/projects`,
`GET|DELETE /api/projects/{id}`, `POST /api/projects/{id}/scan`, `POST|DELETE /api/projects/{id}/experiments`,
`POST /api/files/inspect`, `POST /api/demo`, `GET|POST /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`,
`GET /api/reports`, `GET /api/reports/{id}`, `GET /api/reports/{id}/export?format=json|markdown|html`,
`GET /api/data/series|lengths|records`. OpenAPI docs: `/api/docs`.

Job kinds map 1:1 to engine commands: `audit`, `investigate`, `train`, `dataset`, `leakage`, `tokenizer`,
`generation`, `compare`, `checkpoint` (`scan` and `report` are covered by project scan and report export).
`investigate` re-uses the raw results of the latest audit of the experiment (instant) unless "re-run full audit" is set.

### Orchestration note
`services.analysis.run_audit` mirrors the dispatch of `inventory.run_audit` because experiments may be a subset of
files and the UI needs per-step progress and cancellation. It calls the same engine analyzers; no rule is duplicated.

### Security
Loopback-only bind (`--host` limited to 127.0.0.1/localhost), TrustedHost (DNS-rebinding protection), CORS limited to
the Vite dev origin, every path validated by the engine guard (authorized roots, sensitive files, pickle refusal, size
limit), read-only access to user files, report ids validated, record previews truncated and redacted, HTML exports
escaped by the engine renderer. No outbound network calls.

## Frontend (`frontend/`)

React 18 + TypeScript + Vite 5 + Tailwind 3 + Recharts + Lucide + React Router; fonts bundled with @fontsource (OFL).

```
src/app/        App shell, routes (lazy pages), global state (AppState), i18n (EN/PT labels)
src/components/ ui.tsx (Panel, StatCard, chips, Modal, Loader, JobProgress, EmptyState…), charts.tsx, layout.tsx
src/features/   findings (table, evidence modal, hypotheses, experiments), analysis (audit/single-run bars)
src/hooks/      useJobRunner (submit/poll/cancel), useLatestReport, sourcePath
src/pages/      Dashboard, Training, Dataset, Tokenizer, Generation, Compare, Investigate, Reports, Projects, Settings
src/services/   api.ts (typed fetch client, error surfacing)
src/types/      API/engine types
src/assets/brand logo.png (official), logo-icon.png and mascot.png (cropped from the approved brand material)
```

Data flow per page: active project/experiment (header selectors, persisted in localStorage) → latest report of that
experiment containing the page's section → section blocks + finding ids → page widgets. Page-specific "Run …" bars
submit single-analysis jobs attached to the same experiment, so their results become the latest section data.

Production: `npm run build` → `frontend/dist`, served by the API at `/`. Development: Vite on 5173 proxies `/api` to the API.
