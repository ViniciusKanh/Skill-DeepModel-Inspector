"""Utilitários centrais: achados, estatística descritiva, leitura de arquivos e redação.

Somente biblioteca padrão. Este módulo é embutido em todos os scripts comerciais.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any

VERSION = "1.0.0"
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
STATUSES = ("CONFIRMED", "POTENTIAL", "INCONCLUSIVE")
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}


def finding(
    rule: str,
    category: str,
    severity: str,
    status: str,
    title: str,
    evidence: dict[str, Any],
    source: str,
    explanation: str,
    recommendation: str,
    confirmation: str = "",
) -> dict[str, Any]:
    """Cria um achado padronizado. ``status`` CONFIRMED exige regra objetiva satisfeita."""
    assert severity in SEVERITIES and status in STATUSES
    return {
        "id": "",
        "rule": rule,
        "category": category,
        "severity": severity,
        "status": status,
        "title": title,
        "evidence": evidence,
        "source": source,
        "explanation": explanation,
        "recommendation": recommendation,
        "confirmation": confirmation,
    }


def result(
    analysis: str,
    source: str,
    metrics: dict[str, Any],
    findings: list[dict[str, Any]],
    limitations: list[str],
    **extra: Any,
) -> dict[str, Any]:
    """Monta o resultado de uma análise e numera os achados de forma determinística."""
    prefix = analysis[:3].upper()
    findings = sorted(findings, key=lambda f: (SEV_RANK[f["severity"]], f["rule"]))
    for i, f in enumerate(findings, 1):
        f["id"] = f"{prefix}-{i:03d}"
    out = {
        "tool": "deepmodel-inspector",
        "version": VERSION,
        "analysis": analysis,
        "source": source,
        "metrics": metrics,
        "findings": findings,
        "limitations": limitations,
    }
    out.update(extra)
    return out


# ----------------------------------------------------------------- estatística
def finite(values: list[Any]) -> list[float]:
    """Filtra valores numéricos finitos."""
    out = []
    for v in values:
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            out.append(float(v))
    return out


def describe(values: list[float]) -> dict[str, float | int | None]:
    """Estatística descritiva: n, min, max, média, desvio-padrão, mediana e p95."""
    v = finite(values)
    if not v:
        return {"n": 0, "min": None, "max": None, "mean": None, "std": None, "median": None, "p95": None}
    s = sorted(v)
    p95 = s[min(len(s) - 1, int(math.ceil(0.95 * len(s))) - 1)]
    return {
        "n": len(v),
        "min": rnd(s[0]),
        "max": rnd(s[-1]),
        "mean": rnd(statistics.fmean(v)),
        "std": rnd(statistics.pstdev(v)) if len(v) > 1 else 0.0,
        "median": rnd(statistics.median(s)),
        "p95": rnd(p95),
    }


def rnd(x: float | None, nd: int = 6) -> float | None:
    """Arredonda preservando None e valores não finitos como None."""
    if x is None or not math.isfinite(x):
        return None
    return round(float(x), nd)


def slope(xs: list[float], ys: list[float]) -> float | None:
    """Inclinação por mínimos quadrados (y por unidade de x)."""
    if len(xs) < 2:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Correlação de Pearson descritiva (None se indefinida)."""
    if len(xs) < 3:
        return None
    try:
        return statistics.correlation(xs, ys)
    except (statistics.StatisticsError, ZeroDivisionError):
        return None


def ranks(v: list[float]) -> list[float]:
    """Postos médios (para Spearman)."""
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Correlação de Spearman descritiva."""
    return pearson(ranks(xs), ranks(ys))


def mad(v: list[float]) -> float:
    """Desvio absoluto mediano."""
    if not v:
        return 0.0
    m = statistics.median(v)
    return float(statistics.median([abs(x - m) for x in v]))


# ------------------------------------------------------------------ leitura
def load_table(path: Path, max_records: int = 200_000) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Lê CSV, JSON, JSONL ou TXT em lista de dicionários (somente leitura).

    Retorna (registros, informações de parsing com linhas malformadas e truncamento).
    Suporta ``trainer_state.json`` do Hugging Face (chave ``log_history``).
    """
    info: dict[str, Any] = {"format": "", "malformed": 0, "malformed_lines": [], "truncated": False}
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    info["decode_errors"] = max(0, text.count("�") - raw.count(b"\xef\xbf\xbd"))
    records: list[dict[str, Any]] = []
    if suffix == ".csv" or suffix == ".tsv":
        info["format"] = "csv"
        dialect = "excel-tab" if suffix == ".tsv" else "excel"
        for row in csv.DictReader(io.StringIO(text), dialect=dialect):
            if None in row:
                info["malformed"] += 1
                row.pop(None, None)
            records.append({k.strip() if k else k: _coerce(v) for k, v in row.items()})
    elif suffix == ".json":
        info["format"] = "json"
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        if isinstance(data, dict):
            for key in ("log_history", "records", "data", "rows", "examples", "items"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    info["container_key"] = key
                    break
            else:
                data = [data]
        records = [r if isinstance(r, dict) else {"text": r} for r in data]
    elif suffix in (".jsonl", ".ndjson"):
        info["format"] = "jsonl"
        for n, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                info["malformed"] += 1
                if len(info["malformed_lines"]) < 10:
                    info["malformed_lines"].append(n)
                continue
            records.append(obj if isinstance(obj, dict) else {"text": obj})
    else:
        info["format"] = "text"
        records = [{"text": ln} for ln in text.splitlines()]
    if len(records) > max_records:
        records = records[:max_records]
        info["truncated"] = True
    info["records"] = len(records)
    return records, info


def _coerce(v: Any) -> Any:
    """Converte strings numéricas de CSV em float; strings vazias em None."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return s


def to_float(v: Any) -> float | None:
    """Converte para float aceitando 'nan'/'inf' (retornados como float especiais)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except ValueError:
        return None


# ------------------------------------------------------------ texto e redação
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SECRET = re.compile(r"\b(?:sk|pk|ghp|gho|hf|xox[bap])[-_][A-Za-z0-9_-]{8,}\b")
_DIGITS = re.compile(r"\d{6,}")


def redact(text: Any, max_len: int = 80) -> str:
    """Trecho de evidência com limite de exposição: mascara e-mails, chaves e números longos."""
    s = str(text).replace("\n", " ").replace("\r", " ")
    s = _SECRET.sub("[SECRET]", s)
    s = _EMAIL.sub("[EMAIL]", s)
    s = _DIGITS.sub("[NUM]", s)
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def dump_json(obj: Any, path: Path | None) -> str:
    """Serializa em JSON (UTF-8). Se ``path`` for dado, grava o arquivo."""
    text = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return text
