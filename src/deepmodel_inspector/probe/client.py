"""Cliente HTTP mínimo (biblioteca padrão) para APIs de chat compatíveis com OpenAI.

Funciona com modelos locais (Ollama ``/v1``, LM Studio, llama.cpp server, vLLM, TGI) e
online (OpenAI ou provedores compatíveis). É acionado somente quando o usuário executa
explicitamente uma sondagem: o motor de análise continua offline por padrão.

Segurança: só http/https; redirecionamentos bloqueados (evita vazar a chave para outro
host); chave nunca é registrada em logs nem gravada em disco por este módulo; respostas
são tratadas apenas como dados.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Bloqueia redirecionamentos HTTP."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        return None


@dataclass
class Target:
    """Modelo a inspecionar (endpoint compatível com OpenAI)."""

    base_url: str
    model: str
    api_key: str | None = None
    timeout: float = 60.0
    extra_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        u = urlparse(self.base_url)
        if u.scheme not in ("http", "https") or not u.netloc:
            raise ValueError("base_url must be an http(s) URL, e.g. http://localhost:11434/v1")
        if not self.model.strip():
            raise ValueError("model name is required")
        self.base_url = self.base_url.rstrip("/")

    @property
    def is_local(self) -> bool:
        """Indica se o endpoint está na própria máquina."""
        return (urlparse(self.base_url).hostname or "") in LOCAL_HOSTS

    @property
    def host(self) -> str:
        return urlparse(self.base_url).netloc


def chat(target: Target, messages: list[dict[str, str]], params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Envia uma requisição ``/chat/completions`` e devolve texto, latência, uso e erro (sem lançar)."""
    body: dict[str, Any] = {"model": target.model, "messages": messages, "stream": False}
    for k, v in (params or {}).items():
        if v is not None and k in (
            "temperature",
            "top_p",
            "max_tokens",
            "seed",
            "frequency_penalty",
            "presence_penalty",
            "stop",
        ):
            body[k] = v
    headers = {"Content-Type": "application/json", "Accept": "application/json", **target.extra_headers}
    if target.api_key:
        headers["Authorization"] = f"Bearer {target.api_key}"
    req = urllib.request.Request(
        f"{target.base_url}/chat/completions", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    opener = urllib.request.build_opener(_NoRedirect)
    t0 = time.perf_counter()
    out: dict[str, Any] = {
        "text": "",
        "finish_reason": None,
        "latency_ms": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "error": None,
    }
    try:
        with opener.open(req, timeout=target.timeout) as resp:
            raw = resp.read(8 * 2**20)
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        data = json.loads(raw.decode("utf-8", errors="replace"))
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        out["text"] = str(msg.get("content") or choice.get("text") or "")
        out["finish_reason"] = choice.get("finish_reason")
        usage = data.get("usage") or {}
        out["prompt_tokens"] = usage.get("prompt_tokens")
        out["completion_tokens"] = usage.get("completion_tokens")
    except urllib.error.HTTPError as exc:
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        detail = exc.read(400).decode("utf-8", errors="replace") if exc.fp else ""
        out["error"] = f"HTTP {exc.code}: {detail[:200]}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        out["error"] = f"connection error: {getattr(exc, 'reason', exc)}"[:240]
    except (ValueError, KeyError, IndexError, AttributeError) as exc:
        out["error"] = f"invalid response: {exc}"[:240]
    return out


def list_models(target: Target) -> list[str]:
    """Lista modelos via ``GET /models`` (útil para validar a conexão)."""
    headers = {"Accept": "application/json", **target.extra_headers}
    if target.api_key:
        headers["Authorization"] = f"Bearer {target.api_key}"
    req = urllib.request.Request(f"{target.base_url}/models", headers=headers)
    with urllib.request.build_opener(_NoRedirect).open(req, timeout=min(target.timeout, 15)) as resp:
        data = json.loads(resp.read(2 * 2**20).decode("utf-8", errors="replace"))
    return [str(m.get("id")) for m in data.get("data", []) if isinstance(m, dict)]
