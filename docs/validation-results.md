# Validation results (real runs, 2026-11-09)

Environment: Linux x86_64 sandbox, Python 3.13.18 and Python 3.11.18, pytest 9.1.1, ruff 0.16.9, pytest-cov.
Native Windows (run by the author, 2026-11-09, Python 3.13 venv, pytest 9.2.0, ruff 0.17.4): `pytest -q` → 68 passed;
`python tools\package_agensi.py` → 0 static problems, isolated runs OK, 13 files.

**ZIP checksum note.** The Windows build produced SHA-256
`763704f28654dbb11903a0d716da94277008d51e6b6edea2885dfcfc6d87c362` (the ZIP now in `dist/` on the author's machine),
while the Linux build produced `1dd057164a617f4010ae6f7a7b37a5eafa6dbac21db0cc4b1770e11f30c73739`. The extracted
contents are byte-identical (same SHA-256 over all 13 files: `5a968384…749c7`); only the DEFLATE streams differ
(zlib-ng on Linux vs. zlib on Windows). Use the checksum of the ZIP you actually upload (`dist/SHA256SUMS.txt`).

| Check | Command | Result |
|---|---|---|
| Unit + integration tests (3.13) | `python3 -m pytest -q --cov=deepmodel_inspector` | 68 passed; line coverage 92% |
| Unit + integration tests (3.11) | `python3.11 -m pytest -q` | 68 passed |
| Lint / format | `ruff check src tests tools examples` · `ruff format --check …` | all checks passed · 35 files formatted |
| Packaging + static scan | `python3 tools/package_agensi.py` | 0 static problems; ZIP 85,069 bytes, 13 files |
| Isolated script runs from extracted ZIP | (inside `package_agensi.py`) | 12/12 runs with expected exit codes (10 analyses → 0; outside-root → 3; missing file → 2) |
| Determinism | packaged with 3.13 and 3.11 | identical SHA-256 `1dd057164a617f4010ae6f7a7b37a5eafa6dbac21db0cc4b1770e11f30c73739` |
| Engine ↔ script parity | `tests/test_skill_scripts.py` | identical JSON for training, dataset, leakage, tokenizer, generation, compare; identical findings/hypotheses/answer for investigate; scripts up to date with engine |
| Throughput (informative) | `deepmodel dataset` on 20,000 records × 120 words (14 MB) | 36.9 s; `deepmodel leakage` same file vs itself 66.8 s (single CPU, pure Python) |

## Test inventory (68 tests)

- Training: stable (no problem findings), overfitting CONFIRMED, divergence + NaN, plateau ≠ underfit, underfit,
  LR association POTENTIAL, missing loss → INCONCLUSIVE, no overfitting claim without validation, no gradient
  inference without grad_norm, HF `trainer_state.json`, unordered steps, malformed JSONL, short series, perplexity derivation.
- Dataset/leakage: clean dataset → 0 findings, dirty dataset rules, messages schema, CSV field, formats, empty file,
  deterministic MinHash, redaction, contamination counts (10 exact / 5 near / 3 prompt), clean split → LEK.CLEAN only,
  shared template not flagged as contamination.
- Tokenizer/generation/compare: inefficient vs efficient tokenizations, no tokenizer simulation, comparison, UNK by id,
  repetitive vs diverse outputs, non-causal config comparison, grounding only with references, distinct-n,
  regression, incompatible tokenizer (no regression claimed), no common metrics.
- Engine/CLI/security: intents EN/PT, investigate (confirmed, missing artifacts, negative clean case), all 11 commands,
  report section order, HTML escaping of injected markup, path traversal, sensitive files (.env, id_rsa, .pem,
  credentials.json), `.env.example` allowed, pickle refused, size limit, output cannot overwrite input, CLI exit codes,
  invalid JSON, safetensors header-only reading + pickle listing + vocab mismatch, scan skipping unsafe files, finding schema.
- Skill scripts: up-to-date check, 6 parity cases, investigate/report parity, script security refusals.

## Synthetic scenarios → observed findings

| Scenario | Findings |
|---|---|
| `synthetic_training/stable.csv` | none |
| `overfitting.csv` | TRN.OVERFIT (HIGH, CONFIRMED) |
| `divergent.csv` | TRN.NONFINITE ×3 (CRITICAL), TRN.DIVERGENCE (CONFIRMED), TRN.GRAD_EXPLOSION, TRN.INSTABILITY, TRN.LR_HIGH |
| `plateau.csv` | TRN.PLATEAU (LOW, POTENTIAL) |
| `underfit.csv` | TRN.UNDERFIT (POTENTIAL) |
| `unstable.csv` | TRN.GRAD_EXPLOSION, TRN.INSTABILITY, TRN.LR_HIGH |
| `no_metrics.csv` | TRN.NO_LOSS (INCONCLUSIVE) |
| `synthetic_datasets/clean_train.jsonl` | none |
| `dirty_train.jsonl` | DAT.EXACT_DUP (HIGH), DAT.NEAR_DUP, DAT.REPETITIVE, DAT.STRUCTURE, DAT.EMPTY, DAT.ENCODING, DAT.INSTRUCTION_LIKE |
| `contaminated/train vs test` | LEK.EXACT (CRITICAL), LEK.NEAR (HIGH), LEK.PROMPT |
| `clean_split/train vs test` | LEK.CLEAN only |
| `synthetic_generations/diverse_outputs.jsonl` | none |
| `repetitive_outputs.jsonl` | GEN.REPETITION (CONFIRMED), GEN.LOW_DIVERSITY, GEN.TRUNCATED |
| `synthetic_tokenization/efficient_tokens.jsonl` | none (without `--max-length`) |
| `inefficient_tokens.jsonl` (max 64) | TOK.FERTILITY, TOK.BYTE_FALLBACK, TOK.TRUNCATION |
| `synthetic_runs/run_v1 → run_v2` | CMP.REGRESSION ×2, CMP.LATE_DEGRADATION, CMP.HP_CHANGES |
| `run_v1 → run_v3_other_tokenizer` | CMP.INCOMPATIBLE only |

Sample reports: `examples/sample_reports/` (engine `audit.*`, `investigate_*`, and skill-script `skill_report.*`).
All data is synthetic; no private or corporate data was used.
