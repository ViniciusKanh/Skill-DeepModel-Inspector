"""Evidence-Based Root Cause Engine (regras RC.*).

Consolida resultados de análises, numera achados, gera hipóteses justificadas
(nunca CONFIRMED), prioriza investigações e responde perguntas por intenção.
Não depende de LLM externo: é um motor de regras sobre evidências calculadas.
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any

from deepmodel_inspector.core.common import SEV_RANK, VERSION

INTENTS: dict[str, dict[str, Any]] = {
    "repetition": {
        "kw": r"repeat|repetit|loop|repet|same sentence|mesma frase|degenera",
        "prefixes": ("GEN.", "DAT.REPETITIVE", "DAT.EXACT_DUP", "RC.REPETITION"),
        "needs": ("generation",),
        "ask": "generated outputs JSONL (with decoding params) and the SFT dataset",
    },
    "overfitting": {
        "kw": r"validation loss|val(idation)? loss|eval loss|overfit|sobreajust|loss de valida|generaliz",
        "prefixes": ("TRN.", "DAT.EXACT_DUP", "DAT.NEAR_DUP", "LEK.", "RC.OVERFIT", "RC.LEAKAGE"),
        "needs": ("training",),
        "ask": "a training log with train and eval loss per step",
    },
    "divergence": {
        "kw": r"diverg|nan|\binf\b|explod|unstable|instab|inst[aá]vel|spike|pico",
        "prefixes": ("TRN.", "DAT.ENCODING", "DAT.EMPTY", "RC.DIVERGENCE"),
        "needs": ("training",),
        "ask": "a training log with loss, learning_rate and grad_norm",
    },
    "contamination": {
        "kw": r"contamin|leak|vazament|overlap|sobreposi|test set|conjunto de teste|benchmark",
        "prefixes": ("LEK.", "DAT.EXACT_DUP", "DAT.NEAR_DUP", "TRN.VAL_BELOW_TRAIN", "RC.LEAKAGE"),
        "needs": ("leakage",),
        "ask": "the training file and the validation/test files",
    },
    "regression": {
        "kw": r"drop|worse|regress|degrad|pior|queda|caiu|after sft|ap[oó]s|depois|performance",
        "prefixes": ("CMP.", "TRN.OVERFIT", "LEK.", "DAT.", "RC.REGRESSION", "RC.OVERFIT"),
        "needs": ("comparison",),
        "ask": "two run folders (before/after) with config and metrics JSON",
    },
    "tokenizer": {
        "kw": r"token|fertilit|portugu[eê]s|vocab",
        "prefixes": ("TOK.", "RC.TOKENIZER"),
        "needs": ("tokenizer",),
        "ask": "a JSONL with text plus tokens/token_ids produced by your tokenizer",
    },
    "hallucination": {
        "kw": r"hallucin|alucin|factual|fact|invent|made up",
        "prefixes": ("GEN.UNSUPPORTED", "RC.HALLUCINATION"),
        "needs": ("generation",),
        "ask": "generated outputs with a 'reference' field containing the source evidence",
    },
    "underfitting": {
        "kw": r"not learning|n[aã]o aprende|plateau|stuck|estagn|underfit|not improv|n[aã]o melhora",
        "prefixes": ("TRN.", "RC.UNDERFIT"),
        "needs": ("training",),
        "ask": "a training log with loss per step (and learning_rate)",
    },
    "dataset": {
        "kw": r"dataset|duplicat|quality|qualidade|dados|data",
        "prefixes": ("DAT.", "LEK."),
        "needs": ("dataset",),
        "ask": "the dataset file(s) (JSONL/CSV)",
    },
}


def detect_intents(question: str) -> list[str]:
    """Intenções detectadas na pergunta (inglês ou português) por padrões documentados."""
    q = question.lower()
    found = [k for k, v in INTENTS.items() if re.search(v["kw"], q)]
    return found or ["general"]


def _has(rules: set[str], *names: str) -> bool:
    return any(r.startswith(n) for r in rules for n in names)


def _ids(findings: list[dict[str, Any]], *names: str) -> list[str]:
    return [f["id"] for f in findings if any(f["rule"].startswith(n) for n in names)]


def _decoding_suspect(findings: list[dict[str, Any]]) -> list[str]:
    """Indícios de decodificação propensa a loops nos parâmetros informados."""
    notes = []
    for f in findings:
        if f["rule"] != "GEN.REPETITION":
            continue
        p = f["evidence"].get("decoding_params", {})
        temps = [float(t) for t in p.get("temperature", []) if _num(t)]
        pens = [float(t) for t in p.get("repetition_penalty", []) if _num(t)]
        if temps and max(temps) <= 0.3:
            notes.append(f"temperature<=0.3 ({max(temps)})")
        if pens and max(pens) <= 1.0:
            notes.append("repetition_penalty<=1.0")
        if "do_sample" in p and p["do_sample"] in (["False"], ["false"], ["0"]):
            notes.append("greedy decoding (do_sample=False)")
    return notes


def _num(x: Any) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def hypotheses(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gera hipóteses (POTENTIAL) a partir de combinações de achados. Nunca CONFIRMED."""
    rules = {f["rule"] for f in findings if f["status"] != "INCONCLUSIVE" and f["severity"] != "INFO"}
    rules |= {f["rule"] for f in findings if f["rule"] in ("GEN.CONFIG_DIFF", "CMP.HP_CHANGES", "DAT.INSTRUCTION_LIKE")}
    H: list[dict[str, Any]] = []

    def add(rule: str, statement: str, support: list[str], test: str, counter: str = "") -> None:
        sev = min((SEV_RANK[f["severity"]] for f in findings if f["id"] in support), default=4)
        H.append(
            {
                "id": "",
                "rule": rule,
                "status": "POTENTIAL",
                "statement": statement,
                "supporting_findings": support,
                "counter_evidence": counter,
                "experiment": test,
                "priority_rank": sev,
            }
        )

    if _has(rules, "GEN.REPETITION"):
        if _has(rules, "DAT.REPETITIVE", "DAT.EXACT_DUP"):
            add(
                "RC.REPETITION_DATA",
                "Repetitive or duplicated training targets may be teaching the model to repeat.",
                _ids(findings, "GEN.REPETITION", "DAT.REPETITIVE", "DAT.EXACT_DUP"),
                "Fine-tune on the deduplicated/filtered dataset with identical settings and compare repetition rate.",
            )
        dec = _decoding_suspect(findings)
        if dec:
            add(
                "RC.REPETITION_DECODING",
                "Decoding settings that favour loops: " + ", ".join(dec) + ".",
                _ids(findings, "GEN.REPETITION"),
                "Re-generate the same prompts with repetition_penalty=1.15 or temperature=0.7 (one change at a time).",
            )
        if _has(rules, "GEN.TRUNCATED"):
            add(
                "RC.REPETITION_EOS",
                "The model may fail to emit end-of-sequence and loops until the token limit.",
                _ids(findings, "GEN.REPETITION", "GEN.TRUNCATED"),
                "Check that SFT targets end with the EOS token and that the chat template adds it; count EOS in labels.",
            )
        if not any(h["rule"].startswith("RC.REPETITION") for h in H):
            add(
                "RC.REPETITION_UNKNOWN",
                "Repetition observed, but provided artifacts do not point to a cause.",
                _ids(findings, "GEN.REPETITION"),
                "Provide the SFT dataset and decoding parameters to test data and decoding hypotheses.",
            )
    if _has(rules, "TRN.OVERFIT"):
        if _has(rules, "DAT.EXACT_DUP", "DAT.NEAR_DUP"):
            add(
                "RC.OVERFIT_DUPLICATES",
                "Duplicated training examples may accelerate memorization and overfitting.",
                _ids(findings, "TRN.OVERFIT", "DAT.EXACT_DUP", "DAT.NEAR_DUP"),
                "Train on the deduplicated set; overfitting onset (best eval step) should move later.",
            )
        add(
            "RC.OVERFIT_BUDGET",
            "Training continued past the point of best generalization (too many steps/epochs "
            "or insufficient regularization for the dataset size).",
            _ids(findings, "TRN.OVERFIT"),
            "Enable early stopping on eval_loss or reduce epochs; compare held-out task metrics at the best step.",
        )
    if _has(rules, "LEK.EXACT", "LEK.NEAR", "LEK.NGRAM", "LEK.PROMPT"):
        add(
            "RC.LEAKAGE_INFLATED",
            "Evaluation scores may be inflated by train/test overlap.",
            _ids(findings, "LEK.", "TRN.VAL_BELOW_TRAIN"),
            "Re-compute evaluation metrics on the decontaminated subset and compare with the full set.",
        )
    if _has(rules, "TRN.NONFINITE", "TRN.DIVERGENCE", "TRN.INSTABILITY", "TRN.GRAD_EXPLOSION"):
        if _has(rules, "TRN.LR_HIGH", "TRN.GRAD_EXPLOSION"):
            add(
                "RC.DIVERGENCE_LR",
                "Learning rate too high and/or missing gradient clipping.",
                _ids(
                    findings, "TRN.NONFINITE", "TRN.DIVERGENCE", "TRN.INSTABILITY", "TRN.LR_HIGH", "TRN.GRAD_EXPLOSION"
                ),
                "Resume from the last stable checkpoint with 0.5x peak LR and max_grad_norm=1.0.",
            )
        if _has(rules, "DAT.ENCODING", "DAT.EMPTY", "DAT.REPETITIVE"):
            add(
                "RC.DIVERGENCE_DATA",
                "Corrupted or degenerate batches may trigger instability.",
                _ids(findings, "TRN.", "DAT.ENCODING", "DAT.EMPTY", "DAT.REPETITIVE"),
                "Log sample indices per step and inspect batches around the first spike/NaN.",
            )
        if not any(h["rule"].startswith("RC.DIVERGENCE") for h in H):
            add(
                "RC.DIVERGENCE_GENERIC",
                "Optimization instability (LR, precision or data); lr/grad_norm logs are needed to narrow it down.",
                _ids(findings, "TRN.NONFINITE", "TRN.DIVERGENCE", "TRN.INSTABILITY"),
                "Log learning_rate and grad_norm; re-run with lower LR and gradient clipping.",
            )
    if _has(rules, "TRN.UNDERFIT"):
        add(
            "RC.UNDERFIT",
            "Learning rate too low, too little capacity/steps, or a pipeline bug (e.g. labels masked).",
            _ids(findings, "TRN.UNDERFIT"),
            "Overfit 100 examples; if loss does not approach 0, inspect labels/masking.",
        )
    if _has(rules, "CMP.REGRESSION"):
        changed = [f for f in findings if f["rule"] == "CMP.HP_CHANGES"]
        if changed:
            add(
                "RC.REGRESSION_HP",
                "One of the changed hyperparameters ("
                + ", ".join(sorted(changed[0]["evidence"]))
                + ") may explain the regression.",
                _ids(findings, "CMP.REGRESSION", "CMP.HP_CHANGES"),
                "Ablate: revert each changed hyperparameter individually with a fixed seed.",
            )
        if _has(rules, "DAT.", "LEK."):
            add(
                "RC.REGRESSION_DATA",
                "Data quality issues in the new training data may contribute to the regression.",
                _ids(findings, "CMP.REGRESSION", "DAT.", "LEK."),
                "Retrain after fixing the flagged data issues and compare on the same eval set.",
            )
    if _has(rules, "TOK.FERTILITY", "TOK.BYTE_FALLBACK", "TOK.UNK"):
        add(
            "RC.TOKENIZER_MISMATCH",
            "The tokenizer vocabulary fits this text/language poorly, raising sequence length "
            "and cost" + (" and causing truncation." if _has(rules, "TOK.TRUNCATION") else "."),
            _ids(findings, "TOK."),
            "Tokenize the same texts with a language-appropriate tokenizer; compare tokens/word.",
        )
    if _has(rules, "GEN.UNSUPPORTED"):
        add(
            "RC.HALLUCINATION_REF",
            "Some outputs contain statements not supported by the supplied references (candidate hallucinations).",
            _ids(findings, "GEN.UNSUPPORTED"),
            "Manually label a sample of flagged sentences to estimate how many are true hallucinations.",
        )
    H.sort(key=lambda h: (h["priority_rank"], h["rule"]))
    for i, h in enumerate(H, 1):
        h["id"] = f"HYP-{i:03d}"
    return H


def consolidate(
    results: list[dict[str, Any]], question: str | None = None, inventory: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Une resultados de análises em um relatório com achados globais, hipóteses e resposta."""
    findings: list[dict[str, Any]] = []
    for idx, r in enumerate(results):
        for f in r.get("findings", []):
            g = dict(f)
            g["result_index"] = idx
            g["local_id"] = f.get("id", "")
            g["analysis"] = r.get("analysis", "")
            findings.append(g)
    findings.sort(key=lambda f: (SEV_RANK.get(f["severity"], 9), f["category"], f["rule"]))
    for i, f in enumerate(findings, 1):
        f["id"] = f"DMI-{i:03d}"
    hyps = hypotheses(findings)
    by_sev = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV_RANK}
    by_status = {s: sum(1 for f in findings if f["status"] == s) for s in ("CONFIRMED", "POTENTIAL", "INCONCLUSIVE")}
    experiments, seen = [], set()
    for h in hyps:
        if h["experiment"] not in seen:
            seen.add(h["experiment"])
            experiments.append({"for": h["id"], "experiment": h["experiment"], "priority": len(experiments) + 1})
    for f in findings:
        c = f.get("confirmation")
        if c and c not in seen and f["severity"] in ("CRITICAL", "HIGH", "MEDIUM"):
            seen.add(c)
            experiments.append({"for": f["id"], "experiment": c, "priority": len(experiments) + 1})
    analyses = sorted({r.get("analysis", "") for r in results})
    inv = inventory or [{"analysis": r.get("analysis"), "source": r.get("source")} for r in results]
    limitations = sorted({lim for r in results for lim in r.get("limitations", [])})
    rep: dict[str, Any] = {
        "tool": "deepmodel-inspector",
        "version": VERSION,
        "generated_at": _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inventory": inv,
        "analyses_run": analyses,
        "sections": {r.get("analysis", "other"): [] for r in results},
        "findings": findings,
        "hypotheses": hyps,
        "experiments": experiments,
        "summary": {
            "findings_by_severity": by_sev,
            "findings_by_status": by_status,
            "top_findings": [
                f"{f['id']} [{f['severity']}/{f['status']}] {f['title']}" for f in findings if f["severity"] != "INFO"
            ][:5],
        },
        "limitations": limitations,
    }
    for idx, r in enumerate(results):
        rep["sections"][r.get("analysis", "other")].append(
            {
                "source": r.get("source"),
                "metrics": r.get("metrics", {}),
                "series": r.get("series"),
                "limitations": r.get("limitations", []),
                "finding_ids": [f["id"] for f in findings if f["result_index"] == idx],
            }
        )
    if question:
        rep["question"] = question
        rep["answer"] = answer(question, findings, hyps, analyses)
    return rep


def answer(
    question: str, findings: list[dict[str, Any]], hyps: list[dict[str, Any]], analyses: list[str]
) -> dict[str, Any]:
    """Resposta estruturada à pergunta: evidências relevantes, hipóteses e artefatos faltantes."""
    intents = detect_intents(question)
    out: dict[str, Any] = {
        "intents": intents,
        "relevant_findings": [],
        "hypotheses": [],
        "missing_artifacts": [],
        "conclusion": "",
    }
    prefixes: tuple[str, ...] = ()
    for it in intents:
        if it == "general":
            continue
        spec = INTENTS[it]
        prefixes += spec["prefixes"]
        if not any(n in analyses for n in spec["needs"]):
            out["missing_artifacts"].append({"intent": it, "provide": spec["ask"]})
    rel = [f for f in findings if not prefixes or any(f["rule"].startswith(p) for p in prefixes)]
    rel = [f for f in rel if f["severity"] != "INFO" or f["status"] == "INCONCLUSIVE" or not prefixes]
    out["relevant_findings"] = [f["id"] for f in rel]
    out["hypotheses"] = [h["id"] for h in hyps if not prefixes or any(h["rule"].startswith(p) for p in prefixes)]
    conf = [f for f in rel if f["status"] == "CONFIRMED" and f["severity"] != "INFO"]
    pot = [f for f in rel if f["status"] == "POTENTIAL"]
    if conf:
        out["status"] = "CONFIRMED"
        out["conclusion"] = (
            "Observed problem(s) confirmed by the data: "
            + "; ".join(f"{f['id']} {f['title']}" for f in conf[:4])
            + ". Causes are listed as hypotheses to be tested, not as confirmed causes."
        )
    elif pot:
        out["status"] = "POTENTIAL"
        out["conclusion"] = (
            "Indicators suggest possible problem(s): " + "; ".join(f"{f['id']} {f['title']}" for f in pot[:4]) + "."
        )
    elif out["missing_artifacts"]:
        out["status"] = "INCONCLUSIVE"
        out["conclusion"] = (
            "Insufficient artifacts to answer; provide: "
            + "; ".join(m["provide"] for m in out["missing_artifacts"])
            + "."
        )
    else:
        out["status"] = "INCONCLUSIVE"
        out["conclusion"] = (
            "No evidence of the asked problem was found in the provided artifacts at the documented "
            "thresholds. This does not prove its absence."
        )
    return out
