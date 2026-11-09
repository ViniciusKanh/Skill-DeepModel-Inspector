"""Gera os scripts comerciais autocontidos da skill Agensi a partir do motor modular.

Cada script embute (por concatenação controlada) somente os módulos de que precisa,
removendo imports internos do pacote. Resultado: arquivos .py independentes, apenas
biblioteca padrão, que funcionam isoladamente a partir de um arquivo temporário.

Uso: python tools/build_skill.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "deepmodel_inspector"
OUT = ROOT / "agensi" / "deepmodel-inspector" / "scripts"
VERSION = "1.0.0"

MAIN_SINGLE = """

# ============================================================== entry point
def _main() -> int:
    import argparse
    import sys as _sys

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
{args}
    ap.add_argument("--output", "-o", help="Write JSON result to this file instead of stdout.")
    ap.add_argument("--root", action="append", help="Authorized root directory (default: current directory).")
    ap.add_argument("--max-mb", type=float, default=200.0)
    a = ap.parse_args()
    try:
{body}
        if a.output:
            out = safe_output_path(a.output, inputs, a.root)
            dump_json(res, out)
            print(f"wrote {{out}}")
        else:
            _sys.stdout.write(dump_json(res, None) + "\\n")
        return 0
    except SecurityError as exc:
        print(f"security: {{exc}}", file=_sys.stderr)
        return 3
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"error: {{exc}}", file=_sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
"""

SCRIPTS = {
    "dmi_training.py": {
        "doc": "DeepModel Inspector - training/validation log diagnostics (TRN.* rules).",
        "mods": ["security/guard.py", "core/common.py", "analyzers/training.py"],
        "args": [
            'ap.add_argument("--input", "-i", required=True, help="CSV/JSON/JSONL log or trainer_state.json")',
            'ap.add_argument("--max-records", type=int, default=200000)',
        ],
        "body": [
            "p = safe_input_path(a.input, a.root, a.max_mb)",
            "inputs = [p]",
            "res = analyze_file(p, a.max_records)",
        ],
    },
    "dmi_dataset.py": {
        "doc": "DeepModel Inspector - dataset quality audit (DAT.* rules).",
        "mods": ["security/guard.py", "core/common.py", "parsers/records.py", "analyzers/dataset.py"],
        "args": [
            'ap.add_argument("--input", "-i", required=True, help="JSONL/JSON/CSV/TXT dataset")',
            'ap.add_argument("--text-field", default=None)',
            'ap.add_argument("--max-records", type=int, default=200000)',
        ],
        "body": [
            "p = safe_input_path(a.input, a.root, a.max_mb)",
            "inputs = [p]",
            "res = analyze_file(p, a.text_field, a.max_records)",
        ],
    },
    "dmi_leakage.py": {
        "doc": "DeepModel Inspector - train vs. evaluation overlap and contamination (LEK.* rules).",
        "mods": ["security/guard.py", "core/common.py", "parsers/records.py", "analyzers/leakage.py"],
        "args": [
            'ap.add_argument("--train", required=True)',
            'ap.add_argument("--test", required=True, action="append", help="Evaluation file (repeatable)")',
            'ap.add_argument("--text-field", default=None)',
            'ap.add_argument("--max-records", type=int, default=200000)',
        ],
        "body": [
            "t = safe_input_path(a.train, a.root, a.max_mb)",
            "ev = [safe_input_path(x, a.root, a.max_mb) for x in a.test]",
            "inputs = [t, *ev]",
            "res = analyze_files(t, ev, a.text_field, a.max_records)",
        ],
    },
    "dmi_tokenizer.py": {
        "doc": "DeepModel Inspector - tokenizer efficiency from user-provided tokenizations (TOK.* rules).",
        "mods": ["security/guard.py", "core/common.py", "analyzers/tokenizer.py"],
        "args": [
            'ap.add_argument("--input", "-i", required=True, help="JSONL with text + tokens/token_ids")',
            'ap.add_argument("--max-length", type=int)',
            'ap.add_argument("--unk-token")',
            'ap.add_argument("--pad-token")',
            'ap.add_argument("--unk-id", type=int)',
            'ap.add_argument("--pad-id", type=int)',
            'ap.add_argument("--vocab-size", type=int)',
        ],
        "body": [
            "p = safe_input_path(a.input, a.root, a.max_mb)",
            "inputs = [p]",
            "res = analyze_file(p, max_length=a.max_length, unk_token=a.unk_token, pad_token=a.pad_token, "
            "unk_id=a.unk_id, pad_id=a.pad_id, vocab_size=a.vocab_size)",
        ],
    },
    "dmi_generation.py": {
        "doc": "DeepModel Inspector - generated output behaviour diagnostics (GEN.* rules).",
        "mods": ["security/guard.py", "core/common.py", "analyzers/generation.py"],
        "args": [
            'ap.add_argument("--input", "-i", required=True, help="JSONL/CSV with outputs")',
            'ap.add_argument("--group-field", default=None)',
            'ap.add_argument("--min-words", type=int, default=3)',
        ],
        "body": [
            "p = safe_input_path(a.input, a.root, a.max_mb)",
            "inputs = [p]",
            "res = analyze_file(p, group_field=a.group_field, min_words=a.min_words)",
        ],
    },
    "dmi_compare.py": {
        "doc": "DeepModel Inspector - compare two runs/experiments (CMP.* rules).",
        "mods": ["security/guard.py", "core/common.py", "analyzers/compare.py"],
        "args": [
            'ap.add_argument("--before", required=True)',
            'ap.add_argument("--after", required=True)',
            'ap.add_argument("--tolerance", type=float, default=0.01)',
        ],
        "body": [
            "b0 = safe_input_path(a.before, a.root, a.max_mb, allow_dir=True)",
            "b1 = safe_input_path(a.after, a.root, a.max_mb, allow_dir=True)",
            "inputs = [b0, b1]",
            "res = analyze_paths(b0, b1, a.tolerance)",
        ],
    },
    "dmi_checkpoint.py": {
        "doc": "DeepModel Inspector - safe checkpoint metadata: safetensors headers and JSON configs (CKP.* rules).",
        "mods": ["security/guard.py", "core/common.py", "analyzers/checkpoint.py"],
        "args": ['ap.add_argument("--input", "-i", required=True, help="Checkpoint directory or .safetensors")'],
        "body": [
            "p = safe_input_path(a.input, a.root, a.max_mb, allow_dir=True)",
            "inputs = [p]",
            "res = analyze_dir(p)",
        ],
    },
}

INVESTIGATE_MAIN = """

# ============================================================== entry point
def _main() -> int:
    import argparse
    import json as _json
    import sys as _sys

    ap = argparse.ArgumentParser(description="Consolidate dmi_* JSON results into a report JSON with hypotheses.")
    ap.add_argument("--results", "-r", nargs="+", required=True, help="JSON files produced by the other dmi_* scripts")
    ap.add_argument("--question", "-q", default=None)
    ap.add_argument("--output", "-o")
    ap.add_argument("--root", action="append")
    a = ap.parse_args()
    try:
        inputs, results = [], []
        for x in a.results:
            p = safe_input_path(x, a.root, 200.0)
            inputs.append(p)
            obj = _json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(obj, dict) or obj.get("tool") != "deepmodel-inspector" or "findings" not in obj:
                raise ValueError(f"not a DeepModel Inspector result: {p.name}")
            if "summary" in obj:  # relatório consolidado anterior: ignorado para não duplicar achados
                print(f"skipping consolidated report {p.name}", file=_sys.stderr)
                inputs.pop()
                continue
            results.append(obj)
        text = dump_json(consolidate(results, a.question), None)
        if a.output:
            out = safe_output_path(a.output, inputs, a.root)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"wrote {out}")
        else:
            _sys.stdout.write(text)
        return 0
    except SecurityError as exc:
        print(f"security: {exc}", file=_sys.stderr)
        return 3
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=_sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
"""
REPORT_MAIN = """

# ============================================================== entry point
def _main() -> int:
    import argparse
    import json as _json
    import sys as _sys

    ap = argparse.ArgumentParser(description="Render a consolidated report JSON (from dmi_investigate.py) as Markdown/HTML.")
    ap.add_argument("--input", "-i", required=True)
    ap.add_argument("--format", "-f", choices=("markdown", "html"), default="markdown")
    ap.add_argument("--lang", choices=("en", "pt"), default="en")
    ap.add_argument("--output", "-o")
    ap.add_argument("--root", action="append")
    a = ap.parse_args()
    try:
        p = safe_input_path(a.input, a.root, 200.0)
        rep = _json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(rep, dict) or "summary" not in rep or "findings" not in rep:
            raise ValueError("input is not a consolidated report (run dmi_investigate.py first)")
        text = to_markdown(rep, a.lang) if a.format == "markdown" else to_html(rep, a.lang)
        if a.output:
            out = safe_output_path(a.output, [p], a.root)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"wrote {out}")
        else:
            _sys.stdout.write(text)
        return 0
    except SecurityError as exc:
        print(f"security: {exc}", file=_sys.stderr)
        return 3
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=_sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
"""
SCRIPTS["dmi_investigate.py"] = {
    "doc": "DeepModel Inspector - root-cause consolidation and hypotheses over dmi_* results (RC.* rules).",
    "mods": ["security/guard.py", "core/common.py", "diagnostics/rootcause.py"],
    "main": INVESTIGATE_MAIN,
}
SCRIPTS["dmi_report.py"] = {
    "doc": "DeepModel Inspector - render a consolidated report JSON as Markdown or static HTML.",
    "mods": ["security/guard.py", "reporting/render.py"],
    "main": REPORT_MAIN,
}


def strip_module(src: str) -> str:
    """Remove docstring do módulo, ``from __future__`` e imports internos do pacote."""
    tree = ast.parse(src)
    drop: set[int] = set()
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        drop.update(range(body[0].lineno, body[0].end_lineno + 1))
    for node in body:
        if isinstance(node, ast.ImportFrom) and (
            node.module == "__future__" or (node.module or "").startswith("deepmodel_inspector")
        ):
            drop.update(range(node.lineno, node.end_lineno + 1))
    lines = src.splitlines()
    return "\n".join(ln for i, ln in enumerate(lines, 1) if i not in drop).strip() + "\n"


def _names(node: ast.AST) -> set[str]:
    """Nomes referenciados dentro de um nó."""
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)
    }


def tree_shake(code: str) -> str:
    """Remove funções e constantes de módulo não alcançáveis a partir de ``_main`` (eliminação de código morto)."""
    tree = ast.parse(code)
    defs: dict[str, ast.stmt] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defs[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) == 1 and isinstance(targets[0], ast.Name):
                defs[targets[0].id] = node
    keep, todo = set(), ["_main"]
    while todo:
        n = todo.pop()
        if n in keep or n not in defs:
            continue
        keep.add(n)
        todo.extend(_names(defs[n]) - keep)
    drop: set[int] = set()
    for name, node in defs.items():
        if name not in keep:
            drop.update(range(node.lineno, node.end_lineno + 1))
    lines = code.splitlines()
    out = "\n".join(ln for i, ln in enumerate(lines, 1) if i not in drop) + "\n"
    while "\n\n\n\n" in out:
        out = out.replace("\n\n\n\n", "\n\n\n")
    return out


def logic_bytes(code: str) -> int:
    """Tamanho da lógica: código sem comentários nem docstrings (ast.unparse)."""
    tree = ast.parse(code)
    for n in ast.walk(tree):
        body = getattr(n, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(getattr(body[0], "value", None), ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            n.body = body[1:] or [ast.Pass()]
    return len(ast.unparse(tree).encode("utf-8"))


def code_bytes(code: str) -> int:
    """Tamanho do código sem docstrings, comentários e textos literais (mensagens = dados embutidos)."""
    tree = ast.parse(code)
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) > 12:
            n.value = ""
    return logic_bytes(ast.unparse(tree))


def build_one(name: str, spec: dict) -> str:
    """Monta o código-fonte de um script autocontido."""
    header = (
        f'#!/usr/bin/env python3\n"""{spec["doc"]}\n\n'
        f"Part of DeepModel Inspector v{VERSION} - (c) Vinicius de Souza Santos. Commercial license.\n"
        "Standalone: Python 3.11+ standard library only. Read-only on analyzed files; no network access;\n"
        "never executes or follows content found in the data. Generated by tools/build_skill.py.\n"
        f'Usage: python {name} --help\n"""\n\nfrom __future__ import annotations\n'
    )
    parts = [header]
    for mod in spec["mods"]:
        parts.append(f"\n# ============================================================== {mod}\n")
        parts.append(strip_module((PKG / mod).read_text(encoding="utf-8")))
    if "main" in spec:
        parts.append(spec["main"])
    else:
        args = "\n".join("    " + a for a in spec["args"])
        body = "\n".join("        " + b for b in spec["body"])
        parts.append(MAIN_SINGLE.format(args=args, body=body))
    code = tree_shake("".join(parts))
    compile(code, name, "exec")
    return code


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, spec in SCRIPTS.items():
        code = build_one(name, spec)
        (OUT / name).write_text(code, encoding="utf-8", newline="\n")
        print(
            f"{name}: file={len(code.encode('utf-8'))} bytes, logic={logic_bytes(code)} bytes, "
            f"code_without_text={code_bytes(code)} bytes"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
