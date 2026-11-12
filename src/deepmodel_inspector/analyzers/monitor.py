"""Monitoramento de produção a partir de logs exportados (regras MON.*).

Agrupa respostas por período (dia/semana pelo ``timestamp`` ou pelo nome do arquivo),
calcula indicadores por período reutilizando ``analyzers.generation`` e compara o período
mais recente com a linha de base (períodos anteriores). Somente leitura e offline.
"""

from __future__ import annotations

import datetime as dt
import random
import statistics
from pathlib import Path
from typing import Any

from deepmodel_inspector.analyzers import generation
from deepmodel_inspector.core.common import finding, load_table, result, rnd

DEFAULT_THRESHOLDS = {
    "error_rate": 0.05,
    "p95_latency_ms": 10_000.0,
    "degenerate_rate": 0.10,
    "empty_rate": 0.05,
    "truncation_rate": 0.10,
    "distinct2_drop": 0.25,
}
TS_KEYS = ("timestamp", "created_at", "time", "ts", "date", "created")


def _parse_ts(v: Any) -> dt.datetime | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            return dt.datetime.fromtimestamp(v / 1000 if v > 1e12 else v, tz=dt.UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(v, str) and v.strip():
        s = v.strip().replace("Z", "+00:00")
        try:
            return dt.datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


def period_of(rec: dict[str, Any], fallback: str, period: str) -> str:
    """Rótulo do período: dia (AAAA-MM-DD) ou semana ISO (AAAA-Www); senão o nome do arquivo."""
    if rec.get("period"):
        return str(rec["period"])
    ts = next((_parse_ts(rec[k]) for k in TS_KEYS if k in rec and _parse_ts(rec[k])), None)
    if ts is None:
        return fallback
    if period == "week":
        y, w, _ = ts.isocalendar()
        return f"{y}-W{w:02d}"
    return ts.strftime("%Y-%m-%d")


def _bucket_metrics(recs: list[dict[str, Any]]) -> tuple[dict[str, Any], list[float]]:
    g = generation.analyze_group(recs, 3, 13)
    m = g["metrics"]
    n = max(1, m["responses"])
    errors = sum(1 for r in recs if r.get("error") or str(r.get("status", "")).lower() in ("error", "failed"))
    lat = sorted(float(r["latency_ms"]) for r in recs if isinstance(r.get("latency_ms"), (int, float)))
    trunc = max(m["finish_reason_length"], m["reached_max_tokens"])
    out = {
        "requests": len(recs),
        "error_rate": rnd(errors / n, 4),
        "empty_rate": rnd(m["empty"] / n, 4),
        "degenerate_rate": rnd(m["degenerate_responses"] / n, 4),
        "truncation_rate": rnd(trunc / n, 4),
        "distinct_2": m["distinct_2"],
        "mean_repetition": m["repetition_rate"]["mean"],
        "mean_length_words": m["length_words"]["mean"],
        "latency_p50_ms": rnd(statistics.median(lat), 1) if lat else None,
        "latency_p95_ms": rnd(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 1) if lat else None,
    }
    return out, g["reps"]


def analyze_records(
    groups: dict[str, list[dict[str, Any]]],
    source: str = "",
    thresholds: dict[str, float] | None = None,
    seed: int = 13,
) -> dict[str, Any]:
    """Executa as regras MON.* sobre registros já agrupados por período (ordem cronológica pelo rótulo)."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    labels = sorted(groups)
    timeline, reps = [], {}
    for lb in labels:
        m, r = _bucket_metrics(groups[lb])
        timeline.append({"period": lb, **m})
        reps[lb] = r
    F: list[dict[str, Any]] = []
    lim = [
        "Monitoring is batch-based on exported logs; it is not real-time.",
        "Quality signals are lexical (repetition, diversity, emptiness, truncation); correctness needs references or probes.",
    ]
    metrics: dict[str, Any] = {"periods": len(labels), "timeline": timeline, "thresholds": th}
    if not labels:
        F.append(
            finding(
                "MON.NO_DATA",
                "monitor",
                "INFO",
                "INCONCLUSIVE",
                "No production records found",
                {},
                source,
                "No log records with an output field were found.",
                "Export logs as JSONL with output/response fields.",
            )
        )
        return result("monitor", source, metrics, F, lim)
    cur = timeline[-1]
    lb = cur["period"]
    checks = [
        ("error_rate", "MON.ERRORS", "Error rate above threshold", "HIGH"),
        ("degenerate_rate", "MON.REPETITION", "Degenerate repetition above threshold", "HIGH"),
        ("empty_rate", "MON.EMPTY", "Empty responses above threshold", "MEDIUM"),
        ("truncation_rate", "MON.TRUNCATION", "Responses cut by the token limit above threshold", "MEDIUM"),
        ("latency_p95_ms", "MON.LATENCY", "p95 latency above threshold", "MEDIUM"),
    ]
    for key, rule, title, sev in checks:
        v = cur.get(key)
        if v is not None and v > th[{"latency_p95_ms": "p95_latency_ms"}.get(key, key)]:
            F.append(
                finding(
                    rule,
                    "monitor",
                    sev,
                    "CONFIRMED",
                    f"{title} ({lb})",
                    {
                        "period": lb,
                        key: v,
                        "threshold": th[{"latency_p95_ms": "p95_latency_ms"}.get(key, key)],
                        "requests": cur["requests"],
                    },
                    source,
                    "The most recent period breached the configured threshold.",
                    "Inspect the period's samples, recent deployments, prompt/template or decoding changes.",
                )
            )
    if len(labels) < 2:
        F.append(
            finding(
                "MON.NO_BASELINE",
                "monitor",
                "INFO",
                "INCONCLUSIVE",
                "Drift not assessed (single period)",
                {"periods": 1},
                source,
                "At least two periods are needed to compare against a baseline.",
                "Keep exporting logs per day/week.",
            )
        )
    else:
        base = [x for b in labels[:-1] for x in reps[b]]
        now = reps[lb]
        if len(base) >= 5 and len(now) >= 5:
            rng = random.Random(seed)
            d = statistics.fmean(now) - statistics.fmean(base)
            boots = sorted(
                statistics.fmean(rng.choices(now, k=len(now))) - statistics.fmean(rng.choices(base, k=len(base)))
                for _ in range(1000)
            )
            lo, hi = boots[25], boots[974]
            metrics["repetition_drift"] = {"diff": rnd(d, 4), "ci95": [rnd(lo, 4), rnd(hi, 4)]}
            if lo > 0:
                F.append(
                    finding(
                        "MON.DRIFT_REPETITION",
                        "monitor",
                        "MEDIUM",
                        "POTENTIAL",
                        f"Repetition increased in {lb}",
                        {"period": lb, "diff": rnd(d, 4), "ci95": [rnd(lo, 4), rnd(hi, 4)]},
                        source,
                        "Bootstrap 95% CI of the mean repetition-rate difference vs. previous periods is above 0.",
                        "Correlate with deployments (model, template, decoding) in that period.",
                    )
                )
        prev_d2 = [t["distinct_2"] for t in timeline[:-1] if t["distinct_2"] is not None]
        if prev_d2 and cur["distinct_2"] is not None:
            ref = statistics.fmean(prev_d2)
            drop = (ref - cur["distinct_2"]) / ref if ref else 0
            if drop > th["distinct2_drop"]:
                F.append(
                    finding(
                        "MON.DIVERSITY_DROP",
                        "monitor",
                        "MEDIUM",
                        "POTENTIAL",
                        f"Lexical diversity dropped in {lb}",
                        {
                            "period": lb,
                            "distinct_2": cur["distinct_2"],
                            "baseline": rnd(ref, 4),
                            "relative_drop": rnd(drop, 4),
                        },
                        source,
                        "Distinct-2 fell by more than the threshold vs. the baseline average.",
                        "Check for template answers, mode collapse or traffic mix change.",
                    )
                )
    if not any(f["severity"] in ("CRITICAL", "HIGH", "MEDIUM") for f in F):
        F.append(
            finding(
                "MON.OK",
                "monitor",
                "INFO",
                "CONFIRMED",
                f"No threshold breached ({lb})",
                {"period": lb},
                source,
                "All monitored indicators of the latest period are within thresholds.",
                "Continue monitoring.",
            )
        )
    return result("monitor", source, metrics, F, lim)


def analyze_paths(
    paths: list[Path], period: str = "day", thresholds: dict[str, float] | None = None, max_records: int = 200_000
) -> dict[str, Any]:
    """Lê arquivos de log (JSONL/CSV/JSON) e agrupa por período."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for p in sorted(paths):
        recs, _ = load_table(p, max_records)
        for r in recs:
            if any(k in r for k in generation.OUTPUT_KEYS):
                groups.setdefault(period_of(r, p.stem, period), []).append(r)
    return analyze_records(groups, ", ".join(p.name for p in paths)[:200], thresholds)
