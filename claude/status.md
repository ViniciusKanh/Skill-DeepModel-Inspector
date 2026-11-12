# DeepModel Inspector — status de execução

Última atualização: 2026-11-09. Estado: **Fase 1 e Fase 2 concluídas** (pendências abaixo).

## Fase 1 — Motor (concluída)
- Módulos: security/guard, core/common, parsers/records, analyzers/{training,dataset,leakage,tokenizer,generation,compare,checkpoint}, diagnostics/{inventory,rootcause}, reporting/render, cli (11 comandos).
- Dados sintéticos reproduzíveis: `python examples/generate_synthetic.py`.

## Fase 2 — Skill e release (concluída)
- `tools/build_skill.py` gera 9 scripts standalone em `agensi/deepmodel-inspector/scripts/`.
- `tools/package_agensi.py` valida, empacota e executa os scripts isolados a partir do ZIP.
- Documentação: README, CHANGELOG, docs/{architecture, diagnostic-methodology, validation-results, limitations, agensi-listing, agensi-compliance, PUBLISH_AGENSI, LICENSE-COMMERCIAL-DRAFT}.

## Comandos executados e resultados (ambiente Linux sandbox)
- `python3 -m pytest -q --cov=deepmodel_inspector` (Python 3.13.18) → 68 passed, cobertura 92%.
- `python3.11 -m pytest -q` (Python 3.11.18) → 68 passed.
- `ruff check src tests tools examples` → All checks passed; `ruff format --check` → 35 arquivos formatados.
- `python3 tools/package_agensi.py` (3.13 e 3.11) → 0 problemas estáticos; 12/12 execuções isoladas com código de saída esperado.
- ZIP: `dist/deepmodel-inspector-v1.0.0.zip` — SHA-256 `1dd057164a617f4010ae6f7a7b37a5eafa6dbac21db0cc4b1770e11f30c73739` (idêntico em 3.11 e 3.13).

## Pendências / riscos
1. Windows + Python 3.13 executado pelo autor: 68 passed; package OK. ZIP oficial atual (build Windows) SHA-256 763704f28654dbb11903a0d716da94277008d51e6b6edea2885dfcfc6d87c362 — conteúdo idêntico ao build Linux (diferença só na compressão zlib).
2. dmi_dataset.py, dmi_training.py e dmi_generation.py excedem a diretriz de 20 KB de lógica quando os textos de mensagens são contados (ver docs/agensi-compliance.md).
3. Licença comercial é minuta, sem aprovação.
4. Limiares heurísticos validados somente em dados sintéticos.
5. Nada foi publicado (GitHub/Agensi).

## Inspeção ao vivo e monitoramento (2026-11-12)
- Assistente de conexão (auto-detecção local + cartões de provedores online), veredito em linguagem simples, Start-DeepModel.ps1 ASCII/robusto.
- Arquitetura de publicação (Desktop/Microsoft Store, Cloud/Vercel+workers, Connector): docs/deployment-architecture.md (proposta, não implementada).
- Testes: pytest 101 passed (3.13), 80 (3.11), vitest 8.
Ver `claude/frontend-status.md` e `docs/live-inspection.md`. Próxima ação: testar `deepmodel probe` contra Ollama/LM Studio local.

## HF sem download, projeto Live models, instalador Windows (2026-11-12)
- `src/deepmodel_inspector/probe/hub.py` + `deepmodel hub --repo`: metadados HF sem baixar pesos (regras HUB.*); token só ao host do Hub; redirecionamentos só Hub/CDN. Testado com Hub simulado (tests/test_hub.py) — NÃO validado contra o Hub real (sandbox sem acesso).
- Provedor "Hugging Face (Inference Providers)" no catálogo online.
- Projeto "Live models" (prj-live): cada alvo/repo HF vira experimento; transcrições `generations_probe_*.jsonl`; job `hub`; endpoints `/api/hub/token`.
- UI: assistente "Hugging Face model", botões Open in Dashboard/Generation/Investigate, ficha HF no Dashboard.
- Instalador: desktop/launcher.py, desktop/deepmodel.spec, desktop/installer.iss, desktop/icon.ico, scripts/Build-Installer.ps1, .github/workflows/release.yml, docs/installer.md. PyInstaller validado no Linux; build Windows/Inno/workflow pendentes de execução no Windows.
- Testes: pytest 108 passed (3.13, inclui 9 e2e), 85 passed/3 skipped (3.11), vitest 8, tsc/build OK, ruff OK; skill Agensi e ZIP inalterados.
- Próxima ação: rodar `scripts\Build-Installer.ps1` no Windows; decidir repo público para Releases; testar `deepmodel hub` com rede real.

## Automação GitHub Actions + mídia (2026-11-12)
- `.github/workflows/ci.yml` (ruff+pytest Ubuntu/Windows 3.11/3.13; tsc/vitest/build), `release.yml` (instalador), `docs-media.yml` (e2e + `tools/capture_media.py` → capturas, docs/media/tour.mp4 + tour.gif, bloco `<!-- MEDIA -->` do README, commit do bot com [skip ci]).
- `examples/fake_hf_hub.py` (Hub simulado reutilizado por testes e capturas). Ficha HF: formatação K/M/B e MB.
- Validado localmente: capture_media OK (GIF 4,6 MB, MP4 0,9 MB), pytest 108, 3.11 85, vitest 8. Workflows NÃO executados no GitHub (sem acesso); YAML validado sintaticamente.
- Requer no GitHub: Settings → Actions → Workflow permissions = Read and write.
Ver `claude/frontend-status.md` (app local React + FastAPI, concluído em 2026-11-09).

## Ponto de retomada
Se for preciso regenerar tudo: `pip install -e ".[dev]"` → `python examples/generate_synthetic.py` → `pytest -q` → `python tools/package_agensi.py`.
