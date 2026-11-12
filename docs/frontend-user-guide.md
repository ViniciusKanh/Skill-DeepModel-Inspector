# DeepModel Inspector App — User Guide

## Install & start (Windows)

```powershell
cd "C:\dev\DeepModel Inspector"
py -3.13 -m venv .venv; .\.venv\Scripts\Activate.ps1      # once
pip install -e ".[app]"                                     # engine + FastAPI + uvicorn (once)
.\scripts\Start-DeepModel.ps1                               # opens http://127.0.0.1:8765
```

The production build (`frontend\dist`) is included, so Node.js is not needed to run the app.
To rebuild the UI or develop it: install Node.js 18+, then `.\scripts\Build-Frontend.ps1` (build) or
`.\scripts\Start-DeepModel.ps1 -Dev` (Vite on http://127.0.0.1:5173 with hot reload). Options: `-Port 8800`, `-NoBrowser`.
Linux/macOS: `./scripts/start-deepmodel.sh`.

## Quick demo (synthetic data)
1. Click **Load demo lab** (any page) — creates the project *DEMO — Synthetic LLM Lab* over `examples/` with 8 experiments.
   A yellow **DEMO MODE** banner marks every result as computed by the real engine on synthetic data.
2. Click **Run audit** → the progress bar shows real analysis steps.
3. Dashboard shows findings, alerts, training curve, top hypothesis and recommended actions.
4. **Root-Cause Investigation** → ask e.g. "Why is my model repeating the same responses?" → ranked findings,
   hypothesis tree, experiments; click a finding to open its evidence and supporting records.
5. Export JSON / Markdown / HTML from the investigation or from **Reports**.

## Your own data
1. **Settings → Authorized roots**: add the folder that contains your logs/datasets (read-only access).
2. **Projects & Experiments → New local project**: name + root folder (Browse), then *Create & scan*. The inventory
   classifies files (training_log, dataset, tokenized, generations, run, checkpoint) and flags files that cannot be
   analyzed (unreadable, unknown, sensitive, pickle).
3. Select files (or type a sub-folder) and **Create experiment**. Pick it in the header selector.
4. Run the audit, or use the per-page *Run …* bars (single log, dataset, leakage pair, tokenization, outputs, run comparison).

Accepted formats: see `agensi/deepmodel-inspector/references/input-formats.md`.

## Pages
Dashboard · Training Diagnostics (loss/LR/perplexity/grad-norm charts with series toggles, range zoom, convergence checks) ·
Dataset Quality (duplicates, schema, Unicode, length histogram, split contamination) · Tokenizer Efficiency (needs your
tokens; nothing is simulated) · Generation Behavior (distinct-n, repetition, configs, filtered examples) · Experiment
Comparison (metrics, hyperparameters, compatibility guard, side-by-side curves) · Root-Cause Investigation ·
**Model Lab** (live inspection of local/online models) · **Production Monitor** (logs per day/week, alerts, model
health history; see `docs/live-inspection.md`) · Reports ·
Projects & Experiments · Settings (CRT effects, animations, language, roots, limits, version, limitations).

## Reading results
`CONFIRMED` = rule satisfied by the data (an observation, never a proven cause); `POTENTIAL` = indicators needing
confirmation; `INCONCLUSIVE` = not enough data. Hypotheses are always tests to run. The investigation is rule-based
over computed evidence — it is not a generative chatbot.

## Data & privacy
Everything runs on 127.0.0.1. Files are only read; app state lives in `workspace/` (delete it to reset). Removing a
project only removes its registration, never your files.
