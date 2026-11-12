"""Extensão do motor de causa raiz para sondagem ao vivo (PRB.*) e monitoramento (MON.*).

Mantida separada de ``rootcause.py`` para não alterar a skill comercial (cujos scripts
embutem aquele módulo). ``consolidate`` aqui delega ao motor original e acrescenta
intenções e hipóteses específicas de modelos em execução.
"""

from __future__ import annotations

import threading
from typing import Any

from deepmodel_inspector.core.common import SEV_RANK
from deepmodel_inspector.diagnostics import rootcause

LIVE_INTENTS: dict[str, dict[str, Any]] = {
    "injection": {
        "kw": r"inject|jailbreak|seguran|security|prompt attack|untrusted",
        "prefixes": ("PRB.INJECTION", "DAT.INSTRUCTION_LIKE", "RC.LIVE_INJECTION"),
        "needs": ("probe",),
        "ask": "a live probe of the model endpoint",
    },
    "production": {
        "kw": r"produc|monitor|latenc|slow|lent|error rate|erro|drift|outage|uptime",
        "prefixes": ("MON.", "PRB.ERRORS", "PRB.LATENCY", "PRB.UNREACHABLE", "RC.LIVE_"),
        "needs": ("monitor", "probe"),
        "ask": "production logs (JSONL per day/week) or a live probe",
    },
    "format": {
        "kw": r"json|format|instru[cç]|follow|obedec|seguir",
        "prefixes": ("PRB.INSTRUCTION", "RC.LIVE_FORMAT"),
        "needs": ("probe",),
        "ask": "a live probe of the model",
    },
}
EXTRA_PREFIXES = {
    "repetition": ("PRB.REPETITION_STRESS", "MON.REPETITION", "MON.DRIFT_REPETITION", "MON.DIVERSITY_DROP"),
    "hallucination": ("PRB.GROUNDING", "PRB.ACCURACY"),
    "regression": ("MON.",),
}


_LOCK = threading.Lock()


def merged_intents() -> dict[str, dict[str, Any]]:
    """Cópia das intenções do motor acrescida das intenções ao vivo (não altera o módulo original)."""
    out = {k: dict(v) for k, v in rootcause.INTENTS.items()}
    for k, extra in EXTRA_PREFIXES.items():
        out[k]["prefixes"] = tuple(dict.fromkeys((*out[k]["prefixes"], *extra)))
        if k in ("repetition", "hallucination"):
            out[k]["needs"] = tuple(dict.fromkeys((*out[k]["needs"], "probe", "monitor")))
    out.update(LIVE_INTENTS)
    return out


def _extra_hyps(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rules = {f["rule"] for f in findings}
    ids = lambda *p: [f["id"] for f in findings if f["rule"].startswith(p)]  # noqa: E731
    H = []

    def add(rule: str, statement: str, support: list[str], test: str) -> None:
        sev = min((SEV_RANK[f["severity"]] for f in findings if f["id"] in support), default=4)
        H.append(
            {
                "id": "",
                "rule": rule,
                "status": "POTENTIAL",
                "statement": statement,
                "supporting_findings": support,
                "counter_evidence": "",
                "experiment": test,
                "priority_rank": sev,
            }
        )

    if "PRB.INJECTION" in rules:
        add(
            "RC.LIVE_INJECTION",
            "The prompt/template does not isolate untrusted content from instructions.",
            ids("PRB.INJECTION"),
            "Wrap documents in explicit delimiters, restate the rule after the document, and re-run the probe.",
        )
    if "PRB.INSTRUCTION" in rules:
        add(
            "RC.LIVE_FORMAT",
            "Chat template or decoding does not enforce output constraints (format/length/language).",
            ids("PRB.INSTRUCTION"),
            "Re-run with the model's official chat template and JSON/structured-output mode if available.",
        )
    if rules & {"PRB.ERRORS", "PRB.LATENCY", "MON.ERRORS", "MON.LATENCY"}:
        add(
            "RC.LIVE_CAPACITY",
            "The serving stack is overloaded or misconfigured (timeouts, queueing, context length).",
            ids("PRB.ERRORS", "PRB.LATENCY", "MON.ERRORS", "MON.LATENCY"),
            "Repeat the probe at lower concurrency and smaller max_tokens; compare latency percentiles.",
        )
    if rules & {"MON.REPETITION", "MON.DRIFT_REPETITION", "MON.DIVERSITY_DROP"}:
        add(
            "RC.LIVE_DRIFT",
            "A change in the latest period (model, template, decoding or traffic mix) degraded output diversity.",
            ids("MON."),
            "Diff deployment configs between periods and replay a sample of prompts on both versions.",
        )
    if rules & {"PRB.GROUNDING", "PRB.ACCURACY"}:
        add(
            "RC.LIVE_GROUNDING",
            "The model ignores provided context or lacks the knowledge for closed answers "
            "(model size/quantization or prompt placement).",
            ids("PRB.GROUNDING", "PRB.ACCURACY"),
            "Compare the same probe on a larger/unquantized model and with the context placed after the question.",
        )
    return H


def consolidate(
    results: list[dict[str, Any]], question: str | None = None, inventory: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """``rootcause.consolidate`` + hipóteses e intenções de modelos em execução."""
    rep = rootcause.consolidate(results, None, inventory)
    hyps = rep["hypotheses"] + _extra_hyps(rep["findings"])
    hyps.sort(key=lambda h: (h["priority_rank"], h["rule"]))
    for i, h in enumerate(hyps, 1):
        h["id"] = f"HYP-{i:03d}"
    rep["hypotheses"] = hyps
    experiments, seen = [], set()
    for h in hyps:
        if h["experiment"] not in seen:
            seen.add(h["experiment"])
            experiments.append({"for": h["id"], "experiment": h["experiment"], "priority": len(experiments) + 1})
    for f in rep["findings"]:
        c = f.get("confirmation")
        if c and c not in seen and f["severity"] in ("CRITICAL", "HIGH", "MEDIUM"):
            seen.add(c)
            experiments.append({"for": f["id"], "experiment": c, "priority": len(experiments) + 1})
    rep["experiments"] = experiments
    if question:
        rep["question"] = question
        with _LOCK:  # troca temporária e protegida das intenções usadas por rootcause.answer
            saved = rootcause.INTENTS
            rootcause.INTENTS = merged_intents()
            try:
                rep["answer"] = rootcause.answer(question, rep["findings"], hyps, rep["analyses_run"])
            finally:
                rootcause.INTENTS = saved
    return rep
