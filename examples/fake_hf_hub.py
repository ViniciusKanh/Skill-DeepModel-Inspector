"""Hub do Hugging Face SIMULADO (offline) para testes, demonstrações e capturas de tela.

Imita ``/api/models/{repo}`` e ``/{repo}/resolve/{rev}/{arquivo}`` (Range e redirecionamento
para "CDN"). Repositórios fictícios: ``good/chat-model``, ``bad/pickle-model``, ``gated/model``.
Não é o Hub real e não contém pesos de modelos reais.
"""

from __future__ import annotations

import json
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

SEEN: dict[str, Any] = {"auth": [], "paths": []}


def _st_file() -> bytes:
    header = {
        "model.embed.weight": {"dtype": "BF16", "shape": [1000, 64], "data_offsets": [0, 128000]},
        "model.layer.weight": {"dtype": "BF16", "shape": [64, 64], "data_offsets": [128000, 136192]},
        "__metadata__": {"format": "pt"},
    }
    raw = json.dumps(header).encode()
    return struct.pack("<Q", len(raw)) + raw + b"\0" * 136192


REPOS: dict[str, dict[str, Any]] = {
    "good/chat-model": {
        "info": {
            "id": "good/chat-model",
            "sha": "abc",
            "pipeline_tag": "text-generation",
            "library_name": "transformers",
            "tags": ["license:apache-2.0"],
            "cardData": {"license": "apache-2.0"},
            "siblings": [
                {"rfilename": n, "size": 10}
                for n in ("config.json", "tokenizer_config.json", "generation_config.json", "model.safetensors")
            ],
        },
        "files": {
            "config.json": {
                "architectures": ["LlamaForCausalLM"],
                "model_type": "llama",
                "num_hidden_layers": 2,
                "hidden_size": 64,
                "num_attention_heads": 4,
                "num_key_value_heads": 2,
                "vocab_size": 1000,
                "max_position_embeddings": 4096,
                "eos_token_id": 2,
            },
            "tokenizer_config.json": {
                "chat_template": "{{ messages }}",
                "eos_token": "</s>",
                "added_tokens_decoder": {"2": {"content": "</s>"}},
            },
            "generation_config.json": {"temperature": 0.7, "eos_token_id": 2},
            "model.safetensors": _st_file(),
        },
    },
    "bad/pickle-model": {
        "info": {
            "id": "bad/pickle-model",
            "pipeline_tag": "text-generation",
            "tags": ["custom_code"],
            "siblings": [{"rfilename": n} for n in ("config.json", "tokenizer_config.json", "pytorch_model.bin")],
        },
        "files": {
            "config.json": {"architectures": ["X"], "vocab_size": 100, "auto_map": {"AutoModel": "m.X"}},
            "tokenizer_config.json": {"added_tokens_decoder": {"150": {"content": "<x>"}}},
        },
    },
    "gated/model": {"status": 401},
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a: Any) -> None:  # silencioso
        pass

    def _send(self, code: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        SEEN["auth"].append((self.path, self.headers.get("Authorization")))
        path = self.path.split("?")[0]
        if path.startswith("/api/models/"):
            repo = REPOS.get(path[len("/api/models/") :])
            if repo is None:
                return self._send(404)
            if "status" in repo:
                return self._send(repo["status"])
            return self._send(200, json.dumps(repo["info"]).encode())
        if path.startswith("/cdn/"):
            data = REPOS["good/chat-model"]["files"]["model.safetensors"]
            rng = self.headers.get("Range", "")
            a, b = (int(x) for x in rng.split("=")[1].split("-"))
            return self._send(206, data[a : b + 1])
        if path.startswith("/evil/"):
            return self._send(302, headers={"Location": "http://evil.example/steal"})
        for rid, repo in REPOS.items():
            pre = f"/{rid}/resolve/main/"
            if path.startswith(pre) and "files" in repo:
                name = path[len(pre) :]
                if name == "model.safetensors":  # LFS: redirecionamento para "CDN"
                    return self._send(302, headers={"Location": "/cdn/model.safetensors"})
                if name in repo["files"]:
                    return self._send(200, json.dumps(repo["files"][name]).encode())
        return self._send(404)


def start(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Inicia o Hub simulado em 127.0.0.1 numa thread; devolve (servidor, url base)."""
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
