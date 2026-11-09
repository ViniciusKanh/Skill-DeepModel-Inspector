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
