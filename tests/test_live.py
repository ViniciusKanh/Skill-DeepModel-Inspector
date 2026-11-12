"""Testes da sondagem ao vivo (servidor LLM simulado) e do monitoramento de produção."""

from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import ROOT, rules

from deepmodel_inspector.analyzers import monitor
from deepmodel_inspector.cli import main
from deepmodel_inspector.diagnostics import live, rootcause
from deepmodel_inspector.probe.client import Target, chat
from deepmodel_inspector.probe.runner import ProbeCancelled, analyze_records, run_probe


def _fake():
    spec = importlib.util.spec_from_file_location("fake_llm_server", ROOT / "examples" / "fake_llm_server.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def server():
    srv, port = _fake().start(0)
    yield f"http://127.0.0.1:{port}/v1"
    srv.shutdown()


def all_rules(results):
    return {f["rule"] for r in results for f in r["findings"]}


def test_flawed_model_detected(server):
    recs = run_probe(Target(server, "demo-flawed"), "standard")
    res = analyze_records(recs, "demo-flawed")
    rs = all_rules(res)
    assert {
        "PRB.INJECTION",
        "PRB.INSTRUCTION",
        "PRB.ACCURACY",
        "PRB.GROUNDING",
        "PRB.REPETITION_STRESS",
        "GEN.REPETITION",
    } <= rs
    inj = next(f for f in res[0]["findings"] if f["rule"] == "PRB.INJECTION")
    assert inj["status"] == "CONFIRMED" and inj["evidence"]["leaks"] >= 1
    m = res[0]["metrics"]
    assert m["calls"] == len(recs) == 43 and m["error_rate"] == 0 and m["latency_ms"]["n"] == 43


def test_good_model_no_false_positives(server):
    res = analyze_records(run_probe(Target(server, "demo-good"), "standard"), "demo-good")
    assert all_rules(res) == {"PRB.OK"}
    assert all(c["pass_rate"] in (None, 1.0) for c in res[0]["metrics"]["categories"].values())


def test_quick_suite_and_custom_prompts(server, tmp_path):
    custom = [
        {"prompt": "What is the capital of France?", "expected": "Lyon"},
        {"prompt": "Say hi", "expected": "Paris"},
    ]
    recs = run_probe(Target(server, "demo-good"), "custom", custom)
    assert len(recs) == 2 and "PRB.CUSTOM" in all_rules(analyze_records(recs, "x"))
    assert len(run_probe(Target(server, "demo-good"), "quick")) < 30


def test_unreachable_and_errors():
    t = Target("http://127.0.0.1:9/v1", "m", timeout=2)
    res = analyze_records(run_probe(t, "quick", max_calls=3), "dead")
    assert all_rules(res) == {"PRB.UNREACHABLE"}
    n = {"i": 0}

    def flaky(target, messages, params):
        n["i"] += 1
        err = "HTTP 500: boom" if n["i"] % 4 == 0 else None
        return {
            "text": "" if err else "ok",
            "finish_reason": "stop",
            "latency_ms": 20000.0,
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "error": err,
        }

    res = analyze_records(run_probe(Target("http://localhost/v1", "m"), "quick", chat_fn=flaky), "flaky")
    assert {"PRB.ERRORS", "PRB.LATENCY"} <= all_rules(res)


def test_cancel(server):
    ev = threading.Event()
    ev.set()
    with pytest.raises(ProbeCancelled):
        run_probe(Target(server, "demo-good"), "quick", cancel=ev)


def test_target_validation_and_redirect_blocked():
    with pytest.raises(ValueError):
        Target("file:///etc/passwd", "m")
    with pytest.raises(ValueError):
        Target("http://localhost:1/v1", " ")
    assert Target("http://localhost:11434/v1", "m").is_local and not Target("https://api.example.com/v1", "m").is_local

    class R(BaseHTTPRequestHandler):
        def log_message(self, *a):
            return

        def do_POST(self):  # noqa: N802
            self.send_response(302)
            self.send_header("Location", "http://evil.example/steal")
            self.end_headers()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), R)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    out = chat(
        Target(f"http://127.0.0.1:{srv.server_address[1]}/v1", "m", api_key="secret"),
        [{"role": "user", "content": "x"}],
    )
    srv.shutdown()
    assert out["error"] and out["error"].startswith("HTTP 302") and "secret" not in out["error"]


def test_cli_probe_remote_requires_consent(capsys):
    assert main(["probe", "--base-url", "https://api.example.com/v1", "--model", "m"]) == 3
    assert "allow-remote" in capsys.readouterr().err


def test_cli_probe_local(server, capsys):
    assert main(["probe", "--base-url", server, "--model", "demo-flawed", "--suite", "quick"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert "probe" in rep["analyses_run"] and any(h["rule"] == "RC.LIVE_INJECTION" for h in rep["hypotheses"])


def test_live_question_and_engine_untouched(server):
    before = dict(rootcause.INTENTS)
    res = analyze_records(run_probe(Target(server, "demo-flawed"), "quick"), "x")
    rep = live.consolidate(res, "Is my model vulnerable to prompt injection?")
    assert rep["answer"]["status"] == "CONFIRMED" and "injection" in rep["answer"]["intents"]
    hy = {h["rule"] for h in rep["hypotheses"] if h["id"] in rep["answer"]["hypotheses"]}
    assert "RC.LIVE_INJECTION" in hy
    assert before == rootcause.INTENTS


def test_monitor_detects_degraded_week(synth):
    res = monitor.analyze_paths(sorted((synth / "synthetic_production").glob("*.jsonl")), "week")
    rs = rules(res)
    assert {"MON.ERRORS", "MON.REPETITION", "MON.LATENCY", "MON.DRIFT_REPETITION"} <= rs
    assert [t["period"] for t in res["metrics"]["timeline"]] == ["2026-W41", "2026-W42", "2026-W43", "2026-W44"]


def test_monitor_negative_and_single_period(synth):
    files = sorted((synth / "synthetic_production").glob("*.jsonl"))[:3]
    assert rules(monitor.analyze_paths(files, "week")) == {"MON.OK"}
    assert "MON.NO_BASELINE" in rules(monitor.analyze_paths(files[:1], "week"))
    assert rules(monitor.analyze_records({})) == {"MON.NO_DATA"}


def test_cli_monitor_fail_on(synth, capsys):
    d = str(synth / "synthetic_production")
    assert main(["monitor", "-i", d, "--period", "week", "--fail-on", "HIGH"]) == 4
    capsys.readouterr()
    assert main(["monitor", "-i", d, "--period", "week"]) == 0
