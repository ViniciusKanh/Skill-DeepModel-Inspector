"""Inventário de artefatos: identifica logs, datasets, tokenizações, gerações, execuções
e checkpoints em um diretório, e orquestra a auditoria completa.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from deepmodel_inspector.analyzers import checkpoint, compare, dataset, generation, leakage, tokenizer, training
from deepmodel_inspector.core.common import load_table
from deepmodel_inspector.security.guard import UNSAFE_DESERIALIZATION, is_sensitive

DATA_SUFFIXES = {".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".txt"}
SPLIT = {
    "train": re.compile(r"(^|[_\-.])(train|training)([_\-.]|$)"),
    "validation": re.compile(r"(^|[_\-.])(val|valid|validation|dev)([_\-.]|$)"),
    "test": re.compile(r"(^|[_\-.])(test|eval|evaluation|benchmark)([_\-.]|$)"),
}
GEN_HINT = re.compile(r"gen|output|pred|sample|completion|response")
RUN_FILES = set(compare.CONFIG_FILES) | set(compare.METRIC_FILES) | {"trainer_state.json"}
MAX_FILES = 500


def split_of(name: str) -> str | None:
    """Papel do arquivo pelo nome: train, validation, test ou None."""
    stem = name.lower().rsplit(".", 1)[0]
    for role, rx in SPLIT.items():
        if rx.search(stem):
            return role
    return None


def classify(path: Path) -> dict[str, Any]:
    """Classifica um arquivo pelo nome e pelas chaves dos primeiros registros."""
    name = path.name.lower()
    item: dict[str, Any] = {"path": str(path), "name": path.name, "kind": "unknown", "split": split_of(name)}
    if path.suffix.lower() == ".safetensors":
        item["kind"] = "checkpoint"
        return item
    if name in RUN_FILES and name != "trainer_state.json":
        item["kind"] = "run_metadata"
        return item
    try:
        recs, _ = load_table(path, 50)
    except (ValueError, OSError, UnicodeError):
        item["kind"] = "unreadable"
        return item
    keys = {k for r in recs[:50] for k in r}
    if name == "trainer_state.json" or (
        {"loss", "train_loss", "eval_loss", "val_loss"} & keys and {"step", "epoch", "global_step", "iteration"} & keys
    ):
        item["kind"] = "training_log"
    elif {"tokens", "token_ids", "input_ids"} & keys:
        item["kind"] = "tokenized"
    elif "instruction" in keys or "messages" in keys or "conversations" in keys:
        item["kind"] = "dataset"
    elif {"output", "response", "generation", "completion", "generated_text", "prediction"} & keys and (
        GEN_HINT.search(name) and not item["split"]
    ):
        item["kind"] = "generations"
    elif keys & {"text", "content", "prompt", "response", "completion", "question", "answer"} or path.suffix == ".txt":
        item["kind"] = "dataset"
    return item


def scan(root: Path) -> list[dict[str, Any]]:
    """Percorre o diretório (sem seguir ocultos/sensíveis) e devolve o inventário."""
    items: list[dict[str, Any]] = []
    files = [root] if root.is_file() else sorted(root.rglob("*"))
    for p in files:
        if len(items) >= MAX_FILES:
            break
        if not p.is_file() or any(part.startswith(".") for part in p.relative_to(root.parent).parts[1:]):
            continue
        if is_sensitive(p):
            items.append({"path": str(p), "name": p.name, "kind": "skipped_sensitive"})
            continue
        if p.suffix.lower() in UNSAFE_DESERIALIZATION:
            items.append({"path": str(p), "name": p.name, "kind": "skipped_unsafe_format"})
            continue
        if p.suffix.lower() in DATA_SUFFIXES or p.suffix.lower() == ".safetensors":
            items.append(classify(p))
    if root.is_dir():
        run_dirs = sorted({str(Path(i["path"]).parent) for i in items if i["kind"] == "run_metadata"})
        for d in run_dirs:
            items.append({"path": d, "name": Path(d).name, "kind": "run"})
    return items


def run_audit(root: Path, max_records: int = 200_000) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Executa todas as análises aplicáveis ao inventário. Retorna (inventário, resultados)."""
    inv = scan(root)
    results: list[dict[str, Any]] = []
    run_dirs = {i["path"] for i in inv if i["kind"] == "run"}
    for it in inv:
        p = Path(it["path"])
        if len(run_dirs) >= 2 and str(p.parent) in run_dirs:
            it["note"] = "analyzed via run comparison"
            continue
        try:
            if it["kind"] == "training_log":
                results.append(training.analyze_file(p, max_records))
            elif it["kind"] == "dataset":
                results.append(dataset.analyze_file(p, max_records=max_records))
            elif it["kind"] == "tokenized":
                results.append(tokenizer.analyze_file(p, max_records=max_records))
            elif it["kind"] == "generations":
                results.append(generation.analyze_file(p, max_records=max_records))
        except ValueError as exc:
            it["error"] = str(exc)[:200]
    datasets = [i for i in inv if i["kind"] == "dataset"]
    trains = [i for i in datasets if i.get("split") == "train"]
    evals = [i for i in datasets if i.get("split") in ("validation", "test")]
    for t in trains:
        same_dir = [Path(e["path"]) for e in evals if Path(e["path"]).parent == Path(t["path"]).parent] or [
            Path(e["path"]) for e in evals
        ]
        if same_dir:
            results.append(leakage.analyze_files(Path(t["path"]), same_dir, max_records=max_records))
    runs = [i for i in inv if i["kind"] == "run"]
    if len(runs) >= 2:
        for r in runs[1:]:
            results.append(compare.analyze_paths(Path(runs[0]["path"]), Path(r["path"])))
    ck_dirs = sorted({str(Path(i["path"]).parent) for i in inv if i["kind"] == "checkpoint"})
    for d in ck_dirs:
        results.append(checkpoint.analyze_dir(Path(d)))
    return inv, results
