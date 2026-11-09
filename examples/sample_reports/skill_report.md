# DeepModel Inspector Report

Version 1.0.0 · generated 2026-11-09T15:09:42Z · analyses: comparison, dataset, generation, leakage, tokenizer, training

## 1. Executive Summary

**Question:** Why is my LLM repeating the same sentences?

**Answer status:** `CONFIRMED` — Observed problem(s) confirmed by the data: DMI-004 Exact duplicate records (within this file); DMI-005 Degenerate repetition; DMI-011 Responses cut by the token limit. Causes are listed as hypotheses to be tested, not as confirmed causes.

- Findings by severity: {'CRITICAL': 1, 'HIGH': 6, 'MEDIUM': 8, 'LOW': 1, 'INFO': 1}
- Findings by status: {'CONFIRMED': 10, 'POTENTIAL': 7, 'INCONCLUSIVE': 0}
- DMI-001 [CRITICAL/CONFIRMED] Evaluation records present verbatim in training (test.jsonl)
- DMI-002 [HIGH/CONFIRMED] Metric regressed: eval_accuracy
- DMI-003 [HIGH/CONFIRMED] Metric regressed: eval_loss
- DMI-004 [HIGH/CONFIRMED] Exact duplicate records (within this file)
- DMI-005 [HIGH/CONFIRMED] Degenerate repetition

## 2. Data & Artifact Inventory

| Analysis | Source |
|---|---|
| training | overfitting.csv |
| dataset | train.jsonl |
| leakage | train.jsonl vs test.jsonl |
| tokenizer | tokenizer_comparison.jsonl |
| generation | generations.jsonl |
| comparison | run_v1 -> run_v2 |

## 3. Training Health

**Source:** `overfitting.csv`

Metrics: `{"rows": 100, "unordered_rows": 0, "train_loss": {"n": 100, "min": 0.33294, "max": 2.41629, "mean": 0.82898, "std": 0.548842, "median": 0.59315, "p95": 2.03151, "non_finite": 0, "first": 2.41629, "last": 0.33294, "slope_per_1k_steps": -1.707488, "relative_change": -0.86221, "argmin_step": 1000.0, "window_std": [0.390241, 0.142703, 0.053275, 0.020674], "window_mean": [1.663276, 0.801129, 0.48488, 0.366635]}, "val_loss": {"n": 10, "min": 1.10827, "max": 1.48539, "mean": 1.290488, "std": 0.12943, "median": 1.27923, "p95": 1.48539, "non_finite": 0, "first": 1.48522, "last": 1.48539, "slope_per_1k_steps": 0.127651, "relative_change": 0.000114, "argmin_step": 400.0, "window_std": [0.09546, 0.035115, 0.02708, 0.082517], "window_mean": [1.38976, 1.143385, 1.17275, 1.373272]}, "lr": {"n": 100, "min": 0.0, "max": 0.000293, "mean": 0.000135, "std": 9.8e-05, "median": 0.000129, "p95": 0.000284, "non …`

- DMI-007 [HIGH/CONFIRMED] Validation loss rises while training loss falls (overfitting pattern)

## 4. Dataset Quality

**Source:** `train.jsonl`

Metrics: `{"records": 260, "formats": {"instruction": 260}, "empty_records": 0, "length_chars": {"n": 260, "min": 280.0, "max": 349.0, "mean": 312.296154, "std": 11.819833, "median": 313.0, "p95": 331.0}, "length_words": {"n": 260, "min": 47.0, "max": 48.0, "mean": 47.038462, "std": 0.192308, "median": 47.0, "p95": 47.0}, "exact_duplicate_groups": 30, "exact_duplicate_extra_records": 30, "exact_duplicate_rate": 0.1154, "near_duplicate_pairs": 10, "near_duplicate_records": 20, "near_duplicate_threshold": 0.8, "repetitive_records": 0, "structure_issues": {}, "unicode": {"mojibake_records": 0, "zero_width_records": 0, "control_char_records": 0, "non_nfc_records": 0}, "scripts": {"LATIN": 1.0}, "language_estimate": {"en": 202, "und": 58}, "language_method": "stopword-count heuristic (en/pt/es/fr/de); 'und' when undetermined", "instruction_like_records": 0}`

- DMI-004 [HIGH/CONFIRMED] Exact duplicate records (within this file)
- DMI-009 [MEDIUM/POTENTIAL] Near-duplicate records

**Source:** `train.jsonl vs test.jsonl`

Metrics: `{"train_records": 260, "boilerplate_ngrams_ignored": 0, "splits": {"test.jsonl": {"records": 20, "exact_overlap": 10, "exact_overlap_rate": 0.5, "near_duplicate_overlap": 5, "prompt_seen_in_train": 3, "records_with_13gram_overlap": 0, "mean_13gram_overlap_of_hits": 0.0}}}`

- DMI-001 [CRITICAL/CONFIRMED] Evaluation records present verbatim in training (test.jsonl)
- DMI-006 [HIGH/POTENTIAL] Near-duplicate evaluation records in training (test.jsonl)
- DMI-012 [MEDIUM/POTENTIAL] Evaluation prompts seen in training with different answers (test.jsonl)

## 5. Tokenizer Efficiency

**Source:** `tokenizer_comparison.jsonl`

Metrics: `{"groups": {"english-bpe": {"records": 30, "records_with_tokens": 30, "chars": 4096, "words": 600, "tokens_total": 2362, "tokens_per_record": {"n": 30, "min": 60.0, "max": 102.0, "mean": 78.733333, "std": 10.385674, "median": 79.0, "p95": 96.0}, "tokens_per_word": 3.9367, "tokens_per_word_dist": {"n": 30, "min": 3.0, "max": 5.1, "mean": 3.936667, "std": 0.519284, "median": 3.95, "p95": 4.8}, "chars_per_token": 1.7341, "tokens_per_char": 0.5767, "unk_rate": 0.0, "byte_fallback_rate": 0.200677, "padding_rate": 0.0, "distinct_tokens_observed": 64, "fragmentation_rate": 0.8124, "truncated_records": 27, "truncation_rate": 0.9, "mean_unused_context": 0.0031}, "portuguese-bpe": {"records": 30, "records_with_tokens": 30, "chars": 4096, "words": 600, "tokens_total": 600, "tokens_per_record": {"n": 30, "min": 20.0, "max": 20.0, "mean": 20.0, "std": 0.0, "median": 20.0, "p95": 20.0}, "tokens_per_wo …`

- DMI-013 [MEDIUM/POTENTIAL] Frequent byte-fallback tokens [english-bpe]
- DMI-014 [MEDIUM/POTENTIAL] High token fertility [english-bpe]
- DMI-015 [MEDIUM/CONFIRMED] Sequences reach max length [english-bpe]
- DMI-016 [LOW/POTENTIAL] Large unused context [portuguese-bpe]

## 6. Generation Behavior

**Source:** `generations.jsonl`

Metrics: `{"groups": {"greedy": {"responses": 30, "empty": 0, "length_words": {"n": 30, "min": 53.0, "max": 65.0, "mean": 59.0, "std": 4.898979, "median": 59.0, "p95": 65.0}, "short_responses": 0, "distinct_1": 0.0576, "distinct_2": 0.092, "distinct_3": 0.0936, "repetition_rate": {"n": 30, "min": 0.823529, "max": 0.859649, "mean": 0.841483, "std": 0.014747, "median": 0.84127, "p95": 0.859649}, "degenerate_responses": 30, "mattr": 0.1119, "mean_pairwise_similarity": 0.0884, "near_identical_fraction": 0.0, "finish_reason_length": 15, "reached_max_tokens": 0, "decoding_params": {"temperature": ["0.0"], "repetition_penalty": ["1.0"], "max_new_tokens": ["128"], "do_sample": ["False"]}}}}`

- DMI-005 [HIGH/CONFIRMED] Degenerate repetition
- DMI-010 [MEDIUM/POTENTIAL] Low lexical diversity
- DMI-011 [MEDIUM/CONFIRMED] Responses cut by the token limit

## 7. Experiment Comparison

**Source:** `run_v1 -> run_v2`

Metrics: `{"hyperparameters": {"learning_rate": {"before": 2e-05, "after": 0.0001, "changed": true}, "per_device_batch": {"before": 8, "after": 8, "changed": false}, "grad_accum": {"before": 4, "after": 4, "changed": false}, "epochs": {"before": 3, "after": 5, "changed": true}, "max_seq_length": {"before": 1024, "after": 1024, "changed": false}, "method": {"before": "sft", "after": "sft", "changed": false}, "scheduler": {"before": "cosine", "after": "cosine", "changed": false}, "seed": {"before": 1, "after": 1, "changed": false}, "effective_batch_per_device": {"before": 32, "after": 32, "changed": false}}, "changed_hyperparameters": ["epochs", "learning_rate"], "compatibility": {"tokenizer": {"before": "demo-bpe-32k", "after": "demo-bpe-32k"}, "vocab_size": {"before": 32000, "after": 32000}, "eval_dataset": {"before": "eval-v1-sha256:3f9a", "after": "eval-v1-sha256:3f9a"}, "eval_protocol": {"befor …`

- DMI-002 [HIGH/CONFIRMED] Metric regressed: eval_accuracy
- DMI-003 [HIGH/CONFIRMED] Metric regressed: eval_loss
- DMI-008 [MEDIUM/CONFIRMED] Validation loss of 'after' run ends >5% above its best
- DMI-017 [INFO/CONFIRMED] Hyperparameters changed between runs

## 8. Root Cause Investigation

- **HYP-001** `POTENTIAL` Evaluation scores may be inflated by train/test overlap. (supported by DMI-001, DMI-006, DMI-012)
  - Test: Re-compute evaluation metrics on the decontaminated subset and compare with the full set.
- **HYP-002** `POTENTIAL` Data quality issues in the new training data may contribute to the regression. (supported by DMI-001, DMI-002, DMI-003, DMI-004, DMI-006, DMI-009, DMI-012)
  - Test: Retrain after fixing the flagged data issues and compare on the same eval set.
- **HYP-003** `POTENTIAL` Training continued past the point of best generalization (too many steps/epochs or insufficient regularization for the dataset size). (supported by DMI-007)
  - Test: Enable early stopping on eval_loss or reduce epochs; compare held-out task metrics at the best step.
- **HYP-004** `POTENTIAL` Duplicated training examples may accelerate memorization and overfitting. (supported by DMI-004, DMI-007, DMI-009)
  - Test: Train on the deduplicated set; overfitting onset (best eval step) should move later.
- **HYP-005** `POTENTIAL` One of the changed hyperparameters (epochs, learning_rate) may explain the regression. (supported by DMI-002, DMI-003, DMI-017)
  - Test: Ablate: revert each changed hyperparameter individually with a fixed seed.
- **HYP-006** `POTENTIAL` Repetitive or duplicated training targets may be teaching the model to repeat. (supported by DMI-004, DMI-005)
  - Test: Fine-tune on the deduplicated/filtered dataset with identical settings and compare repetition rate.
- **HYP-007** `POTENTIAL` Decoding settings that favour loops: temperature<=0.3 (0.0), repetition_penalty<=1.0, greedy decoding (do_sample=False). (supported by DMI-005)
  - Test: Re-generate the same prompts with repetition_penalty=1.15 or temperature=0.7 (one change at a time).
- **HYP-008** `POTENTIAL` The model may fail to emit end-of-sequence and loops until the token limit. (supported by DMI-005, DMI-011)
  - Test: Check that SFT targets end with the EOS token and that the chat template adds it; count EOS in labels.
- **HYP-009** `POTENTIAL` The tokenizer vocabulary fits this text/language poorly, raising sequence length and cost and causing truncation. (supported by DMI-013, DMI-014, DMI-015, DMI-016)
  - Test: Tokenize the same texts with a language-appropriate tokenizer; compare tokens/word.

## 9. Findings by Severity

### DMI-001 · CRITICAL · CONFIRMED · Evaluation records present verbatim in training (test.jsonl)

- Rule: `LEK.EXACT` · Category: leakage · Source: `train.jsonl vs test.jsonl`
- Evidence: `{"split": "test.jsonl", "count": 10, "rate": 0.5, "first_indices": [2, 3, 4, 5, 6], "sample": "Complex result dataset recipe with loss to slow text input apple loss. Bottle r…"}`
- Explanation: These evaluation examples (after normalization) also appear in the training data, so metrics on them measure memorization, not generalization.
- Recommendation: Remove the overlapping records from the evaluation set (or training set) and re-evaluate.
- How to confirm: Report metrics separately on the clean subset vs. the overlapping subset.

### DMI-002 · HIGH · CONFIRMED · Metric regressed: eval_accuracy

- Rule: `CMP.REGRESSION` · Category: comparison · Source: `run_v1 -> run_v2`
- Evidence: `{"metric": "eval_accuracy", "before": 0.71, "after": 0.66, "relative_change": -0.0704, "direction": "higher", "assessment": "regression", "changed_hyperparameters": ["epochs", "learning_rate"]}`
- Explanation: The metric moved in the worse direction beyond the tolerance (1%). Status reflects whether evaluation compatibility was verified.
- Recommendation: Investigate the changed hyperparameters/data; changes listed are candidates, not proven causes.
- How to confirm: Revert one changed setting at a time (same seed and eval set) and re-measure.

### DMI-003 · HIGH · CONFIRMED · Metric regressed: eval_loss

- Rule: `CMP.REGRESSION` · Category: comparison · Source: `run_v1 -> run_v2`
- Evidence: `{"metric": "eval_loss", "before": 1.2, "after": 1.34, "relative_change": 0.1167, "direction": "lower", "assessment": "regression", "changed_hyperparameters": ["epochs", "learning_rate"]}`
- Explanation: The metric moved in the worse direction beyond the tolerance (1%). Status reflects whether evaluation compatibility was verified.
- Recommendation: Investigate the changed hyperparameters/data; changes listed are candidates, not proven causes.
- How to confirm: Revert one changed setting at a time (same seed and eval set) and re-measure.

### DMI-004 · HIGH · CONFIRMED · Exact duplicate records (within this file)

- Rule: `DAT.EXACT_DUP` · Category: dataset · Source: `train.jsonl`
- Evidence: `{"duplicate_groups": 30, "extra_copies": 30, "rate": 0.1154, "largest_group_size": 2, "sample": "Harbor cheese moves research carrot kitchen paper honey yellow coffee study exp…"}`
- Explanation: Identical records after normalization. Within one split this is a quality issue (over-weighting, memorization), not evaluation leakage; it may be intentional upsampling.
- Recommendation: Deduplicate unless the repetition is a deliberate weighting choice.
- How to confirm: Train on the deduplicated set and compare validation loss and generation repetition.

### DMI-005 · HIGH · CONFIRMED · Degenerate repetition

- Rule: `GEN.REPETITION` · Category: generation · Source: `generations.jsonl`
- Evidence: `{"degenerate_responses": 30, "rate": 1.0, "mean_repetition_rate": 0.841483, "decoding_params": {"temperature": ["0.0"], "repetition_penalty": ["1.0"], "max_new_tokens": ["128"], "do_sample": ["False"]}, "sample": "I think that I think that I think that I think that I think that I think that I think that I think that I think that I …"}`
- Explanation: >=10% of responses repeat more than half of their word 3-grams (looping output).
- Recommendation: Try repetition_penalty 1.1-1.3, no_repeat_ngram_size, higher temperature/top-p; check SFT data for repetitive targets and EOS supervision.
- How to confirm: Re-generate the same prompts varying only one decoding parameter at a time.

### DMI-006 · HIGH · POTENTIAL · Near-duplicate evaluation records in training (test.jsonl)

- Rule: `LEK.NEAR` · Category: leakage · Source: `train.jsonl vs test.jsonl`
- Evidence: `{"split": "test.jsonl", "count": 5, "threshold_jaccard": 0.8, "examples_eval_to_train": [[12, 250, 0.9773], [13, 251, 0.9773], [14, 252, 0.9773]]}`
- Explanation: High shingle overlap with a training record; may be paraphrase-level leakage.
- Recommendation: Inspect pairs and exclude near copies from evaluation.
- How to confirm: Compare metrics with and without these records.

### DMI-007 · HIGH · CONFIRMED · Validation loss rises while training loss falls (overfitting pattern)

- Rule: `TRN.OVERFIT` · Category: training · Source: `overfitting.csv`
- Evidence: `{"best_val_step": 400.0, "best_val_loss": 1.10827, "final_val_loss": 1.48539, "relative_rise": 0.340278, "increases_after_best": 6, "train_slope_after_best": -0.006258}`
- Explanation: After its minimum, validation loss rose >=5% across repeated evaluations while training loss kept decreasing - the observable signature of overfitting.
- Recommendation: Use the checkpoint near step 400; add early stopping, regularization (dropout/weight decay), more or deduplicated data, or fewer epochs.
- How to confirm: Re-train with early stopping on eval_loss and compare held-out task metrics.

### DMI-008 · MEDIUM · CONFIRMED · Validation loss of 'after' run ends >5% above its best

- Rule: `CMP.LATE_DEGRADATION` · Category: comparison · Source: `run_v1 -> run_v2`
- Evidence: `{"run": "after", "best": 1.10827, "final": 1.48539, "best_step": 400.0}`
- Explanation: The final checkpoint is worse than an earlier one of the same run.
- Recommendation: Compare the best checkpoints, not the final ones; consider early stopping.

### DMI-009 · MEDIUM · POTENTIAL · Near-duplicate records

- Rule: `DAT.NEAR_DUP` · Category: dataset · Source: `train.jsonl`
- Evidence: `{"pairs": 10, "records_involved": 20, "threshold_jaccard": 0.8, "example_pair_indices": [[30, 230], [31, 231], [32, 232]]}`
- Explanation: Pairs with word 5-shingle Jaccard similarity >= threshold (MinHash/LSH, verified).
- Recommendation: Review examples; templated prompts can be legitimate, paraphrased copies usually are not.
- How to confirm: Inspect the listed pairs and deduplicate if they carry the same content.

### DMI-010 · MEDIUM · POTENTIAL · Low lexical diversity

- Rule: `GEN.LOW_DIVERSITY` · Category: generation · Source: `generations.jsonl`
- Evidence: `{"distinct_2": 0.092, "distinct_1": 0.0576, "mattr": 0.1119}`
- Explanation: Fewer than 30% of bigrams across outputs are unique.
- Recommendation: Compare with a reference corpus of similar length; adjust sampling.

### DMI-011 · MEDIUM · CONFIRMED · Responses cut by the token limit

- Rule: `GEN.TRUNCATED` · Category: generation · Source: `generations.jsonl`
- Evidence: `{"count": 15, "rate": 0.5}`
- Explanation: finish_reason == length or output tokens reached max_tokens.
- Recommendation: Raise max_new_tokens or investigate failure to emit EOS (often linked to repetition).

### DMI-012 · MEDIUM · POTENTIAL · Evaluation prompts seen in training with different answers (test.jsonl)

- Rule: `LEK.PROMPT` · Category: leakage · Source: `train.jsonl vs test.jsonl`
- Evidence: `{"split": "test.jsonl", "count": 3, "first_indices": [17, 18, 19]}`
- Explanation: The input side is identical to a training example while the target differs.
- Recommendation: Decide whether shared prompts are acceptable for this benchmark; usually remove them.

### DMI-013 · MEDIUM · POTENTIAL · Frequent byte-fallback tokens [english-bpe]

- Rule: `TOK.BYTE_FALLBACK` · Category: tokenizer · Source: `tokenizer_comparison.jsonl`
- Evidence: `{"byte_fallback_rate": 0.200677}`
- Explanation: Characters outside the vocabulary are spelled as raw bytes (common with accented characters when the tokenizer was trained on another language).
- Recommendation: Check which characters trigger fallback; consider vocabulary extension.

### DMI-014 · MEDIUM · POTENTIAL · High token fertility [english-bpe]

- Rule: `TOK.FERTILITY` · Category: tokenizer · Source: `tokenizer_comparison.jsonl`
- Evidence: `{"tokens_per_word": 3.9367, "threshold": 2.0, "fragmentation_rate": 0.8124}`
- Explanation: More than the threshold tokens per word on this text means each word costs several tokens, reducing effective context and raising compute per example.
- Recommendation: Compare against an alternative tokenizer on the same texts; consider vocabulary extension or a tokenizer trained on the target language.
- How to confirm: Tokenize the same sample with a candidate tokenizer and compare tokens_per_word.

### DMI-015 · MEDIUM · CONFIRMED · Sequences reach max length [english-bpe]

- Rule: `TOK.TRUNCATION` · Category: tokenizer · Source: `tokenizer_comparison.jsonl`
- Evidence: `{"truncation_rate": 0.9, "max_length": 64}`
- Explanation: These sequences are at or above max_length and will be (or were) truncated.
- Recommendation: Raise max_length, split long documents, or filter them.

### DMI-016 · LOW · POTENTIAL · Large unused context [portuguese-bpe]

- Rule: `TOK.CONTEXT_WASTE` · Category: tokenizer · Source: `tokenizer_comparison.jsonl`
- Evidence: `{"padding_rate": 0.0, "mean_unused_context": 0.6875}`
- Explanation: A large fraction of the context window is padding or unused.
- Recommendation: Use sequence packing or dynamic padding / bucketing by length.

### DMI-017 · INFO · CONFIRMED · Hyperparameters changed between runs

- Rule: `CMP.HP_CHANGES` · Category: comparison · Source: `run_v1 -> run_v2`
- Evidence: `{"epochs": {"before": 3, "after": 5, "changed": true}, "learning_rate": {"before": 2e-05, "after": 0.0001, "changed": true}}`
- Explanation: Several simultaneous changes prevent attributing an effect to any single one.
- Recommendation: Plan ablations that vary one setting at a time.

## 10. Recommended Experiments

1. (HYP-001) Re-compute evaluation metrics on the decontaminated subset and compare with the full set.
2. (HYP-002) Retrain after fixing the flagged data issues and compare on the same eval set.
3. (HYP-003) Enable early stopping on eval_loss or reduce epochs; compare held-out task metrics at the best step.
4. (HYP-004) Train on the deduplicated set; overfitting onset (best eval step) should move later.
5. (HYP-005) Ablate: revert each changed hyperparameter individually with a fixed seed.
6. (HYP-006) Fine-tune on the deduplicated/filtered dataset with identical settings and compare repetition rate.
7. (HYP-007) Re-generate the same prompts with repetition_penalty=1.15 or temperature=0.7 (one change at a time).
8. (HYP-008) Check that SFT targets end with the EOS token and that the chat template adds it; count EOS in labels.
9. (HYP-009) Tokenize the same texts with a language-appropriate tokenizer; compare tokens/word.
10. (DMI-001) Report metrics separately on the clean subset vs. the overlapping subset.
11. (DMI-002) Revert one changed setting at a time (same seed and eval set) and re-measure.
12. (DMI-004) Train on the deduplicated set and compare validation loss and generation repetition.
13. (DMI-005) Re-generate the same prompts varying only one decoding parameter at a time.
14. (DMI-006) Compare metrics with and without these records.
15. (DMI-007) Re-train with early stopping on eval_loss and compare held-out task metrics.
16. (DMI-009) Inspect the listed pairs and deduplicate if they carry the same content.
17. (DMI-014) Tokenize the same sample with a candidate tokenizer and compare tokens_per_word.

## 11. Evidence & Limitations

Statuses: CONFIRMED = rule satisfied by the data; POTENTIAL = indicators support a possible problem; INCONCLUSIVE = insufficient information. Hypotheses are never presented as confirmed causes.

- Compatibility unverified for: eval_protocol (not present in both configs).
- Contamination by 13-gram overlap ignores n-grams present in >= 1% of training records (and >= 5 records) to avoid flagging shared templates.
- Differences between configurations are associations; causality requires controlled re-runs.
- Grounding checks are lexical (content-word overlap and numbers vs. the provided reference); they do not prove factual correctness or detect hallucinations without references.
- Only lexical overlap is measured; paraphrased or translated contamination is not detected.
- Single-run differences do not establish statistical significance; repeat with several seeds.
