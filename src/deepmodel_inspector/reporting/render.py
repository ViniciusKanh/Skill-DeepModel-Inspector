"""Renderização de relatórios consolidados em Markdown e HTML estático (sem dependências).

Todo conteúdo vindo dos dados analisados é escapado (HTML) ou neutralizado (Markdown);
nenhuma instrução contida nos dados é interpretada.
"""

from __future__ import annotations

import html
import json
from typing import Any

LABELS = {
    "en": [
        "Executive Summary",
        "Data & Artifact Inventory",
        "Training Health",
        "Dataset Quality",
        "Tokenizer Efficiency",
        "Generation Behavior",
        "Experiment Comparison",
        "Root Cause Investigation",
        "Findings by Severity",
        "Recommended Experiments",
        "Evidence & Limitations",
    ],
    "pt": [
        "Resumo Executivo",
        "Inventário de Dados e Artefatos",
        "Saúde do Treinamento",
        "Qualidade do Dataset",
        "Eficiência do Tokenizer",
        "Comportamento de Geração",
        "Comparação de Experimentos",
        "Investigação de Causa Raiz",
        "Achados por Severidade",
        "Experimentos Recomendados",
        "Evidências e Limitações",
    ],
}
SECTION_KEYS = [
    None,
    None,
    ("training", "checkpoint"),
    ("dataset", "leakage"),
    ("tokenizer",),
    ("generation",),
    ("comparison",),
    None,
    None,
    None,
    None,
]
NOT_RUN = {
    "en": "Not analyzed (no matching artifact provided).",
    "pt": "Não analisado (nenhum artefato correspondente).",
}


def _md(x: Any) -> str:
    """Neutraliza texto para Markdown (pipes, quebras e crases)."""
    return str(x).replace("|", "\\|").replace("\n", " ").replace("`", "'")


def _brief(metrics: dict[str, Any], limit: int = 900) -> str:
    """Métricas em JSON compacto e truncado para leitura."""
    s = json.dumps(metrics, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + " …"


def to_markdown(rep: dict[str, Any], lang: str = "en") -> str:
    """Relatório Markdown com as 11 seções padronizadas."""
    L = LABELS.get(lang, LABELS["en"])
    fid = {f["id"]: f for f in rep.get("findings", [])}
    out = [
        "# DeepModel Inspector Report",
        "",
        f"Version {rep.get('version')} · generated {rep.get('generated_at')} · analyses: "
        f"{', '.join(rep.get('analyses_run', [])) or 'none'}",
        "",
    ]
    s = rep.get("summary", {})
    out += [f"## 1. {L[0]}", ""]
    if rep.get("question"):
        a = rep.get("answer", {})
        out += [
            f"**Question:** {_md(rep['question'])}",
            "",
            f"**Answer status:** `{a.get('status')}` — {_md(a.get('conclusion', ''))}",
            "",
        ]
    out += [
        f"- Findings by severity: {s.get('findings_by_severity')}",
        f"- Findings by status: {s.get('findings_by_status')}",
    ]
    out += [f"- {_md(t)}" for t in s.get("top_findings", [])] + [""]
    out += [f"## 2. {L[1]}", "", "| Analysis | Source |", "|---|---|"]
    out += [
        f"| {_md(i.get('kind') or i.get('analysis'))} | {_md(i.get('source') or i.get('path'))} |"
        for i in rep.get("inventory", [])
    ]
    out.append("")
    for n in range(2, 7):
        out += [f"## {n + 1}. {L[n]}", ""]
        blocks = [b for k in SECTION_KEYS[n] for b in rep.get("sections", {}).get(k, [])]
        if not blocks:
            out += [NOT_RUN.get(lang, NOT_RUN["en"]), ""]
        for b in blocks:
            out += [f"**Source:** `{_md(b.get('source'))}`", "", f"Metrics: `{_md(_brief(b.get('metrics', {})))}`", ""]
            ids = b.get("finding_ids", [])
            out += [f"- {i} [{fid[i]['severity']}/{fid[i]['status']}] {_md(fid[i]['title'])}" for i in ids if i in fid]
            out.append("")
    out += [f"## 8. {L[7]}", ""]
    hyps = rep.get("hypotheses", [])
    if not hyps:
        out += ["No cross-artifact hypothesis was triggered by the evidence.", ""]
    for h in hyps:
        out += [
            f"- **{h['id']}** `{h['status']}` {_md(h['statement'])} (supported by {', '.join(h['supporting_findings'])})",
            f"  - Test: {_md(h['experiment'])}",
        ]
    a = rep.get("answer")
    if a and a.get("missing_artifacts"):
        out += ["", "Missing artifacts to answer the question:"] + [
            f"- {_md(m['provide'])}" for m in a["missing_artifacts"]
        ]
    out += ["", f"## 9. {L[8]}", ""]
    for f in rep.get("findings", []):
        out += [
            f"### {f['id']} · {f['severity']} · {f['status']} · {_md(f['title'])}",
            "",
            f"- Rule: `{f['rule']}` · Category: {f['category']} · Source: `{_md(f['source'])}`",
            f"- Evidence: `{_md(_brief(f['evidence'], 600))}`",
            f"- Explanation: {_md(f['explanation'])}",
            f"- Recommendation: {_md(f['recommendation'])}",
        ]
        if f.get("confirmation"):
            out.append(f"- How to confirm: {_md(f['confirmation'])}")
        out.append("")
    out += [f"## 10. {L[9]}", ""]
    out += [f"{e['priority']}. ({e['for']}) {_md(e['experiment'])}" for e in rep.get("experiments", [])] or ["None."]
    out += [
        "",
        f"## 11. {L[10]}",
        "",
        "Statuses: CONFIRMED = rule satisfied by the data; POTENTIAL = indicators support a possible problem; "
        "INCONCLUSIVE = insufficient information. Hypotheses are never presented as confirmed causes.",
        "",
    ]
    out += [f"- {_md(x)}" for x in rep.get("limitations", [])]
    return "\n".join(out) + "\n"


def _svg(series: dict[str, list[list[float]]], w: int = 560, h: int = 180) -> str:
    """Gráfico SVG de linhas (apenas quando há séries reais)."""
    pts = [p for v in series.values() for p in v]
    if len(pts) < 2:
        return ""
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    sx = (w - 40) / ((x1 - x0) or 1)
    sy = (h - 30) / ((y1 - y0) or 1)
    colors = {"train_loss": "#2563eb", "val_loss": "#dc2626"}
    lines = []
    for name, v in series.items():
        d = " ".join(f"{30 + (x - x0) * sx:.1f},{h - 20 - (y - y0) * sy:.1f}" for x, y in v)
        lines.append(
            f'<polyline fill="none" stroke="{colors.get(name, "#555")}" stroke-width="1.5" points="{d}"/>'
            f'<text x="{w - 110}" y="{14 + 14 * len(lines)}" fill="{colors.get(name, "#555")}" font-size="11">{html.escape(name)}</text>'
        )
    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="loss curves">'
        f'<text x="2" y="12" font-size="10">{y1:.3g}</text><text x="2" y="{h - 20}" font-size="10">{y0:.3g}</text>'
        f'<text x="30" y="{h - 4}" font-size="10">step {x0:g}</text><text x="{w - 70}" y="{h - 4}" font-size="10">{x1:g}</text>'
        + "".join(lines)
        + "</svg>"
    )


def to_html(rep: dict[str, Any], lang: str = "en") -> str:
    """HTML estático autocontido; Markdown convertido de forma simples e escapado."""
    body = []
    for line in to_markdown(rep, lang).splitlines():
        e = html.escape(line)
        if line.startswith("### "):
            body.append(f"<h3>{e[4:]}</h3>")
        elif line.startswith("## "):
            body.append(f"<h2>{e[3:]}</h2>")
        elif line.startswith("# "):
            body.append(f"<h1>{e[2:]}</h1>")
        elif line.startswith(("- ", "  - ")):
            body.append(f"<li>{e.lstrip(' -')}</li>")
        elif line.startswith("|"):
            body.append(f"<pre>{e}</pre>")
        elif line.strip():
            body.append(f"<p>{e}</p>")
        if line.startswith("## 3."):
            for b in rep.get("sections", {}).get("training", []):
                if b.get("series"):
                    body.append(_svg(b["series"]))
    css = (
        "body{font-family:system-ui,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;color:#111;"
        "background:#fff}h2{border-bottom:1px solid #ddd;padding-bottom:4px}li{margin:2px 0}"
        "pre{margin:0;font-size:12px;white-space:pre-wrap}p,li{font-size:14px;line-height:1.45}"
    )
    return (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" '
        f'content="width=device-width,initial-scale=1"><title>DeepModel Inspector Report</title><style>{css}</style>'
        f"</head><body>{''.join(body)}</body></html>\n"
    )
