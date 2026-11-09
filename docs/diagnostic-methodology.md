# Diagnostic Methodology

This document is the authoritative description of every rule implemented in v1.0.0. It is kept identical to
`agensi/deepmodel-inspector/references/rules.md` (the copy shipped with the skill).

General principles:

- Findings are produced only by documented, deterministic rules over computed statistics (seeded where random).
- `CONFIRMED` describes an observed fact satisfying a rule, never a proven cause.
- Hypotheses (`RC.*`) combine findings across artifacts and are always `POTENTIAL`, each with a test.
- Severity reflects the potential impact on the validity of training/evaluation: CRITICAL (results invalid or
  training broken), HIGH (likely materially wrong conclusions), MEDIUM (quality/efficiency problem), LOW (minor),
  INFO (context, no action needed).
- Missing inputs lead to `INCONCLUSIVE`, not to guesses.


Every finding carries `rule`, `severity` (CRITICAL/HIGH/MEDIUM/LOW/INFO), `status`, `evidence`,
`explanation`, `recommendation` and (when useful) `confirmation` (how to confirm or reject it).

## Status semantics

| Status | Meaning |
|---|---|
| `CONFIRMED` | The documented rule is satisfied by the data (an observed fact, e.g. "eval records appear verbatim in train"). It never means a *cause* is proven. |
| `POTENTIAL` | Indicators support a possible problem; needs the listed confirmation step. |
| `INCONCLUSIVE` | Not enough information to evaluate (missing columns, too few points, incompatible runs). |

No arbitrary confidence percentages are produced. Root-cause hypotheses (`RC.*`) are always `POTENTIAL`.

## Training health (`dmi_training.py`)

Accepted columns (aliases): step/global_step/iteration, epoch, loss/train_loss, eval_loss/val_loss/validation_loss,
learning_rate/lr, grad_norm, eval_perplexity/perplexity. Rows are sorted by step (time order). Minimum 5 finite points for trend rules.

| Rule | Condition | Status / severity |
|---|---|---|
| TRN.NONFINITE | NaN/Inf in loss, eval loss or grad norm | CONFIRMED / CRITICAL |
| TRN.DIVERGENCE | mean of last 20% > mean of first 20% **and** > 1.5× minimum | CONFIRMED / HIGH |
| TRN.DIVERGENCE | last-third trend rising (relative > 0.1) and tail > 1.3× minimum | POTENTIAL / MEDIUM |
| TRN.UNDERFIT | < 10% improvement first→last window (≥ 10 points) | POTENTIAL / MEDIUM |
| TRN.PLATEAU | ≥ 10% overall improvement but < 1% over the last third | POTENTIAL / LOW |
| TRN.INSTABILITY | ≥ 3 spikes (or > 5% of ≥ 20 points); spike = interior point above the centred 7-point median by > max(6 × 1.4826 × MAD of residuals, 2% of median loss) | POTENTIAL / MEDIUM |
| TRN.LR_HIGH | ≥ half of spikes (min 2) occur at LR ≥ 90% of peak | POTENTIAL / MEDIUM (association only) |
| TRN.NO_VALIDATION | < 3 validation points → overfitting not assessed | INCONCLUSIVE / INFO |
| TRN.OVERFIT | after its minimum, eval loss rises ≥ 5% with ≥ 2 increases while train-loss slope < 0 | CONFIRMED if ≥ 3 increases, else POTENTIAL / HIGH |
| TRN.VAL_BELOW_TRAIN | eval loss below train loss over the second half of evaluations | POTENTIAL / LOW (check leakage) |
| TRN.GRAD_EXPLOSION | grad norm > 10× its median (only if grad_norm is logged) | POTENTIAL / HIGH |
| TRN.GRAD_VANISH | final grad-norm median < 0.1% of initial | POTENTIAL / MEDIUM |
| TRN.ORDER | rows not in step order (re-sorted) | CONFIRMED / LOW |
| TRN.NO_LOSS | no loss column | INCONCLUSIVE / INFO |

Statistics reported: n, min, max, mean, std, median, p95, first, last, least-squares slope per 1k steps, relative change,
per-quarter window mean/std (stability), Spearman/Pearson LR↔loss (descriptive), val–train gap, perplexity
(logged, or derived as exp(eval_loss) assuming mean token cross-entropy in nats — stated in the output).
Gradient behaviour is never inferred from loss alone.

## Dataset quality (`dmi_dataset.py`)

Formats: plain text (one record per line), JSONL `text`, `instruction/input/output`, `messages` (or ShareGPT
`conversations`), `prompt/response|completion`, CSV with `--text-field`.

| Rule | Condition | Status / severity |
|---|---|---|
| DAT.EMPTY | records without text | CONFIRMED / MEDIUM if ≥ 5% else LOW |
| DAT.EXACT_DUP | identical after NFKC + casefold + punctuation/whitespace normalization | CONFIRMED / HIGH ≥ 10%, MEDIUM ≥ 2%, else LOW |
| DAT.NEAR_DUP | MinHash (64 seeded permutations, LSH 16×4) on word 5-shingles, verified Jaccard ≥ 0.8 (first 20,000 records) | POTENTIAL / MEDIUM if ≥ 5% of records |
| DAT.REPETITIVE | ≥ 20 words and > 50% repeated word 3-grams inside the record | CONFIRMED / MEDIUM if ≥ 2% |
| DAT.STRUCTURE | missing/empty instruction or output, invalid roles, no assistant turn, last turn not assistant, consecutive same role, unrecognized schema | CONFIRMED / MEDIUM (HIGH if > 50% unrecognized) |
| DAT.ENCODING | mojibake (e.g. `Ã©`) or control characters | CONFIRMED / MEDIUM if ≥ 1% |
| DAT.INSTRUCTION_LIKE | text that tries to override an AI model's instructions — flagged and treated as data, never followed | CONFIRMED / INFO |
| DAT.MALFORMED | unparsable lines skipped | CONFIRMED / MEDIUM |

Within-file duplicates are a quality issue (possibly intentional upsampling), **not** leakage.
Language: stopword-count heuristic for en/pt/es/fr/de; `und` when < 3 stopwords or tie. Scripts: Unicode name prefix of letters.
Evidence samples are truncated to 80–120 characters with e-mails, long digit runs and API-key-like strings masked.

## Leakage / contamination (`dmi_leakage.py`)

| Rule | Condition | Status / severity |
|---|---|---|
| LEK.EXACT | eval record identical (normalized) to a train record | CONFIRMED / CRITICAL ≥ 5% of eval, else HIGH |
| LEK.NEAR | not exact, but shingle Jaccard ≥ 0.8 with a train record | POTENTIAL / HIGH ≥ 5%, else MEDIUM |
| LEK.PROMPT | input side identical to a train example with a different target | POTENTIAL / MEDIUM |
| LEK.NGRAM | ≥ 50% of the record's word 13-grams occur in train; 13-grams present in ≥ max(5, 1% of train) records are ignored as templates | POTENTIAL / MEDIUM |
| LEK.CLEAN | none of the above | CONFIRMED / INFO |

Only lexical overlap is measured (paraphrase/translation contamination is out of scope).

## Tokenizer efficiency (`dmi_tokenizer.py`)

Input: JSONL with `text` plus `tokens` (strings) and/or `token_ids`/`input_ids`; optional `tokenizer` field to compare groups.
Tokenizer output is **never simulated**; without tokens only text statistics are produced (TOK.NO_TOKENS).

| Rule | Condition | Status / severity |
|---|---|---|
| TOK.FERTILITY | tokens per word > 2.0 (configurable) | POTENTIAL / MEDIUM |
| TOK.UNK | unknown tokens present | CONFIRMED / HIGH > 1%, else MEDIUM |
| TOK.BYTE_FALLBACK | `<0xNN>` tokens > 2% | POTENTIAL / MEDIUM |
| TOK.TRUNCATION | > 5% of sequences reach `--max-length` | CONFIRMED / MEDIUM |
| TOK.CONTEXT_WASTE | padding > 30% or mean unused context > 50% of `--max-length` | POTENTIAL / LOW |

Metrics: tokens/word, tokens/char, chars/token, tokens per record distribution, fragmentation rate (words split
into ≥ 2 tokens, requires `Ġ`/`▁` word markers), observed vocabulary coverage (with `--vocab-size`), UNK, byte-fallback,
padding, truncation, relative cost vs. the most efficient tokenizer group.

## Generation behaviour (`dmi_generation.py`)

Output field: output/response/generation/completion/generated_text/prediction/text. Group by config/run/experiment/model
(or `--group-field`). Decoding metadata recorded when present: temperature, top_k, top_p, repetition_penalty,
max_tokens/max_new_tokens, do_sample, finish_reason, token_count.

| Rule | Condition | Status / severity |
|---|---|---|
| GEN.EMPTY | empty outputs | CONFIRMED / MEDIUM ≥ 5% |
| GEN.REPETITION | ≥ 10% of responses repeat > 50% of their word 3-grams | CONFIRMED / HIGH |
| GEN.LOW_DIVERSITY | corpus distinct-2 < 0.3 (≥ 20 responses) | POTENTIAL / MEDIUM |
| GEN.REDUNDANT | ≥ 20% of outputs near-identical (3-gram Jaccard ≥ 0.8) across different prompts (sample ≤ 200, seed 13) | POTENTIAL / MEDIUM |
| GEN.TRUNCATED | finish_reason = length or token_count ≥ max tokens | CONFIRMED / MEDIUM ≥ 10% |
| GEN.SHORT | ≥ 20% of responses below `--min-words` | POTENTIAL / LOW |
| GEN.UNSUPPORTED | with a `reference` field: ≥ 20% of sentences with < 50% content-word overlap, or numbers absent from the reference | POTENTIAL / MEDIUM |
| GEN.CONFIG_DIFF | bootstrap (1000 resamples, seed 13) 95% CI of the mean repetition-rate difference excludes 0 | CONFIRMED / INFO (difference, not cause) |

Metrics: distinct-1/2/3, per-response repetition rate, MATTR (window 50), length distribution, mean pairwise similarity.

## Experiment comparison (`dmi_compare.py`)

Reads `config.json`, `run_config.json`, `hparams.json`, `training_args.json`, `adapter_config.json`, `metrics.json`,
`eval_results.json`, `all_results.json`, `trainer_state.json` and loss logs. Weights are never loaded.

| Rule | Condition | Status / severity |
|---|---|---|
| CMP.INCOMPATIBLE | tokenizer, vocab size, eval dataset or eval protocol differ → no loss/perplexity regression is claimed | INCONCLUSIVE / MEDIUM |
| CMP.REGRESSION | metric worse by > tolerance (default 1%); direction from name (loss/perplexity/error lower is better; accuracy/F1/BLEU/ROUGE/EM higher is better) | CONFIRMED when eval-set compatibility is verified, else POTENTIAL / HIGH ≥ 5% |
| CMP.HP_CHANGES | learning rate, batch, epochs, sequence length, LoRA r/alpha, scheduler, seed… changed | CONFIRMED / INFO |
| CMP.LATE_DEGRADATION | final eval loss > 5% above the run's best with ≥ 2 later evaluations | CONFIRMED / MEDIUM |
| CMP.NO_COMMON_METRICS | nothing comparable | INCONCLUSIVE / INFO |

## Checkpoint metadata (`dmi_checkpoint.py`)

Reads only the JSON header of `.safetensors` files (8-byte length + JSON, max 100 MB) and JSON configs.
Pickle-based files (`.bin`, `.pt`, `.pth`, `.ckpt`, `.pkl`) are listed and never opened (CKP.PICKLE).
CKP.VOCAB_MISMATCH: `config.json` vs `tokenizer_config.json` vocab size differ (CONFIRMED / HIGH).

## Root-cause hypotheses (`dmi_investigate.py`)

| Hypothesis | Triggered by |
|---|---|
| RC.REPETITION_DATA | GEN.REPETITION + DAT.REPETITIVE or DAT.EXACT_DUP |
| RC.REPETITION_DECODING | GEN.REPETITION + temperature ≤ 0.3, repetition_penalty ≤ 1.0 or do_sample=False |
| RC.REPETITION_EOS | GEN.REPETITION + GEN.TRUNCATED |
| RC.OVERFIT_DUPLICATES / RC.OVERFIT_BUDGET | TRN.OVERFIT (+ duplicates) |
| RC.LEAKAGE_INFLATED | any LEK.* overlap |
| RC.DIVERGENCE_LR / _DATA / _GENERIC | TRN.NONFINITE/DIVERGENCE/INSTABILITY/GRAD_EXPLOSION (+ LR or data evidence) |
| RC.UNDERFIT | TRN.UNDERFIT |
| RC.REGRESSION_HP / _DATA | CMP.REGRESSION + hyperparameter changes / data findings |
| RC.TOKENIZER_MISMATCH | TOK.FERTILITY/BYTE_FALLBACK/UNK |
| RC.HALLUCINATION_REF | GEN.UNSUPPORTED |

Question intents (English and Portuguese keywords): repetition, overfitting, divergence, contamination, regression,
tokenizer, hallucination, underfitting, dataset. Each intent lists the artifacts it needs; when they are missing the
answer is `INCONCLUSIVE` and names the files to provide. When artifacts exist but no rule fires, the answer says no
evidence was found at the documented thresholds (which does not prove absence).
