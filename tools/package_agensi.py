"""Valida e empacota a skill Agensi em dist/deepmodel-inspector-v1.0.0.zip.

Etapas: (1) regenera scripts, (2) valida SKILL.md, (3) verifica tipos de arquivo,
(4) varre segredos e chamadas perigosas, (5) mede tamanhos, (6) cria ZIP determinístico,
(7) extrai o ZIP e executa cada script isoladamente sobre dados sintéticos, (8) calcula SHA-256.

Uso: python tools/package_agensi.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "agensi" / "deepmodel-inspector"
DIST = ROOT / "dist"
ZIP_NAME = "deepmodel-inspector-v1.0.0.zip"
ALLOWED_SUFFIXES = {".md", ".py"}
BLOCKED = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".app",
    ".dmg",
    ".msi",
    ".deb",
    ".rpm",
    ".wasm",
    ".class",
    ".jar",
    ".war",
    ".pyc",
    ".pkl",
    ".pt",
}
SECRET_PATTERNS = {
    "openai_like_key": r"\bsk-[A-Za-z0-9]{20,}",
    "github_token": r"\bgh[pousr]_[A-Za-z0-9]{20,}",
    "aws_access_key": r"\bAKIA[0-9A-Z]{16}\b",
    "private_key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "hf_token": r"\bhf_[A-Za-z0-9]{20,}",
}
DANGEROUS = {
    "subprocess": r"\bimport subprocess|\bsubprocess\.",
    "os_system": r"\bos\.system\(|\bos\.popen\(",
    "eval_exec": r"(?<![\w.])(eval|exec)\(",
    "network": r"\bimport (socket|urllib|requests|http\.client|ftplib)\b|"
    r"\bfrom (urllib|requests|http)\b",
    "pickle": r"\bimport pickle\b|\bpickle\.load",
    "env_access": r"os\.environ|getenv\(",
    "delete": r"shutil\.rmtree|os\.remove\(|os\.unlink\(|\.unlink\(",
    "shell": r"shell=True",
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def frontmatter(text: str) -> dict[str, str]:
    """Extrai chaves de nível superior do frontmatter YAML (validação estrutural simples)."""
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with frontmatter '---'")
    end = text.index("\n---", 4)
    keys = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if m:
            keys[m.group(1)] = m.group(2)
    return keys


def main() -> int:
    build = _load("build_skill", ROOT / "tools" / "build_skill.py")
    build.main()
    report: dict = {"zip": f"dist/{ZIP_NAME}", "checks": {}, "files": [], "scripts": {}}
    fm = frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
    assert fm.get("name") and fm.get("description"), "name/description required"
    assert len(fm["description"]) <= 1024
    report["checks"]["frontmatter"] = {k: (v[:60] + "…" if len(v) > 60 else v) for k, v in fm.items()}
    files = sorted(p for p in SKILL.rglob("*") if p.is_file())
    problems = []
    for p in files:
        rel = p.relative_to(SKILL).as_posix()
        if "__pycache__" in rel or p.suffix.lower() in BLOCKED or p.suffix.lower() not in ALLOWED_SUFFIXES:
            problems.append(f"disallowed file: {rel}")
        text = p.read_text(encoding="utf-8")
        for k, rx in SECRET_PATTERNS.items():
            if re.search(rx, text):
                problems.append(f"secret pattern {k} in {rel}")
        if p.suffix == ".py":
            for k, rx in DANGEROUS.items():
                if re.search(rx, text):
                    problems.append(f"dangerous pattern {k} in {rel}")
            code = text
            report["scripts"][p.name] = {
                "file_bytes": len(code.encode()),
                "logic_bytes": build.logic_bytes(code),
                "code_without_text_bytes": build.code_bytes(code),
            }
    report["checks"]["static_problems"] = problems
    if problems:
        print("\n".join(problems))
        return 1
    DIST.mkdir(exist_ok=True)
    zpath = DIST / ZIP_NAME
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            info = zipfile.ZipInfo("deepmodel-inspector/" + p.relative_to(SKILL).as_posix(), (2026, 11, 9, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, p.read_bytes())
    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    with zipfile.ZipFile(zpath) as z:
        report["files"] = [{"path": i.filename, "bytes": i.file_size} for i in z.infolist()]
    report.update({"sha256": sha, "zip_bytes": zpath.stat().st_size, "file_count": len(report["files"])})
    report["checks"]["isolated_runs"] = isolated_runs(zpath)
    ok = all(r["exit"] == r["expected_exit"] for r in report["checks"]["isolated_runs"])
    (DIST / "package-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (DIST / "SHA256SUMS.txt").write_text(f"{sha}  {ZIP_NAME}\n", encoding="utf-8")
    print(f"{ZIP_NAME} sha256={sha} files={report['file_count']} isolated_runs_ok={ok}")
    return 0 if ok else 1


def isolated_runs(zpath: Path) -> list[dict]:
    """Extrai o ZIP e executa cada script sozinho (cópia isolada, python -I) sobre dados sintéticos."""
    gen = _load("gen_synth", ROOT / "examples" / "generate_synthetic.py")
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(t / "zip")
        data = t / "work"
        gen.generate(data)
        res = data / "dmi_results"
        res.mkdir()
        cases = [
            (
                "dmi_training.py",
                ["--input", "synthetic_training/overfitting.csv", "-o", "dmi_results/training.json"],
                0,
            ),
            ("dmi_dataset.py", ["--input", "demo_experiment/data/train.jsonl", "-o", "dmi_results/dataset.json"], 0),
            (
                "dmi_leakage.py",
                [
                    "--train",
                    "demo_experiment/data/train.jsonl",
                    "--test",
                    "demo_experiment/data/test.jsonl",
                    "-o",
                    "dmi_results/leakage.json",
                ],
                0,
            ),
            (
                "dmi_tokenizer.py",
                [
                    "--input",
                    "synthetic_tokenization/tokenizer_comparison.jsonl",
                    "--max-length",
                    "64",
                    "-o",
                    "dmi_results/tokenizer.json",
                ],
                0,
            ),
            (
                "dmi_generation.py",
                ["--input", "demo_experiment/outputs/generations.jsonl", "-o", "dmi_results/generation.json"],
                0,
            ),
            (
                "dmi_compare.py",
                [
                    "--before",
                    "synthetic_runs/run_v1",
                    "--after",
                    "synthetic_runs/run_v2",
                    "-o",
                    "dmi_results/compare.json",
                ],
                0,
            ),
            ("dmi_checkpoint.py", ["--input", "synthetic_runs/run_v1"], 0),
            (
                "dmi_investigate.py",
                [
                    "--results",
                    "dmi_results/training.json",
                    "dmi_results/dataset.json",
                    "dmi_results/leakage.json",
                    "dmi_results/tokenizer.json",
                    "dmi_results/generation.json",
                    "dmi_results/compare.json",
                    "--question",
                    "Why is my LLM repeating the same sentences?",
                    "-o",
                    "dmi_results/report.json",
                ],
                0,
            ),
            (
                "dmi_report.py",
                ["--input", "dmi_results/report.json", "--format", "markdown", "-o", "dmi_results/report.md"],
                0,
            ),
            (
                "dmi_report.py",
                ["--input", "dmi_results/report.json", "--format", "html", "-o", "dmi_results/report.html"],
                0,
            ),
            ("dmi_dataset.py", ["--input", "/etc/hosts"], 3),
            ("dmi_training.py", ["--input", "synthetic_training/does_not_exist.csv"], 2),
        ]
        for script, args, expected in cases:
            iso = t / f"iso_{len(out)}"
            iso.mkdir()
            shutil.copy(t / "zip" / "deepmodel-inspector" / "scripts" / script, iso / script)
            p = subprocess.run(
                [sys.executable, "-I", str(iso / script), *args], cwd=data, capture_output=True, text=True, timeout=300
            )
            out.append(
                {
                    "script": script,
                    "args": " ".join(args)[:120],
                    "exit": p.returncode,
                    "expected_exit": expected,
                    "stderr": p.stderr.strip()[:200],
                }
            )
        for name in ("report.md", "report.html"):
            dest = ROOT / "examples" / "sample_reports" / f"skill_{name}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            if (res / name).exists():
                shutil.copy(res / name, dest)
        if (res / "report.json").exists():
            shutil.copy(res / "report.json", ROOT / "examples" / "sample_reports" / "skill_report.json")
    return out


if __name__ == "__main__":
    sys.exit(main())
