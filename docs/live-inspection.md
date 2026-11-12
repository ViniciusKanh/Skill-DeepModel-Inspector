# Live Model Inspection & Production Monitoring

DeepModel Inspector can inspect a **running model** — local or online — and monitor **production logs** over time.
The offline engine is unchanged; network access happens only when you explicitly run a probe against an endpoint you
registered.

## 1. Live inspection (Model Lab · `deepmodel probe`)

Any server exposing the **OpenAI-compatible** `POST /v1/chat/completions` API works:

| Server | Base URL (default) | Model example |
|---|---|---|
| Ollama | `http://localhost:11434/v1` | `llama3.1:8b` |
| LM Studio | `http://localhost:1234/v1` | name shown in LM Studio |
| llama.cpp `llama-server` | `http://localhost:8080/v1` | `default` |
| vLLM | `http://localhost:8000/v1` | `meta-llama/Llama-3.1-8B-Instruct` |
| OpenAI / compatible providers | `https://api.openai.com/v1` | `gpt-4o-mini` |

### What the probe suite measures

| Category | Probes | Check | Rule |
|---|---|---|---|
| Determinism | same prompt ×3 at temperature 0 | identical outputs | `PRB.NONDETERMINISM` (POTENTIAL) |
| Decoding behaviour | 6 open prompts × T=0.0 / T=0.8 | repetition, distinct-n, truncation | `GEN.*` + bootstrap config comparison |
| Instruction & format | JSON-only, word limits, Portuguese answers, exact list counts, number sequence | objective parser | `PRB.INSTRUCTION` |
| Closed answers | 6 questions with a single correct short answer | expected regex | `PRB.ACCURACY` |
| Context grounding | 4 questions answerable only from a given context | expected fact + lexical support | `PRB.GROUNDING` (POTENTIAL), `GEN.UNSUPPORTED` |
| Prompt injection | 3 documents with an embedded instruction to output a canary token | canary must not appear | `PRB.INJECTION` (HIGH) |
| Repetition stress | "list 40 different animals" | ≥ 30 unique lines | `PRB.REPETITION_STRESS` |
| Operational | every call | error rate, latency p50/p95, tokens/s (from reported usage) | `PRB.ERRORS`, `PRB.LATENCY`, `PRB.UNREACHABLE` |

`quick` ≈ 20 calls, `standard` ≈ 44 calls. You can add a **custom prompt file** (JSONL with `prompt`, optional
`expected` and `reference`) → `PRB.CUSTOM`.

Pass rates describe behaviour **on these probes only**; they are not benchmark scores. Root-cause hypotheses
(`RC.LIVE_*`) remain `POTENTIAL` and come with a confirmation experiment.

### CLI

```bash
deepmodel probe --base-url http://localhost:11434/v1 --model llama3.1:8b --suite standard --format html -o probe.html
# Online endpoint: key read from an environment variable; explicit consent flag required
set OPENAI_API_KEY=...            # PowerShell: $env:OPENAI_API_KEY="..."
deepmodel probe --base-url https://api.openai.com/v1 --model gpt-4o-mini --api-key-env OPENAI_API_KEY --allow-remote
```

### App (Model Lab)
1. **Connect a model** wizard: *On this computer* (auto-detects Ollama, LM Studio, llama.cpp, vLLM, Jan,
   text-generation-webui and lists their models) or *Online service* (OpenAI, Anthropic, Gemini, Groq, OpenRouter,
   Mistral, Azure, custom) → **Load models** → **Connect & test**. API keys stay in memory (or name an environment
   variable). Online endpoints require ticking the consent box. Manual registration is under *Advanced*.
2. **Test connection** → latency, reply and whether the model is listed by `/models`.
3. **Inspect** → live console (one line per request: PASS/FAIL/ERR, latency, detail), real progress, cancel.
4. Results: scorecard, latency chart, findings, hypotheses, **Ask the inspector**, full probe transcript, JSON/MD/HTML export.
5. **Simulated demo** starts a local scripted server (`examples/fake_llm_server.py`) with a flawed and a healthy
   model — clearly labelled **SIMULATED**; the analyses are real.

## 2. Production monitoring (Production Monitor · `deepmodel monitor`)

Export logs as JSONL/CSV (one file per day/week, or a `timestamp` field):

```json
{"timestamp": "2026-10-26T09:00:00Z", "prompt": "...", "output": "...", "latency_ms": 840, "finish_reason": "stop", "error": null, "model": "prod-v1"}
```

Per period the engine computes requests, error rate, empty/degenerate/truncated rates, distinct-2, mean repetition and
latency p50/p95, then evaluates the latest period:

| Rule | Condition (defaults, configurable) |
|---|---|
| `MON.ERRORS` | error rate > 5% |
| `MON.REPETITION` | degenerate responses > 10% |
| `MON.EMPTY` / `MON.TRUNCATION` | > 5% / > 10% |
| `MON.LATENCY` | p95 > 10,000 ms |
| `MON.DRIFT_REPETITION` | bootstrap 95% CI of repetition vs. previous periods > 0 (POTENTIAL) |
| `MON.DIVERSITY_DROP` | distinct-2 drops > 25% vs. baseline (POTENTIAL) |

```bash
deepmodel monitor --input ./prod_logs --period week --fail-on HIGH   # exit code 4 when HIGH+ alerts exist
```

Schedule it (Windows Task Scheduler / cron) and use the exit code for alerting. The app's **Model health history**
plots every Model Lab inspection of a model over time (pass rates and latency).

### Troubleshooting local models
- `dial tcp 127.0.0.1:11434 ... refused` / "Nothing is listening at this address": the Ollama server is not running.
  Open the Ollama app (tray icon) or run `ollama serve` in another terminal, then `ollama pull llama3.2`.
- Model not listed: pull it first (`ollama pull <model>`) and press **Scan again**.

## 2b. Hugging Face models (no download)

`deepmodel hub --repo owner/name` (or Model Lab → *Hugging Face model* → **Inspect files**) reads only metadata:
Hub API, `config.json`, `tokenizer_config.json`, `generation_config.json` and the JSON header of each `.safetensors`
file (HTTP Range, a few KB). It reports parameters, memory for fp16/int8/4-bit weights, context length, KV-cache
size, chat template, EOS, license, gated status and security risks (pickle-only weights, `trust_remote_code`).
Public repos need **no token**; private/gated repos need a read token (`HF_TOKEN` env var or kept in memory in the app).

Behaviour (quality, injection, hallucination) can't be measured from files. Options:
- run it locally (Ollama / LM Studio / llama.cpp — GGUF builds exist for most popular models), or
- **HF Inference Providers** (`https://router.huggingface.co/v1`, OpenAI-compatible, free HF account token with
  monthly credits; availability per model varies) → then INSPECT as any online model.

Why OpenAI / Gemini / Groq need a key: the model runs on the provider's GPUs; the key identifies who pays. There is no
key-free way to call them. Local models and HF metadata inspection are free and key-free.

Not validated against the real Hub in the development sandbox (no access); tests use a local Hub simulator.

## 3. Security & privacy
- Only http(s) URLs; **redirects are blocked** (the API key can't be forwarded to another host).
- API keys are **never written to disk** by the app (memory only) — or read from an environment variable you name.
- Remote endpoints require explicit consent (`--allow-remote` / checkbox). Only probe prompts (and custom prompt files
  you select) are sent; datasets and logs are never uploaded.
- Model responses are treated as data: escaped in HTML, never executed.

## 4. Limitations
- Batch, not real-time: no streaming ingestion, no request-level tracing integration (OpenTelemetry/Langfuse) yet.
- The suite is small and generic; for domain quality add a custom prompt file with expected answers or references.
- Latency includes network and server queueing; tokens/s depends on the server reporting `usage`.
- Non-OpenAI-compatible APIs (e.g. native Anthropic/Gemini SDK formats) are not supported directly — use a compatible
  gateway.
