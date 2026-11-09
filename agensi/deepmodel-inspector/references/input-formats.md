# Input formats accepted by DeepModel Inspector

All inputs are read-only. Encodings: UTF-8 (BOM accepted). Default limit 200 MB per file (`--max-mb`), 200,000 records (`--max-records`).

## Training logs (`dmi_training.py --input`)

CSV (one row per logging step):

```csv
step,epoch,loss,eval_loss,learning_rate,grad_norm
10,0.02,2.41,,3e-05,1.02
100,0.2,1.80,1.95,2.9e-04,0.98
```

JSONL with the same keys, or Hugging Face `trainer_state.json` (its `log_history` list is used; train and eval rows are merged by step).
Empty cells are missing values; `nan`/`inf` are kept and reported as non-finite.

## Datasets (`dmi_dataset.py`, `dmi_leakage.py`)

```jsonl
{"text": "plain pre-training document"}
{"instruction": "Summarize ...", "input": "", "output": "..."}
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
{"prompt": "...", "completion": "..."}
```

CSV: pass `--text-field <column>`. TXT: one record per line. Name split files with `train`, `val`/`valid`/`dev`, `test`/`eval`.

## Tokenizations (`dmi_tokenizer.py`)

```jsonl
{"text": "A informação é processada", "tokens": ["ĠA", "Ġinform", "a", "<0xC3>", "<0xA7>", "ão"], "tokenizer": "english-bpe"}
{"text": "A informação é processada", "token_ids": [32, 4521, 64], "tokenizer": "pt-bpe"}
```

Produce it with your own tokenizer, e.g. in Python: `{"text": t, "tokens": tok.tokenize(t), "token_ids": tok.encode(t)}`.
Options: `--max-length`, `--unk-token`/`--unk-id`, `--pad-token`/`--pad-id`, `--vocab-size`.

## Generations (`dmi_generation.py`)

```jsonl
{"prompt": "...", "output": "...", "config": "greedy", "temperature": 0.0, "top_p": 1.0, "repetition_penalty": 1.0, "max_new_tokens": 256, "finish_reason": "length", "reference": "optional source text for grounding checks"}
```

## Runs (`dmi_compare.py --before DIR --after DIR`)

Each run directory may contain `config.json` / `training_args.json` / `adapter_config.json` (hyperparameters and,
ideally, `tokenizer`, `vocab_size`, `eval_dataset`, `eval_protocol`), `metrics.json` / `eval_results.json`
(flat numeric metrics) and a loss log or `trainer_state.json`. A single log file per run is also accepted.

## Checkpoints (`dmi_checkpoint.py --input DIR`)

`.safetensors` (header only), `config.json`, `tokenizer_config.json`, `adapter_config.json`, `generation_config.json`.
Pickle formats are never opened.
