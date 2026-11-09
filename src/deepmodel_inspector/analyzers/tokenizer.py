"""Tokenizer Efficiency Analyzer (regras TOK.*).

Usa SOMENTE tokenizações fornecidas pelo usuário (campos ``tokens`` e/ou ``token_ids``).
Nunca simula um tokenizer: sem tokens, apenas estatísticas textuais são produzidas.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from deepmodel_inspector.core.common import describe, finding, load_table, result, rnd

WORD = re.compile(r"\w+", re.UNICODE)
BYTE_TOKEN = re.compile(r"^<0x[0-9A-Fa-f]{2}>$")
WORD_START = ("Ġ", "▁", " ")  # Ġ (GPT-2 BPE), ▁ (SentencePiece), espaço
UNK_DEFAULT = ("<unk>", "[UNK]", "<UNK>", "<|unk|>")
PAD_DEFAULT = ("<pad>", "[PAD]", "<|pad|>", "<|endoftext|>")
GROUP_KEYS = ("tokenizer", "tokenizer_name", "model", "name")


def _tokens(rec: dict[str, Any]) -> tuple[list[str] | None, list[int] | None]:
    """Extrai tokens textuais e/ou ids do registro."""
    toks = rec.get("tokens")
    ids = rec.get("token_ids", rec.get("input_ids"))
    toks = [str(t) for t in toks] if isinstance(toks, list) else None
    ids = [int(i) for i in ids if isinstance(i, (int, float))] if isinstance(ids, list) else None
    return toks, ids


def _fragmentation(toks: list[str]) -> tuple[int, int] | None:
    """(palavras, palavras com >=2 tokens) usando marcadores de início de palavra; None se não detectável."""
    if not any(t.startswith(WORD_START) for t in toks[1:]):
        return None
    wcount, multi, cur = 0, 0, 0
    for i, t in enumerate(toks):
        starts = i == 0 or t.startswith(WORD_START)
        if starts:
            if cur:
                wcount += 1
                multi += cur >= 2
            cur = 0
        if WORD.search(t):
            cur += 1
    if cur:
        wcount += 1
        multi += cur >= 2
    return wcount, multi


def analyze_group(
    recs: list[dict[str, Any]],
    max_length: int | None,
    unk: set[str],
    pad: set[str],
    unk_id: int | None,
    pad_id: int | None,
    vocab_size: int | None,
) -> dict[str, Any]:
    """Métricas de eficiência para um grupo (um tokenizer)."""
    tok_counts, tpw, tpc, chars, words_n = [], [], [], 0, 0
    unk_n = pad_n = byte_n = total = 0
    frag_w = frag_m = 0
    frag_ok = True
    vocab: Counter[str] = Counter()
    trunc = 0
    with_tokens = 0
    for r in recs:
        text = str(r.get("text") or "")
        nw = len(WORD.findall(text))
        chars += len(text)
        words_n += nw
        toks, ids = _tokens(r)
        seq = toks if toks is not None else ids
        if seq is None:
            continue
        with_tokens += 1
        n = len(seq)
        if toks is not None:
            rp = sum(1 for t in toks if t in pad)
            unk_n += sum(1 for t in toks if t in unk)
            byte_n += sum(1 for t in toks if BYTE_TOKEN.match(t))
            vocab.update(toks)
            fr = _fragmentation(toks)
            if fr is None:
                frag_ok = False
            else:
                frag_w += fr[0]
                frag_m += fr[1]
        else:
            rp = sum(1 for i in ids if pad_id is not None and i == pad_id)
            unk_n += sum(1 for i in ids if unk_id is not None and i == unk_id)
            vocab.update(str(i) for i in ids)
        pad_n += rp
        eff = n - rp
        total += n
        tok_counts.append(float(eff))
        if nw:
            tpw.append(eff / nw)
        if text:
            tpc.append(eff / len(text))
        if max_length and n >= max_length:
            trunc += 1
    m: dict[str, Any] = {"records": len(recs), "records_with_tokens": with_tokens, "chars": chars, "words": words_n}
    if not with_tokens:
        m["unavailable"] = [
            "tokens_per_word",
            "tokens_per_char",
            "fragmentation",
            "unk_rate",
            "vocab_coverage",
            "truncation",
            "context_waste",
        ]
        return m
    real = total - pad_n
    m.update(
        {
            "tokens_total": total,
            "tokens_per_record": describe(tok_counts),
            "tokens_per_word": rnd(real / words_n, 4) if words_n else None,
            "tokens_per_word_dist": describe(tpw),
            "chars_per_token": rnd(chars / real, 4) if real else None,
            "tokens_per_char": rnd(real / chars, 4) if chars else None,
            "unk_rate": rnd(unk_n / real, 6) if real else None,
            "byte_fallback_rate": rnd(byte_n / real, 6) if real else None,
            "padding_rate": rnd(pad_n / total, 6) if total else None,
            "distinct_tokens_observed": len(vocab),
        }
    )
    m["fragmentation_rate"] = rnd(frag_m / frag_w, 4) if frag_ok and frag_w else None
    if vocab_size:
        m["observed_vocab_coverage"] = rnd(len(vocab) / vocab_size, 6)
    if max_length:
        m["truncated_records"] = trunc
        m["truncation_rate"] = rnd(trunc / with_tokens, 4)
        m["mean_unused_context"] = rnd(
            sum(max(0.0, max_length - c) for c in tok_counts) / (with_tokens * max_length), 4
        )
    return m


def analyze_records(
    recs: list[dict[str, Any]],
    source: str = "",
    max_length: int | None = None,
    unk_token: str | None = None,
    pad_token: str | None = None,
    unk_id: int | None = None,
    pad_id: int | None = None,
    vocab_size: int | None = None,
    fertility_threshold: float = 2.0,
) -> dict[str, Any]:
    """Executa as regras TOK.* por grupo de tokenizer e compara grupos."""
    unk = {unk_token} if unk_token else set(UNK_DEFAULT)
    pad = {pad_token} if pad_token else set(PAD_DEFAULT)
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in recs:
        key = next((str(r[k]) for k in GROUP_KEYS if r.get(k)), "default")
        groups.setdefault(key, []).append(r)
    F: list[dict[str, Any]] = []
    lim: list[str] = []
    metrics: dict[str, Any] = {"groups": {}}
    for g, rs in groups.items():
        m = analyze_group(rs, max_length, unk, pad, unk_id, pad_id, vocab_size)
        metrics["groups"][g] = m
        tag = f" [{g}]" if len(groups) > 1 else ""
        if "unavailable" in m:
            F.append(
                finding(
                    "TOK.NO_TOKENS",
                    "tokenizer",
                    "INFO",
                    "INCONCLUSIVE",
                    f"No tokenization provided{tag}",
                    {"unavailable_metrics": m["unavailable"]},
                    source,
                    "Records lack 'tokens' or 'token_ids'; tokenizer output is never simulated.",
                    "Export tokens from your tokenizer (e.g. tokenizer.tokenize/encode) into the JSONL.",
                )
            )
            continue
        tpw = m.get("tokens_per_word")
        if tpw and tpw > fertility_threshold:
            F.append(
                finding(
                    "TOK.FERTILITY",
                    "tokenizer",
                    "MEDIUM",
                    "POTENTIAL",
                    f"High token fertility{tag}",
                    {
                        "tokens_per_word": tpw,
                        "threshold": fertility_threshold,
                        "fragmentation_rate": m.get("fragmentation_rate"),
                    },
                    source,
                    "More than the threshold tokens per word on this text means each word costs several "
                    "tokens, reducing effective context and raising compute per example.",
                    "Compare against an alternative tokenizer on the same texts; consider vocabulary "
                    "extension or a tokenizer trained on the target language.",
                    "Tokenize the same sample with a candidate tokenizer and compare tokens_per_word.",
                )
            )
        if m.get("unk_rate"):
            sev = "HIGH" if m["unk_rate"] > 0.01 else "MEDIUM"
            F.append(
                finding(
                    "TOK.UNK",
                    "tokenizer",
                    sev,
                    "CONFIRMED",
                    f"Unknown tokens present{tag}",
                    {"unk_rate": m["unk_rate"]},
                    source,
                    "Unknown tokens irreversibly drop information from the input.",
                    "Use a byte-level/byte-fallback tokenizer or extend the vocabulary.",
                )
            )
        if (m.get("byte_fallback_rate") or 0) > 0.02:
            F.append(
                finding(
                    "TOK.BYTE_FALLBACK",
                    "tokenizer",
                    "MEDIUM",
                    "POTENTIAL",
                    f"Frequent byte-fallback tokens{tag}",
                    {"byte_fallback_rate": m["byte_fallback_rate"]},
                    source,
                    "Characters outside the vocabulary are spelled as raw bytes (common with accented "
                    "characters when the tokenizer was trained on another language).",
                    "Check which characters trigger fallback; consider vocabulary extension.",
                )
            )
        if (m.get("truncation_rate") or 0) > 0.05:
            F.append(
                finding(
                    "TOK.TRUNCATION",
                    "tokenizer",
                    "MEDIUM",
                    "CONFIRMED",
                    f"Sequences reach max length{tag}",
                    {"truncation_rate": m["truncation_rate"], "max_length": max_length},
                    source,
                    "These sequences are at or above max_length and will be (or were) truncated.",
                    "Raise max_length, split long documents, or filter them.",
                )
            )
        if (m.get("padding_rate") or 0) > 0.3 or (m.get("mean_unused_context") or 0) > 0.5:
            F.append(
                finding(
                    "TOK.CONTEXT_WASTE",
                    "tokenizer",
                    "LOW",
                    "POTENTIAL",
                    f"Large unused context{tag}",
                    {"padding_rate": m.get("padding_rate"), "mean_unused_context": m.get("mean_unused_context")},
                    source,
                    "A large fraction of the context window is padding or unused.",
                    "Use sequence packing or dynamic padding / bucketing by length.",
                )
            )
        if m.get("fragmentation_rate") is None:
            lim.append(f"Fragmentation not computed{tag}: no word-boundary markers (Ġ/▁) in tokens.")
    if len(groups) > 1:
        comp = {g: m.get("tokens_per_word") for g, m in metrics["groups"].items()}
        valid = {g: v for g, v in comp.items() if v}
        if len(valid) > 1:
            best = min(valid, key=lambda k: valid[k])
            metrics["comparison"] = {
                "tokens_per_word": comp,
                "most_efficient": best,
                "relative_cost_vs_best": {g: rnd(v / valid[best], 4) for g, v in valid.items()},
            }
            texts = {g: [str(r.get("text") or "") for r in rs] for g, rs in groups.items()}
            same = len({tuple(t) for t in texts.values()}) == 1
            metrics["comparison"]["same_texts"] = same
            if not same:
                lim.append("Tokenizer groups were measured on different texts; comparison is indicative only.")
    if max_length is None:
        lim.append("max_length not provided; truncation and context waste not evaluated.")
    return result("tokenizer", source, metrics, F, lim)


def analyze_file(path: Path, **kw: Any) -> dict[str, Any]:
    """Carrega um JSONL com tokens e o analisa."""
    recs, info = load_table(path, kw.pop("max_records", 200_000))
    out = analyze_records(recs, path.name, **kw)
    out["parse"] = info
    return out
