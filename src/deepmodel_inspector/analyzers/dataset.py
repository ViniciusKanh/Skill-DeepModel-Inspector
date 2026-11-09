"""Dataset Intelligence & Quality: auditoria de datasets de pré-treino, SFT e avaliação.

Regras com prefixo DAT.* (ver docs/diagnostic-methodology.md).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from deepmodel_inspector.core.common import describe, finding, load_table, redact, result, rnd
from deepmodel_inspector.parsers.records import (
    VALID_ROLES,
    detect_format,
    messages_of,
    near_duplicate_pairs,
    normalize,
    split_parts,
    text_hash,
    words,
)

NEAR_DUP_LIMIT = 20_000
# Padrões de DETECÇÃO de texto com instruções embutidas (prompt injection) nos DADOS analisados.
# São usados apenas para sinalizar registros; nunca são seguidos. Montados a partir de listas
# legíveis para que o padrão seja auditável.
_INJ_VERB = ("ignore", "disregard", "forget")
_INJ_SCOPE = ("previous", "prior", "above", "all previous", "all prior")
_INJ_EXTRA = (
    "you are now in developer mode",
    "you are now developer mode",
    "reveal (?:your|the) system prompt",
    "ignore as instru[cç][oõ]es anteriores",
)
INJECTION = re.compile(
    "|".join([rf"\b{v} (?:{'|'.join(_INJ_SCOPE)}) (?:instructions|rules)" for v in _INJ_VERB] + list(_INJ_EXTRA)),
    re.I,
)
MOJIBAKE = re.compile("Ã[\u0080-¿]|â€|Â[ -¿]")
ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
CONTROL = re.compile("[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]")
# Listas curtas de palavras funcionais para estimativa heurística de idioma (documentada).
STOPWORDS = {
    "en": {"the", "and", "is", "of", "to", "in", "that", "it", "for", "with", "you", "are", "this", "was"},
    "pt": {"de", "que", "não", "para", "com", "uma", "os", "no", "na", "do", "da", "em", "é", "você", "são"},
    "es": {"el", "que", "los", "las", "por", "con", "una", "para", "es", "del", "se", "y", "como", "pero"},
    "fr": {"le", "les", "des", "est", "et", "une", "pour", "dans", "que", "pas", "qui", "sur", "vous", "avec"},
    "de": {"der", "die", "und", "das", "ist", "nicht", "mit", "ein", "zu", "den", "sie", "auf", "für", "ich"},
}


def guess_language(ws: list[str]) -> str:
    """Estimativa heurística por contagem de stopwords; 'und' se < 3 ocorrências ou empate."""
    scores = {lang: sum(1 for w in ws if w in sw) for lang, sw in STOPWORDS.items()}
    best = sorted(scores.items(), key=lambda kv: -kv[1])
    if best[0][1] < 3 or best[0][1] == best[1][1]:
        return "und"
    return best[0][0]


def script_of(ch: str) -> str:
    """Sistema de escrita aproximado de um caractere alfabético via nome Unicode."""
    try:
        return unicodedata.name(ch).split(" ")[0]
    except ValueError:
        return "UNKNOWN"


def _rep_ratio(ws: list[str], n: int = 3) -> float:
    """Fração de n-gramas repetidos dentro de um texto (0 = sem repetição)."""
    grams = [tuple(ws[i : i + n]) for i in range(len(ws) - n + 1)]
    return 1 - len(set(grams)) / len(grams) if grams else 0.0


def validate_structure(rec: dict[str, Any], fmt: str) -> list[str]:
    """Problemas estruturais do registro conforme o formato detectado."""
    issues = []
    if fmt == "instruction":
        if not str(rec.get("instruction") or "").strip():
            issues.append("empty_instruction")
        out = str(rec.get("output") or "").strip()
        if not out:
            issues.append("empty_output")
        elif normalize(out) == normalize(str(rec.get("instruction") or "")):
            issues.append("output_equals_instruction")
    elif fmt == "messages":
        msgs = messages_of(rec)
        roles = []
        for m in msgs:
            if not isinstance(m, dict):
                issues.append("non_object_message")
                continue
            role = str(m.get("role", m.get("from", ""))).lower()
            roles.append(role)
            if role not in VALID_ROLES:
                issues.append("invalid_role")
            if not str(m.get("content", m.get("value", "")) or "").strip():
                issues.append("empty_message_content")
        if not msgs:
            issues.append("empty_messages")
        elif not any(r in ("assistant", "gpt") for r in roles):
            issues.append("no_assistant_turn")
        elif roles and roles[-1] not in ("assistant", "gpt"):
            issues.append("last_turn_not_assistant")
        if any(roles[i] == roles[i - 1] and roles[i] != "tool" for i in range(1, len(roles))):
            issues.append("consecutive_same_role")
    elif fmt == "prompt_response":
        p, r = split_parts(rec, fmt)
        if not r.strip():
            issues.append("empty_response")
        if not p.strip():
            issues.append("empty_prompt")
    elif fmt == "unknown":
        issues.append("unrecognized_schema")
    return sorted(set(issues))


def analyze_records(
    records: list[dict[str, Any]], source: str = "", text_field: str | None = None, near_threshold: float = 0.8
) -> dict[str, Any]:
    """Executa as regras DAT.* sobre registros carregados."""
    F: list[dict[str, Any]] = []
    lim: list[str] = []
    n = len(records)
    if n == 0:
        F.append(
            finding(
                "DAT.EMPTY_FILE",
                "dataset",
                "HIGH",
                "CONFIRMED",
                "Dataset has no records",
                {"records": 0},
                source,
                "No parsable records were found.",
                "Check the file path, format and encoding.",
            )
        )
        return result("dataset", source, {"records": 0}, F, ["Empty input."])
    fmts = Counter()
    texts, struct, lens_c, lens_w, langs, scripts = [], Counter(), [], [], Counter(), Counter()
    empty_idx, rep_idx, inj_idx, moj, zw, ctrl, non_nfc = [], [], [], 0, 0, 0, 0
    for i, rec in enumerate(records):
        fmt = detect_format(rec, text_field)
        fmts[fmt] += 1
        p, r = split_parts(rec, fmt, text_field)
        t = (p + "\n" + r).strip()
        texts.append(t)
        for issue in validate_structure(rec, fmt):
            struct[issue] += 1
        if not t.strip():
            empty_idx.append(i)
            continue
        ws = [w for w in re_words(t)]
        lens_c.append(len(t))
        lens_w.append(len(ws))
        if len(ws) >= 20 and _rep_ratio(ws) > 0.5:
            rep_idx.append(i)
        if INJECTION.search(t):
            inj_idx.append(i)
        moj += bool(MOJIBAKE.search(t))
        zw += bool(ZERO_WIDTH.search(t))
        ctrl += bool(CONTROL.search(t))
        non_nfc += unicodedata.normalize("NFC", t) != t
        langs[guess_language(ws[:400])] += 1
        for ch in t[:2000]:
            if ch.isalpha():
                scripts[script_of(ch)] += 1
    nonempty = n - len(empty_idx)
    # duplicatas exatas (texto normalizado)
    groups: dict[str, list[int]] = {}
    for i, t in enumerate(texts):
        if t.strip():
            groups.setdefault(text_hash(t), []).append(i)
    dup_groups = [g for g in groups.values() if len(g) > 1]
    dup_extra = sum(len(g) - 1 for g in dup_groups)
    # quase-duplicatas
    sample = [t for t in texts if t.strip()][:NEAR_DUP_LIMIT]
    if nonempty > NEAR_DUP_LIMIT:
        lim.append(f"Near-duplicate search limited to the first {NEAR_DUP_LIMIT} non-empty records.")
    exact_hashes = [text_hash(t) for t in sample]
    near = [(i, j, s) for i, j, s in near_duplicate_pairs(sample, near_threshold) if exact_hashes[i] != exact_hashes[j]]
    near_records = len({i for i, _, _ in near} | {j for _, j, _ in near})
    total_chars = sum(scripts.values()) or 1
    metrics: dict[str, Any] = {
        "records": n,
        "formats": dict(fmts),
        "empty_records": len(empty_idx),
        "length_chars": describe([float(x) for x in lens_c]),
        "length_words": describe([float(x) for x in lens_w]),
        "exact_duplicate_groups": len(dup_groups),
        "exact_duplicate_extra_records": dup_extra,
        "exact_duplicate_rate": rnd(dup_extra / n, 4),
        "near_duplicate_pairs": len(near),
        "near_duplicate_records": near_records,
        "near_duplicate_threshold": near_threshold,
        "repetitive_records": len(rep_idx),
        "structure_issues": dict(struct),
        "unicode": {
            "mojibake_records": moj,
            "zero_width_records": zw,
            "control_char_records": ctrl,
            "non_nfc_records": non_nfc,
        },
        "scripts": {k: rnd(v / total_chars, 4) for k, v in scripts.most_common(6)},
        "language_estimate": dict(langs.most_common()),
        "language_method": "stopword-count heuristic (en/pt/es/fr/de); 'und' when undetermined",
        "instruction_like_records": len(inj_idx),
    }
    if empty_idx:
        rate = len(empty_idx) / n
        F.append(
            finding(
                "DAT.EMPTY",
                "dataset",
                "MEDIUM" if rate >= 0.05 else "LOW",
                "CONFIRMED",
                "Empty records",
                {"count": len(empty_idx), "rate": rnd(rate, 4), "first_indices": empty_idx[:5]},
                source,
                "Records with no text content after parsing.",
                "Remove or repair empty records.",
            )
        )
    if dup_groups:
        rate = dup_extra / n
        sev = "HIGH" if rate >= 0.10 else "MEDIUM" if rate >= 0.02 else "LOW"
        big = max(dup_groups, key=len)
        F.append(
            finding(
                "DAT.EXACT_DUP",
                "dataset",
                sev,
                "CONFIRMED",
                "Exact duplicate records (within this file)",
                {
                    "duplicate_groups": len(dup_groups),
                    "extra_copies": dup_extra,
                    "rate": rnd(rate, 4),
                    "largest_group_size": len(big),
                    "sample": redact(texts[big[0]]),
                },
                source,
                "Identical records after normalization. Within one split this is a quality issue "
                "(over-weighting, memorization), not evaluation leakage; it may be intentional upsampling.",
                "Deduplicate unless the repetition is a deliberate weighting choice.",
                "Train on the deduplicated set and compare validation loss and generation repetition.",
            )
        )
    if near:
        rate = near_records / max(1, len(sample))
        F.append(
            finding(
                "DAT.NEAR_DUP",
                "dataset",
                "MEDIUM" if rate >= 0.05 else "LOW",
                "POTENTIAL",
                "Near-duplicate records",
                {
                    "pairs": len(near),
                    "records_involved": near_records,
                    "threshold_jaccard": near_threshold,
                    "example_pair_indices": [list(p[:2]) for p in near[:3]],
                },
                source,
                "Pairs with word 5-shingle Jaccard similarity >= threshold (MinHash/LSH, verified).",
                "Review examples; templated prompts can be legitimate, paraphrased copies usually are not.",
                "Inspect the listed pairs and deduplicate if they carry the same content.",
            )
        )
    if rep_idx:
        rate = len(rep_idx) / max(1, nonempty)
        F.append(
            finding(
                "DAT.REPETITIVE",
                "dataset",
                "MEDIUM" if rate >= 0.02 else "LOW",
                "CONFIRMED",
                "Records with excessive internal repetition",
                {
                    "count": len(rep_idx),
                    "rate": rnd(rate, 4),
                    "first_indices": rep_idx[:5],
                    "sample": redact(texts[rep_idx[0]]),
                },
                source,
                "More than 50% of word 3-grams inside the record are repeats.",
                "Filter or fix these records; repetitive targets can teach degenerate repetition.",
            )
        )
    if struct:
        total = sum(struct.values())
        sev = "HIGH" if struct.get("unrecognized_schema", 0) > n * 0.5 else "MEDIUM"
        F.append(
            finding(
                "DAT.STRUCTURE",
                "dataset",
                sev,
                "CONFIRMED",
                "Schema/structure problems",
                {"issues": dict(struct), "total": total},
                source,
                "Records violate the expected instruction/response or messages structure.",
                "Fix missing fields, invalid roles and conversations that do not end with an assistant turn.",
            )
        )
    if moj or ctrl:
        F.append(
            finding(
                "DAT.ENCODING",
                "dataset",
                "MEDIUM" if (moj + ctrl) / n >= 0.01 else "LOW",
                "CONFIRMED",
                "Encoding artifacts (mojibake/control characters)",
                {"mojibake_records": moj, "control_char_records": ctrl},
                source,
                "Patterns such as 'Ã©' indicate UTF-8 text decoded as Latin-1; control characters are noise.",
                "Re-decode the source as UTF-8 (e.g. ftfy) and strip control characters.",
            )
        )
    if inj_idx:
        F.append(
            finding(
                "DAT.INSTRUCTION_LIKE",
                "dataset",
                "INFO",
                "CONFIRMED",
                "Records contain instruction-like text aimed at models",
                {"count": len(inj_idx), "first_indices": inj_idx[:5]},
                source,
                "Text such as 'ignore previous instructions' was found. It was treated strictly as data "
                "and not followed. It may be legitimate (safety training) or poisoned content.",
                "Review these records to confirm they are intended.",
            )
        )
    if "und" in langs and langs["und"] == nonempty:
        lim.append("Language could not be estimated (short texts or unsupported language).")
    return result("dataset", source, metrics, F, lim)


def re_words(text: str) -> list[str]:
    """Palavras do texto (wrapper para facilitar testes)."""
    return words(text)


def analyze_file(path: Path, text_field: str | None = None, max_records: int = 200_000) -> dict[str, Any]:
    """Carrega e audita um arquivo de dataset."""
    recs, info = load_table(path, max_records)
    out = analyze_records(recs, path.name, text_field)
    out["parse"] = info
    if info["malformed"]:
        f = finding(
            "DAT.MALFORMED",
            "dataset",
            "MEDIUM",
            "CONFIRMED",
            "Malformed lines skipped",
            {"count": info["malformed"], "line_numbers": info["malformed_lines"]},
            path.name,
            "Lines that could not be parsed were skipped and are not part of the analysis.",
            "Repair or remove malformed lines.",
        )
        out["findings"].append(f)
        f["id"] = f"DAT-{len(out['findings']):03d}"
    if info["truncated"]:
        out["limitations"].append(f"Only the first {max_records} records were analyzed.")
    return out
