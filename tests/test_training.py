"""Testes positivos e negativos de Training Health Diagnostics."""

from __future__ import annotations

import math

from conftest import rules

from deepmodel_inspector.analyzers import training


def run(synth, name):
    return training.analyze_file(synth / "synthetic_training" / name)


def test_stable_has_no_problem_findings(synth):
    r = run(synth, "stable.csv")
    assert not [f for f in r["findings"] if f["severity"] != "INFO"]
    assert r["metrics"]["train_loss"]["slope_per_1k_steps"] < 0


def test_overfitting_confirmed_with_evidence(synth):
    r = run(synth, "overfitting.csv")
    f = next(f for f in r["findings"] if f["rule"] == "TRN.OVERFIT")
    assert f["status"] == "CONFIRMED" and f["severity"] == "HIGH"
    assert f["evidence"]["best_val_step"] == 400
    assert f["evidence"]["train_slope_after_best"] < 0
    assert f["confirmation"] and f["recommendation"]


def test_divergence_and_nonfinite(synth):
    r = run(synth, "divergent.csv")
    rs = rules(r)
    assert {"TRN.NONFINITE", "TRN.DIVERGENCE", "TRN.GRAD_EXPLOSION"} <= rs
    assert any(f["severity"] == "CRITICAL" and f["status"] == "CONFIRMED" for f in r["findings"])


def test_plateau_not_underfit(synth):
    rs = rules(run(synth, "plateau.csv"))
    assert "TRN.PLATEAU" in rs and "TRN.UNDERFIT" not in rs and "TRN.INSTABILITY" not in rs


def test_underfit(synth):
    assert "TRN.UNDERFIT" in rules(run(synth, "underfit.csv"))


def test_unstable_lr_association_is_potential(synth):
    r = run(synth, "unstable.csv")
    f = next(f for f in r["findings"] if f["rule"] == "TRN.LR_HIGH")
    assert f["status"] == "POTENTIAL"
    assert "association" in f["explanation"]


def test_no_loss_columns_inconclusive(synth):
    r = run(synth, "no_metrics.csv")
    assert [f["status"] for f in r["findings"]] == ["INCONCLUSIVE"]


def test_no_overfit_claim_without_validation():
    rows = [{"step": s, "loss": 2.0 - s / 1000} for s in range(0, 1000, 10)]
    r = training.analyze_rows(rows, "x")
    assert "TRN.OVERFIT" not in rules(r)
    assert "TRN.NO_VALIDATION" in rules(r)


def test_no_gradient_inference_without_grad_norm():
    rows = [{"step": s, "loss": 2.0 - s / 1000, "eval_loss": 2.1 - s / 1000} for s in range(0, 1000, 10)]
    r = training.analyze_rows(rows, "x")
    assert not any(f["rule"].startswith("TRN.GRAD") for f in r["findings"])
    assert any("Gradient norm not logged" in x for x in r["limitations"])


def test_hf_trainer_state(synth):
    r = run(synth, "trainer_state.json")
    assert r["parse"]["container_key"] == "log_history"
    assert r["metrics"]["val_loss"]["n"] == 10
    assert "TRN.ORDER" not in rules(r)


def test_unordered_steps_detected_and_sorted():
    rows = [{"step": s, "loss": 1 + s / 1e4} for s in (30, 10, 20, 40, 50, 60)]
    r = training.analyze_rows(rows, "x")
    assert "TRN.ORDER" in rules(r)


def test_malformed_lines_counted(synth):
    r = run(synth, "malformed.jsonl")
    assert r["parse"]["malformed"] == 2


def test_short_series_inconclusive():
    r = training.analyze_rows([{"step": 1, "loss": 2.0}, {"step": 2, "loss": float("nan")}], "x")
    assert "TRN.NONFINITE" in rules(r)
    assert any("fewer than" in x for x in r["limitations"])


def test_derived_perplexity_documented(synth):
    m = run(synth, "stable.csv")["metrics"]
    assert "assumes" in m["perplexity_source"]
    assert math.isclose(m["val_perplexity_derived"]["min"], math.exp(m["val_loss"]["min"]), rel_tol=1e-4)
