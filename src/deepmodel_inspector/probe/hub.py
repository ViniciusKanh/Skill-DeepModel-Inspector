"""Inspeção de modelos do Hugging Face Hub SEM baixar os pesos (regras HUB.*).

Lê apenas metadados: API do Hub, ``config.json``, ``tokenizer_config.json``,
``generation_config.json`` e, quando necessário, o cabeçalho JSON dos ``.safetensors``
via requisições HTTP Range (alguns KB). Nenhum peso é baixado nem desserializado.

Segurança: só HTTPS (exceto testes locais), redirecionamentos seguidos manualmente
apenas para hosts do Hub/CDN e o token NUNCA é enviado a outro host.
"""

from __future__ import annotations

import json
import re
import struct
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urljoin, urlparse

from deepmodel_inspector.core.common import finding, result, rnd
from deepmodel_inspector.probe.client import _NoRedirect

HUB = "https://huggingface.co"
ALLOWED_SUFFIXES = ("huggingface.co", "hf.co")
REPO_RX = re.compile(r"^[A-Za-z0-9][\w.-]{0,95}(/[\w.-]{1,96})?$")
PICKLE_EXT = (".bin", ".pt", ".pth", ".ckpt", ".pkl")
DTYPE_BYTES = {
    "F64": 8,
    "F32": 4,
    "BF16": 2,
    "F16": 2,
    "F8_E4M3": 1,
    "F8_E5M2": 1,
    "I64": 8,
    "I32": 4,
    "I16": 2,
    "I8": 1,
    "U8": 1,
    "BOOL": 1,
}


class HubError(Exception):
    """Erro de acesso ao Hub (repositório inexistente, privado, protegido ou rede)."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _host_ok(url: str, hub: str) -> bool:
    h = urlparse(url).hostname or ""
    return h == urlparse(hub).hostname or any(h == s or h.endswith("." + s) for s in ALLOWED_SUFFIXES)


def _get(
    url: str,
    hub: str,
    token: str | None,
    headers: dict[str, str] | None = None,
    limit: int = 4 * 2**20,
    timeout: float = 20.0,
) -> bytes:
    """GET com redirecionamentos manuais restritos ao Hub/CDN; o token só vai ao host do Hub."""
    hub_host = urlparse(hub).hostname
    for _ in range(6):
        if not _host_ok(url, hub):
            raise HubError(0, f"refusing redirect to non-Hub host: {urlparse(url).hostname}")
        h = {"User-Agent": "deepmodel-inspector", **(headers or {})}
        if token and urlparse(url).hostname == hub_host:
            h["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=h)
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as resp:
                return resp.read(limit)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                url = urljoin(url, exc.headers["Location"])
                continue
            raise HubError(exc.code, f"HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HubError(0, f"network error: {getattr(exc, 'reason', exc)}") from None
    raise HubError(0, "too many redirects")


def _json(url: str, hub: str, token: str | None) -> dict[str, Any] | None:
    try:
        data = json.loads(_get(url, hub, token).decode("utf-8", errors="replace"))
        return data if isinstance(data, dict) else None
    except HubError as exc:
        if exc.code == 404:
            return None
        raise
    except ValueError:
        return None


def _safetensors_header(url: str, hub: str, token: str | None) -> dict[str, Any]:
    head = _get(url, hub, token, {"Range": "bytes=0-7"}, limit=8)
    (n,) = struct.unpack("<Q", head[:8])
    if not 0 < n < 50 * 2**20:
        raise HubError(0, "invalid safetensors header length")
    raw = _get(url, hub, token, {"Range": f"bytes=8-{7 + n}"}, limit=n)
    return json.loads(raw.decode("utf-8"))


def fetch(repo_id: str, token: str | None = None, revision: str = "main", hub: str = HUB) -> dict[str, Any]:
    """Coleta metadados do repositório (sem pesos)."""
    if not REPO_RX.match(repo_id) or ".." in repo_id:
        raise ValueError("invalid repository id, expected e.g. 'Qwen/Qwen2.5-0.5B-Instruct'")
    if not re.match(r"^[\w.-]{1,64}$", revision):
        raise ValueError("invalid revision")
    hub = hub.rstrip("/")
    try:
        info = json.loads(_get(f"{hub}/api/models/{repo_id}?blobs=true", hub, token).decode("utf-8", errors="replace"))
    except HubError as exc:
        if exc.code in (401, 403):
            raise HubError(
                exc.code, "repository is private or gated: accept the license on the Hub and provide a token"
            ) from None
        if exc.code == 404:
            raise HubError(404, "repository not found (check the id, or it may be private)") from None
        raise

    def file(name: str) -> dict[str, Any] | None:
        return _json(f"{hub}/{repo_id}/resolve/{revision}/{name}", hub, token)

    files = [s for s in info.get("siblings", []) if isinstance(s, dict)]
    names = [s.get("rfilename", "") for s in files]
    out = {
        "info": info,
        "config": file("config.json") if "config.json" in names else None,
        "tokenizer_config": file("tokenizer_config.json") if "tokenizer_config.json" in names else None,
        "generation_config": file("generation_config.json") if "generation_config.json" in names else None,
        "files": files,
        "headers": {},
    }
    if not (info.get("safetensors") or {}).get("parameters"):
        for name in [n for n in names if n.endswith(".safetensors")][:8]:
            try:
                out["headers"][name] = _safetensors_header(f"{hub}/{repo_id}/resolve/{revision}/{name}", hub, token)
            except (HubError, ValueError, struct.error):
                continue
    return out


def analyze(repo_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Aplica as regras HUB.* aos metadados coletados."""
    info, cfg = meta["info"], meta.get("config") or {}
    tok, gen = meta.get("tokenizer_config") or {}, meta.get("generation_config") or {}
    src = f"hf:{repo_id}"
    F: list[dict[str, Any]] = []
    lim = [
        "Only metadata and safetensors headers were read; behaviour requires a live probe "
        "(e.g. through Hugging Face Inference Providers) or a local run.",
        "Memory estimates cover weights only (no activations, framework overhead or batching).",
    ]
    tcfg = cfg.get("text_config") if isinstance(cfg.get("text_config"), dict) else {}
    c = {**tcfg, **{k: v for k, v in cfg.items() if not isinstance(v, dict)}}
    params: dict[str, int] = dict((info.get("safetensors") or {}).get("parameters") or {})
    if not params:
        for h in meta.get("headers", {}).values():
            for k, v in h.items():
                if k == "__metadata__" or not isinstance(v, dict):
                    continue
                n = 1
                for d in v.get("shape", []):
                    n *= int(d)
                params[v.get("dtype", "?")] = params.get(v.get("dtype", "?"), 0) + n
    total = sum(params.values())
    names = [f.get("rfilename", "") for f in meta.get("files", [])]
    sizes = {f.get("rfilename", ""): f.get("size") for f in meta.get("files", [])}
    st = [n for n in names if n.endswith(".safetensors")]
    pk = [n for n in names if n.endswith(PICKLE_EXT) and ("model" in n or "pytorch" in n)]
    gguf = [n for n in names if n.endswith(".gguf")]
    layers = c.get("num_hidden_layers") or c.get("n_layer") or c.get("num_layers")
    hidden = c.get("hidden_size") or c.get("n_embd") or c.get("d_model")
    heads = c.get("num_attention_heads") or c.get("n_head")
    kv = c.get("num_key_value_heads") or heads
    ctx = c.get("max_position_embeddings") or c.get("n_positions") or c.get("max_seq_len") or c.get("seq_length")
    head_dim = c.get("head_dim") or (hidden // heads if hidden and heads else None)
    kv_tok = 2 * layers * kv * head_dim * 2 if layers and kv and head_dim else None
    license_ = (info.get("cardData") or {}).get("license") or next(
        (t.split(":", 1)[1] for t in info.get("tags", []) if str(t).startswith("license:")), None
    )
    stored = sum(DTYPE_BYTES.get(d, 2) * n for d, n in params.items())
    metrics: dict[str, Any] = {
        "repo_id": repo_id,
        "sha": info.get("sha"),
        "pipeline_tag": info.get("pipeline_tag"),
        "library": info.get("library_name"),
        "license": license_,
        "gated": info.get("gated"),
        "downloads": info.get("downloads"),
        "likes": info.get("likes"),
        "architecture": (cfg.get("architectures") or [None])[0],
        "model_type": cfg.get("model_type"),
        "parameters_total": total or None,
        "parameters_by_dtype": params,
        "torch_dtype": c.get("torch_dtype"),
        "layers": layers,
        "hidden_size": hidden,
        "attention_heads": heads,
        "kv_heads": kv,
        "head_dim": head_dim,
        "vocab_size": c.get("vocab_size"),
        "context_length": ctx,
        "rope_scaling": c.get("rope_scaling"),
        "tie_word_embeddings": c.get("tie_word_embeddings"),
        "weights_files": {"safetensors": len(st), "pickle": len(pk), "gguf": len(gguf)},
        "weights_size_gb": rnd(sum((sizes.get(n) or 0) for n in st + pk) / 1e9, 2)
        if any(sizes.get(n) for n in st + pk)
        else None,
        "memory_gb": {
            "stored_dtype": rnd(stored / 1e9, 4),
            "fp16": rnd(total * 2 / 1e9, 4),
            "int8": rnd(total / 1e9, 4),
            "int4": rnd(total * 0.5 / 1e9, 4),
        }
        if total
        else None,
        "kv_cache_mb_per_1k_tokens": rnd(kv_tok * 1000 / 2**20, 1) if kv_tok else None,
        "kv_cache_gb_full_context": rnd(kv_tok * ctx / 2**30, 4) if kv_tok and ctx else None,
        "chat_template": bool(tok.get("chat_template")),
        "eos_token": tok.get("eos_token") or gen.get("eos_token_id"),
        "tokenizer_max_length": tok.get("model_max_length")
        if isinstance(tok.get("model_max_length"), int) and tok.get("model_max_length") < 10**9
        else None,
        "generation_defaults": {
            k: gen.get(k) for k in ("temperature", "top_p", "top_k", "repetition_penalty", "max_new_tokens") if k in gen
        },
    }
    if pk and not st:
        F.append(
            finding(
                "HUB.PICKLE_ONLY",
                "hub",
                "HIGH",
                "CONFIRMED",
                "Weights only in pickle format",
                {"files": pk[:5]},
                src,
                "Loading .bin/.pt/.ckpt files executes Python pickle code; a "
                "malicious file can run arbitrary code on your machine.",
                "Prefer a safetensors revision or a trusted conversion; load in a sandbox if unavoidable.",
            )
        )
    if cfg.get("auto_map") or "custom_code" in info.get("tags", []):
        F.append(
            finding(
                "HUB.REMOTE_CODE",
                "hub",
                "MEDIUM",
                "CONFIRMED",
                "Requires trust_remote_code",
                {"auto_map": list((cfg.get("auto_map") or {}).keys())[:6]},
                src,
                "The model ships custom Python code that runs when loaded with trust_remote_code=True.",
                "Review the repository code (pin a revision) before loading it.",
            )
        )
    added = tok.get("added_tokens_decoder") or {}
    max_id = max((int(k) for k in added if str(k).isdigit()), default=-1)
    if c.get("vocab_size") and max_id >= int(c["vocab_size"]):
        F.append(
            finding(
                "HUB.VOCAB_MISMATCH",
                "hub",
                "HIGH",
                "CONFIRMED",
                "Tokenizer has token ids beyond the embedding size",
                {"vocab_size": c["vocab_size"], "max_added_token_id": max_id},
                src,
                "Some special tokens map to ids outside the embedding matrix; using them causes errors or garbage.",
                "Resize embeddings or use the matching tokenizer revision.",
            )
        )
    textgen = info.get("pipeline_tag") in ("text-generation", "image-text-to-text", None)
    if textgen and meta.get("tokenizer_config") is not None and not tok.get("chat_template"):
        F.append(
            finding(
                "HUB.NO_CHAT_TEMPLATE",
                "hub",
                "MEDIUM",
                "POTENTIAL",
                "No chat template in tokenizer_config.json",
                {"pipeline_tag": info.get("pipeline_tag")},
                src,
                "Chat/instruct servers rely on the chat template to format messages; without it, conversations "
                "may be formatted wrongly (often a base model, which is fine for completion use).",
                "Use the instruct variant or supply the official template; verify with a live probe.",
            )
        )
    if textgen and meta.get("config") is not None and not metrics["eos_token"] and not c.get("eos_token_id"):
        F.append(
            finding(
                "HUB.NO_EOS",
                "hub",
                "MEDIUM",
                "POTENTIAL",
                "End-of-sequence token not declared",
                {},
                src,
                "Without an EOS token, generation may not stop and run to the token limit (repetition).",
                "Set eos_token_id in generation_config.json; check with the probe's truncation/repetition rules.",
            )
        )
    if not license_:
        F.append(
            finding(
                "HUB.NO_LICENSE",
                "hub",
                "LOW",
                "CONFIRMED",
                "No license declared",
                {},
                src,
                "The repository does not declare a license; commercial use rights are unclear.",
                "Check the model card or contact the authors before commercial use.",
            )
        )
    if info.get("gated"):
        F.append(
            finding(
                "HUB.GATED",
                "hub",
                "INFO",
                "CONFIRMED",
                "Gated model (license acceptance required)",
                {"gated": info.get("gated")},
                src,
                "Downloads and inference require accepting terms on the Hub.",
                "Accept the terms on huggingface.co and use a token.",
            )
        )
    if total:
        F.append(
            finding(
                "HUB.FOOTPRINT",
                "hub",
                "INFO",
                "CONFIRMED",
                "Size and memory footprint",
                {
                    "parameters": total,
                    "memory_gb": metrics["memory_gb"],
                    "context_length": ctx,
                    "kv_cache_gb_full_context": metrics["kv_cache_gb_full_context"],
                },
                src,
                "Computed from safetensors parameter counts and config (weights only).",
                "Pick a quantization that fits your GPU/CPU memory with room for the KV cache.",
            )
        )
    if not st and not pk and not gguf:
        F.append(
            finding(
                "HUB.NO_WEIGHTS",
                "hub",
                "INFO",
                "INCONCLUSIVE",
                "No weight files found in the repository",
                {"files": names[:10]},
                src,
                "This may be an adapter, a dataset-like repo or weights stored elsewhere.",
                "Check adapter_config.json / the model card.",
            )
        )
    return result("hub", src, metrics, F, lim)


def inspect(repo_id: str, token: str | None = None, revision: str = "main", hub: str = HUB) -> dict[str, Any]:
    """Coleta + análise em uma chamada."""
    return analyze(repo_id, fetch(repo_id, token, revision, hub))
