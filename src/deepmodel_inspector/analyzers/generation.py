"""Generation Behavior Diagnostics (regras GEN.*): repetição, diversidade, truncamento,
redundância entre saídas, comparação entre configurações e checagem contra referências.
"""

from __future__ import annotations

import random
import re
import statistics
from pathlib import Path
from typing import Any

from deepmodel_inspector.core.common import describe, finding, load_table, redact, result, rnd

OUTPUT_KEYS = ("output", "response", "generation", "completion", "generated_text", "prediction", "text")
GROUP_KEYS = ("config", "run", "experiment", "model", "setting")
DECODING = ("temperature", "top_k", "top_p", "repetition_penalty", "max_tokens", "max_new_tokens", "do_sample")
WORD = re.compile(r"\w+", re.UNICODE)
SENT = re.compile(r"(?<=[.!?。])\s+|\n+")
NUM = re.compile(r"\d+(?:[.,]\d+)?")
STOP = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "and",
    "is",
    "are",
    "was",
    "for",
    "on",
    "with",
    "that",
    "it",
    "as",
    "o",
    "os",
    "de",
    "do",
    "da",
    "em",
    "e",
    "que",
    "um",
    "uma",
    "para",
    "com",
    "no",
    "na",
    "é",
}


def _ngrams(ws: list[str], n: int) -> list[tuple[str, ...]]:
    """Lista de n-gramas de palavras."""
    return [tuple(ws[i : i + n]) for i in range(len(ws) - n + 1)]


def distinct_n(outputs: list[list[str]], n: int) -> float | None:
    """Distinct-n no nível do corpus: n-gramas únicos / n-gramas totais."""
    grams = [g for ws in outputs for g in _ngrams(ws, n)]
    return rnd(len(set(grams)) / len(grams), 4) if grams else None


def repetition_rate(ws: list[str], n: int = 3) -> float:
    """Fração de n-gramas repetidos dentro de uma resposta."""
    g = _ngrams(ws, n)
    return 1 - len(set(g)) / len(g) if g else 0.0


def mattr(ws: list[str], window: int = 50) -> float | None:
    """Moving-Average Type-Token Ratio (diversidade lexical robusta ao comprimento)."""
    if not ws:
        return None
    if len(ws) <= window:
        return len(set(ws)) / len(ws)
    vals = [len(set(ws[i : i + window])) / window for i in range(len(ws) - window + 1)]
    return statistics.fmean(vals)


def _shingle(ws: list[str]) -> set[tuple[str, ...]]:
    """Conjunto de 3-gramas (ou unigramas para textos curtos)."""
    return set(_ngrams(ws, 3)) or {(w,) for w in ws}


def grounding(output: str, reference: str) -> dict[str, Any]:
    """Suporte lexical das frases da saída na referência (não é verificação semântica)."""
    ref_w = {w for w in WORD.findall(reference.casefold()) if w not in STOP}
    ref_nums = set(NUM.findall(reference))
    sents = [s for s in SENT.split(output) if len(WORD.findall(s)) >= 3]
    unsupported, num_bad = [], []
    for s in sents:
        cw = [w for w in WORD.findall(s.casefold()) if w not in STOP]
        if cw and sum(w in ref_w for w in cw) / len(cw) < 0.5:
            unsupported.append(s)
        num_bad += [x for x in NUM.findall(s) if x not in ref_nums]
    return {"sentences": len(sents), "unsupported": unsupported, "numbers_not_in_reference": num_bad}


def analyze_group(recs: list[dict[str, Any]], min_words: int, seed: int) -> dict[str, Any]:
    """Métricas de um grupo de saídas."""
    outs = [str(next((r[k] for k in OUTPUT_KEYS if k in r and r[k] is not None), "")) for r in recs]
    toks = [WORD.findall(o.casefold()) for o in outs]
    nonempty = [t for t in toks if t]
    reps = [repetition_rate(t) for t in nonempty]
    lens = [float(len(t)) for t in toks]
    trunc = sum(1 for r in recs if str(r.get("finish_reason", "")).lower() in ("length", "max_tokens"))
    over = 0
    for r in recs:
        lim = r.get("max_new_tokens", r.get("max_tokens"))
        tc = r.get("token_count", r.get("output_tokens"))
        if isinstance(lim, (int, float)) and isinstance(tc, (int, float)) and tc >= lim:
            over += 1
    rng = random.Random(seed)
    idx = list(range(len(nonempty)))
    if len(idx) > 200:
        idx = sorted(rng.sample(idx, 200))
    sh = [_shingle(nonempty[i]) for i in idx]
    sims, near_ident = [], set()
    for a in range(len(sh)):
        for b in range(a + 1, len(sh)):
            j = len(sh[a] & sh[b]) / len(sh[a] | sh[b]) if sh[a] | sh[b] else 1.0
            sims.append(j)
            if j >= 0.8:
                near_ident.update((a, b))
    params = {k: sorted({str(r[k]) for r in recs if k in r}) for k in DECODING if any(k in r for r in recs)}
    m = {
        "responses": len(outs),
        "empty": len(outs) - len(nonempty),
        "length_words": describe(lens),
        "short_responses": sum(1 for t in nonempty if len(t) < min_words),
        "distinct_1": distinct_n(nonempty, 1),
        "distinct_2": distinct_n(nonempty, 2),
        "distinct_3": distinct_n(nonempty, 3),
        "repetition_rate": describe(reps),
        "degenerate_responses": sum(1 for x in reps if x > 0.5),
        "mattr": rnd(statistics.fmean([v for v in (mattr(t) for t in nonempty) if v is not None]), 4)
        if nonempty
        else None,
        "mean_pairwise_similarity": rnd(statistics.fmean(sims), 4) if sims else None,
        "near_identical_fraction": rnd(len(near_ident) / len(sh), 4) if sh else None,
        "finish_reason_length": trunc,
        "reached_max_tokens": over,
        "decoding_params": params,
    }
    return {"metrics": m, "reps": reps, "outs": outs, "toks": toks}


def _boot_diff(a: list[float], b: list[float], seed: int, n: int = 1000) -> tuple[float, float, float]:
    """Diferença de médias (b - a) com IC bootstrap de 95% (semente fixa)."""
    rng = random.Random(seed)
    d = statistics.fmean(b) - statistics.fmean(a)
    boots = sorted(
        statistics.fmean(rng.choices(b, k=len(b))) - statistics.fmean(rng.choices(a, k=len(a))) for _ in range(n)
    )
    return d, boots[int(0.025 * n)], boots[int(0.975 * n) - 1]


def analyze_records(
    recs: list[dict[str, Any]], source: str = "", min_words: int = 3, group_field: str | None = None, seed: int = 13
) -> dict[str, Any]:
    """Executa as regras GEN.* por grupo e compara grupos."""
    keys = (group_field,) if group_field else GROUP_KEYS
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in recs:
        groups.setdefault(next((str(r[k]) for k in keys if k in r and r[k] is not None), "all"), []).append(r)
    F: list[dict[str, Any]] = []
    lim = [
        "Grounding checks are lexical (content-word overlap and numbers vs. the provided reference); "
        "they do not prove factual correctness or detect hallucinations without references.",
        "Differences between configurations are associations; causality requires controlled re-runs.",
    ]
    metrics: dict[str, Any] = {"groups": {}}
    raw: dict[str, Any] = {}
    for g, rs in groups.items():
        res = analyze_group(rs, min_words, seed)
        m = res["metrics"]
        metrics["groups"][g] = m
        raw[g] = res
        n = max(1, m["responses"])
        tag = f" [{g}]" if len(groups) > 1 else ""
        if m["empty"]:
            F.append(
                finding(
                    "GEN.EMPTY",
                    "generation",
                    "MEDIUM" if m["empty"] / n >= 0.05 else "LOW",
                    "CONFIRMED",
                    f"Empty responses{tag}",
                    {"count": m["empty"], "rate": rnd(m["empty"] / n, 4)},
                    source,
                    "The model produced no text for these prompts.",
                    "Check stop sequences, EOS handling and chat template.",
                )
            )
        if m["degenerate_responses"] and m["degenerate_responses"] / n >= 0.10:
            worst = max(range(len(res["reps"])), key=lambda i: res["reps"][i])
            sample = [o for o, t in zip(res["outs"], res["toks"]) if t][worst]
            F.append(
                finding(
                    "GEN.REPETITION",
                    "generation",
                    "HIGH",
                    "CONFIRMED",
                    f"Degenerate repetition{tag}",
                    {
                        "degenerate_responses": m["degenerate_responses"],
                        "rate": rnd(m["degenerate_responses"] / n, 4),
                        "mean_repetition_rate": m["repetition_rate"]["mean"],
                        "decoding_params": m["decoding_params"],
                        "sample": redact(sample, 120),
                    },
                    source,
                    ">=10% of responses repeat more than half of their word 3-grams (looping output).",
                    "Try repetition_penalty 1.1-1.3, no_repeat_ngram_size, higher temperature/top-p; "
                    "check SFT data for repetitive targets and EOS supervision.",
                    "Re-generate the same prompts varying only one decoding parameter at a time.",
                )
            )
        d2 = m["distinct_2"]
        if d2 is not None and m["responses"] >= 20 and d2 < 0.3:
            F.append(
                finding(
                    "GEN.LOW_DIVERSITY",
                    "generation",
                    "MEDIUM",
                    "POTENTIAL",
                    f"Low lexical diversity{tag}",
                    {"distinct_2": d2, "distinct_1": m["distinct_1"], "mattr": m["mattr"]},
                    source,
                    "Fewer than 30% of bigrams across outputs are unique.",
                    "Compare with a reference corpus of similar length; adjust sampling.",
                )
            )
        nif = m["near_identical_fraction"]
        prompts = {str(r.get("prompt", i)) for i, r in enumerate(rs)}
        if nif is not None and m["responses"] >= 10 and nif >= 0.2 and len(prompts) > 1:
            F.append(
                finding(
                    "GEN.REDUNDANT",
                    "generation",
                    "MEDIUM",
                    "POTENTIAL",
                    f"Near-identical outputs across different prompts{tag}",
                    {"near_identical_fraction": nif, "mean_pairwise_similarity": m["mean_pairwise_similarity"]},
                    source,
                    "Many outputs share >=80% of their 3-grams despite different prompts "
                    "(possible mode collapse or template answers).",
                    "Inspect whether the model ignores the prompt; check SFT data diversity.",
                )
            )
        if m["finish_reason_length"] or m["reached_max_tokens"]:
            c = max(m["finish_reason_length"], m["reached_max_tokens"])
            F.append(
                finding(
                    "GEN.TRUNCATED",
                    "generation",
                    "MEDIUM" if c / n >= 0.1 else "LOW",
                    "CONFIRMED",
                    f"Responses cut by the token limit{tag}",
                    {"count": c, "rate": rnd(c / n, 4)},
                    source,
                    "finish_reason == length or output tokens reached max_tokens.",
                    "Raise max_new_tokens or investigate failure to emit EOS (often linked to repetition).",
                )
            )
        if m["short_responses"] / n >= 0.2:
            F.append(
                finding(
                    "GEN.SHORT",
                    "generation",
                    "LOW",
                    "POTENTIAL",
                    f"Many very short responses{tag}",
                    {"short_responses": m["short_responses"], "min_words": min_words},
                    source,
                    "At least 20% of responses are below the minimum word count.",
                    "Check whether short answers are expected for this task; inspect early EOS.",
                )
            )
        refs = [(o, str(r.get("reference") or r.get("references") or "")) for o, r in zip(res["outs"], rs)]
        refs = [(o, ref) for o, ref in refs if ref.strip() and o.strip()]
        if refs:
            tot = uns = 0
            nums: list[str] = []
            ex = ""
            for o, ref in refs:
                gr = grounding(o, ref)
                tot += gr["sentences"]
                uns += len(gr["unsupported"])
                nums += gr["numbers_not_in_reference"]
                ex = ex or (gr["unsupported"][0] if gr["unsupported"] else "")
            m["grounding"] = {
                "responses_with_reference": len(refs),
                "sentences": tot,
                "unsupported_sentences": uns,
                "numbers_not_in_reference": len(nums),
            }
            if tot and (uns / tot >= 0.2 or nums):
                F.append(
                    finding(
                        "GEN.UNSUPPORTED",
                        "generation",
                        "MEDIUM",
                        "POTENTIAL",
                        f"Statements not supported by the provided references{tag}",
                        {**m["grounding"], "unsupported_rate": rnd(uns / tot, 4), "example": redact(ex, 120)},
                        source,
                        "Sentences with <50% content-word overlap with the reference, or numbers absent "
                        "from it. Candidate hallucinations relative to the reference only.",
                        "Review flagged sentences manually or with an entailment model.",
                        "Annotate a sample of flagged vs. unflagged sentences to estimate precision.",
                    )
                )
    if len(groups) > 1:
        names = sorted(groups)
        base = names[0]
        comp = {}
        for g in names[1:]:
            a, b = raw[base]["reps"], raw[g]["reps"]
            if len(a) >= 5 and len(b) >= 5:
                d, lo, hi = _boot_diff(a, b, seed)
                comp[f"{g} vs {base}"] = {
                    "repetition_rate_diff": rnd(d, 4),
                    "ci95": [rnd(lo, 4), rnd(hi, 4)],
                    "significant": lo > 0 or hi < 0,
                    "params": {
                        base: metrics["groups"][base]["decoding_params"],
                        g: metrics["groups"][g]["decoding_params"],
                    },
                }
                if lo > 0 or hi < 0:
                    F.append(
                        finding(
                            "GEN.CONFIG_DIFF",
                            "generation",
                            "INFO",
                            "CONFIRMED",
                            f"Repetition differs between '{g}' and '{base}'",
                            comp[f"{g} vs {base}"],
                            source,
                            "Bootstrap 95% CI of the mean repetition-rate difference excludes 0. This shows a "
                            "difference in behaviour, not which parameter caused it.",
                            "Isolate the parameter by changing one setting at a time on identical prompts.",
                        )
                    )
        metrics["comparison"] = comp
    return result("generation", source, metrics, F, lim)


def analyze_file(path: Path, **kw: Any) -> dict[str, Any]:
    """Carrega um arquivo de saídas geradas e o analisa."""
    recs, info = load_table(path, kw.pop("max_records", 200_000))
    out = analyze_records(recs, path.name, **kw)
    out["parse"] = info
    return out
