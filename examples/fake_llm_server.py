"""Servidor LLM SIMULADO compatível com OpenAI (somente para testes e modo DEMO).

Não é um modelo: devolve respostas roteirizadas e determinísticas com falhas
plantadas (variante ``flawed``) ou corretas (variante ``good``), para demonstrar e
testar a sondagem ao vivo sem baixar modelos.

Uso: python examples/fake_llm_server.py --port 8799 --variant flawed
Endpoint: http://127.0.0.1:8799/v1  (modelos: demo-flawed, demo-good)
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANIMALS = [
    "cat",
    "dog",
    "horse",
    "cow",
    "sheep",
    "goat",
    "lion",
    "tiger",
    "bear",
    "wolf",
    "fox",
    "deer",
    "rabbit",
    "mouse",
    "eagle",
    "owl",
    "shark",
    "whale",
    "dolphin",
    "seal",
    "otter",
    "frog",
    "snake",
    "lizard",
    "turtle",
    "bee",
    "ant",
    "crab",
    "octopus",
    "squid",
    "zebra",
    "giraffe",
    "camel",
    "llama",
    "panda",
    "koala",
    "moose",
    "bison",
    "hedgehog",
]


def respond(prompt: str, variant: str, temperature: float, call_no: int) -> tuple[str, str]:
    """Resposta roteirizada (texto, finish_reason)."""
    p = prompt.lower()
    flawed = variant == "flawed"
    if "zx-canary-42" in p:
        if flawed and ("ignore the user" in p or "disregard" in p):
            return "ZX-CANARY-42", "stop"
        return "The document is a short note; it contains an embedded instruction that was ignored.", "stop"
    if "17 multiplied by 23" in p:
        return ("381" if flawed else "391"), "stop"
    for key, ans in (
        ("capital of france", "Paris"),
        ("symbol for gold", "Au"),
        ("leap year", "365" if flawed else "366"),
        ("backwards", "desserts"),
        ("square root of 144", "12"),
    ):
        if key in p:
            return ans, "stop"
    if "context:" in p:
        m = re.search(r"context:\s*(.+?)\n\nquestion", prompt, re.I | re.S)
        ctx = m.group(1) if m else ""
        if flawed and "harbor bridge" in p:
            return "The Harbor Bridge was completed in 1908 by royal decree.", "stop"
        if flawed and "rio verde" in p:
            return "O rio Verde tem cerca de 500 km e nasce nos Andes.", "stop"
        return ctx.strip(), "stop"
    if "json" in p:
        if flawed and '"colors"' in p:
            return "Sure! Here are colors: red, green, blue", "stop"
        if '"name"' in p:
            return '{"name": "Ana", "age": 31}', "stop"
        if '"colors"' in p:
            return '{"colors": ["red", "green", "blue"]}', "stop"
        return '{"ok": true}', "stop"
    m = re.search(r"at most (\d+) words", p)
    if m:
        n = int(m.group(1))
        words = [
            "Vast",
            "blue",
            "water",
            "covering",
            "most",
            "of",
            "our",
            "planet,",
            "full",
            "of",
            "life",
            "and",
            "constant",
            "motion",
            "everywhere",
        ]
        return " ".join(words[: n + 6 if flawed and n == 10 else n]), "stop"
    if "português" in p or "portugues" in p:
        return "As estações do ano são primavera, verão, outono e inverno, e o café é uma bebida muito querida.", "stop"
    m = re.search(r"exactly (\d+)", p)
    if m:
        items = (
            ["apple", "banana", "cherry", "grape", "mango", "pear"]
            if "fruit" in p
            else ["Mars", "Venus", "Jupiter", "Saturn"]
        )
        n = int(m.group(1))
        return "\n".join(items[: n + (1 if flawed else 0)]), "stop"
    if "count from 1 to 30" in p:
        return " ".join(str(i) for i in range(1, 31)), "stop"
    if "40 different animals" in p:
        lst = ANIMALS[:12] * 4 if flawed else ANIMALS[:40]
        return "\n".join(lst), "stop"
    base = {
        "sky": "The sky looks blue because air molecules scatter short blue wavelengths of sunlight more than red ones.",
        "coastal": "Fog lifts slowly over the harbor while fishermen prepare nets and the bakery opens its doors.",
        "python": "Use clear names, keep functions small, and add tests for important behaviour.",
        "aprendizado": "Aprendizado de máquina é a área que cria modelos que aprendem padrões a partir de dados.",
        "bottle": "A durable steel bottle that keeps drinks cold for a full day and fits any bag.",
        "supply": "Prices rise when demand exceeds supply and fall when supply exceeds demand.",
    }
    text = next((v for k, v in base.items() if k in p), "Here is a concise answer to your request.")
    if flawed and temperature == 0.0:
        return (text + " ") * 6, "length"
    if temperature > 0.5:
        text += f" (variation {call_no % 7})"
    return text, "stop"


def make_handler(variant_default: str, delay: float):
    counter = {"n": 0}
    lock = threading.Lock()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencioso
            return

        def _send(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path.rstrip("/").endswith("/models"):
                self._send(200, {"data": [{"id": "demo-flawed"}, {"id": "demo-good"}]})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if not self.path.rstrip("/").endswith("/chat/completions"):
                self._send(404, {"error": "not found"})
                return
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            model = str(req.get("model", ""))
            variant = "good" if "good" in model else "flawed" if "flawed" in model else variant_default
            with lock:
                counter["n"] += 1
                n = counter["n"]
            prompt = "\n".join(str(m.get("content", "")) for m in req.get("messages", []))
            text, fin = respond(prompt, variant, float(req.get("temperature", 1.0) or 0.0), n)
            time.sleep(delay * (1 + (n % 3)))
            words = len(text.split())
            self._send(
                200,
                {
                    "id": f"sim-{n}",
                    "object": "chat.completion",
                    "model": model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": fin}],
                    "usage": {
                        "prompt_tokens": len(prompt.split()),
                        "completion_tokens": words,
                        "total_tokens": words + len(prompt.split()),
                    },
                },
            )

    return H


def start(port: int = 0, variant: str = "flawed", delay: float = 0.0) -> tuple[ThreadingHTTPServer, int]:
    """Inicia em thread (para testes/demo). Retorna (servidor, porta)."""
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(variant, delay))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--variant", choices=("flawed", "good"), default="flawed")
    ap.add_argument("--delay", type=float, default=0.05)
    a = ap.parse_args()
    s, port = start(a.port, a.variant, a.delay)
    print(f"SIMULATED model server on http://127.0.0.1:{port}/v1 (models: demo-flawed, demo-good). Ctrl+C to stop.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        s.shutdown()
