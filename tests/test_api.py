"""Testes da API local (FastAPI): status, projetos, importação, auditoria, investigação,
relatórios, cancelamento, segurança de caminhos e restrições de rede."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from backend.api.main import create_app  # noqa: E402
from backend.services.store import Store  # noqa: E402


@pytest.fixture()
def client(tmp_path: Path, synth: Path) -> TestClient:
    store = Store(tmp_path / "ws")
    store.save_settings({"allowed_roots": [str(synth), str(tmp_path)], "reports_dir": str(tmp_path / "ws" / "reports")})
    return TestClient(create_app(store))


def wait(c: TestClient, jid: str, timeout: float = 60) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.1)
    raise AssertionError("job timeout")


def project(c: TestClient, root: Path, items: list[str]) -> tuple[str, str]:
    p = c.post("/api/projects", json={"name": "synthetic", "root": str(root)}).json()
    c.post(f"/api/projects/{p['id']}/scan")
    e = c.post(f"/api/projects/{p['id']}/experiments", json={"name": "exp", "items": items}).json()
    return p["id"], e["id"]


def test_status_and_capabilities(client):
    s = client.get("/api/status").json()
    assert s["engine_version"] == "1.0.0"
    assert {c["kind"] for c in s["capabilities"]} >= {
        "audit",
        "investigate",
        "train",
        "dataset",
        "leakage",
        "tokenizer",
        "generation",
        "compare",
        "checkpoint",
    }


def test_project_import_and_inventory(client, synth):
    pid, _ = project(client, synth, ["demo_experiment"])
    inv = client.get(f"/api/projects/{pid}").json()["inventory"]
    kinds = {i["kind"] for i in inv}
    assert {"dataset", "training_log", "generations", "tokenized", "run"} <= kinds
    assert all(not Path(i["path"]).is_absolute() for i in inv)


def test_audit_investigate_and_exports(client, synth):
    pid, eid = project(client, synth, ["demo_experiment"])
    j = wait(
        client, client.post("/api/jobs", json={"project_id": pid, "experiment_id": eid, "kind": "audit"}).json()["id"]
    )
    assert j["status"] == "done" and j["progress_done"] == j["progress_total"] and j["progress_total"] >= 5
    rep = client.get(f"/api/reports/{j['report_id']}").json()
    assert rep["report"]["findings"] and "raw" not in rep
    j2 = wait(
        client,
        client.post(
            "/api/jobs",
            json={
                "project_id": pid,
                "experiment_id": eid,
                "kind": "investigate",
                "question": "Why is my model repeating?",
            },
        ).json()["id"],
    )
    assert j2["status"] == "done"
    ans = client.get(f"/api/reports/{j2['report_id']}").json()["report"]["answer"]
    assert ans["status"] == "CONFIRMED" and ans["intents"] == ["repetition"]
    for fmt, needle in (
        ("json", '"findings"'),
        ("markdown", "## 8. Root Cause Investigation"),
        ("html", "<!doctype html>"),
    ):
        r = client.get(f"/api/reports/{j2['report_id']}/export", params={"format": fmt})
        assert r.status_code == 200 and needle in r.text
        assert "attachment" in r.headers["content-disposition"]
    metas = client.get("/api/reports", params={"experiment_id": eid}).json()
    assert [m["kind"] for m in metas][:2] == ["investigate", "audit"]


def test_single_analyses(client, synth):
    pid, eid = project(client, synth, ["synthetic_runs"])
    cases = [
        ("train", {"path": "synthetic_training/overfitting.csv"}, "TRN.OVERFIT"),
        ("dataset", {"path": "synthetic_datasets/dirty_train.jsonl"}, "DAT.EXACT_DUP"),
        (
            "leakage",
            {
                "train": "synthetic_datasets/contaminated/train.jsonl",
                "tests": ["synthetic_datasets/contaminated/test.jsonl"],
            },
            "LEK.EXACT",
        ),
        ("tokenizer", {"path": "synthetic_tokenization/inefficient_tokens.jsonl", "max_length": 64}, "TOK.TRUNCATION"),
        ("generation", {"path": "synthetic_generations/repetitive_outputs.jsonl"}, "GEN.REPETITION"),
        (
            "compare",
            {"before": "synthetic_runs/run_v1", "after": "synthetic_runs/run_v3_other_tokenizer"},
            "CMP.INCOMPATIBLE",
        ),
    ]
    for kind, params, rule in cases:
        j = wait(
            client,
            client.post(
                "/api/jobs", json={"project_id": pid, "experiment_id": eid, "kind": kind, "params": params}
            ).json()["id"],
        )
        assert j["status"] == "done", (kind, j)
        rules = {f["rule"] for f in client.get(f"/api/reports/{j['report_id']}").json()["report"]["findings"]}
        assert rule in rules, (kind, rules)
        assert "CMP.REGRESSION" not in rules


def test_chart_and_record_endpoints(client, synth):
    pid, _ = project(client, synth, ["demo_experiment"])
    s = client.get("/api/data/series", params={"project_id": pid, "path": "synthetic_training/divergent.csv"}).json()
    assert {"train_loss", "val_loss", "lr", "grad_norm", "val_ppl"} <= set(s["series"])
    assert s["perplexity_source"].startswith("derived")
    h = client.get(
        "/api/data/lengths", params={"project_id": pid, "path": "synthetic_datasets/dirty_train.jsonl"}
    ).json()
    assert sum(b["count"] for b in h["bins"]) == h["records"]
    r = client.get(
        "/api/data/records",
        params={
            "project_id": pid,
            "path": "synthetic_generations/repetitive_outputs.jsonl",
            "indices": "0,1",
            "limit": 2,
        },
    ).json()
    assert [x["index"] for x in r["rows"]] == [0, 1] and r["rows"][0]["repetition_rate"] > 0.5


def test_invalid_and_failed_inputs(client, synth, tmp_path):
    pid, eid = project(client, synth, ["demo_experiment"])
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    j = wait(
        client,
        client.post(
            "/api/jobs", json={"project_id": pid, "experiment_id": eid, "kind": "train", "params": {"path": str(bad)}}
        ).json()["id"],
    )
    assert j["status"] == "failed" and "invalid JSON" in j["error"]
    j = wait(
        client,
        client.post("/api/jobs", json={"project_id": pid, "kind": "train", "params": {"path": "missing.csv"}}).json()[
            "id"
        ],
    )
    assert j["status"] == "failed"
    assert client.post("/api/jobs", json={"project_id": pid, "kind": "audit"}).status_code == 422
    assert client.post("/api/jobs", json={"project_id": pid, "kind": "rm -rf"}).status_code == 422
    assert client.get("/api/reports/rep-doesnotexist").status_code == 404
    assert client.post(f"/api/projects/{pid}/experiments", json={"name": "x", "items": ["nope/"]}).status_code == 404


def test_cancel(client, synth):
    pid, eid = project(client, synth, ["."])
    jid = client.post("/api/jobs", json={"project_id": pid, "experiment_id": eid, "kind": "audit"}).json()["id"]
    client.post(f"/api/jobs/{jid}/cancel")
    j = wait(client, jid)
    assert j["status"] in ("cancelled", "done")  # pode concluir antes do pedido; nunca falha


def test_security_paths_hosts_and_cors(client, synth, tmp_path):
    pid, _ = project(client, synth, ["demo_experiment"])
    assert client.post("/api/projects", json={"name": "x", "root": "/etc"}).status_code == 403
    assert (
        client.get("/api/data/records", params={"project_id": pid, "path": "../../../../etc/passwd"}).status_code == 403
    )
    (synth / ".env").write_text("TOKEN=1")
    assert client.get("/api/data/records", params={"project_id": pid, "path": ".env"}).status_code == 403
    assert client.get("/api/fs/list", params={"path": "/"}).status_code == 403
    assert client.get("/api/status", headers={"host": "evil.example"}).status_code == 400
    r = client.options("/api/status", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") is None
    r = client.options(
        "/api/status", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert client.put("/api/settings", json={"allowed_roots": ["/"], "reports_dir": str(tmp_path)}).status_code == 403


def test_demo_mode(client, synth, monkeypatch):
    import backend.api.main as m

    monkeypatch.setattr(m, "EXAMPLES", synth)
    c = TestClient(m.create_app(client.app.state.store))
    p = c.post("/api/demo").json()
    assert p["demo"] is True and len(p["experiments"]) == len(m.DEMO_EXPERIMENTS)
    j = wait(
        c,
        c.post(
            "/api/jobs", json={"project_id": p["id"], "experiment_id": p["experiments"][0]["id"], "kind": "audit"}
        ).json()["id"],
    )
    meta = c.get("/api/reports", params={"project_id": p["id"]}).json()[0]
    assert j["status"] == "done" and meta["demo"] is True


def test_live_probe_flow(client, synth, monkeypatch):
    import backend.api.main as m

    monkeypatch.setattr(m, "EXAMPLES", m.REPO_ROOT / "examples")
    c = TestClient(m.create_app(client.app.state.store))
    ts = c.post("/api/targets/simulated").json()
    assert len(ts) == 2 and all(t["simulated"] and t["local"] for t in ts)
    flawed = next(t for t in ts if t["model"] == "demo-flawed")
    t = c.post(f"/api/targets/{flawed['id']}/test").json()
    assert t["ok"] and t["model_listed"] is True
    j = wait(
        c,
        c.post("/api/jobs", json={"kind": "probe", "params": {"target_id": flawed["id"], "suite": "quick"}}).json()[
            "id"
        ],
    )
    assert j["status"] == "done" and j["progress_done"] == j["progress_total"] and any("FAIL" in ln for ln in j["log"])
    full = c.get(f"/api/reports/{j['report_id']}").json()
    assert full["meta"]["simulated"] is True and "PRB.INJECTION" in {f["rule"] for f in full["report"]["findings"]}
    hist = c.get(f"/api/targets/{flawed['id']}/history").json()
    assert hist and hist[-1]["pass_rates"]["injection"] < 1
    a = c.post(
        f"/api/reports/{j['report_id']}/ask", json={"question": "Is my model vulnerable to prompt injection?"}
    ).json()
    assert a["answer_status"] == "CONFIRMED" and a["kind"] == "investigate"
    # o modelo conectado vira experimento do projeto "Live models" com a transcrição gravada
    assert j["project_id"] == "prj-live" and j["experiment_id"] == flawed["experiment_id"]
    proj = c.get("/api/projects/prj-live").json()
    exp = next(e for e in proj["experiments"] if e["id"] == flawed["experiment_id"])
    tr = list((Path(proj["root"]) / exp["items"][0]).glob("generations_probe_*.jsonl"))
    assert len(tr) == 1 and tr[0].read_text(encoding="utf-8").count("\n") == len(
        c.get(f"/api/reports/{j['report_id']}/probe-records").json()
    )
    au = wait(
        c,
        c.post("/api/jobs", json={"kind": "audit", "project_id": "prj-live", "experiment_id": exp["id"]}).json()["id"],
    )
    assert au["status"] == "done", au
    rep = c.get(f"/api/reports/{au['report_id']}").json()
    assert any(f["category"] == "generation" for f in rep["report"]["findings"]), rep["report"]["findings"][:3]


def test_target_security(client, tmp_path):
    r = client.post("/api/targets", json={"name": "x", "base_url": "https://api.example.com/v1", "model": "m"})
    assert r.status_code == 403
    r = client.post(
        "/api/targets",
        json={
            "name": "x",
            "base_url": "https://api.example.com/v1",
            "model": "m",
            "allow_remote": True,
            "api_key": "sk-TESTSECRET123456789",
        },
    )
    assert r.status_code == 201 and r.json()["has_session_key"] and not r.json()["local"]
    ws = client.app.state.store.home
    assert all("TESTSECRET" not in p.read_text(encoding="utf-8") for p in ws.glob("*.json"))
    assert (
        client.post("/api/targets", json={"name": "x", "base_url": "file:///etc/passwd", "model": "m"}).status_code
        == 422
    )
    assert client.post("/api/jobs", json={"kind": "probe", "params": {"target_id": "nope"}}).status_code == 404


def test_monitor_job(client, synth):
    pid, _ = project(client, synth, ["demo_experiment"])
    j = wait(
        client,
        client.post(
            "/api/jobs",
            json={"project_id": pid, "kind": "monitor", "params": {"path": "synthetic_production", "period": "week"}},
        ).json()["id"],
    )
    assert j["status"] == "done"
    rep = client.get(f"/api/reports/{j['report_id']}").json()["report"]
    assert "MON.REPETITION" in {f["rule"] for f in rep["findings"]}
    assert len(rep["sections"]["monitor"][0]["metrics"]["timeline"]) == 4


def test_connect_wizard_endpoints(client):
    import importlib.util as iu

    spec = iu.spec_from_file_location("fls", Path(__file__).resolve().parents[1] / "examples" / "fake_llm_server.py")
    mod = iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    srv, port = mod.start(0)
    client.app.state.local_servers = [
        {"id": "sim", "label": "Simulated", "port": port, "base_url": f"http://127.0.0.1:{port}/v1", "help": "-"},
        {"id": "dead", "label": "Nothing", "port": 9, "base_url": "http://127.0.0.1:9/v1", "help": "start it"},
    ]
    found = {s["id"]: s for s in client.get("/api/connect/discover").json()}
    assert found["sim"]["running"] and "demo-good" in found["sim"]["models"] and not found["dead"]["running"]
    cat = client.get("/api/connect/catalog").json()
    assert {p["id"] for p in cat["online"]} >= {"openai", "anthropic", "gemini", "custom"}
    r = client.post("/api/connect/models", json={"base_url": f"http://127.0.0.1:{port}/v1"}).json()
    assert r["ok"] and len(r["models"]) == 2
    r = client.post("/api/connect/models", json={"base_url": "http://127.0.0.1:9/v1"}).json()
    assert not r["ok"] and "running" in r["error"]
    assert client.post("/api/connect/models", json={"base_url": "https://api.example.com/v1"}).status_code == 403
    srv.shutdown()
