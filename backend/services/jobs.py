"""Execução assíncrona de análises em threads locais, com progresso real e cancelamento cooperativo."""

from __future__ import annotations

import datetime as dt
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend.services import analysis
from backend.services.store import Store, new_id, now
from deepmodel_inspector.analyzers import monitor
from deepmodel_inspector.core.common import load_table
from deepmodel_inspector.diagnostics.live import consolidate
from deepmodel_inspector.probe import hub
from deepmodel_inspector.probe.client import Target
from deepmodel_inspector.probe.runner import ProbeCancelled, run_probe
from deepmodel_inspector.probe.runner import analyze_records as analyze_probe
from deepmodel_inspector.security.guard import SecurityError


class JobManager:
    """Fila de tarefas (máx. 2 simultâneas) com estado consultável."""

    def __init__(self, store: Store, secrets: dict[str, str] | None = None) -> None:
        self.store = store
        self.secrets = secrets if secrets is not None else {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self.hub_url = hub.HUB
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dmi-job")

    def public(self, job: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in job.items() if not k.startswith("_")}

    def submit(self, req: dict[str, Any]) -> dict[str, Any]:
        kind = req["kind"]
        if kind == "probe":
            t = self.store.target(str(req.get("params", {}).get("target_id", "")))
            proj = self.store.live_project()
            exp = next((e for e in proj["experiments"] if e["id"] == t.get("experiment_id")), None)
        elif kind == "hub":
            if not hub.REPO_RX.match(str(req.get("params", {}).get("repo_id", ""))):
                raise ValueError("invalid Hugging Face repository id (expected owner/name)")
            proj, exp = self.store.attach_experiment(
                f"HF · {req.get('params', {}).get('repo_id', '')}", f"hf:{req.get('params', {}).get('repo_id', '')}"
            )
        else:
            if not req.get("project_id"):
                raise ValueError("project_id is required for this analysis")
            proj = self.store.project(req["project_id"])
            exp = None
            if req.get("experiment_id"):
                exp = next((e for e in proj["experiments"] if e["id"] == req["experiment_id"]), None)
                if exp is None:
                    raise KeyError("experiment not found")
        if kind in ("audit", "investigate") and exp is None:
            raise ValueError("audit/investigate require an experiment")
        job = {
            "id": new_id("job"),
            "kind": kind,
            "status": "queued",
            "created": now(),
            "project_id": proj["id"],
            "experiment_id": exp["id"] if exp else None,
            "progress_done": None,
            "progress_total": None,
            "message": "queued",
            "report_id": None,
            "error": None,
            "log": [],
        }
        ev = threading.Event()
        with self._lock:
            self.jobs[job["id"]] = job
            self._cancel[job["id"]] = ev
        self.pool.submit(self._run, job, req, proj, exp, ev)
        return job

    def cancel(self, jid: str) -> dict[str, Any]:
        job = self.jobs[jid]
        if job["status"] in ("queued", "running"):
            self._cancel[jid].set()
            job["message"] = "cancellation requested"
        return job

    # ------------------------------------------------------------------ execução
    def _run(
        self,
        job: dict[str, Any],
        req: dict[str, Any],
        proj: dict[str, Any],
        exp: dict[str, Any] | None,
        cancel: threading.Event,
    ) -> None:
        if cancel.is_set():
            job.update(status="cancelled", message="cancelled before start")
            return
        job.update(status="running", message="starting")
        settings = self.store.settings()

        def progress(done: int, total: int, label: str) -> None:
            job.update(progress_done=done, progress_total=total, message=label)

        try:
            question = (req.get("question") or "").strip() or None
            target = None
            if req["kind"] == "probe":
                target, raw, inv = self._probe(job, req, proj, settings, cancel, progress)
            elif req["kind"] == "hub":
                raw, inv = self._hub(job, req, proj, exp)
            elif req["kind"] == "monitor":
                p = analysis.resolve(
                    proj["root"], str(req.get("params", {}).get("path") or ""), settings, allow_dir=True
                )
                files = (
                    [p]
                    if p.is_file()
                    else sorted(x for x in p.rglob("*") if x.suffix.lower() in (".jsonl", ".csv", ".json"))
                )
                files = [analysis.resolve(proj["root"], str(f), settings) for f in files]
                job.update(progress_done=0, progress_total=1, message=f"{len(files)} log files")
                th = {k: float(v) for k, v in (req.get("params", {}).get("thresholds") or {}).items()}
                raw = [
                    monitor.analyze_paths(
                        files, req.get("params", {}).get("period") or "day", th, settings["max_records"]
                    )
                ]
                inv = [
                    {"path": analysis.relpath(str(f), proj["root"]), "name": f.name, "kind": "production_log"}
                    for f in files
                ]
                job.update(progress_done=1)
            elif req["kind"] in ("audit", "investigate"):
                raw, inv = None, None
                if req["kind"] == "investigate" and not req.get("params", {}).get("fresh"):
                    raw, inv = self._latest_raw(proj["id"], exp["id"])
                if raw is None:
                    inv = analysis.expand(proj["root"], exp["items"], settings)
                    raw = analysis.run_audit(inv, settings, cancel, progress)
                    inv = [{**i, "path": analysis.relpath(i["path"], proj["root"])} for i in inv]
                else:
                    job["message"] = "re-using latest audit results"
            else:
                job.update(progress_done=0, progress_total=1, message=req["kind"])
                raw = [analysis.run_single(req["kind"], proj["root"], req.get("params", {}), settings)]
                inv = [
                    {"path": str(v), "name": Path(str(v)).name, "kind": req["kind"]}
                    for k, v in req.get("params", {}).items()
                    if k in ("path", "train", "before", "after")
                ]
                job.update(progress_done=1)
            if cancel.is_set():
                raise analysis.Cancelled()
            report = consolidate(raw, question, inv)
            meta = self._meta(job, proj, exp, req, report, question)
            if target:
                meta.update(
                    target_id=target["id"], target_name=target["name"], simulated=target.get("simulated", False)
                )
            meta["params"] = req.get("params", {})
            self.store.save_report(meta, report, raw)
            job.update(status="done", report_id=meta["id"], message="completed")
        except (analysis.Cancelled, ProbeCancelled):
            job.update(status="cancelled", message="cancelled by user")
        except hub.HubError as exc:
            job.update(status="failed", error=f"Hugging Face: {exc}"[:400], message="failed")
        except (SecurityError, ValueError, OSError, KeyError, UnicodeError) as exc:
            job.update(status="failed", error=f"{type(exc).__name__}: {exc}"[:400], message="failed")
        except Exception as exc:  # noqa: BLE001 - falha inesperada é reportada ao usuário, não silenciada
            job.update(status="failed", error=f"unexpected error: {type(exc).__name__}: {exc}"[:400], message="failed")

    def _probe(
        self,
        job: dict[str, Any],
        req: dict[str, Any],
        proj: dict[str, Any],
        settings: dict[str, Any],
        cancel: threading.Event,
        progress: Any,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        """Executa a sondagem ao vivo com console de eventos (log) e progresso por requisição."""
        params = req.get("params", {})
        t = self.store.target(str(params["target_id"]))
        key = self.secrets.get(t["id"]) or (os.environ.get(t["api_key_env"]) if t.get("api_key_env") else None)
        tgt = Target(t["base_url"], t["model"], key, float(t.get("timeout", 60.0)))
        custom = None
        if params.get("prompts"):
            if not req.get("project_id"):
                raise ValueError("custom prompts require a selected project")
            src = self.store.project(req["project_id"])
            custom = load_table(analysis.resolve(src["root"], str(params["prompts"]), settings), 2000)[0]

        def log(line: str) -> None:
            job["log"] = (job["log"] + [line])[-300:]

        def on_record(r: dict[str, Any]) -> None:
            mark = "ERR " if r["error"] else {True: "PASS", False: "FAIL", None: "OK  "}[r["passed"]]
            lat = f"{r['latency_ms']:.0f}ms" if r["latency_ms"] is not None else "--"
            log(
                f"[{(job['progress_done'] or 0) + 1:>3}/{job['progress_total'] or 0}] {mark} {r['probe_id']:<22} {lat:>8}  {r['detail'][:60]}"
            )

        log(f"> target {t['name']} ({t['model']} @ {tgt.host}){' [SIMULATED]' if t.get('simulated') else ''}")
        log(
            f"> suite {params.get('suite') or 'standard'} · data leaves this machine: {'no' if tgt.is_local else 'YES'}"
        )
        recs = run_probe(
            tgt,
            params.get("suite") or "standard",
            custom,
            cancel,
            progress,
            int(params.get("max_calls") or 200),
            on_record=on_record,
        )
        log("> analyzing responses with the engine…")
        raw = analyze_probe(recs, f"{t['model']}@{tgt.host}")
        inv = [
            {
                "path": f"{t['model']}@{tgt.host}",
                "name": t["name"],
                "kind": "probe",
                "source": f"probe:{t['model']}@{tgt.host}",
            }
        ]
        log(f"> done: {sum(len(r['findings']) for r in raw)} findings")
        if t.get("folder") and proj.get("root"):  # transcrição vira dado do experimento (Generation/Monitor/Audit)
            stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
            out = Path(proj["root"]) / t["folder"] / f"generations_probe_{stamp}.jsonl"
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", encoding="utf-8") as fh:
                for r in recs:
                    fh.write(
                        json.dumps(
                            {
                                "timestamp": dt.datetime.now(dt.UTC).isoformat(),
                                "model": t["model"],
                                **{
                                    k: r.get(k)
                                    for k in (
                                        "probe_id",
                                        "category",
                                        "prompt",
                                        "output",
                                        "config",
                                        "temperature",
                                        "finish_reason",
                                        "latency_ms",
                                        "error",
                                        "reference",
                                        "passed",
                                    )
                                },
                                "max_new_tokens": r.get("max_tokens"),
                                "token_count": r.get("completion_tokens"),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            log(f"> transcript saved to project 'Live models' / {t['folder']}/{out.name}")
        return t, raw, inv

    def _hub(
        self, job: dict[str, Any], req: dict[str, Any], proj: dict[str, Any], exp: dict[str, Any] | None
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Inspeciona um repositório do Hugging Face sem baixar pesos; grava o resumo no experimento."""
        params = req.get("params", {})
        repo = str(params.get("repo_id") or "").strip()
        token = self.secrets.get("hf:token") or os.environ.get(str(params.get("token_env") or "HF_TOKEN")) or None
        job["log"].append(f"> reading metadata of {repo} (no weights are downloaded)")
        job.update(progress_done=0, progress_total=1, message=f"hub {repo}")
        res = hub.inspect(repo, token, str(params.get("revision") or "main"), self.hub_url)
        job["log"].append(f"> done: {len(res['findings'])} findings")
        if exp and proj.get("root"):
            out = Path(proj["root"]) / exp["items"][0] / "hub_metadata.json"
            out.write_text(json.dumps(res["metrics"], ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        job.update(progress_done=1)
        return [res], [{"path": f"hf:{repo}", "name": repo, "kind": "hub", "source": f"hf:{repo}"}]

    def _latest_raw(self, pid: str, eid: str) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
        for m in self.store.reports():
            if m["project_id"] == pid and m.get("experiment_id") == eid and m["kind"] in ("audit", "probe", "hub"):
                full = self.store.report(m["id"])
                return full["raw"], full["report"].get("inventory")
        return None, None

    def _meta(
        self,
        job: dict[str, Any],
        proj: dict[str, Any],
        exp: dict[str, Any] | None,
        req: dict[str, Any],
        report: dict[str, Any],
        question: str | None,
    ) -> dict[str, Any]:
        s = report.get("summary", {})
        return {
            "id": new_id("rep"),
            "created": now(),
            "kind": req["kind"],
            "project_id": proj["id"],
            "project_name": proj["name"],
            "experiment_id": exp["id"] if exp else None,
            "experiment_name": exp["name"] if exp else None,
            "question": question,
            "demo": proj.get("demo", False),
            "findings_by_severity": s.get("findings_by_severity", {}),
            "findings_by_status": s.get("findings_by_status", {}),
            "analyses_run": report.get("analyses_run", []),
            "answer_status": (report.get("answer") or {}).get("status"),
            "job_id": job["id"],
        }
