"""Testes de Tokenizer, Generation e Compare."""

from __future__ import annotations

from conftest import rules

from deepmodel_inspector.analyzers import compare, generation, tokenizer


def test_tokenizer_inefficient(synth):
    r = tokenizer.analyze_file(synth / "synthetic_tokenization" / "inefficient_tokens.jsonl", max_length=64)
    rs = rules(r)
    assert {"TOK.FERTILITY", "TOK.BYTE_FALLBACK", "TOK.TRUNCATION"} <= rs
    m = r["metrics"]["groups"]["default"]
    assert m["tokens_per_word"] > 2 and m["fragmentation_rate"] > 0.5


def test_tokenizer_efficient_no_findings(synth):
    r = tokenizer.analyze_file(synth / "synthetic_tokenization" / "efficient_tokens.jsonl")
    assert r["findings"] == []
    assert r["metrics"]["groups"]["default"]["tokens_per_word"] == 1.0


def test_tokenizer_never_simulated(synth):
    r = tokenizer.analyze_file(synth / "synthetic_tokenization" / "text_only.jsonl")
    assert rules(r) == {"TOK.NO_TOKENS"}
    assert "tokens_per_word" not in r["metrics"]["groups"]["default"]


def test_tokenizer_comparison(synth):
    r = tokenizer.analyze_file(synth / "synthetic_tokenization" / "tokenizer_comparison.jsonl")
    c = r["metrics"]["comparison"]
    assert c["most_efficient"] == "portuguese-bpe" and c["same_texts"] is True


def test_unk_from_ids():
    recs = [{"text": "a b c", "token_ids": [5, 0, 7]}]
    r = tokenizer.analyze_records(recs, "x", unk_id=0)
    assert "TOK.UNK" in rules(r)


def test_generation_repetitive(synth):
    r = generation.analyze_file(synth / "synthetic_generations" / "repetitive_outputs.jsonl")
    rs = rules(r)
    assert {"GEN.REPETITION", "GEN.TRUNCATED"} <= rs
    f = next(f for f in r["findings"] if f["rule"] == "GEN.REPETITION")
    assert f["status"] == "CONFIRMED" and f["evidence"]["decoding_params"]["temperature"] == ["0.0"]


def test_generation_diverse_negative(synth):
    r = generation.analyze_file(synth / "synthetic_generations" / "diverse_outputs.jsonl")
    assert r["findings"] == []
    m = r["metrics"]["groups"]["sampling"]
    assert m["distinct_2"] > 0.9


def test_generation_config_comparison_not_causal(synth):
    r = generation.analyze_file(synth / "synthetic_generations" / "configs_comparison.jsonl")
    comp = r["metrics"]["comparison"]["sampling vs greedy"]
    assert comp["significant"] and comp["repetition_rate_diff"] < 0
    f = next(f for f in r["findings"] if f["rule"] == "GEN.CONFIG_DIFF")
    assert "not which parameter caused it" in f["explanation"]


def test_generation_grounding_requires_reference(synth):
    r = generation.analyze_file(synth / "synthetic_generations" / "grounded_outputs.jsonl")
    g = r["metrics"]["groups"]["all"]["grounding"]
    assert g["unsupported_sentences"] >= 5 and g["numbers_not_in_reference"] >= 5
    r2 = generation.analyze_file(synth / "synthetic_generations" / "diverse_outputs.jsonl")
    assert "grounding" not in r2["metrics"]["groups"]["sampling"]


def test_distinct_n():
    assert generation.distinct_n([["a", "b", "a", "b"]], 1) == 0.5
    assert generation.repetition_rate(["a"] * 10) > 0.8


def test_compare_regression(synth):
    d = synth / "synthetic_runs"
    r = compare.analyze_paths(d / "run_v1", d / "run_v2")
    reg = {f["evidence"]["metric"] for f in r["findings"] if f["rule"] == "CMP.REGRESSION"}
    assert reg == {"eval_loss", "eval_accuracy"}
    assert set(r["metrics"]["changed_hyperparameters"]) == {"learning_rate", "epochs"}


def test_compare_incompatible_tokenizer(synth):
    d = synth / "synthetic_runs"
    r = compare.analyze_paths(d / "run_v1", d / "run_v3_other_tokenizer")
    assert "CMP.INCOMPATIBLE" in rules(r) and "CMP.REGRESSION" not in rules(r)


def test_compare_no_common_metrics(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "metrics.json").write_text('{"x_acc": 1}', encoding="utf-8")
    (b / "metrics.json").write_text('{"y_acc": 1}', encoding="utf-8")
    assert "CMP.NO_COMMON_METRICS" in rules(compare.analyze_paths(a, b))
