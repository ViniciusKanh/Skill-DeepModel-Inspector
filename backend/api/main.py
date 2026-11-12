"""API FastAPI local do DeepModel Inspector (somente localhost).

Executar: ``python -m backend.api.main`` (porta padrão 8765). Serve também o frontend
compilado em ``frontend/dist`` quando disponível.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.schemas.models import (
    AskIn,
    Capability,
    Experiment,
    ExperimentIn,
    FileInspectIn,
    HubTokenIn,
    InventoryItem,
    JobIn,
    JobOut,
    ModelsIn,
    Project,
    ProjectIn,
    ReportMeta,
    SettingsModel,
    StatusOut,
    TargetIn,
    TargetOut,
)
from backend.services import analysis
from backend.services.jobs import JobManager
from backend.services.store import REPO_ROOT, Store, new_id, now
from deepmodel_inspector.core.common import VERSION
from deepmodel_inspector.diagnostics import inventory as inv_mod
from deepmodel_inspector.diagnostics.live import consolidate
from deepmodel_inspector.probe import providers
from deepmodel_inspector.probe.client import Target, chat, list_models
from deepmodel_inspector.reporting.render import to_html, to_markdown
from deepmodel_inspector.security.guard import SecurityError, safe_input_path

APP_VERSION = "1.0.0"
DIST = REPO_ROOT / "frontend" / "dist"
EXAMPLES = REPO_ROOT / "examples"
LIMITATIONS = [
    "Duplicate, leakage and grounding checks are lexical, not semantic.",
    "Hallucination checks only compare against references supplied with each output.",
    "Thresholds are documented heuristics validated on synthetic scenarios.",
    "Single-run comparisons do not establish statistical significance.",
    "Tokenizer metrics require tokenizations you provide; no tokenizer is simulated.",
    "Overfitting needs validation loss; gradient rules need logged grad_norm.",
    "Near-duplicate search is capped at 20,000 records per file (pure Python, CPU).",
    "Checkpoint weights are never loaded; only safetensors headers and JSON configs.",
    "Investigation is rule-based over computed evidence; it is not a generative chatbot.",
]
DEMO_EXPERIMENTS = [
    ("Demo experiment (full audit)", ["demo_experiment"]),
    ("Overfitting run", ["synthetic_training/overfitting.csv"]),
    ("Divergent run", ["synthetic_training/divergent.csv"]),
    ("Contaminated dataset", ["synthetic_datasets/contaminated"]),
    ("Clean dataset (negative control)", ["synthetic_datasets/clean_split"]),
    ("Runs v1 vs v2", ["synthetic_runs/run_v1", "synthetic_runs/run_v2"]),
    ("Tokenizer comparison (PT)", ["synthetic_tokenization/tokenizer_comparison.jsonl"]),
    ("Decoding configs", ["synthetic_generations/configs_comparison.jsonl"]),
]


def _friendly(exc: Exception) -> str:
    """Mensagem de erro de conexão em linguagem simples."""
    msg = str(exc)
    if "401" in msg or "403" in msg:
        return "The server rejected the API key (401/403). Check that the key is correct and active."
    if "404" in msg:
        return "The address answered, but /models was not found. Check the base URL (it usually ends with /v1)."
    if "refused" in msg.lower() or "10061" in msg or "Connection refused" in msg:
        return "Nothing is listening at this address. Is the model server running?"
    if "timed out" in msg.lower():
        return "The server did not answer in time. Check the address or your network."
    return f"Could not reach the server: {msg[:160]}"


def create_app(store: Store | None = None) -> FastAPI:
    """Fábrica da aplicação (injeção do armazenamento facilita testes)."""
    st = store or Store()
    secrets: dict[str, str] = {}  # chaves de API em memória (nunca persistidas)
    jobs = JobManager(st, secrets)
    sim: dict[str, Any] = {}
    app = FastAPI(
        title="DeepModel Inspector API",
        version=APP_VERSION,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.jobs = jobs
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.state.store, app.state.jobs = st, jobs
    app.state.local_servers = providers.LOCAL_SERVERS

    @app.exception_handler(SecurityError)
    async def _sec(_: Request, exc: SecurityError) -> JSONResponse:
        return JSONResponse({"detail": f"security: {exc}"}, status_code=403)

    @app.exception_handler(KeyError)
    async def _nf(_: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse({"detail": str(exc).strip("'\"")}, status_code=404)

    @app.exception_handler(FileNotFoundError)
    async def _fnf(_: Request, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(ValueError)
    async def _bad(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    def settings() -> dict[str, Any]:
        return st.settings()

    # ------------------------------------------------------------------ status/settings
    @app.get("/api/status", response_model=StatusOut)
    def status() -> StatusOut:
        return StatusOut(
            app_version=APP_VERSION,
            engine_version=VERSION,
            python=sys.version.split()[0],
            platform=f"{platform.system()} {platform.release()}",
            workspace=str(st.home),
            allowed_roots=settings()["allowed_roots"],
            capabilities=[
                Capability(kind=k, command=c, description=d, inputs=i) for k, c, d, i in analysis.CAPABILITIES
            ],
            limitations=LIMITATIONS,
            demo_available=(EXAMPLES / "generate_synthetic.py").exists(),
        )

    @app.get("/api/settings", response_model=SettingsModel)
    def get_settings() -> dict[str, Any]:
        return settings()

    @app.put("/api/settings", response_model=SettingsModel)
    def put_settings(body: SettingsModel) -> dict[str, Any]:
        return st.save_settings(body.model_dump())

    # ------------------------------------------------------------------ filesystem (restrito)
    @app.get("/api/fs/list")
    def fs_list(path: str = Query(..., max_length=1024)) -> dict[str, Any]:
        p = safe_input_path(path, settings()["allowed_roots"], settings()["max_mb"], allow_dir=True)
        if not p.is_dir():
            raise ValueError("not a directory")
        entries = []
        for c in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:500]:
            if c.name.startswith(".") or c.name in ("node_modules", "__pycache__"):
                continue
            entries.append(
                {
                    "name": c.name,
                    "path": str(c),
                    "dir": c.is_dir(),
                    "size": c.stat().st_size if c.is_file() else None,
                    "supported": c.is_dir() or c.suffix.lower() in inv_mod.DATA_SUFFIXES | {".safetensors"},
                }
            )
        parent = str(p.parent) if any(str(p.parent).startswith(r) for r in settings()["allowed_roots"]) else None
        return {"path": str(p), "parent": parent, "entries": entries}

    # ------------------------------------------------------------------ projetos
    @app.get("/api/projects", response_model=list[Project])
    def projects() -> list[dict[str, Any]]:
        return st.projects()

    @app.post("/api/projects", response_model=Project, status_code=201)
    def create_project(body: ProjectIn) -> dict[str, Any]:
        root = safe_input_path(body.root, settings()["allowed_roots"], settings()["max_mb"], allow_dir=True)
        if not root.is_dir():
            raise ValueError("project root must be a directory")
        proj = {
            "id": new_id("prj"),
            "name": body.name.strip(),
            "root": str(root),
            "demo": False,
            "created": now(),
            "experiments": [],
            "inventory": [],
        }
        return st.save_project(proj)

    @app.get("/api/projects/{pid}", response_model=Project)
    def get_project(pid: str) -> dict[str, Any]:
        return st.project(pid)

    @app.delete("/api/projects/{pid}", status_code=204)
    def delete_project(pid: str) -> Response:
        st.project(pid)
        st.delete_project(pid)
        return Response(status_code=204)

    @app.post("/api/projects/{pid}/scan", response_model=Project)
    def scan_project(pid: str) -> dict[str, Any]:
        proj = st.project(pid)
        root = safe_input_path(proj["root"], settings()["allowed_roots"], settings()["max_mb"], allow_dir=True)
        items = inv_mod.scan(root)
        proj["inventory"] = [
            InventoryItem(**{**i, "path": analysis.relpath(i["path"], proj["root"])}).model_dump() for i in items
        ]
        return st.save_project(proj)

    @app.post("/api/projects/{pid}/experiments", response_model=Experiment, status_code=201)
    def create_experiment(pid: str, body: ExperimentIn) -> dict[str, Any]:
        proj = st.project(pid)
        for it in body.items:  # valida cada item antes de registrar
            analysis.resolve(proj["root"], it, settings(), allow_dir=True)
        exp = {"id": new_id("exp"), "name": body.name.strip(), "items": body.items, "created": now()}
        proj["experiments"].append(exp)
        st.save_project(proj)
        return exp

    @app.delete("/api/projects/{pid}/experiments/{eid}", status_code=204)
    def delete_experiment(pid: str, eid: str) -> Response:
        proj = st.project(pid)
        proj["experiments"] = [e for e in proj["experiments"] if e["id"] != eid]
        st.save_project(proj)
        return Response(status_code=204)

    @app.post("/api/files/inspect")
    def inspect_file(body: FileInspectIn) -> dict[str, Any]:
        proj = st.project(body.project_id)
        p = analysis.resolve(proj["root"], body.path, settings(), allow_dir=True)
        if p.is_dir():
            return {"path": body.path, "kind": "directory", "items": len(inv_mod.scan(p))}
        item = inv_mod.classify(p)
        info: dict[str, Any] = {}
        try:
            _, info = inv_mod.load_table(p, 1000)
        except (ValueError, OSError, UnicodeError) as exc:
            info = {"error": str(exc)[:200]}
        return {"path": body.path, "kind": item["kind"], "split": item.get("split"), "parse": info}

    # ------------------------------------------------------------------ demo
    @app.post("/api/demo", response_model=Project)
    def demo() -> dict[str, Any]:
        if not (EXAMPLES / "demo_experiment").exists():
            spec = importlib.util.spec_from_file_location("gen_synth", EXAMPLES / "generate_synthetic.py")
            if spec is None or spec.loader is None:
                raise ValueError("synthetic generator not found")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.generate(EXAMPLES)
        root = safe_input_path(EXAMPLES, settings()["allowed_roots"], settings()["max_mb"], allow_dir=True)
        existing = next((p for p in st.projects() if p.get("demo")), None)
        proj = existing or {
            "id": new_id("prj"),
            "name": "DEMO — Synthetic LLM Lab",
            "root": str(root),
            "demo": True,
            "created": now(),
            "experiments": [],
            "inventory": [],
        }
        if not proj["experiments"]:
            proj["experiments"] = [
                {"id": new_id("exp"), "name": n, "items": items, "created": now()} for n, items in DEMO_EXPERIMENTS
            ]
        st.save_project(proj)
        return scan_project(proj["id"])

    # ------------------------------------------------------------------ jobs
    @app.post("/api/jobs", response_model=JobOut, status_code=202)
    def submit(body: JobIn) -> dict[str, Any]:
        return jobs.public(jobs.submit(body.model_dump()))

    @app.get("/api/jobs", response_model=list[JobOut])
    def list_jobs() -> list[dict[str, Any]]:
        return [jobs.public(j) for j in sorted(jobs.jobs.values(), key=lambda j: j["created"], reverse=True)][:50]

    @app.get("/api/jobs/{jid}", response_model=JobOut)
    def get_job(jid: str) -> dict[str, Any]:
        return jobs.public(jobs.jobs[jid])

    @app.post("/api/jobs/{jid}/cancel", response_model=JobOut)
    def cancel_job(jid: str) -> dict[str, Any]:
        return jobs.public(jobs.cancel(jid))

    # ------------------------------------------------------------------ Hugging Face Hub (sem download)
    @app.get("/api/hub/token")
    def hub_token_status() -> dict[str, Any]:
        return {"session_token": "hf:token" in secrets, "env_token": bool(os.environ.get("HF_TOKEN"))}

    @app.post("/api/hub/token", status_code=204)
    def hub_token_set(body: HubTokenIn) -> Response:
        secrets["hf:token"] = body.token.strip()  # apenas em memória
        return Response(status_code=204)

    @app.delete("/api/hub/token", status_code=204)
    def hub_token_clear() -> Response:
        secrets.pop("hf:token", None)
        return Response(status_code=204)

    # ------------------------------------------------------------------ modelos ao vivo (alvos)
    def _target_out(t: dict[str, Any]) -> dict[str, Any]:
        return {**t, "has_session_key": t["id"] in secrets}

    @app.get("/api/targets", response_model=list[TargetOut])
    def targets() -> list[dict[str, Any]]:
        return [_target_out(t) for t in st.targets()]

    @app.post("/api/targets", response_model=TargetOut, status_code=201)
    def create_target(body: TargetIn) -> dict[str, Any]:
        tgt = Target(body.base_url, body.model, None, body.timeout)  # valida URL
        if not tgt.is_local and not body.allow_remote:
            raise SecurityError(f"remote endpoint {tgt.host}: confirm that probe prompts may be sent to it")
        t = {
            "id": new_id("tgt"),
            "name": body.name.strip(),
            "base_url": tgt.base_url,
            "model": body.model.strip(),
            "local": tgt.is_local,
            "simulated": False,
            "api_key_env": body.api_key_env,
            "timeout": body.timeout,
            "created": now(),
        }
        st.save_target(t)
        if body.api_key:
            secrets[t["id"]] = body.api_key
        return _target_out(t)

    @app.delete("/api/targets/{tid}", status_code=204)
    def delete_target(tid: str) -> Response:
        st.target(tid)
        st.delete_target(tid)
        secrets.pop(tid, None)
        return Response(status_code=204)

    @app.post("/api/targets/{tid}/test")
    def test_target(tid: str) -> dict[str, Any]:
        t = st.target(tid)
        key = secrets.get(tid) or (os.environ.get(t["api_key_env"]) if t.get("api_key_env") else None)
        tgt = Target(t["base_url"], t["model"], key, min(float(t.get("timeout", 60)), 30))
        models: list[str] | None = None
        models_error = None
        try:
            models = list_models(tgt)[:50]
        except Exception as exc:  # noqa: BLE001 - /models é opcional em alguns servidores
            models_error = str(exc)[:160]
        ping = chat(tgt, [{"role": "user", "content": "Reply with the word OK."}], {"temperature": 0, "max_tokens": 8})
        return {
            "ok": ping["error"] is None,
            "latency_ms": ping["latency_ms"],
            "reply": ping["text"][:80],
            "error": _friendly(Exception(ping["error"])) if ping["error"] else None,
            "models": models,
            "models_error": models_error,
            "model_listed": (t["model"] in models) if models else None,
        }

    @app.get("/api/connect/catalog")
    def connect_catalog() -> dict[str, Any]:
        """Provedores online e servidores locais conhecidos (assistente de conexão)."""
        return {"local": providers.LOCAL_SERVERS, "online": providers.ONLINE_PROVIDERS}

    @app.get("/api/connect/discover")
    def connect_discover() -> list[dict[str, Any]]:
        """Detecta servidores LLM locais em execução (somente 127.0.0.1)."""
        return providers.discover(app.state.local_servers)

    @app.post("/api/connect/models")
    def connect_models(body: ModelsIn) -> dict[str, Any]:
        """Lista modelos de um endpoint antes de registrá-lo (valida URL, chave e consentimento)."""
        tgt = Target(
            body.base_url, "probe", body.api_key or (os.environ.get(body.api_key_env) if body.api_key_env else None), 15
        )
        if not tgt.is_local and not body.allow_remote:
            raise SecurityError(f"remote endpoint {tgt.host}: confirm that requests may be sent to it")
        try:
            return {"ok": True, "models": sorted(list_models(tgt))[:500], "error": None}
        except Exception as exc:  # noqa: BLE001 - erro exibido ao usuário em linguagem simples
            return {"ok": False, "models": [], "error": _friendly(exc)}

    @app.post("/api/targets/simulated", response_model=list[TargetOut])
    def simulated_targets() -> list[dict[str, Any]]:
        if "port" not in sim:
            spec = importlib.util.spec_from_file_location(
                "fake_llm_server", REPO_ROOT / "examples" / "fake_llm_server.py"
            )
            if spec is None or spec.loader is None:
                raise ValueError("simulated server not available")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            sim["server"], sim["port"] = mod.start(0, "flawed", 0.02)
        url = f"http://127.0.0.1:{sim['port']}/v1"
        out = []
        for t in [x for x in st.targets() if x.get("simulated")]:
            st.delete_target(t["id"])
        for name, model in (("SIMULATED · flawed model", "demo-flawed"), ("SIMULATED · healthy model", "demo-good")):
            t = {
                "id": new_id("tgt"),
                "key": f"sim:{model}",
                "name": name,
                "base_url": url,
                "model": model,
                "local": True,
                "simulated": True,
                "api_key_env": None,
                "timeout": 30.0,
                "created": now(),
            }
            st.save_target(t)
            out.append(_target_out(t))
        return out

    @app.get("/api/targets/{tid}/history")
    def target_history(tid: str) -> list[dict[str, Any]]:
        st.target(tid)
        out = []
        for m in reversed(st.reports()):
            if m.get("target_id") != tid or m["kind"] != "probe":
                continue
            rep = st.report(m["id"])["report"]
            pm = (rep["sections"].get("probe") or [{}])[0].get("metrics", {})
            out.append(
                {
                    "report_id": m["id"],
                    "created": m["created"],
                    "error_rate": pm.get("error_rate"),
                    "latency_p95_ms": pm.get("latency_p95_ms"),
                    "latency_median_ms": (pm.get("latency_ms") or {}).get("median"),
                    "pass_rates": {k: v.get("pass_rate") for k, v in (pm.get("categories") or {}).items()},
                    "findings_by_severity": m["findings_by_severity"],
                }
            )
        return out

    @app.get("/api/reports/{rid}/probe-records")
    def probe_records(rid: str) -> list[dict[str, Any]]:
        """Registros por chamada de uma sondagem (prompts da suíte e respostas do modelo, truncados)."""
        full = st.report(rid)
        return [r for res in full["raw"] if res.get("analysis") == "probe" for r in res.get("records", [])]

    @app.post("/api/reports/{rid}/ask", response_model=ReportMeta)
    def ask(rid: str, body: AskIn) -> dict[str, Any]:
        full = st.report(rid)
        rep = consolidate(full["raw"], body.question.strip(), full["report"].get("inventory"))
        meta = {
            **full["meta"],
            "id": new_id("rep"),
            "created": now(),
            "kind": "investigate",
            "question": body.question.strip(),
            "answer_status": rep["answer"]["status"],
            "findings_by_severity": rep["summary"]["findings_by_severity"],
            "findings_by_status": rep["summary"]["findings_by_status"],
            "analyses_run": rep["analyses_run"],
            "based_on": rid,
        }
        st.save_report(meta, rep, full["raw"])
        return meta

    # ------------------------------------------------------------------ relatórios
    @app.get("/api/reports", response_model=list[ReportMeta])
    def reports(project_id: str | None = None, experiment_id: str | None = None) -> list[dict[str, Any]]:
        out = st.reports()
        if project_id:
            out = [m for m in out if m["project_id"] == project_id]
        if experiment_id:
            out = [m for m in out if m.get("experiment_id") == experiment_id]
        return out

    @app.get("/api/reports/{rid}")
    def report(rid: str) -> dict[str, Any]:
        full = st.report(rid)
        return {"meta": full["meta"], "report": full["report"]}

    @app.get("/api/reports/{rid}/export")
    def export(rid: str, format: str = Query("json", pattern="^(json|markdown|html)$"), lang: str = "en") -> Response:
        full = st.report(rid)
        rep = full["report"]
        lang = "pt" if lang == "pt" else "en"
        if format == "json":
            import json

            body, media, ext = json.dumps(rep, ensure_ascii=False, indent=2, default=str), "application/json", "json"
        elif format == "markdown":
            body, media, ext = to_markdown(rep, lang), "text/markdown; charset=utf-8", "md"
        else:
            body, media, ext = to_html(rep, lang), "text/html; charset=utf-8", "html"
        return Response(
            body, media_type=media, headers={"Content-Disposition": f'attachment; filename="deepmodel-{rid}.{ext}"'}
        )

    # ------------------------------------------------------------------ dados para gráficos/evidências
    def _project_path(pid: str, path: str, allow_dir: bool = False) -> Path:
        return analysis.resolve(st.project(pid)["root"], path, settings(), allow_dir)

    @app.get("/api/data/series")
    def data_series(project_id: str, path: str) -> dict[str, Any]:
        return analysis.series(_project_path(project_id, path), settings())

    @app.get("/api/data/lengths")
    def data_lengths(project_id: str, path: str, text_field: str | None = None) -> dict[str, Any]:
        return analysis.lengths(_project_path(project_id, path), settings(), text_field)

    @app.get("/api/data/records")
    def data_records(
        project_id: str, path: str, indices: str | None = None, limit: int = Query(25, ge=1, le=200)
    ) -> dict[str, Any]:
        idx = [int(x) for x in indices.split(",") if x.strip().isdigit()] if indices else None
        return analysis.preview(_project_path(project_id, path), settings(), idx, limit)

    # ------------------------------------------------------------------ frontend estático
    if DIST.exists():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(404)
            f = (DIST / full_path).resolve()
            if full_path and f.is_file() and DIST.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(DIST / "index.html")

    return app


def main() -> None:
    """Inicia o servidor somente em loopback."""
    import uvicorn

    ap = argparse.ArgumentParser(description="DeepModel Inspector local API")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost"])
    a = ap.parse_args()
    uvicorn.run(create_app(), host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
