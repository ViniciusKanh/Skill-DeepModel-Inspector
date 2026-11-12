# Frontend & API Validation

## Update 2026-11-12 — Model Lab & Production Monitor

| Check | Result |
|---|---|
| `pytest -q` (Python 3.13) | 99 passed: 68 engine + 12 live probe/monitor + 12 API + 7 Playwright e2e |
| `python3.11 -m pytest -q` | 80 passed, 2 skipped (API/e2e need FastAPI) |
| `npm run typecheck` / `npm test` / `npm run build` | 0 errors / 8 passed / OK |
| `ruff check` + `ruff format --check` | clean |
| Skill & ZIP regression | `agensi/` and `dist/deepmodel-inspector-v1.0.0.zip` byte-identical to the previous release |
| New screenshots | `docs/screenshots/14-model-lab.png`, `15-model-lab-transcript.png`, `16-production-monitor.png` |

Live probes were validated against the **simulated** OpenAI-compatible server (`examples/fake_llm_server.py`), which
exercises the real HTTP client and analyses. A real model (e.g. Ollama) was not available in the build environment.

# Frontend & API Validation (real runs, 2026-11-09)

Environment: Linux sandbox, Node 22.23.4 / npm 10.9.9, Python 3.13.18 (+ 3.11.18 for engine regression),
FastAPI 0.162.2, uvicorn 0.54.0, Playwright (Python) 1.63 with Chromium.

| # | Check | Command | Result |
|---|---|---|---|
| 1 | Production build | `cd frontend && npm run build` | OK — `frontend/dist` (1.8 MB, lazy-loaded pages) |
| 2 | TypeScript | `npm run typecheck` (`tsc --noEmit`, strict) | 0 errors |
| 3 | Component tests | `npm test` (Vitest + Testing Library) | 8 passed (formatting, chips, determinate/indeterminate progress + cancel, findings filters, series merge, API error surfacing, unreachable backend) |
| 4 | API tests | `pytest tests/test_api.py` | 9 passed (status/capabilities, import + inventory, audit progress, investigate, exports, 6 single analyses, chart/record endpoints, invalid inputs, cancel, security: roots/sensitive/traversal/Host/CORS/settings, demo mode) |
| 5–8 | Integration / import+audit / report download / error states (browser) | `pytest tests/e2e` (Playwright, production build served by the API) | 6 passed: full DEMO flow (load demo → audit → 10 pages → chart toggle → investigation → evidence modal with supporting records → HTML + Markdown downloads → CRT toggle), backend-offline state, no JS page errors |
| 9 | Responsiveness | same suite | no horizontal scroll at 1920×1080, 1440×900, 1366×768, 390×844 |
| 10 | Python regression | `pytest -q` (3.13) / `python3.11 -m pytest -q` | 83 passed (68 engine + 9 API + 6 e2e) / 68 passed, 2 skipped (no FastAPI on 3.11 in the sandbox) |
| — | Lint | `ruff check src tests tools examples backend`, `ruff format --check` | all checks passed, 46 files formatted |

Skill/ZIP regression: `tests/test_skill_scripts.py::test_scripts_are_up_to_date` passed → the Agensi scripts were not
changed; the engine source (`src/`) was not modified for the frontend, and `dist/deepmodel-inspector-v1.0.0.zip` was
not rebuilt.

## Screenshots (captured from the running app by the e2e suite)
`docs/screenshots/`: 01-dashboard, 02-training, 03-dataset, 04-tokenizer, 05-generation, 06-compare,
07-investigate, 08-evidence-modal, 09-reports, 10-projects, 11-settings (1920×1080), 12-backend-offline (1440×900),
13-dashboard-1366x768, 13-dashboard-390x844.

## Not verified here
- `scripts/Start-DeepModel.ps1` and `Build-Frontend.ps1` were not executed (no Windows/PowerShell in the sandbox);
  the Linux launcher `scripts/start-deepmodel.sh` was executed (HTTP 200 on `/` and `/api/status`).
- Browsers other than Chromium; screen readers.
