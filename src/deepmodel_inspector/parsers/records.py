"""Parsers de registros textuais (text, instruction, messages, prompt/response, CSV)
e primitivas de similaridade (normalização, shingles, MinHash + LSH).

Somente biblioteca padrão; embutido nos scripts de dataset, leakage e generation.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

TEXT_KEYS = ("text", "content", "document", "body", "sentence")
PROMPT_KEYS = ("prompt", "question", "query")
RESPONSE_KEYS = ("response", "completion", "answer", "chosen", "output_text")
VALID_ROLES = {"system", "user", "assistant", "tool", "function", "developer", "human", "gpt"}
_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WORD = re.compile(r"\w+", re.UNICODE)


def detect_format(rec: dict[str, Any], text_field: str | None = None) -> str:
    """Detecta o formato do registro: messages, instruction, prompt_response, text ou unknown."""
    if text_field:
        return "custom" if text_field in rec else "unknown"
    if isinstance(rec.get("messages"), list) or isinstance(rec.get("conversations"), list):
        return "messages"
    if "instruction" in rec and "output" in rec:
        return "instruction"
    if any(k in rec for k in PROMPT_KEYS) and any(k in rec for k in RESPONSE_KEYS):
        return "prompt_response"
    if any(k in rec for k in TEXT_KEYS):
        return "text"
    return "unknown"


def _s(v: Any) -> str:
    """Converte valor em string (None -> '')."""
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


def messages_of(rec: dict[str, Any]) -> list[Any]:
    """Lista de mensagens (aceita 'messages' ou 'conversations' no estilo ShareGPT)."""
    msgs = rec.get("messages")
    if not isinstance(msgs, list):
        msgs = rec.get("conversations")
    return msgs if isinstance(msgs, list) else []


def split_parts(rec: dict[str, Any], fmt: str, text_field: str | None = None) -> tuple[str, str]:
    """Separa (parte de entrada/prompt, parte de resposta). Para 'text', resposta = ''."""
    if fmt == "custom":
        return _s(rec.get(text_field or "")), ""
    if fmt == "messages":
        prompt, resp = [], []
        for m in messages_of(rec):
            if not isinstance(m, dict):
                continue
            role = _s(m.get("role", m.get("from", ""))).lower()
            content = _s(m.get("content", m.get("value", "")))
            (resp if role in ("assistant", "gpt") else prompt).append(content)
        return "\n".join(prompt), "\n".join(resp)
    if fmt == "instruction":
        return (_s(rec.get("instruction")) + "\n" + _s(rec.get("input"))).strip(), _s(rec.get("output"))
    if fmt == "prompt_response":
        p = next((_s(rec[k]) for k in PROMPT_KEYS if k in rec), "")
        r = next((_s(rec[k]) for k in RESPONSE_KEYS if k in rec), "")
        return p, r
    if fmt == "text":
        return next((_s(rec[k]) for k in TEXT_KEYS if k in rec), ""), ""
    return "", ""


def full_text(rec: dict[str, Any], fmt: str, text_field: str | None = None) -> str:
    """Texto completo do registro (entrada + resposta)."""
    p, r = split_parts(rec, fmt, text_field)
    return (p + "\n" + r).strip()


def normalize(text: str) -> str:
    """Normalização para comparação: NFKC, casefold, sem pontuação, espaços colapsados."""
    t = unicodedata.normalize("NFKC", text).casefold()
    t = _PUNCT.sub(" ", t)
    return _WS.sub(" ", t).strip()


def words(text: str) -> list[str]:
    """Tokenização simples por palavras (\\w+, Unicode, minúsculas)."""
    return _WORD.findall(text.casefold())


def h64(s: str) -> int:
    """Hash estável de 64 bits (blake2b), independente de PYTHONHASHSEED."""
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")


def text_hash(text: str) -> str:
    """Hash hexadecimal do texto normalizado (detecção de duplicatas exatas)."""
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:16]


def shingles(text: str, k: int = 5) -> set[int]:
    """Conjunto de hashes de k-shingles de palavras (ou de caracteres se texto curto)."""
    w = normalize(text).split()
    if len(w) >= k:
        return {h64(" ".join(w[i : i + k])) for i in range(len(w) - k + 1)}
    t = " ".join(w)
    if len(t) < 5:
        return {h64(t)} if t else set()
    return {h64(t[i : i + 5]) for i in range(len(t) - 4)}


def ngram_hashes(text: str, n: int = 13) -> set[int]:
    """Hashes de n-gramas de palavras (metodologia de contaminação por 13-gramas)."""
    w = normalize(text).split()
    return {h64(" ".join(w[i : i + n])) for i in range(len(w) - n + 1)}


def jaccard(a: set[int], b: set[int]) -> float:
    """Similaridade de Jaccard entre dois conjuntos."""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


_P = (1 << 61) - 1
_PERMS = [((h64(f"a{i}") % (_P - 1)) + 1, h64(f"b{i}") % _P) for i in range(64)]


def minhash(sh: set[int]) -> tuple[int, ...]:
    """Assinatura MinHash com 64 permutações determinísticas."""
    if not sh:
        return tuple([_P] * 64)
    return tuple(min((a * x + b) % _P for x in sh) for a, b in _PERMS)


def lsh_candidates(sigs: list[tuple[int, ...]], bands: int = 16) -> set[tuple[int, int]]:
    """Pares candidatos via LSH (16 bandas x 4 linhas: ~limiar de Jaccard 0,5)."""
    rows = len(_PERMS) // bands
    pairs: set[tuple[int, int]] = set()
    for b in range(bands):
        buckets: dict[tuple[int, ...], list[int]] = {}
        for i, s in enumerate(sigs):
            if s[0] == _P:
                continue
            buckets.setdefault(s[b * rows : (b + 1) * rows], []).append(i)
        for idx in buckets.values():
            if 1 < len(idx) <= 200:
                for x in range(len(idx)):
                    for y in range(x + 1, len(idx)):
                        pairs.add((idx[x], idx[y]))
    return pairs


def near_duplicate_pairs(texts: list[str], threshold: float = 0.8) -> list[tuple[int, int, float]]:
    """Pares quase-duplicados (Jaccard verificado >= limiar) via MinHash/LSH reproduzível."""
    sh = [shingles(t) for t in texts]
    sigs = [minhash(s) for s in sh]
    out = []
    for i, j in sorted(lsh_candidates(sigs)):
        sim = jaccard(sh[i], sh[j])
        if sim >= threshold:
            out.append((i, j, round(sim, 4)))
    return out
