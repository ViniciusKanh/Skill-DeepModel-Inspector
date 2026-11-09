"""Testes de Dataset Quality e Leakage."""

from __future__ import annotations

import json

from conftest import rules

from deepmodel_inspector.analyzers import dataset, leakage
from deepmodel_inspector.core.common import redact
from deepmodel_inspector.parsers.records import detect_format, near_duplicate_pairs


def test_clean_dataset_has_no_findings(synth):
    r = dataset.analyze_file(synth / "synthetic_datasets" / "clean_train.jsonl")
    assert r["findings"] == []
    assert r["metrics"]["exact_duplicate_rate"] == 0


def test_dirty_dataset_rules(synth):
    r = dataset.analyze_file(synth / "synthetic_datasets" / "dirty_train.jsonl")
    rs = rules(r)
    assert {
        "DAT.EXACT_DUP",
        "DAT.NEAR_DUP",
        "DAT.EMPTY",
        "DAT.REPETITIVE",
        "DAT.ENCODING",
        "DAT.INSTRUCTION_LIKE",
        "DAT.STRUCTURE",
    } <= rs
    m = r["metrics"]
    assert m["exact_duplicate_extra_records"] >= 30
    assert m["near_duplicate_pairs"] >= 10
    dup = next(f for f in r["findings"] if f["rule"] == "DAT.EXACT_DUP")
    assert "not evaluation leakage" in dup["explanation"]


def test_messages_structure(synth):
    r = dataset.analyze_file(synth / "synthetic_datasets" / "messages.jsonl")
    issues = r["metrics"]["structure_issues"]
    assert issues["no_assistant_turn"] == 3 and issues["invalid_role"] == 1


def test_csv_text_field(synth):
    r = dataset.analyze_file(synth / "synthetic_datasets" / "reviews.csv", text_field="body")
    assert r["metrics"]["records"] == 61 and r["metrics"]["empty_records"] == 1


def test_formats():
    assert detect_format({"text": "a"}) == "text"
    assert detect_format({"instruction": "a", "input": "", "output": "b"}) == "instruction"
    assert detect_format({"messages": []}) == "messages"
    assert detect_format({"prompt": "a", "completion": "b"}) == "prompt_response"
    assert detect_format({"foo": 1}) == "unknown"


def test_empty_file(tmp_path):
    p = tmp_path / "e.jsonl"
    p.write_text("", encoding="utf-8")
    r = dataset.analyze_file(p)
    assert rules(r) == {"DAT.EMPTY_FILE"}


def test_near_dup_is_deterministic():
    t = [
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu",
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda nu",
        "completely different words here about rivers and mountains and cities",
    ]
    assert near_duplicate_pairs(t, 0.7) == near_duplicate_pairs(t, 0.7)
    assert [p[:2] for p in near_duplicate_pairs(t, 0.7)] == [(0, 1)]


def test_redaction():
    s = redact("contact me at john.doe@example.com key sk-ABCDEFGH12345678 card 4111111111111111")
    assert "@" not in s and "sk-" not in s and "4111" not in s


def test_contamination_detected(synth):
    d = synth / "synthetic_datasets" / "contaminated"
    r = leakage.analyze_files(d / "train.jsonl", [d / "test.jsonl"])
    split = r["metrics"]["splits"]["test.jsonl"]
    assert split["exact_overlap"] == 10 and split["near_duplicate_overlap"] == 5 and split["prompt_seen_in_train"] == 3
    exact = next(f for f in r["findings"] if f["rule"] == "LEK.EXACT")
    assert exact["status"] == "CONFIRMED"


def test_clean_split_no_leakage(synth):
    d = synth / "synthetic_datasets" / "clean_split"
    r = leakage.analyze_files(d / "train.jsonl", [d / "test.jsonl"])
    assert rules(r) == {"LEK.CLEAN"}


def test_shared_template_not_flagged_as_contamination(tmp_path):
    tpl = "You are a helpful assistant. Answer the following question carefully and cite the provided context please."
    import random

    rng = random.Random(1)
    words = [
        "river",
        "city",
        "mountain",
        "data",
        "model",
        "bread",
        "garden",
        "bright",
        "quiet",
        "engine",
        "signal",
        "camera",
    ]

    def rec():
        return {"text": tpl + " " + " ".join(rng.choice(words) for _ in range(40))}

    tr, te = tmp_path / "train.jsonl", tmp_path / "test.jsonl"
    tr.write_text("".join(json.dumps(rec()) + "\n" for _ in range(100)), encoding="utf-8")
    te.write_text("".join(json.dumps(rec()) + "\n" for _ in range(20)), encoding="utf-8")
    r = leakage.analyze_files(tr, [te])
    assert "LEK.NGRAM" not in rules(r) and "LEK.EXACT" not in rules(r)
    assert r["metrics"]["boilerplate_ngrams_ignored"] > 0
