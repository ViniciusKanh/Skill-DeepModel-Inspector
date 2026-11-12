# Limitations (v1.0.0)

- **Lexical, not semantic.** Duplicate, leakage and grounding checks use normalized text, shingles and n-grams.
  Paraphrased, translated or reformatted contamination and semantically wrong but lexically similar answers are not detected.
- **Hallucinations** are only checked against a `reference` field supplied with each output; no universal factuality
  detection is claimed. Flagged sentences are candidates.
- **Thresholds are heuristics** (documented in the methodology). They were validated on synthetic scenarios, not on a
  large corpus of real training runs; tune them for your setting.
- **Single-run comparisons** do not establish statistical significance; seeds/variance are not modelled except for the
  bootstrap comparison of generation repetition.
- **Overfitting** requires validation loss; **gradient** rules require logged `grad_norm`. Nothing is inferred
  about model internals from metrics that do not represent them.
- **Perplexity** is derived as exp(eval_loss) when not logged, assuming mean token cross-entropy in nats; perplexities
  from different tokenizers/datasets are not compared (`CMP.INCOMPATIBLE`).
- **Tokenizer analysis** needs tokenizations produced by the user (or a local Hugging Face tokenizer in the engine,
  optional `transformers` dependency). Fragmentation needs `Ġ`/`▁` word-boundary markers.
- **Language estimate** is a stopword heuristic for en/pt/es/fr/de; other languages appear as `und`.
- **Scale.** Pure-Python MinHash: near-duplicate search is capped at the first 20,000 records per file; default
  limits 200 MB per file and 200,000 records (configurable). 13-gram sets for very large training files use memory
  proportional to the corpus.
- **Checkpoints**: weights are never loaded, so NaN weights or numeric tensor health are not inspected.
- **Platform**: engine tested on Linux (Python 3.11/3.13) and on Windows (Python 3.13, 68 tests passed). The local app's
  PowerShell launcher has not been executed by the developer environment; the app UI was tested in Chromium only.
- **Live inspection** covers OpenAI-compatible chat APIs only; the probe suite is small and generic (not a benchmark);
  latency includes network/queueing. Production monitoring is batch (exported logs), not real-time.
- **Script size guideline**: Agensi suggests < 20 KB of logic per script. Measured sizes are listed in
  `docs/agensi-compliance.md`; three scripts exceed 20 KB when message strings are counted.
