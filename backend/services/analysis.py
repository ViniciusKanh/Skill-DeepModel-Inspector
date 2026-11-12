"""Orquestração das análises reutilizando DIRETAMENTE o motor ``deepmodel_inspector``.

Nenhum algoritmo científico é reimplementado aqui: este módulo apenas expande os itens
de um experimento em inventário, despacha cada artefato ao analisador correspondente do
motor (com verificação de cancelamento e progresso real) e prepara dados para gráficos.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from deepmodel_inspector.analyzers import checkpoint, compare, dataset, generation, leakage, tokenizer, training
from deepmodel_inspector.core.common import load_table, redact
from deepmodel_inspector.diagnostics import inventory as inv_mod
from deepmodel_inspector.parsers.records import detect_format, split_parts, words
from deepmodel_inspector.security.guard import safe_input_path

CAPABILITIES = [
    ("audit", "deepmodel audit", "Every applicable analysis on an experiment", "directory or selected files"),
    (
        "investigate",
        "deepmodel investigate",
        "Evidence-based answer, hypotheses and experiments",
        "experiment + question",
    ),
    ("train", "deepmodel train", "Training/validation log health (TRN.*)", "CSV/JSONL log, trainer_state.json"),
    ("dataset", "deepmodel dataset", "Dataset quality (DAT.*)", "JSONL/JSON/CSV/TXT dataset"),
    ("leakage", "deepmodel leakage", "Train vs eval overlap (LEK.*)", "train file + eval file(s)"),
    ("tokenizer", "deepmodel tokenizer", "Tokenizer efficiency from provided tokens (TOK.*)", "JSONL text+tokens"),
    ("generation", "deepmodel generation", "Generated output behaviour (GEN.*)", "JSONL outputs"),
    ("compare", "deepmodel compare", "Run comparison with compatibility guard (CMP.*)", "two run directories"),
    ("checkpoint", "deepmodel checkpoint", "Safe checkpoint metadata (CKP.*)", "checkpoint directory"),
    (
        "probe",
        "deepmodel probe",
        "Live behavioural inspection of a local or online model (PRB.*)",
        "OpenAI-compatible endpoint",
    ),
    ("monitor", "deepmodel monitor", "Production monitoring from exported logs (MON.*)", "JSONL/CSV logs per day/week"),
]


class Cancelled(Exception):
    """Execução cancelada pelo usuário."""


def resolve(root: str, rel: str, settings: dict[str, Any], allow_dir: bool = False) -> Path:
    """Resolve ``rel`` relativo à raiz do projeto e valida com o guard do motor."""
    p = Path(rel)
    full = p if p.is_absolute() else Path(root) / p
    return safe_input_path(full, settings["allowed_roots"], settings["max_mb"], allow_dir=allow_dir)


def expand(root: str, items: list[str], settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Expande itens (arquivos/diretórios) em inventário classificado pelo motor."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in items:
        p = resolve(root, it, settings, allow_dir=True)
        entries = inv_mod.scan(p) if p.is_dir() else [inv_mod.classify(p)]
        for e in entries:
            if e["path"] not in seen:
                seen.add(e["path"])
                out.append(e)
    return out


def relpath(path: str, root: str) -> str:
    """Caminho relativo à raiz do projeto (sem expor diretórios do usuário)."""
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(path).name


def run_audit(
    inv: list[dict[str, Any]],
    settings: dict[str, Any],
    cancel: threading.Event,
    progress: Callable[[int, int, str], None],
) -> list[dict[str, Any]]:
    """Mesma lógica de despacho de ``inventory.run_audit``, com cancelamento e progresso por etapa."""
    mr = settings["max_records"]
    runs = [i for i in inv if i["kind"] == "run"]
    run_dirs = {i["path"] for i in runs}
    steps: list[tuple[str, Callable[[], dict[str, Any]]]] = []
    for it in inv:
        p = Path(it["path"])
        if len(run_dirs) >= 2 and str(p.parent) in run_dirs:
            it["note"] = "analyzed via run comparison"
            continue
        fn = {
            "training_log": lambda p=p: training.analyze_file(p, mr),
            "dataset": lambda p=p: dataset.analyze_file(p, max_records=mr),
            "tokenized": lambda p=p: tokenizer.analyze_file(p, max_records=mr),
            "generations": lambda p=p: generation.analyze_file(p, max_records=mr),
        }.get(it["kind"])
        if fn:
            steps.append((it["name"], fn))
    datasets = [i for i in inv if i["kind"] == "dataset"]
    evals = [Path(i["path"]) for i in datasets if i.get("split") in ("validation", "test")]
    for t in [i for i in datasets if i.get("split") == "train"]:
        same = [e for e in evals if e.parent == Path(t["path"]).parent] or evals
        if same:
            steps.append(
                (f"leakage {t['name']}", lambda t=t, s=same: leakage.analyze_files(Path(t["path"]), s, max_records=mr))
            )
    if len(runs) >= 2:
        for r in runs[1:]:
            steps.append(
                (
                    f"compare {runs[0]['name']} -> {r['name']}",
                    lambda r=r: compare.analyze_paths(Path(runs[0]["path"]), Path(r["path"])),
                )
            )
    for d in sorted({str(Path(i["path"]).parent) for i in inv if i["kind"] == "checkpoint"}):
        steps.append((f"checkpoint {Path(d).name}", lambda d=d: checkpoint.analyze_dir(Path(d))))
    results = []
    for n, (label, fn) in enumerate(steps):
        if cancel.is_set():
            raise Cancelled()
        progress(n, len(steps), label)
        try:
            results.append(fn())
        except ValueError as exc:
            for it in inv:
                if it["name"] == label:
                    it["error"] = str(exc)[:200]
    progress(len(steps), len(steps), "done")
    return results


def run_single(kind: str, root: str, params: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    """Executa uma análise individual do motor com parâmetros validados."""
    mr = settings["max_records"]

    def f(key: str, allow_dir: bool = False) -> Path:
        if not params.get(key):
            raise ValueError(f"missing parameter: {key}")
        return resolve(root, str(params[key]), settings, allow_dir)

    def opt_int(key: str) -> int | None:
        v = params.get(key)
        return int(v) if v not in (None, "") else None

    if kind == "train":
        return training.analyze_file(f("path"), mr)
    if kind == "dataset":
        return dataset.analyze_file(f("path"), params.get("text_field") or None, mr)
    if kind == "leakage":
        tests = params.get("tests") or []
        if not tests:
            raise ValueError("missing parameter: tests")
        return leakage.analyze_files(
            f("train"), [resolve(root, t, settings) for t in tests], params.get("text_field") or None, mr
        )
    if kind == "tokenizer":
        return tokenizer.analyze_file(
            f("path"),
            max_records=mr,
            max_length=opt_int("max_length"),
            vocab_size=opt_int("vocab_size"),
            unk_token=params.get("unk_token") or None,
            pad_token=params.get("pad_token") or None,
        )
    if kind == "generation":
        return generation.analyze_file(f("path"), max_records=mr, group_field=params.get("group_field") or None)
    if kind == "compare":
        return compare.analyze_paths(f("before", True), f("after", True), float(params.get("tolerance") or 0.01))
    if kind == "checkpoint":
        return checkpoint.analyze_dir(f("path", True))
    raise ValueError(f"unsupported analysis: {kind}")


# --------------------------------------------------------------- dados para gráficos
def _down(points: list[tuple[float, float]], n: int = 800) -> list[list[float | None]]:
    step = max(1, math.ceil(len(points) / n))
    return [[x, y if math.isfinite(y) else None] for x, y in points[::step]]


def series(path: Path, settings: dict[str, Any]) -> dict[str, Any]:
    """Séries completas de um log (via ``training.extract_series`` do motor) para gráficos.

    Perplexidade derivada = exp(eval_loss), rotulada como derivada (mesma premissa do motor).
    """
    rows, info = load_table(path, settings["max_records"])
    ext = training.extract_series(rows)
    s = ext["series"]
    out = {k: _down(v) for k, v in s.items() if v}
    ppl_source = "logged" if s["val_ppl"] else None
    if not s["val_ppl"] and s["val_loss"]:
        out["val_ppl"] = _down([(x, math.exp(v)) for x, v in s["val_loss"] if math.isfinite(v) and v < 50])
        ppl_source = "derived exp(eval_loss)"
    return {"series": out, "perplexity_source": ppl_source, "rows": len(rows), "parse": info}


def lengths(path: Path, settings: dict[str, Any], text_field: str | None = None) -> dict[str, Any]:
    """Histograma de comprimento (palavras) usando os parsers de formato do motor."""
    recs, _ = load_table(path, settings["max_records"])
    lens = []
    for r in recs:
        fmt = detect_format(r, text_field)
        p, q = split_parts(r, fmt, text_field)
        lens.append(len(words(p + " " + q)))
    edges = [0, 1, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]
    bins = []
    for i, lo in enumerate(edges):
        hi = edges[i + 1] if i + 1 < len(edges) else None
        c = sum(1 for v in lens if v >= lo and (hi is None or v < hi))
        bins.append({"label": f"{lo}" if hi == lo + 1 else (f"{lo}-{hi - 1}" if hi else f"≥{lo}"), "count": c})
    return {"records": len(lens), "bins": bins}


def preview(path: Path, settings: dict[str, Any], indices: list[int] | None, limit: int) -> dict[str, Any]:
    """Prévia redigida de registros (somente leitura, texto truncado, PII mascarada)."""
    recs, info = load_table(path, settings["max_records"])
    idx = [i for i in (indices or range(min(limit, len(recs)))) if 0 <= i < len(recs)][:limit]
    rows = []
    for i in idx:
        r = recs[i]
        fmt = detect_format(r)
        p, q = split_parts(r, fmt)
        out_text = next((str(r[k]) for k in generation.OUTPUT_KEYS if r.get(k) is not None), "")
        ws = words(out_text)
        if not p and r.get("prompt") is not None:
            p = str(r["prompt"])
        row = {
            "index": i,
            "format": fmt,
            "input": redact(p, 300),
            "target": redact(q, 300),
            "output": redact(out_text, 300),
            "words": len(ws),
            "repetition_rate": round(generation.repetition_rate(ws), 4) if ws else None,
            "meta": {
                k: r[k]
                for k in (*generation.GROUP_KEYS, *generation.DECODING, "finish_reason", "step", "loss", "eval_loss")
                if k in r and not isinstance(r[k], (dict, list))
            },
        }
        rows.append(row)
    return {"total_records": len(recs), "rows": rows, "malformed": info["malformed"]}
