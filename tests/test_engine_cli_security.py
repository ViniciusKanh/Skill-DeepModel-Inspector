"""Testes do motor de causa raiz, CLI, relatórios e segurança."""

from __future__ import annotations

import json
import os
import struct

import pytest

from deepmodel_inspector.analyzers import checkpoint
from deepmodel_inspector.cli import main
from deepmodel_inspector.diagnostics.rootcause import consolidate, detect_intents
from deepmodel_inspector.reporting.render import to_html
from deepmodel_inspector.security.guard import SecurityError, safe_input_path, safe_output_path


def _run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_intents_en_pt():
    assert detect_intents("Why is my LLM repeating the same sentences?") == ["repetition"]
    assert "overfitting" in detect_intents("Por que a loss de validação está subindo?")
    assert "contamination" in detect_intents("Is my fine-tuning dataset contaminated?")
    assert "tokenizer" in detect_intents("Is my tokenizer inefficient for Portuguese?")


def test_investigate_repetition(synth, capsys):
    code, out, _ = _run(
        capsys, "investigate", "-i", str(synth / "demo_experiment"), "-q", "Why is my LLM repeating the same sentences?"
    )
    rep = json.loads(out)
    assert code == 0 and rep["answer"]["status"] == "CONFIRMED"
    hyp = {h["rule"] for h in rep["hypotheses"] if h["id"] in rep["answer"]["hypotheses"]}
    assert {"RC.REPETITION_DATA", "RC.REPETITION_DECODING", "RC.REPETITION_EOS"} <= hyp
    assert all(h["status"] == "POTENTIAL" for h in rep["hypotheses"])
    assert not any(os.sep + "tmp" in str(i["path"]) for i in rep["inventory"])


def test_investigate_missing_artifacts(synth, capsys):
    code, out, _ = _run(
        capsys, "investigate", "-i", str(synth / "synthetic_datasets" / "clean_split"), "-q", "Why is my LLM repeating?"
    )
    a = json.loads(out)["answer"]
    assert a["status"] == "INCONCLUSIVE" and a["missing_artifacts"]


def test_investigate_negative_clean(synth, capsys):
    code, out, _ = _run(
        capsys,
        "investigate",
        "-i",
        str(synth / "synthetic_datasets" / "clean_split"),
        "-q",
        "Is my fine-tuning dataset contaminated?",
    )
    a = json.loads(out)["answer"]
    assert a["status"] == "INCONCLUSIVE" and "No evidence" in a["conclusion"]


def test_all_commands(synth, capsys, tmp_path):
    s = str(synth)
    cmds = [
        ["scan", "-i", s],
        ["train", "--logs", f"{s}/synthetic_training/stable.csv"],
        ["dataset", "-i", f"{s}/synthetic_datasets/dirty_train.jsonl"],
        [
            "leakage",
            "--train",
            f"{s}/synthetic_datasets/contaminated/train.jsonl",
            "--test",
            f"{s}/synthetic_datasets/contaminated/test.jsonl",
        ],
        ["tokenizer", "-i", f"{s}/synthetic_tokenization/inefficient_tokens.jsonl", "--max-length", "64"],
        ["generation", "-i", f"{s}/synthetic_generations/repetitive_outputs.jsonl"],
        ["compare", "--before", f"{s}/synthetic_runs/run_v1", "--after", f"{s}/synthetic_runs/run_v2"],
        ["checkpoint", "-i", f"{s}/synthetic_runs/run_v1"],
    ]
    for c in cmds:
        code, out, err = _run(capsys, *c)
        assert code == 0, (c, err)
        json.loads(out)
    code, _, _ = _run(capsys, "audit", "-i", f"{s}/demo_experiment", "-o", str(tmp_path / "rep"))
    assert code == 0 and {p.name for p in (tmp_path / "rep").iterdir()} == {"audit.json", "audit.md", "audit.html"}
    for fmt in ("markdown", "html"):
        code, out, _ = _run(capsys, "report", "-i", str(tmp_path / "rep" / "audit.json"), "--format", fmt)
        assert code == 0 and "Root Cause Investigation" in out
    code, out, _ = _run(
        capsys, "dataset", "-i", f"{s}/synthetic_datasets/clean_train.jsonl", "-f", "markdown", "--lang", "pt"
    )
    assert "Qualidade do Dataset" in out


def test_report_sections_order(synth):
    from deepmodel_inspector.analyzers import training
    from deepmodel_inspector.reporting.render import to_markdown

    md = to_markdown(consolidate([training.analyze_file(synth / "synthetic_training" / "overfitting.csv")]))
    heads = [ln for ln in md.splitlines() if ln.startswith("## ")]
    assert [h.split(".")[0] for h in heads] == [f"## {i}" for i in range(1, 12)]


def test_html_escapes_injected_content():
    rep = consolidate(
        [
            {
                "analysis": "dataset",
                "source": "<script>alert(1)</script>",
                "metrics": {},
                "limitations": [],
                "findings": [
                    {
                        "id": "DAT-001",
                        "rule": "DAT.X",
                        "category": "dataset",
                        "severity": "LOW",
                        "status": "CONFIRMED",
                        "title": "<img src=x onerror=alert(1)>",
                        "evidence": {},
                        "source": "s",
                        "explanation": "e",
                        "recommendation": "r",
                        "confirmation": "",
                    }
                ],
            }
        ]
    )
    h = to_html(rep)
    assert "<script>" not in h and "<img" not in h


def test_path_outside_root_rejected(tmp_path):
    (tmp_path / "allowed").mkdir()
    (tmp_path / "secret.txt").write_text("x")
    with pytest.raises(SecurityError):
        safe_input_path(tmp_path / "allowed" / ".." / "secret.txt", [str(tmp_path / "allowed")])


@pytest.mark.parametrize("name", [".env", "id_rsa", "server.pem", "credentials.json"])
def test_sensitive_files_rejected(tmp_path, name):
    p = tmp_path / name
    p.write_text("SECRET=1")
    with pytest.raises(SecurityError):
        safe_input_path(p)


def test_env_example_allowed(tmp_path):
    p = tmp_path / ".env.example"
    p.write_text("KEY=")
    assert safe_input_path(p) == p.resolve()


def test_unsafe_deserialization_refused(tmp_path):
    p = tmp_path / "model.pt"
    p.write_bytes(b"\x80\x04cos\nsystem\n.")
    with pytest.raises(SecurityError):
        safe_input_path(p)


def test_size_limit(tmp_path):
    p = tmp_path / "big.jsonl"
    p.write_bytes(b"{}\n" * 400_000)
    with pytest.raises(SecurityError):
        safe_input_path(p, max_mb=1)


def test_output_cannot_overwrite_input(tmp_path):
    p = tmp_path / "data.jsonl"
    p.write_text("{}\n")
    with pytest.raises(SecurityError):
        safe_output_path(p, [p])


def test_cli_security_exit_code(tmp_path, capsys, monkeypatch):
    (tmp_path / ".env").write_text("TOKEN=abc")
    code, _, err = _run(capsys, "dataset", "-i", str(tmp_path / ".env"))
    assert code == 3 and "sensitive" in err
    p = tmp_path / "ok.jsonl"
    p.write_text('{"text": "a b c"}\n')
    code, _, err = _run(capsys, "dataset", "-i", str(p), "--root", str(tmp_path / "nowhere"))
    assert code == 3 and "outside" in err
    code, _, err = _run(capsys, "dataset", "-i", "/etc/passwd")
    assert code == 3


def test_cli_invalid_json(tmp_path, capsys):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    code, _, err = _run(capsys, "train", "--logs", str(p))
    assert code == 2 and "invalid JSON" in err


def test_checkpoint_reads_only_safetensors_header(tmp_path):
    header = json.dumps(
        {"w": {"dtype": "F32", "shape": [4, 8], "data_offsets": [0, 128]}, "__metadata__": {"format": "pt"}}
    ).encode()
    (tmp_path / "model.safetensors").write_bytes(struct.pack("<Q", len(header)) + header + b"\x00" * 128)
    (tmp_path / "pytorch_model.bin").write_bytes(b"\x80\x04cos\nsystem\n.")
    (tmp_path / "config.json").write_text('{"vocab_size": 100}')
    (tmp_path / "tokenizer_config.json").write_text('{"vocab_size": 120}')
    r = checkpoint.analyze_dir(tmp_path)
    assert r["metrics"]["parameters_from_headers"] == 32
    assert r["metrics"]["pickle_files_not_loaded"][0]["file"] == "pytorch_model.bin"
    assert {"CKP.PICKLE", "CKP.VOCAB_MISMATCH"} <= {f["rule"] for f in r["findings"]}


def test_scan_skips_sensitive(tmp_path, capsys):
    (tmp_path / ".env").write_text("A=1")
    (tmp_path / "data.jsonl").write_text('{"text": "hello world"}\n')
    (tmp_path / "w.pt").write_bytes(b"x")
    code, out, _ = _run(capsys, "scan", "-i", str(tmp_path))
    kinds = {i["name"]: i["kind"] for i in json.loads(out)["inventory"]}
    assert kinds["w.pt"] == "skipped_unsafe_format" and ".env" not in kinds or kinds.get(".env") == "skipped_sensitive"


def test_findings_schema(synth, capsys):
    _, out, _ = _run(capsys, "audit", "-i", str(synth / "demo_experiment"))
    rep = json.loads(out)
    for f in rep["findings"]:
        assert {"id", "category", "severity", "status", "evidence", "source", "explanation", "recommendation"} <= set(f)
        assert f["status"] in ("CONFIRMED", "POTENTIAL", "INCONCLUSIVE")
