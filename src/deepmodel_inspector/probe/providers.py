"""Catálogo de provedores e descoberta automática de servidores LLM locais.

Facilita a conexão para usuários não técnicos: detecta Ollama, LM Studio, llama.cpp,
vLLM, Jan e text-generation-webui na própria máquina e lista os modelos disponíveis.
As URLs dos provedores online seguem os endpoints compatíveis com OpenAI documentados
por cada fornecedor (verifique a documentação do provedor em caso de mudança).
"""

from __future__ import annotations

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from deepmodel_inspector.probe.client import Target, _NoRedirect, list_models

LOCAL_SERVERS: list[dict[str, Any]] = [
    {
        "id": "ollama",
        "label": "Ollama",
        "port": 11434,
        "base_url": "http://127.0.0.1:11434/v1",
        "help": "Install from ollama.com, open the Ollama app (or run `ollama serve`), then `ollama pull llama3.2`.",
    },
    {
        "id": "lmstudio",
        "label": "LM Studio",
        "port": 1234,
        "base_url": "http://127.0.0.1:1234/v1",
        "help": "In LM Studio open the Developer tab, load a model and press Start Server.",
    },
    {
        "id": "llamacpp",
        "label": "llama.cpp server",
        "port": 8080,
        "base_url": "http://127.0.0.1:8080/v1",
        "help": "Run `llama-server -m model.gguf --port 8080`.",
    },
    {
        "id": "vllm",
        "label": "vLLM",
        "port": 8000,
        "base_url": "http://127.0.0.1:8000/v1",
        "help": "Run `vllm serve <model>` (Linux/WSL with GPU).",
    },
    {
        "id": "jan",
        "label": "Jan",
        "port": 1337,
        "base_url": "http://127.0.0.1:1337/v1",
        "help": "In Jan enable the Local API Server in Settings.",
    },
    {
        "id": "textgen",
        "label": "text-generation-webui",
        "port": 5000,
        "base_url": "http://127.0.0.1:5000/v1",
        "help": "Start with the `--api` flag.",
    },
]

ONLINE_PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "key_hint": "sk-…",
        "key_url": "https://platform.openai.com/api-keys",
        "example_model": "gpt-4o-mini",
    },
    {
        "id": "anthropic",
        "label": "Anthropic (OpenAI-compatible endpoint)",
        "base_url": "https://api.anthropic.com/v1",
        "key_hint": "sk-ant-…",
        "key_url": "https://console.anthropic.com/settings/keys",
        "example_model": "claude-sonnet-4-5",
    },
    {
        "id": "gemini",
        "label": "Google Gemini (OpenAI-compatible endpoint)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_hint": "AIza…",
        "key_url": "https://aistudio.google.com/apikey",
        "example_model": "gemini-2.0-flash",
    },
    {
        "id": "groq",
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key_hint": "gsk_…",
        "key_url": "https://console.groq.com/keys",
        "example_model": "llama-3.1-8b-instant",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "key_hint": "sk-or-…",
        "key_url": "https://openrouter.ai/keys",
        "example_model": "meta-llama/llama-3.1-8b-instruct",
    },
    {
        "id": "mistral",
        "label": "Mistral AI",
        "base_url": "https://api.mistral.ai/v1",
        "key_hint": "…",
        "key_url": "https://console.mistral.ai/api-keys",
        "example_model": "mistral-small-latest",
    },
    {
        "id": "azure",
        "label": "Azure OpenAI (v1 endpoint)",
        "base_url": "https://<resource>.openai.azure.com/openai/v1",
        "key_hint": "Azure key",
        "key_url": "https://portal.azure.com",
        "example_model": "<deployment name>",
    },
    {
        "id": "huggingface",
        "label": "Hugging Face (Inference Providers)",
        "base_url": "https://router.huggingface.co/v1",
        "key_hint": "hf_… (free account token)",
        "key_url": "https://huggingface.co/settings/tokens",
        "example_model": "meta-llama/Llama-3.1-8B-Instruct",
    },
    {
        "id": "custom",
        "label": "Other OpenAI-compatible API",
        "base_url": "",
        "key_hint": "API key",
        "key_url": "",
        "example_model": "",
    },
]


def _ollama_native(port: int, timeout: float) -> list[str]:
    """Fallback: ``/api/tags`` do Ollama (quando ``/v1/models`` não responde)."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/tags", headers={"Accept": "application/json"})
    with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as resp:
        data = json.loads(resp.read(2 * 2**20).decode("utf-8", errors="replace"))
    return [str(m.get("name")) for m in data.get("models", []) if isinstance(m, dict)]


def _check(server: dict[str, Any], timeout: float) -> dict[str, Any]:
    out = {**server, "running": False, "models": [], "error": None}
    try:
        out["models"] = list_models(Target(server["base_url"], "probe", None, timeout))
        out["running"] = True
    except Exception as exc:  # noqa: BLE001 - servidor ausente é o caso normal
        out["error"] = type(exc).__name__
        if server["id"] == "ollama":
            try:
                out["models"] = _ollama_native(server["port"], timeout)
                out["running"] = True
                out["error"] = None
            except Exception:  # noqa: BLE001
                pass
    return out


def discover(servers: list[dict[str, Any]] | None = None, timeout: float = 1.0) -> list[dict[str, Any]]:
    """Verifica em paralelo os servidores locais conhecidos (somente 127.0.0.1)."""
    servers = servers or LOCAL_SERVERS
    with ThreadPoolExecutor(max_workers=len(servers)) as ex:
        return list(ex.map(lambda s: _check(s, timeout), servers))
