"""Fine-Tuning & Experiment Inspector (regras CMP.*): compara duas execuções.

Uma execução pode ser um diretório (configs, métricas, logs, trainer_state.json) ou um
arquivo de log. Somente JSON/CSV são lidos; pesos nunca são desserializados.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from deepmodel_inspector.core.common import finding, load_table, result, rnd
from deepmodel_inspector.security.guard import UNSAFE_DESERIALIZATION, is_sensitive

CONFIG_FILES = (
    "config.json",
    "run_config.json",
    "hparams.json",
    "training_args.json",
    "args.json",
    "adapter_config.json",
    "experiment.json",
)
METRIC_FILES = ("metrics.json", "eval_results.json", "all_results.json", "results.json", "eval_metrics.json")
LOG_HINTS = ("trainer_state.json", "training", "train_log", "log", "metrics.csv", "history")
HP = {
    "learning_rate": ("learning_rate", "lr"),
    "per_device_batch": ("per_device_train_batch_size", "batch_size", "train_batch_size", "micro_batch_size"),
    "grad_accum": ("gradient_accumulation_steps",),
    "epochs": ("num_train_epochs", "epochs", "num_epochs"),
    "max_seq_length": ("max_seq_length", "max_length", "seq_len", "block_size", "sequence_length", "cutoff_len"),
    "method": ("method", "training_type", "finetuning_type", "stage"),
    "lora_r": ("lora_r", "r"),
    "lora_alpha": ("lora_alpha",),
    "warmup": ("warmup_ratio", "warmup_steps"),
    "weight_decay": ("weight_decay",),
    "scheduler": ("lr_scheduler_type", "scheduler"),
    "seed": ("seed",),
    "base_model": ("base_model_name_or_path", "model_name_or_path", "base_model"),
}
COMPAT = {
    "tokenizer": ("tokenizer", "tokenizer_name", "tokenizer_name_or_path", "tokenizer_hash"),
    "vocab_size": ("vocab_size",),
    "eval_dataset": ("eval_dataset", "eval_dataset_hash", "validation_file", "eval_file", "eval_data"),
    "eval_protocol": ("eval_protocol", "eval_harness", "eval_method"),
}
LOWER_BETTER = ("loss", "perplexity", "ppl", "error", "wer", "cer", "bpb", "bits_per")
HIGHER_BETTER = (
    "accuracy",
    "acc",
    "f1",
    "bleu",
    "rouge",
    "exact_match",
    "em",
    "pass@",
    "precision",
    "recall",
    "score",
    "win_rate",
    "mmlu",
    "meteor",
    "chrf",
)


def _read_json(p: Path) -> dict[str, Any]:
    """Lê um JSON de objeto (retorna {} se inválido ou não for objeto)."""
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def load_run(path: Path) -> dict[str, Any]:
    """Coleta config, métricas e curvas de uma execução."""
    run: dict[str, Any] = {"name": path.name, "config": {}, "metrics": {}, "curves": {}, "files": []}
    files = (
        [path]
        if path.is_file()
        else sorted(
            p
            for p in path.rglob("*")
            if p.is_file() and p.suffix.lower() in (".json", ".jsonl", ".csv") and p.stat().st_size < 50 * 2**20
        )
    )
    for p in files[:200]:
        low = p.name.lower()
        if is_sensitive(p) or p.suffix.lower() in UNSAFE_DESERIALIZATION:
            continue
        if low in CONFIG_FILES:
            run["config"].update({k: v for k, v in _read_json(p).items() if not isinstance(v, (dict, list))})
            run["files"].append(p.name)
        elif low in METRIC_FILES:
            run["metrics"].update({k: v for k, v in _read_json(p).items() if isinstance(v, (int, float))})
            run["files"].append(p.name)
        elif any(h in low for h in LOG_HINTS) or path.is_file():
            try:
                rows, _ = load_table(p)
            except ValueError:
                continue
            tr, va = _curve(rows, ("loss", "train_loss")), _curve(rows, ("eval_loss", "val_loss", "validation_loss"))
            if tr or va:
                run["curves"] = {"train_loss": tr, "val_loss": va}
                run["files"].append(p.name)
                if low == "trainer_state.json":
                    st = _read_json(p)
                    for k in ("best_metric", "global_step"):
                        if isinstance(st.get(k), (int, float)):
                            run["metrics"].setdefault(f"trainer_{k}", st[k])
    if run["curves"].get("val_loss"):
        run["metrics"].setdefault("curve_final_val_loss", run["curves"]["val_loss"][-1][1])
        run["metrics"].setdefault("curve_min_val_loss", min(v for _, v in run["curves"]["val_loss"]))
    if run["curves"].get("train_loss"):
        run["metrics"].setdefault("curve_final_train_loss", run["curves"]["train_loss"][-1][1])
    return run


def _curve(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[tuple[float, float]]:
    """Série (passo, valor) finita para a primeira chave disponível, ordenada por passo."""
    out = []
    for i, r in enumerate(rows):
        v = next((r[k] for k in keys if isinstance(r.get(k), (int, float))), None)
        x = r.get("step", r.get("global_step", i))
        if v is not None and isinstance(x, (int, float)) and math.isfinite(v):
            out.append((float(x), float(v)))
    return sorted(out)


def _get(cfg: dict[str, Any], names: tuple[str, ...]) -> Any:
    """Primeiro valor de configuração presente."""
    return next((cfg[n] for n in names if n in cfg and cfg[n] is not None), None)


def direction(metric: str) -> str:
    """'lower', 'higher' ou 'unknown' segundo o nome da métrica."""
    m = metric.lower()
    if any(t in m for t in LOWER_BETTER):
        return "lower"
    if any(t in m for t in HIGHER_BETTER):
        return "higher"
    return "unknown"


def compare_runs(a: dict[str, Any], b: dict[str, Any], tolerance: float = 0.01) -> dict[str, Any]:
    """Compara execução ``a`` (antes) com ``b`` (depois) aplicando as regras CMP.*."""
    src = f"{a['name']} -> {b['name']}"
    F: list[dict[str, Any]] = []
    lim: list[str] = ["Single-run differences do not establish statistical significance; repeat with several seeds."]
    hp = {}
    for k, names in HP.items():
        va, vb = _get(a["config"], names), _get(b["config"], names)
        if va is not None or vb is not None:
            hp[k] = {"before": va, "after": vb, "changed": va != vb}
    for r in (a, b):
        pd, ga = _get(r["config"], HP["per_device_batch"]), _get(r["config"], HP["grad_accum"]) or 1
        if isinstance(pd, (int, float)) and isinstance(ga, (int, float)):
            r["effective_batch"] = pd * ga
    if "effective_batch" in a or "effective_batch" in b:
        hp["effective_batch_per_device"] = {
            "before": a.get("effective_batch"),
            "after": b.get("effective_batch"),
            "changed": a.get("effective_batch") != b.get("effective_batch"),
        }
    changed = sorted(k for k, v in hp.items() if v["changed"])
    compat: dict[str, Any] = {}
    incompatible, unknown = [], []
    for k, names in COMPAT.items():
        va, vb = _get(a["config"], names), _get(b["config"], names)
        compat[k] = {"before": va, "after": vb}
        if va is None or vb is None:
            unknown.append(k)
        elif va != vb:
            incompatible.append(k)
    deltas = {}
    regress, improve = [], []
    for m in sorted(set(a["metrics"]) & set(b["metrics"])):
        va, vb = float(a["metrics"][m]), float(b["metrics"][m])
        d = direction(m)
        rel = (vb - va) / abs(va) if va else None
        worse = rel is not None and ((d == "lower" and rel > tolerance) or (d == "higher" and rel < -tolerance))
        better = rel is not None and ((d == "lower" and rel < -tolerance) or (d == "higher" and rel > tolerance))
        deltas[m] = {
            "before": rnd(va),
            "after": rnd(vb),
            "relative_change": rnd(rel, 4),
            "direction": d,
            "assessment": "regression"
            if worse
            else "improvement"
            if better
            else ("unknown_direction" if d == "unknown" else "within_tolerance"),
        }
        (regress if worse else improve if better else []).append(m)
    metrics = {
        "hyperparameters": hp,
        "changed_hyperparameters": changed,
        "compatibility": compat,
        "metric_deltas": deltas,
        "files": {"before": a["files"], "after": b["files"]},
    }
    comparable = not incompatible and "eval_dataset" not in unknown
    if incompatible:
        F.append(
            finding(
                "CMP.INCOMPATIBLE",
                "comparison",
                "MEDIUM",
                "INCONCLUSIVE",
                "Runs are not directly comparable",
                {"differs": incompatible, "compatibility": compat},
                src,
                "Tokenizer, vocabulary, evaluation data or protocol differ; loss and perplexity values are not "
                "on the same scale and are not compared as regressions.",
                "Re-evaluate both checkpoints with the same tokenizer-independent metric and the same eval set "
                "(e.g. bits-per-byte or task accuracy).",
            )
        )
    elif unknown:
        lim.append(f"Compatibility unverified for: {', '.join(unknown)} (not present in both configs).")
    ppl_like = ("loss", "perplexity", "ppl")
    for m in regress:
        if incompatible:
            continue
        is_ppl = any(t in m.lower() for t in ppl_like)
        status = "CONFIRMED" if comparable else "POTENTIAL"
        if is_ppl and "tokenizer" in unknown:
            status = "POTENTIAL"
        dd = deltas[m]
        F.append(
            finding(
                "CMP.REGRESSION",
                "comparison",
                "HIGH" if abs(dd["relative_change"] or 0) >= 0.05 else "MEDIUM",
                status,
                f"Metric regressed: {m}",
                {"metric": m, **dd, "changed_hyperparameters": changed},
                src,
                "The metric moved in the worse direction beyond the tolerance "
                f"({tolerance:.0%}). Status reflects whether evaluation compatibility was verified.",
                "Investigate the changed hyperparameters/data; changes listed are candidates, not proven causes.",
                "Revert one changed setting at a time (same seed and eval set) and re-measure.",
            )
        )
    if changed:
        F.append(
            finding(
                "CMP.HP_CHANGES",
                "comparison",
                "INFO",
                "CONFIRMED",
                "Hyperparameters changed between runs",
                {k: hp[k] for k in changed},
                src,
                "Several simultaneous changes prevent attributing an effect to any single one."
                if len(changed) > 1
                else "A single hyperparameter changed between runs.",
                "Plan ablations that vary one setting at a time."
                if len(changed) > 1
                else "Repeat with multiple seeds to confirm the effect.",
            )
        )
    ca, cb = a["curves"].get("val_loss"), b["curves"].get("val_loss")
    if ca and cb and not incompatible:
        ia = min(range(len(ca)), key=lambda i: ca[i][1])
        ib = min(range(len(cb)), key=lambda i: cb[i][1])
        metrics["curves"] = {
            "before": {"best_val_loss": rnd(ca[ia][1]), "best_step": ca[ia][0], "final": rnd(ca[-1][1])},
            "after": {"best_val_loss": rnd(cb[ib][1]), "best_step": cb[ib][0], "final": rnd(cb[-1][1])},
        }
        for nm, c, i in (("after", cb, ib), ("before", ca, ia)):
            if c[-1][1] > c[i][1] * 1.05 and len(c) - 1 - i >= 2:
                F.append(
                    finding(
                        "CMP.LATE_DEGRADATION",
                        "comparison",
                        "MEDIUM",
                        "CONFIRMED",
                        f"Validation loss of '{nm}' run ends >5% above its best",
                        {"run": nm, "best": rnd(c[i][1]), "final": rnd(c[-1][1]), "best_step": c[i][0]},
                        src,
                        "The final checkpoint is worse than an earlier one of the same run.",
                        "Compare the best checkpoints, not the final ones; consider early stopping.",
                    )
                )
    if not deltas and not (ca and cb):
        F.append(
            finding(
                "CMP.NO_COMMON_METRICS",
                "comparison",
                "INFO",
                "INCONCLUSIVE",
                "No common metrics to compare",
                {"before": sorted(a["metrics"]), "after": sorted(b["metrics"])},
                src,
                "The runs do not share metric names or validation curves.",
                "Export the same evaluation metrics (metrics.json / eval_results.json) for both runs.",
            )
        )
    return result("comparison", src, metrics, F, lim)


def analyze_paths(before: Path, after: Path, tolerance: float = 0.01) -> dict[str, Any]:
    """Carrega duas execuções e as compara."""
    return compare_runs(load_run(before), load_run(after), tolerance)
