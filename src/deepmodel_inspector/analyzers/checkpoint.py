"""Inspeção segura de metadados de checkpoints (regras CKP.*).

Lê apenas: cabeçalho JSON de arquivos ``.safetensors`` (sem carregar tensores) e JSONs de
configuração. Arquivos pickle (.bin/.pt/.pth/.ckpt) são listados, nunca desserializados.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from deepmodel_inspector.core.common import finding, result
from deepmodel_inspector.security.guard import UNSAFE_DESERIALIZATION, is_sensitive

MAX_HEADER = 100 * 2**20
CONFIG_NAMES = ("config.json", "adapter_config.json", "generation_config.json", "tokenizer_config.json")


def safetensors_header(path: Path) -> dict[str, Any]:
    """Lê somente o cabeçalho JSON de um .safetensors (formato: u64 LE + JSON)."""
    with path.open("rb") as fh:
        raw = fh.read(8)
        if len(raw) != 8:
            raise ValueError("file too small for safetensors")
        (n,) = struct.unpack("<Q", raw)
        if n <= 0 or n > MAX_HEADER:
            raise ValueError("invalid safetensors header length")
        header = json.loads(fh.read(n).decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("invalid safetensors header")
    return header


def analyze_dir(path: Path) -> dict[str, Any]:
    """Resume metadados de um diretório de checkpoint sem desserialização insegura."""
    F: list[dict[str, Any]] = []
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())[:500]
    tensors, params, dtypes, unsafe, configs = 0, 0, {}, [], {}
    for p in files:
        if is_sensitive(p):
            continue
        suf = p.suffix.lower()
        if suf == ".safetensors":
            try:
                h = safetensors_header(p)
            except (ValueError, OSError) as exc:
                F.append(
                    finding(
                        "CKP.BAD_HEADER",
                        "checkpoint",
                        "MEDIUM",
                        "CONFIRMED",
                        f"Unreadable safetensors header: {p.name}",
                        {"error": str(exc)[:120]},
                        p.name,
                        "The header could not be parsed.",
                        "Verify the file is complete (download/transfer may be truncated).",
                    )
                )
                continue
            for k, v in h.items():
                if k == "__metadata__" or not isinstance(v, dict):
                    continue
                tensors += 1
                n = 1
                for d in v.get("shape", []):
                    n *= int(d)
                params += n
                dtypes[v.get("dtype", "?")] = dtypes.get(v.get("dtype", "?"), 0) + n
        elif suf in UNSAFE_DESERIALIZATION:
            unsafe.append({"file": p.name, "bytes": p.stat().st_size})
        elif p.name in CONFIG_NAMES:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                configs[p.name] = (
                    {k: v for k, v in d.items() if isinstance(v, (str, int, float, bool))}
                    if isinstance(d, dict)
                    else {}
                )
            except (ValueError, OSError):
                configs[p.name] = {"error": "invalid JSON"}
    metrics = {
        "safetensors_tensors": tensors,
        "parameters_from_headers": params,
        "dtype_parameters": dtypes,
        "pickle_files_not_loaded": unsafe,
        "configs": configs,
    }
    if unsafe:
        F.append(
            finding(
                "CKP.PICKLE",
                "checkpoint",
                "INFO",
                "CONFIRMED",
                "Pickle-based weight files were not opened",
                {"files": [u["file"] for u in unsafe][:10]},
                path.name,
                "Pickle files can execute code when loaded; only their names and sizes were recorded.",
                "Prefer the safetensors format for distribution and inspection.",
            )
        )
    cfg = configs.get("config.json", {})
    tcfg = configs.get("tokenizer_config.json", {})
    if cfg.get("vocab_size") and tcfg.get("vocab_size") and cfg["vocab_size"] != tcfg["vocab_size"]:
        F.append(
            finding(
                "CKP.VOCAB_MISMATCH",
                "checkpoint",
                "HIGH",
                "CONFIRMED",
                "Model and tokenizer vocab sizes differ",
                {"model": cfg["vocab_size"], "tokenizer": tcfg["vocab_size"]},
                path.name,
                "Embedding matrix and tokenizer disagree on vocabulary size.",
                "Resize embeddings or use the matching tokenizer.",
            )
        )
    lim = ["Weights are never loaded; numeric health of tensors (NaN weights) is not inspected."]
    return result("checkpoint", path.name, metrics, F, lim)
