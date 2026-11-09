"""Detecção de sobreposição/contaminação entre treino e conjuntos de avaliação (regras LEK.*).

Distingue: duplicata exata entre conjuntos (vazamento confirmado), quase-duplicata,
prompt de avaliação visto no treino e sobreposição de 13-gramas (indício de contaminação).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from deepmodel_inspector.core.common import finding, load_table, redact, result, rnd
from deepmodel_inspector.parsers.records import (
    detect_format,
    jaccard,
    lsh_candidates,
    minhash,
    ngram_hashes,
    normalize,
    shingles,
    split_parts,
    text_hash,
)

NGRAM = 13
BOILERPLATE_FRACTION = 0.01


def _prepare(records: list[dict[str, Any]], text_field: str | None) -> list[tuple[str, str, str]]:
    """Lista de (texto completo, prompt, resposta) por registro não vazio."""
    out = []
    for rec in records:
        fmt = detect_format(rec, text_field)
        p, r = split_parts(rec, fmt, text_field)
        full = (p + "\n" + r).strip()
        if full:
            out.append((full, p.strip(), r.strip()))
    return out


def analyze_sets(
    train: list[dict[str, Any]],
    evals: dict[str, list[dict[str, Any]]],
    source: str = "",
    text_field: str | None = None,
    near_threshold: float = 0.8,
) -> dict[str, Any]:
    """Compara o conjunto de treino com um ou mais conjuntos de avaliação."""
    tr = _prepare(train, text_field)
    F: list[dict[str, Any]] = []
    lim = [
        f"Contamination by {NGRAM}-gram overlap ignores n-grams present in >= {BOILERPLATE_FRACTION:.0%} of "
        "training records (and >= 5 records) to avoid flagging shared templates.",
        "Only lexical overlap is measured; paraphrased or translated contamination is not detected.",
    ]
    full_h = {text_hash(t[0]) for t in tr}
    prompt_h = {text_hash(t[1]) for t in tr if t[1] and t[2]}
    gram_count: Counter[int] = Counter()
    for t in tr:
        gram_count.update(ngram_hashes(t[0], NGRAM))
    cut = max(5, int(BOILERPLATE_FRACTION * len(tr)))
    boiler = {g for g, c in gram_count.items() if c >= cut}
    train_grams = set(gram_count) - boiler
    tr_sh = [shingles(t[0]) for t in tr]
    tr_sig = [minhash(s) for s in tr_sh]
    metrics: dict[str, Any] = {"train_records": len(tr), "boilerplate_ngrams_ignored": len(boiler), "splits": {}}
    for name, recs in evals.items():
        ev = _prepare(recs, text_field)
        n = len(ev) or 1
        exact = [i for i, t in enumerate(ev) if text_hash(t[0]) in full_h]
        exact_set = set(exact)
        # quase-duplicatas entre conjuntos: LSH sobre a união
        ev_sh = [shingles(t[0]) for t in ev]
        sigs = tr_sig + [minhash(s) for s in ev_sh]
        k = len(tr_sig)
        near = {}
        for a, b in lsh_candidates(sigs):
            if a < k <= b:
                j = b - k
                if j in exact_set:
                    continue
                sim = jaccard(tr_sh[a], ev_sh[j])
                if sim >= near_threshold and sim > near.get(j, (0, 0))[1]:
                    near[j] = (a, round(sim, 4))
        seen = exact_set | set(near)
        prompt_only = [i for i, t in enumerate(ev) if i not in seen and t[1] and t[2] and text_hash(t[1]) in prompt_h]
        gram_hit = []
        for i, t in enumerate(ev):
            if i in seen:
                continue
            g = ngram_hashes(t[0], NGRAM)
            if g:
                ov = len(g & train_grams) / len(g)
                if ov > 0:
                    gram_hit.append((i, ov))
        metrics["splits"][name] = {
            "records": len(ev),
            "exact_overlap": len(exact),
            "exact_overlap_rate": rnd(len(exact) / n, 4),
            "near_duplicate_overlap": len(near),
            "prompt_seen_in_train": len(prompt_only),
            f"records_with_{NGRAM}gram_overlap": len(gram_hit),
            f"mean_{NGRAM}gram_overlap_of_hits": rnd(sum(o for _, o in gram_hit) / len(gram_hit), 4)
            if gram_hit
            else 0.0,
        }
        if exact:
            rate = len(exact) / n
            F.append(
                finding(
                    "LEK.EXACT",
                    "leakage",
                    "CRITICAL" if rate >= 0.05 else "HIGH",
                    "CONFIRMED",
                    f"Evaluation records present verbatim in training ({name})",
                    {
                        "split": name,
                        "count": len(exact),
                        "rate": rnd(rate, 4),
                        "first_indices": exact[:5],
                        "sample": redact(ev[exact[0]][0]),
                    },
                    source,
                    "These evaluation examples (after normalization) also appear in the training data, so "
                    "metrics on them measure memorization, not generalization.",
                    "Remove the overlapping records from the evaluation set (or training set) and re-evaluate.",
                    "Report metrics separately on the clean subset vs. the overlapping subset.",
                )
            )
        if near:
            F.append(
                finding(
                    "LEK.NEAR",
                    "leakage",
                    "HIGH" if len(near) / n >= 0.05 else "MEDIUM",
                    "POTENTIAL",
                    f"Near-duplicate evaluation records in training ({name})",
                    {
                        "split": name,
                        "count": len(near),
                        "threshold_jaccard": near_threshold,
                        "examples_eval_to_train": [[j, a, s] for j, (a, s) in list(sorted(near.items()))[:3]],
                    },
                    source,
                    "High shingle overlap with a training record; may be paraphrase-level leakage.",
                    "Inspect pairs and exclude near copies from evaluation.",
                    "Compare metrics with and without these records.",
                )
            )
        if prompt_only:
            F.append(
                finding(
                    "LEK.PROMPT",
                    "leakage",
                    "MEDIUM",
                    "POTENTIAL",
                    f"Evaluation prompts seen in training with different answers ({name})",
                    {"split": name, "count": len(prompt_only), "first_indices": prompt_only[:5]},
                    source,
                    "The input side is identical to a training example while the target differs.",
                    "Decide whether shared prompts are acceptable for this benchmark; usually remove them.",
                )
            )
        strong = [i for i, o in gram_hit if o >= 0.5]
        if strong:
            F.append(
                finding(
                    "LEK.NGRAM",
                    "leakage",
                    "MEDIUM",
                    "POTENTIAL",
                    f"Substantial {NGRAM}-gram overlap with training ({name})",
                    {"split": name, "records_over_50pct": len(strong), "records_any_overlap": len(gram_hit)},
                    source,
                    f"At least half of these records' {NGRAM}-grams occur in training text (templates excluded).",
                    "Review for partial contamination (copied passages).",
                )
            )
        if not (exact or near or prompt_only or strong):
            F.append(
                finding(
                    "LEK.CLEAN",
                    "leakage",
                    "INFO",
                    "CONFIRMED",
                    f"No overlap detected ({name})",
                    {"split": name, "records": len(ev)},
                    source,
                    "No exact, near-duplicate, prompt or strong n-gram overlap at the configured thresholds.",
                    "No action needed for lexical leakage; semantic leakage is not covered.",
                )
            )
    return result("leakage", source, metrics, F, lim)


def analyze_files(
    train: Path, evals: list[Path], text_field: str | None = None, max_records: int = 200_000
) -> dict[str, Any]:
    """Carrega os arquivos e executa a análise de vazamento."""
    tr, info = load_table(train, max_records)
    ev = {}
    for p in evals:
        ev[p.name] = load_table(p, max_records)[0]
    out = analyze_sets(tr, ev, f"{train.name} vs {', '.join(p.name for p in evals)}", text_field)
    out["parse"] = {"train": info}
    return out


def normalized_equal(a: str, b: str) -> bool:
    """Igualdade após normalização (utilitário de teste)."""
    return normalize(a) == normalize(b)
