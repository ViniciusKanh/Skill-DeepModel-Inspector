"""Paridade entre o motor local e os scripts comerciais, e execução isolada dos scripts."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from deepmodel_inspector.analyzers import compare, dataset, generation, leakage, tokenizer, training
from deepmodel_inspector.diagnostics.rootcause import consolidate

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "agensi" / "deepmodel-inspector" / "scripts"


def _build():
    spec = importlib.util.spec_from_file_location("build_skill", ROOT / "tools" / "build_skill.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_scripts_are_up_to_date():
    b = _build()
    for name, spec in b.SCRIPTS.items():
        assert (SCRIPTS / name).read_text(encoding="utf-8") == b.build_one(name, spec), f"rebuild {name}"


def _run_isolated(tmp_path: Path, script: str, args: list[str], cwd: Path) -> tuple[int, str, str]:
    iso = tmp_path / f"iso_{script}"
    iso.mkdir(exist_ok=True)
    shutil.copy(SCRIPTS / script, iso / script)
    p = subprocess.run(
        [sys.executable, "-I", str(iso / script), *args], cwd=cwd, capture_output=True, text=True, timeout=300
    )
    return p.returncode, p.stdout, p.stderr


def _norm(obj):
    return json.loads(json.dumps(obj, default=str))


CASES = [
    (
        "dmi_training.py",
        ["--input", "synthetic_training/divergent.csv"],
        lambda s: training.analyze_file(s / "synthetic_training/divergent.csv"),
    ),
    (
        "dmi_dataset.py",
        ["--input", "synthetic_datasets/dirty_train.jsonl"],
        lambda s: dataset.analyze_file(s / "synthetic_datasets/dirty_train.jsonl"),
    ),
    (
        "dmi_leakage.py",
        [
            "--train",
            "synthetic_datasets/contaminated/train.jsonl",
            "--test",
            "synthetic_datasets/contaminated/test.jsonl",
        ],
        lambda s: leakage.analyze_files(
            s / "synthetic_datasets/contaminated/train.jsonl", [s / "synthetic_datasets/contaminated/test.jsonl"]
        ),
    ),
    (
        "dmi_tokenizer.py",
        ["--input", "synthetic_tokenization/tokenizer_comparison.jsonl", "--max-length", "64"],
        lambda s: tokenizer.analyze_file(s / "synthetic_tokenization/tokenizer_comparison.jsonl", max_length=64),
    ),
    (
        "dmi_generation.py",
        ["--input", "synthetic_generations/configs_comparison.jsonl"],
        lambda s: generation.analyze_file(s / "synthetic_generations/configs_comparison.jsonl"),
    ),
    (
        "dmi_compare.py",
        ["--before", "synthetic_runs/run_v1", "--after", "synthetic_runs/run_v2"],
        lambda s: compare.analyze_paths(s / "synthetic_runs/run_v1", s / "synthetic_runs/run_v2"),
    ),
]


@pytest.mark.parametrize("script,args,engine", CASES, ids=[c[0] for c in CASES])
def test_parity_engine_vs_script(synth, tmp_path, script, args, engine):
    code, out, err = _run_isolated(tmp_path, script, args, synth)
    assert code == 0, err
    assert json.loads(out) == _norm(engine(synth))


def test_investigate_and_report_parity(synth, tmp_path):
    files, results = [], []
    for i, (script, args, engine) in enumerate(CASES):
        out = tmp_path / f"r{i}.json"
        code, _, err = _run_isolated(
            tmp_path, script, [*args, "--output", str(out), "--root", str(tmp_path), "--root", str(synth)], synth
        )
        assert code == 0, err
        files.append(str(out))
        results.append(_norm(engine(synth)))
    q = "Why did model performance drop after SFT?"
    rep_path = tmp_path / "report.json"
    code, _, err = _run_isolated(
        tmp_path,
        "dmi_investigate.py",
        ["--results", *files, "--question", q, "-o", str(rep_path), "--root", str(tmp_path)],
        synth,
    )
    assert code == 0, err
    script_rep = json.loads(rep_path.read_text(encoding="utf-8"))
    engine_rep = _norm(consolidate(results, q))
    for key in ("findings", "hypotheses", "experiments", "answer", "summary"):
        assert script_rep[key] == engine_rep[key], key
    code, md, err = _run_isolated(tmp_path, "dmi_report.py", ["--input", str(rep_path), "--root", str(tmp_path)], synth)
    assert code == 0 and "## 8. Root Cause Investigation" in md


def test_script_security_refusals(synth, tmp_path):
    (synth / "fake.env").write_text("x")
    (synth / ".env").write_text("TOKEN=1")
    code, _, err = _run_isolated(tmp_path, "dmi_dataset.py", ["--input", ".env"], synth)
    assert code == 3 and "sensitive" in err
    code, _, err = _run_isolated(tmp_path, "dmi_dataset.py", ["--input", "../../../../etc/hosts"], synth)
    assert code == 3
    code, _, _ = _run_isolated(tmp_path, "dmi_training.py", ["--input", "missing.csv"], synth)
    assert code == 2
