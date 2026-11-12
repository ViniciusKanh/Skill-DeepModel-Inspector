"""Testes da inspeção de repositórios do Hugging Face sem download (servidor Hub simulado local).

O Hub real não é acessado nos testes (execução offline); o servidor imita os endpoints
``/api/models/{repo}`` e ``/{repo}/resolve/{rev}/{arquivo}`` (incluindo Range e redirecionamento).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from deepmodel_inspector.cli import main
from deepmodel_inspector.probe import hub

_spec = importlib.util.spec_from_file_location(
    "fake_hf_hub", Path(__file__).resolve().parents[1] / "examples" / "fake_hf_hub.py"
)
fake_hub = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fake_hub)
SEEN, Handler = fake_hub.SEEN, fake_hub.Handler


@pytest.fixture(scope="module")
def hub_url():
    srv, url = fake_hub.start()
    yield url
    srv.shutdown()


def rules(res: dict[str, Any]) -> set[str]:
    return {f["rule"] for f in res["findings"]}


def test_good_repo_metadata_and_footprint(hub_url):
    res = hub.inspect("good/chat-model", None, hub=hub_url)
    m = res["metrics"]
    assert m["parameters_total"] == 1000 * 64 + 64 * 64  # via cabeçalho safetensors (Range)
    assert m["parameters_by_dtype"] == {"BF16": 68096}
    assert m["layers"] == 2 and m["kv_heads"] == 2 and m["head_dim"] == 16 and m["context_length"] == 4096
    assert m["kv_cache_mb_per_1k_tokens"] == round(2 * 2 * 2 * 16 * 2 * 1000 / 2**20, 1)
    assert m["chat_template"] is True and m["license"] == "apache-2.0"
    assert rules(res) == {"HUB.FOOTPRINT"}


def test_risky_repo_findings(hub_url):
    res = hub.inspect("bad/pickle-model", None, hub=hub_url)
    r = rules(res)
    assert {"HUB.PICKLE_ONLY", "HUB.REMOTE_CODE", "HUB.VOCAB_MISMATCH", "HUB.NO_CHAT_TEMPLATE", "HUB.NO_LICENSE"} <= r
    assert next(f for f in res["findings"] if f["rule"] == "HUB.PICKLE_ONLY")["severity"] == "HIGH"


def test_gated_missing_and_invalid(hub_url):
    with pytest.raises(hub.HubError, match="gated"):
        hub.inspect("gated/model", None, hub=hub_url)
    with pytest.raises(hub.HubError, match="not found"):
        hub.inspect("nobody/nothing", None, hub=hub_url)
    for bad in ("../etc", "a/b/c", "", "x y/z"):
        with pytest.raises(ValueError):
            hub.fetch(bad, hub=hub_url)


def test_token_only_to_hub_and_redirects_restricted(hub_url):
    SEEN["auth"].clear()
    hub.inspect("good/chat-model", "hf_testtoken123", hub=hub_url)
    assert all(a == "Bearer hf_testtoken123" for _, a in SEEN["auth"])  # mesmo host do hub
    with pytest.raises(hub.HubError, match="non-Hub host"):
        hub._get(f"{hub_url}/evil/x", hub_url, "hf_testtoken123")


def test_cli_hub(hub_url, capsys):
    code = main(["hub", "--repo", "bad/pickle-model", "--hub-url", hub_url, "--format", "json"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert any(f["rule"] == "HUB.PICKLE_ONLY" for f in out["findings"])
    assert main(["hub", "--repo", "gated/model", "--hub-url", hub_url]) == 2


def test_api_hub_job_goes_to_live_project(hub_url, tmp_path):
    import time

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.api.main import create_app
    from backend.services.store import Store

    app = create_app(Store(tmp_path / "ws"))
    c = TestClient(app)
    app.state.jobs.hub_url = hub_url  # aponta o JobManager para o hub simulado
    assert c.post("/api/hub/token", json={"token": "bad token!"}).status_code == 422
    assert c.post("/api/hub/token", json={"token": "hf_abcdefgh123"}).status_code == 204
    assert c.get("/api/hub/token").json()["session_token"] is True
    assert c.post("/api/jobs", json={"kind": "hub", "params": {"repo_id": "../x"}}).status_code == 422
    j = c.post("/api/jobs", json={"kind": "hub", "params": {"repo_id": "good/chat-model"}}).json()
    for _ in range(100):
        j = c.get(f"/api/jobs/{j['id']}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert j["status"] == "done", j
    proj = c.get("/api/projects/prj-live").json()
    exp = next(e for e in proj["experiments"] if e["name"] == "HF · good/chat-model")
    assert j["experiment_id"] == exp["id"]
    assert (tmp_path / "ws" / "live_models" / exp["items"][0] / "hub_metadata.json").exists()
    rep = c.get(f"/api/reports/{j['report_id']}").json()
    assert any(f["rule"] == "HUB.FOOTPRINT" for f in rep["report"]["findings"])
    assert "hf_abcdefgh123" not in json.dumps(rep) and not list((tmp_path / "ws").rglob("*token*"))
