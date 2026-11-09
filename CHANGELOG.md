# Changelog

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
