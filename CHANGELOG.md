# Changelog

## Unreleased — Hugging Face, Live models project, Windows installer

- `deepmodel hub --repo owner/name`: inspects a Hugging Face repo **without downloading weights** (Hub API, config,
  tokenizer/generation config, safetensors headers via HTTP Range). Rules `HUB.PICKLE_ONLY`, `HUB.REMOTE_CODE`,
  `HUB.VOCAB_MISMATCH`, `HUB.NO_CHAT_TEMPLATE`, `HUB.NO_EOS`, `HUB.NO_LICENSE`, `HUB.GATED`, `HUB.FOOTPRINT`,
  `HUB.NO_WEIGHTS`. Redirects only to Hub/CDN hosts; token sent only to the Hub host; token kept in memory.
- HF Inference Providers added to the online provider catalog (OpenAI-compatible router, HF token).
- Every connected model (and every inspected HF repo) becomes an experiment of the **Live models** project; probe
  transcripts are saved as `generations_probe_*.jsonl`, so Dashboard / Generation / Investigate / Reports / Audit work on it.
- Model Lab: "Open in Dashboard / Generation / Investigate"; wizard option "Hugging Face model"; Dashboard model card.
- Windows installer: `desktop/launcher.py`, PyInstaller spec, Inno Setup script, `scripts/Build-Installer.ps1`,
  GitHub Actions `release.yml` (tag `v*` → Release with Setup.exe, portable ZIP, SHA256SUMS).

## Unreleased — live inspection & production monitoring

- `deepmodel probe`: live behavioural inspection of local or online models through OpenAI-compatible APIs
  (instruction/format, closed answers, grounding, prompt injection, determinism, repetition stress, latency/errors);
  rules `PRB.*`, hypotheses `RC.LIVE_*`; custom prompt files; redirects blocked; remote endpoints require consent.
- `deepmodel monitor`: batch production monitoring from exported logs per day/week (rules `MON.*`, thresholds,
  bootstrap drift, exit code 4 with `--fail-on`).
- App: **Model Lab** (targets, connection test, live retro console, scorecard, transcript, ask) and **Production
  Monitor** (per-period charts, alerts, model health history); simulated demo model server.
- Engine core and Agensi skill unchanged (live extensions live in `probe/`, `analyzers/monitor.py`, `diagnostics/live.py`).

## Unreleased — local app (frontend + API)

- Retro AI Lab web app (`frontend/`, React/TypeScript/Vite/Tailwind/Recharts) with 10 screens and DEMO mode.
- Local FastAPI layer (`backend/`) reusing the engine: projects/experiments, jobs with progress and cancellation,
  audits, investigations, single analyses, reports and exports. Localhost-only, path-validated, read-only.
- Windows launcher `scripts/Start-DeepModel.ps1`, build script, API and Playwright e2e tests, real screenshots.
- Engine and Agensi skill unchanged.

## 1.0.0 — 2026-11-09 (unreleased; pending author approval)

- Local engine (`deepmodel` CLI) with training, dataset, leakage, tokenizer, generation, comparison and
  checkpoint-metadata analyzers; root-cause engine with question intents (EN/PT); JSON/Markdown/HTML reports.
- Security layer: path confinement, sensitive-file refusal, no pickle deserialization, size limits, output guard,
  redacted evidence, escaped HTML.
- Agensi skill: `SKILL.md`, 9 standalone standard-library scripts generated from the engine, references and template.
- Reproducible synthetic scenarios, pytest suite with engine/script parity and isolated-run checks, packaging tool.
