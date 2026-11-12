"""Interface de linha de comando ``deepmodel``.

Comandos: scan, train, dataset, leakage, tokenizer, generation, compare, checkpoint,
audit, report, investigate. Todas as entradas são lidas em modo somente leitura.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from deepmodel_inspector.analyzers import checkpoint, compare, dataset, generation, leakage, tokenizer, training
from deepmodel_inspector.core.common import VERSION, dump_json
from deepmodel_inspector.diagnostics.inventory import run_audit, scan
from deepmodel_inspector.diagnostics.live import consolidate
from deepmodel_inspector.reporting.render import to_html, to_markdown
from deepmodel_inspector.security.guard import SecurityError, safe_input_path, safe_output_path

EXIT_OK, EXIT_ERROR, EXIT_SECURITY, EXIT_THRESHOLD = 0, 2, 3, 4


def _common(p: argparse.ArgumentParser) -> None:
    """Opções compartilhadas por todos os subcomandos."""
    p.add_argument("--output", "-o", help="Output file (or directory for 'audit').")
    p.add_argument("--format", "-f", choices=("json", "markdown", "html"), default="json")
    p.add_argument("--lang", choices=("en", "pt"), default="en", help="Report heading language.")
    p.add_argument(
        "--root",
        action="append",
        default=None,
        help="Authorized root directory (repeatable). Default: current directory.",
    )
    p.add_argument("--max-mb", type=float, default=200.0, help="Maximum size per input file in MB.")
    p.add_argument("--max-records", type=int, default=200_000)


def build_parser() -> argparse.ArgumentParser:
    """Constrói o parser com todos os subcomandos."""
    ap = argparse.ArgumentParser(
        prog="deepmodel",
        description="DeepModel Inspector - LLM training, dataset & generation diagnostics (offline, read-only).",
    )
    ap.add_argument("--version", action="version", version=f"deepmodel-inspector {VERSION}")
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="Inventory artifacts in a directory.")
    s.add_argument("--input", "-i", required=True)
    s = sub.add_parser("train", help="Training/validation log diagnostics.")
    s.add_argument("--logs", "-i", "--input", dest="input", required=True)
    s = sub.add_parser("dataset", help="Dataset quality audit.")
    s.add_argument("--input", "-i", required=True)
    s.add_argument("--text-field", default=None, help="Column/field holding text (CSV or custom JSONL).")
    s = sub.add_parser("leakage", help="Train vs. eval overlap / contamination.")
    s.add_argument("--train", required=True)
    s.add_argument("--test", required=True, action="append", help="Evaluation file (repeatable).")
    s.add_argument("--text-field", default=None)
    s = sub.add_parser("tokenizer", help="Tokenizer efficiency from provided tokenizations.")
    s.add_argument("--input", "-i", required=True)
    s.add_argument("--max-length", type=int)
    s.add_argument("--unk-token")
    s.add_argument("--pad-token")
    s.add_argument("--vocab-size", type=int)
    s.add_argument("--hf-tokenizer", help="Optional LOCAL Hugging Face tokenizer directory to tokenize 'text'.")
    s = sub.add_parser("generation", help="Generated output behaviour diagnostics.")
    s.add_argument("--input", "-i", required=True)
    s.add_argument("--group-field", default=None)
    s.add_argument("--min-words", type=int, default=3)
    s = sub.add_parser("compare", help="Compare two runs (directories or log files).")
    s.add_argument("--before", required=True)
    s.add_argument("--after", required=True)
    s.add_argument("--tolerance", type=float, default=0.01)
    s = sub.add_parser("checkpoint", help="Safe checkpoint metadata (safetensors headers, configs).")
    s.add_argument("--input", "-i", required=True)
    s = sub.add_parser("audit", help="Run every applicable analysis on a directory.")
    s.add_argument("--input", "-i", required=True)
    s = sub.add_parser("report", help="Render an audit JSON as markdown/html.")
    s.add_argument("--input", "-i", required=True)
    s = sub.add_parser("investigate", help="Evidence-based answer to a question about an experiment directory.")
    s.add_argument("--input", "-i", required=True)
    s.add_argument("--question", "-q", required=True)
    s = sub.add_parser("probe", help="Live behavioural inspection of a model via an OpenAI-compatible API.")
    s.add_argument(
        "--base-url", required=True, help="e.g. http://localhost:11434/v1 (Ollama) or https://api.openai.com/v1"
    )
    s.add_argument("--model", required=True)
    s.add_argument("--api-key-env", default=None, help="Name of the environment variable holding the API key.")
    s.add_argument("--suite", choices=("quick", "standard", "custom"), default="standard")
    s.add_argument("--prompts", default=None, help="Optional JSONL with prompt[, expected, reference].")
    s.add_argument("--max-calls", type=int, default=200)
    s.add_argument("--timeout", type=float, default=60.0)
    s.add_argument(
        "--allow-remote",
        action="store_true",
        help="Required for non-localhost endpoints: probe prompts will be sent to that server.",
    )
    s = sub.add_parser("hub", help="Inspect a Hugging Face model repo WITHOUT downloading weights (metadata only).")
    s.add_argument("--repo", required=True, help="e.g. Qwen/Qwen2.5-0.5B-Instruct")
    s.add_argument("--revision", default="main")
    s.add_argument("--token-env", default="HF_TOKEN", help="Env var with an HF token (only for private/gated repos).")
    s.add_argument("--hub-url", default="https://huggingface.co", help=argparse.SUPPRESS)
    s = sub.add_parser("monitor", help="Production monitoring from exported logs (per day/week).")
    s.add_argument("--input", "-i", required=True, help="Log file or directory of JSONL/CSV logs.")
    s.add_argument("--period", choices=("day", "week"), default="day")
    s.add_argument("--thresholds", default=None, help="JSON file overriding default thresholds.")
    s.add_argument(
        "--fail-on",
        choices=("CRITICAL", "HIGH", "MEDIUM", "LOW"),
        default=None,
        help="Exit with code 4 when a finding of this severity or worse is present.",
    )
    for p in sub.choices.values():
        _common(p)
    return ap


def _hf_tokenize(path: Path, tok_dir: Path, recs_path: Path, max_records: int) -> list[dict[str, Any]]:
    """Tokeniza com um tokenizer Hugging Face LOCAL (opcional; local_files_only)."""
    try:
        from transformers import AutoTokenizer  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ValueError("--hf-tokenizer requires the optional 'transformers' package") from exc
    from deepmodel_inspector.core.common import load_table

    tok = AutoTokenizer.from_pretrained(str(tok_dir), local_files_only=True, trust_remote_code=False)
    recs, _ = load_table(recs_path, max_records)
    return [
        {"text": str(r.get("text", "")), "tokens": tok.tokenize(str(r.get("text", ""))), "tokenizer": tok_dir.name}
        for r in recs
    ]


def _relative(inv: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    """Substitui caminhos absolutos por relativos à raiz analisada (evita expor diretórios do usuário)."""
    base = root if root.is_dir() else root.parent
    out = []
    for it in inv:
        c = dict(it)
        try:
            c["path"] = Path(it["path"]).relative_to(base).as_posix() or "."
        except ValueError:
            c["path"] = Path(it["path"]).name
        out.append(c)
    return out


def run(args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    """Executa o subcomando e devolve (relatório/resultado, entradas usadas)."""
    roots, mb, mr = args.root, args.max_mb, args.max_records

    def inp(p: str, allow_dir: bool = False) -> Path:
        return safe_input_path(p, roots, mb, allow_dir)

    c = args.command
    if c == "scan":
        p = inp(args.input, True)
        inv = _relative(scan(p), p)
        return {"tool": "deepmodel-inspector", "version": VERSION, "analysis": "scan", "inventory": inv}, [p]
    if c == "train":
        p = inp(args.input)
        return training.analyze_file(p, mr), [p]
    if c == "dataset":
        p = inp(args.input)
        return dataset.analyze_file(p, args.text_field, mr), [p]
    if c == "leakage":
        t = inp(args.train)
        ev = [inp(x) for x in args.test]
        return leakage.analyze_files(t, ev, args.text_field, mr), [t, *ev]
    if c == "tokenizer":
        p = inp(args.input)
        kw = dict(
            max_length=args.max_length, unk_token=args.unk_token, pad_token=args.pad_token, vocab_size=args.vocab_size
        )
        if args.hf_tokenizer:
            recs = _hf_tokenize(p, inp(args.hf_tokenizer, True), p, mr)
            return tokenizer.analyze_records(recs, p.name, **kw), [p]
        return tokenizer.analyze_file(p, max_records=mr, **kw), [p]
    if c == "generation":
        p = inp(args.input)
        return generation.analyze_file(p, max_records=mr, group_field=args.group_field, min_words=args.min_words), [p]
    if c == "compare":
        a, b = inp(args.before, True), inp(args.after, True)
        return compare.analyze_paths(a, b, args.tolerance), [a, b]
    if c == "checkpoint":
        p = inp(args.input, True)
        return checkpoint.analyze_dir(p), [p]
    if c == "report":
        p = inp(args.input)
        rep = json.loads(p.read_text(encoding="utf-8"))
        if "findings" not in rep:
            raise ValueError("input is not a DeepModel Inspector JSON")
        if "summary" not in rep:
            rep = consolidate([rep])
        return rep, [p]
    if c == "probe":
        import os

        from deepmodel_inspector.probe.client import Target
        from deepmodel_inspector.probe.runner import analyze_records as analyze_probe
        from deepmodel_inspector.probe.runner import run_probe

        key = os.environ.get(args.api_key_env) if args.api_key_env else None
        if args.api_key_env and not key:
            raise ValueError(f"environment variable {args.api_key_env} is not set")
        tgt = Target(args.base_url, args.model, key, args.timeout)
        if not tgt.is_local and not args.allow_remote:
            raise SecurityError(f"remote endpoint {tgt.host}: pass --allow-remote to send probe prompts to it")
        custom, used = None, []
        if args.prompts:
            pp = inp(args.prompts)
            from deepmodel_inspector.core.common import load_table

            custom, used = load_table(pp, mr)[0], [pp]
        recs = run_probe(
            tgt,
            args.suite,
            custom,
            max_calls=args.max_calls,
            progress=lambda d, t, m: print(f"[{d}/{t}] {m}", file=sys.stderr),
        )
        res = analyze_probe(recs, f"{tgt.model}@{tgt.host}")
        return consolidate(res, None, [{"analysis": "probe", "source": f"{tgt.model}@{tgt.host}"}]), used
    if c == "hub":
        import os

        from deepmodel_inspector.probe import hub

        try:
            res = hub.inspect(args.repo, os.environ.get(args.token_env) or None, args.revision, args.hub_url)
        except hub.HubError as exc:
            raise ValueError(f"Hugging Face: {exc}") from None
        return consolidate([res], None, [{"analysis": "hub", "source": f"hf:{args.repo}"}]), []
    if c == "monitor":
        from deepmodel_inspector.analyzers import monitor

        p = inp(args.input, True)
        files = (
            [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.suffix.lower() in (".jsonl", ".csv", ".json"))
        )
        th = json.loads(inp(args.thresholds).read_text(encoding="utf-8")) if args.thresholds else None
        res = monitor.analyze_paths([safe_input_path(f, roots, mb) for f in files], args.period, th, mr)
        return consolidate([res]), [p]
    if c in ("audit", "investigate"):
        p = inp(args.input, True)
        inv, results = run_audit(p, mr)
        return consolidate(results, getattr(args, "question", None), _relative(inv, p)), [p]
    raise ValueError(f"unknown command {c}")


def render(obj: dict[str, Any], fmt: str, lang: str) -> str:
    """Converte o resultado no formato pedido (relatórios consolidados para md/html)."""
    if fmt == "json":
        return dump_json(obj, None)
    rep = obj if "summary" in obj else consolidate([obj]) if "findings" in obj else None
    if rep is None:
        return dump_json(obj, None)
    return to_markdown(rep, lang) if fmt == "markdown" else to_html(rep, lang)


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da CLI. Retorna 0 (ok), 2 (erro de entrada) ou 3 (segurança)."""
    args = build_parser().parse_args(argv)
    try:
        obj, inputs = run(args)
        if args.command == "audit" and args.output:
            out_dir = safe_output_path(args.output, inputs, args.root)
            if out_dir.suffix:
                out_dir = out_dir.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            dump_json(obj, out_dir / "audit.json")
            (out_dir / "audit.md").write_text(to_markdown(obj, args.lang), encoding="utf-8")
            (out_dir / "audit.html").write_text(to_html(obj, args.lang), encoding="utf-8")
            print(f"wrote {out_dir / 'audit.json'}, audit.md, audit.html")
            return EXIT_OK
        code = EXIT_OK
        fail_on = getattr(args, "fail_on", None)
        if fail_on:
            order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
            worst = {f["severity"] for f in obj.get("findings", [])}
            if any(s in worst for s in order[: order.index(fail_on) + 1]):
                code = EXIT_THRESHOLD
        text = render(obj, args.format, args.lang)
        if args.output:
            out = safe_output_path(args.output, inputs, args.root)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"wrote {out}")
        else:
            sys.stdout.write(text)
        return code
    except SecurityError as exc:
        print(f"security: {exc}", file=sys.stderr)
        return EXIT_SECURITY
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
