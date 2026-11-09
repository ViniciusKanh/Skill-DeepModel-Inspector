"""Training Health Diagnostics: análise de logs de treino/validação.

Regras documentadas em docs/diagnostic-methodology.md (prefixo TRN.*).
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any

from deepmodel_inspector.core.common import (
    describe,
    finding,
    finite,
    load_table,
    mad,
    pearson,
    result,
    rnd,
    slope,
    spearman,
    to_float,
)

ALIASES = {
    "step": ("step", "global_step", "iteration", "iter", "steps"),
    "epoch": ("epoch", "epochs"),
    "train_loss": ("train_loss", "loss", "training_loss", "train/loss"),
    "val_loss": ("eval_loss", "val_loss", "validation_loss", "valid_loss", "eval/loss", "val/loss"),
    "lr": ("learning_rate", "lr", "train/learning_rate"),
    "grad_norm": ("grad_norm", "gradient_norm", "train/grad_norm", "gnorm"),
    "val_ppl": ("eval_perplexity", "val_perplexity", "perplexity", "ppl", "eval_ppl"),
}
MIN_POINTS = 5


def _pick(row: dict[str, Any], key: str) -> Any:
    """Retorna o primeiro alias presente na linha."""
    for a in ALIASES[key]:
        if a in row and row[a] is not None:
            return row[a]
    return None


def extract_series(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Extrai séries (passo, valor) por métrica, respeitando a ordem temporal.

    Linhas sem passo usam a época ou o índice. Retorna também problemas de ordenação.
    """
    series: dict[str, list[tuple[float, float]]] = {k: [] for k in ALIASES if k not in ("step", "epoch")}
    unordered = 0
    last = -math.inf
    for i, row in enumerate(rows):
        x = to_float(_pick(row, "step"))
        if x is None:
            ep = to_float(_pick(row, "epoch"))
            x = ep if ep is not None else float(i)
        if x < last:
            unordered += 1
        last = max(last, x)
        for key in series:
            v = to_float(_pick(row, key))
            if v is not None:
                series[key].append((x, v))
    for key in series:
        series[key].sort(key=lambda t: t[0])
    return {"series": series, "unordered_rows": unordered}


def _windows(vals: list[float], k: int = 4) -> list[list[float]]:
    """Divide a série em k janelas consecutivas."""
    n = len(vals)
    size = max(1, n // k)
    return [vals[i * size : (i + 1) * size if i < k - 1 else n] for i in range(k) if vals[i * size :]]


def _summary(points: list[tuple[float, float]]) -> dict[str, Any]:
    """Resumo estatístico de uma série com inclinação, variação e estabilidade por janela."""
    xs = [p[0] for p in points if math.isfinite(p[1])]
    ys = [p[1] for p in points if math.isfinite(p[1])]
    d: dict[str, Any] = describe(ys)
    d["non_finite"] = len(points) - len(ys)
    if len(ys) >= 2:
        d["first"], d["last"] = rnd(ys[0]), rnd(ys[-1])
        d["slope_per_1k_steps"] = rnd((slope(xs, ys) or 0.0) * 1000)
        d["relative_change"] = rnd((ys[-1] - ys[0]) / abs(ys[0])) if ys[0] else None
        d["argmin_step"] = xs[ys.index(min(ys))]
        d["window_std"] = [rnd(statistics.pstdev(w)) if len(w) > 1 else 0.0 for w in _windows(ys)]
        d["window_mean"] = [rnd(statistics.fmean(w)) for w in _windows(ys)]
    return d


def _spikes(ys: list[float], factor: float = 6.0) -> list[int]:
    """Índices de picos: desvio do resíduo (vs. mediana móvel) acima de ``factor``·MAD global."""
    if len(ys) < 7:
        return []
    resid = [0.0] * len(ys)
    for i in range(3, len(ys) - 3):  # somente pontos internos: evita efeito de borda em curvas íngremes
        resid[i] = ys[i] - statistics.median(ys[i - 3 : i + 4])
    scale = mad(resid) or 1e-12
    floor = 0.02 * (statistics.median([abs(y) for y in ys]) or 1.0)
    return [i for i, r in enumerate(resid) if r > max(factor * scale * 1.4826, floor)]


def analyze_rows(rows: list[dict[str, Any]], source: str = "") -> dict[str, Any]:
    """Executa todas as regras TRN.* sobre linhas de log já carregadas."""
    ext = extract_series(rows)
    s = ext["series"]
    tr, va, lr, gn = s["train_loss"], s["val_loss"], s["lr"], s["grad_norm"]
    F: list[dict[str, Any]] = []
    lim: list[str] = []
    metrics: dict[str, Any] = {"rows": len(rows), "unordered_rows": ext["unordered_rows"]}
    for key, pts in s.items():
        if pts:
            metrics[key] = _summary(pts)
    if ext["unordered_rows"]:
        F.append(
            finding(
                "TRN.ORDER",
                "training",
                "LOW",
                "CONFIRMED",
                "Log rows are not in step order",
                {"unordered_rows": ext["unordered_rows"]},
                source,
                "Rows were re-sorted by step before analysis; resumed runs or merged logs often cause this.",
                "Verify that logs from resumed runs were not duplicated or overlapped.",
            )
        )
    if not tr and not va:
        F.append(
            finding(
                "TRN.NO_LOSS",
                "training",
                "INFO",
                "INCONCLUSIVE",
                "No loss columns found",
                {"columns": sorted({k for r in rows[:50] for k in r})[:30]},
                source,
                "None of the recognized loss column names were present.",
                "Provide a log with 'loss'/'train_loss' and optionally 'eval_loss' per step.",
            )
        )
        return result("training", source, metrics, F, ["No loss series available."])

    # TRN.NONFINITE: NaN/Inf em loss ou grad norm
    for name, pts in (("train_loss", tr), ("val_loss", va), ("grad_norm", gn)):
        bad = [p[0] for p in pts if not math.isfinite(p[1])]
        if bad:
            F.append(
                finding(
                    "TRN.NONFINITE",
                    "training",
                    "CRITICAL",
                    "CONFIRMED",
                    f"Non-finite values (NaN/Inf) in {name}",
                    {"metric": name, "count": len(bad), "first_step": bad[0]},
                    source,
                    "Non-finite values mean the optimization numerically diverged at or before this step.",
                    "Lower the learning rate, enable gradient clipping, check mixed-precision loss scaling "
                    "and inspect the batch at the first failing step.",
                    "Resume from the last finite checkpoint with a lower LR and confirm values stay finite.",
                )
            )
    ys = finite([p[1] for p in tr])
    xs = [p[0] for p in tr if math.isfinite(p[1])]
    if len(ys) < MIN_POINTS:
        lim.append(f"Training loss has fewer than {MIN_POINTS} finite points; trend rules skipped.")
    else:
        q = max(2, len(ys) // 5)
        head, tail = statistics.fmean(ys[:q]), statistics.fmean(ys[-q:])
        lo = min(ys)
        third = max(3, len(ys) // 3)
        tail_slope = slope(xs[-third:], ys[-third:]) or 0.0
        rel_tail = tail_slope * (xs[-1] - xs[-third]) / (abs(lo) or 1.0)
        ev = {"head_mean": rnd(head), "tail_mean": rnd(tail), "min": rnd(lo), "tail_relative_trend": rnd(rel_tail)}
        if tail > head and tail > 1.5 * lo:
            F.append(
                finding(
                    "TRN.DIVERGENCE",
                    "training",
                    "HIGH",
                    "CONFIRMED",
                    "Training loss diverged",
                    ev,
                    source,
                    "The final-window mean loss is above the initial-window mean and >1.5x "
                    "the minimum, so training ended worse than it started.",
                    "Reduce the learning rate or increase warmup; enable gradient clipping.",
                    "Re-run from the best checkpoint with LR halved and compare the tail trend.",
                )
            )
        elif tail > 1.3 * lo and rel_tail > 0.1:
            F.append(
                finding(
                    "TRN.DIVERGENCE",
                    "training",
                    "MEDIUM",
                    "POTENTIAL",
                    "Training loss is rising late in training",
                    ev,
                    source,
                    "The last third of the curve trends upward and is >1.3x the minimum.",
                    "Check LR schedule, data order (shuffling) and gradient norms near the rise.",
                    "Re-run the last segment with a lower LR; if the rise disappears, LR is implicated.",
                )
            )
        improve = (head - tail) / abs(head) if head else 0.0
        metrics["train_relative_improvement"] = rnd(improve)
        late = ys[-third:]
        late_imp = (late[0] - late[-1]) / abs(late[0]) if late[0] else 0.0
        if improve < 0.10 and tail <= head and len(ys) >= 10:
            F.append(
                finding(
                    "TRN.UNDERFIT",
                    "training",
                    "MEDIUM",
                    "POTENTIAL",
                    "Little learning progress (possible underfitting)",
                    {"relative_improvement": rnd(improve), "points": len(ys)},
                    source,
                    "Training loss improved by less than 10% between the first and last windows.",
                    "Check LR (may be too low), model capacity, label/target formatting and data loading.",
                    "Run a short LR range test or overfit a tiny subset (~100 examples); if it cannot "
                    "overfit, suspect a pipeline bug.",
                )
            )
        elif improve >= 0.10 and abs(late_imp) < 0.01 and abs(rel_tail) < 0.02:
            F.append(
                finding(
                    "TRN.PLATEAU",
                    "training",
                    "LOW",
                    "POTENTIAL",
                    "Training loss plateaued",
                    {"late_relative_improvement": rnd(late_imp), "overall_improvement": rnd(improve)},
                    source,
                    "Loss improved overall but changed <1% over the last third of training. This may be "
                    "normal convergence or a stalled schedule.",
                    "Compare with validation metrics; consider LR decay, more data or early stopping.",
                    "Extend training briefly with a decayed LR and check whether validation improves.",
                )
            )
        sp = _spikes(ys)
        metrics["train_loss_spikes"] = len(sp)
        if len(sp) >= 3 or (len(ys) >= 20 and len(sp) / len(ys) > 0.05):
            spike_steps = [xs[i] for i in sp]
            ev2: dict[str, Any] = {"spikes": len(sp), "first_steps": spike_steps[:5]}
            F.append(
                finding(
                    "TRN.INSTABILITY",
                    "training",
                    "MEDIUM",
                    "POTENTIAL",
                    "Unstable loss with repeated spikes",
                    ev2,
                    source,
                    "Several points exceed the local median by >6 robust deviations.",
                    "Inspect batches at spike steps, enable gradient clipping, check LR peaks and fp16 overflow.",
                    "Re-run with clipping (e.g. 1.0) and a lower peak LR; count spikes again.",
                )
            )
            lrd = dict(lr)
            if lrd:
                peak = max(lrd.values()) or 0.0
                near = [x for x in spike_steps if x in lrd and lrd[x] >= 0.9 * peak]
                if peak > 0 and len(near) >= max(2, len(spike_steps) // 2):
                    F.append(
                        finding(
                            "TRN.LR_HIGH",
                            "training",
                            "MEDIUM",
                            "POTENTIAL",
                            "Loss spikes coincide with peak learning rate",
                            {"spikes_at_peak_lr": len(near), "peak_lr": peak},
                            source,
                            "Most spikes occur while LR is >=90% of its peak; this is an association, not proof.",
                            "Lower peak LR or lengthen warmup.",
                            "A/B run with 0.5x peak LR, same seed and data order.",
                        )
                    )
    # Correlação descritiva LR x loss
    if lr and len(tr) >= MIN_POINTS:
        lrd = dict(lr)
        pairs = [(lrd[x], y) for x, y in tr if x in lrd and math.isfinite(y)]
        if len(pairs) >= MIN_POINTS:
            a, b = [p[0] for p in pairs], [p[1] for p in pairs]
            metrics["lr_loss_spearman"] = rnd(spearman(a, b), 4)
            metrics["lr_loss_pearson"] = rnd(pearson(a, b), 4)
    # Validação / overfitting
    vys = finite([p[1] for p in va])
    vxs = [p[0] for p in va if math.isfinite(p[1])]
    if len(vys) < 3:
        F.append(
            finding(
                "TRN.NO_VALIDATION",
                "training",
                "INFO",
                "INCONCLUSIVE",
                "Overfitting cannot be assessed without validation loss",
                {"validation_points": len(vys)},
                source,
                "At least 3 validation points aligned with training are required.",
                "Log eval_loss periodically (e.g. every N steps) on a held-out set.",
            )
        )
    else:
        imin = vys.index(min(vys))
        after = vys[imin:]
        rises = sum(1 for i in range(1, len(after)) if after[i] > after[i - 1])
        rel_rise = (vys[-1] - vys[imin]) / abs(vys[imin]) if vys[imin] else 0.0
        tr_after = [y for x, y in zip(xs, ys) if x >= vxs[imin]] if ys else []
        tr_slope = slope(list(range(len(tr_after))), tr_after) if len(tr_after) >= 2 else None
        gap_series = []
        trd = dict(zip(xs, ys))
        for x, v in zip(vxs, vys):
            near = min(trd, key=lambda t: abs(t - x)) if trd else None
            if near is not None:
                gap_series.append(v - trd[near])
        metrics["val_train_gap"] = {
            "first": rnd(gap_series[0]) if gap_series else None,
            "last": rnd(gap_series[-1]) if gap_series else None,
        }
        ev = {
            "best_val_step": vxs[imin],
            "best_val_loss": rnd(vys[imin]),
            "final_val_loss": rnd(vys[-1]),
            "relative_rise": rnd(rel_rise),
            "increases_after_best": rises,
            "train_slope_after_best": rnd(tr_slope) if tr_slope is not None else None,
        }
        if rel_rise >= 0.05 and rises >= 2 and tr_slope is not None and tr_slope < 0:
            status = "CONFIRMED" if rises >= 3 else "POTENTIAL"
            F.append(
                finding(
                    "TRN.OVERFIT",
                    "training",
                    "HIGH",
                    status,
                    "Validation loss rises while training loss falls (overfitting pattern)",
                    ev,
                    source,
                    "After its minimum, validation loss rose >=5% across repeated evaluations while "
                    "training loss kept decreasing - the observable signature of overfitting.",
                    f"Use the checkpoint near step {vxs[imin]:g}; add early stopping, regularization "
                    "(dropout/weight decay), more or deduplicated data, or fewer epochs.",
                    "Re-train with early stopping on eval_loss and compare held-out task metrics.",
                )
            )
        elif len(gap_series) >= 3 and all(g < 0 for g in gap_series[len(gap_series) // 2 :]):
            F.append(
                finding(
                    "TRN.VAL_BELOW_TRAIN",
                    "training",
                    "LOW",
                    "POTENTIAL",
                    "Validation loss consistently below training loss",
                    {"last_gap": rnd(gap_series[-1])},
                    source,
                    "Can be normal (dropout active only in training, loss averaging) but also occurs "
                    "when validation data overlaps the training data or is easier.",
                    "Run the leakage check between train and validation sets.",
                    "deepmodel leakage --train <train> --test <validation>",
                )
            )
    # Grad norm
    gys = finite([p[1] for p in gn])
    if len(gys) >= MIN_POINTS:
        med = statistics.median(gys)
        big = [i for i, g in enumerate(gys) if med > 0 and g > 10 * med]
        metrics["grad_norm_explosions"] = len(big)
        if big:
            F.append(
                finding(
                    "TRN.GRAD_EXPLOSION",
                    "training",
                    "HIGH",
                    "POTENTIAL",
                    "Gradient norm explosions",
                    {"count": len(big), "median": rnd(med), "max": rnd(max(gys))},
                    source,
                    "Gradient norm exceeded 10x its median at least once.",
                    "Enable/lower gradient clipping and check the LR and data at those steps.",
                    "Re-run with max_grad_norm=1.0 and confirm the explosions disappear.",
                )
            )
        q = max(2, len(gys) // 5)
        head_g, tail_g = statistics.median(gys[:q]), statistics.median(gys[-q:])
        if head_g > 0 and tail_g < 1e-3 * head_g:
            F.append(
                finding(
                    "TRN.GRAD_VANISH",
                    "training",
                    "MEDIUM",
                    "POTENTIAL",
                    "Gradient norm collapsed toward zero",
                    {"head_median": rnd(head_g), "tail_median": rnd(tail_g)},
                    source,
                    "Final gradient norms are <0.1% of initial ones; updates may have stalled.",
                    "Check LR schedule end value, frozen parameters and loss masking.",
                    "Inspect the count of trainable parameters and the LR at the final steps.",
                )
            )
    elif not gn:
        lim.append("Gradient norm not logged; gradient rules not evaluated (no inference from loss alone).")
    # Perplexidade: usa coluna explícita; senão deriva exp(loss) assumindo entropia cruzada em nats
    if s["val_ppl"]:
        metrics["perplexity_source"] = "logged"
    elif vys:
        ppl = [math.exp(v) for v in vys if v < 50]
        metrics["val_perplexity_derived"] = describe(ppl)
        metrics["perplexity_source"] = "derived exp(eval_loss), assumes mean token cross-entropy in nats"
    chart = {k: _down(v) for k, v in (("train_loss", tr), ("val_loss", va)) if v}
    return result("training", source, metrics, F, lim, series=chart)


def _down(points: list[tuple[float, float]], n: int = 200) -> list[list[float]]:
    """Reduz a série para no máximo ``n`` pontos finitos (para gráficos)."""
    pts = [[p[0], p[1]] for p in points if math.isfinite(p[1])]
    step = max(1, len(pts) // n)
    return pts[::step]


def analyze_file(path: Path, max_records: int = 200_000) -> dict[str, Any]:
    """Carrega um log (CSV/JSON/JSONL/trainer_state.json) e o analisa."""
    rows, info = load_table(path, max_records)
    out = analyze_rows(rows, path.name)
    out["parse"] = info
    return out
