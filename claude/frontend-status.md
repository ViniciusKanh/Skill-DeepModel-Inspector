# Frontend — status de execução

Última atualização: 2026-11-09. Estado: **Fase 1 e Fase 2 concluídas**; pendências abaixo.

## Implementado
- `frontend/` (React 18 + TS + Vite 5 + Tailwind 3 + Recharts + Lucide + React Router; fontes OFL locais).
  10 telas: Dashboard, Training, Dataset, Tokenizer, Generation, Compare, Investigate, Reports, Projects, Settings.
- `backend/` (FastAPI local): status, settings, fs restrito, projetos/experimentos, inventário, jobs (progresso real,
  cancelamento), auditoria, investigação, análises individuais, relatórios + export JSON/MD/HTML, séries/histograma/prévia.
- Modo DEMO (`POST /api/demo`) sobre `examples/` com 8 experimentos e faixa "DEMO MODE".
- Scripts: `scripts/Start-DeepModel.ps1`, `scripts/Build-Frontend.ps1`, `scripts/start-deepmodel.sh`.
- Docs: frontend-architecture, ui-design-system, frontend-user-guide, frontend-validation; referências em `design/references/`.
- Motor (`src/`) e skill/ZIP Agensi **não alterados**. `pyproject.toml`: extras `app` e `ui-test`, marker `e2e`, pythonpath ".".

## Testes (comandos e resultados)
- `npm run typecheck` → 0 erros · `npm test` → 8 passed · `npm run build` → OK.
- `pytest -q` (3.13) → 83 passed (68 motor + 9 API + 6 e2e Playwright) · `python3.11 -m pytest -q` → 68 passed, 2 skipped.
- `ruff check` / `ruff format --check` → OK.
- Screenshots reais: `docs/screenshots/` (14 arquivos).

## Pendências / riscos
1. Scripts PowerShell não executados (sem Windows no sandbox) — testar `.\scripts\Start-DeepModel.ps1`.
2. Rodar `pip install -e ".[app]"` no venv do Windows (fastapi/uvicorn ainda não instalados lá).
3. Idioma PT cobre navegação e rótulos principais; textos dos achados vêm do motor em inglês.
4. Investigação é baseada em regras (sem LLM); cancelamento é cooperativo entre etapas (uma análise longa em curso termina antes de cancelar).
5. Exportação PDF não implementada (não anunciada).
6. Testado apenas em Chromium.

## Próxima ação recomendada
No Windows: `pip install -e ".[app]"` → `.\scripts\Start-DeepModel.ps1` → fluxo DEMO; opcional `pip install -e ".[ui-test]"; playwright install chromium; pytest tests/e2e`.
