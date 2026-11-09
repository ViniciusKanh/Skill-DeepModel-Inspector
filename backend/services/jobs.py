"""Execução assíncrona de análises em threads locais, com progresso real e cancelamento cooperativo."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend.services import analysis
from backend.services.store import Store, new_id, now
from deepmodel_inspector.diagnostics.rootcause import consolidate
from deepmodel_inspector.security.guard import SecurityError


class JobManager:
    """Fila de tarefas (máx. 2 simultâneas) com estado consultável."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.jobs: dict[str, dict[str, Any]] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dmi-job")

    def public(self, job: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in job.items() if not k.startswith("_")}

    def submit(self, req: dict[str, Any]) -> dict[str, Any]:
        proj = self.store.project(req["project_id"])
        exp = None
        if req.get("experiment_id"):
            exp = next((e for e in proj["experiments"] if e["id"] == req["experiment_id"]), None)
            if exp is None:
                raise KeyError("experiment not found")
        if req["kind"] in ("audit", "investigate") and exp is None:
            raise ValueError("audit/investigate require an experiment")
        job = {
            "id": new_id("job"),
            "kind": req["kind"],
            "status": "queued",
            "created": now(),
            "project_id": proj["id"],
            "experiment_id": exp["id"] if exp else None,
            "progress_done": None,
            "progress_total": None,
            "message": "queued",
            "report_id": None,
            "error": None,
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
            if req["kind"] in ("audit", "investigate"):
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
            meta["params"] = req.get("params", {})
            self.store.save_report(meta, report, raw)
            job.update(status="done", report_id=meta["id"], message="completed")
        except analysis.Cancelled:
            job.update(status="cancelled", message="cancelled by user")
        except (SecurityError, ValueError, OSError, KeyError, UnicodeError) as exc:
            job.update(status="failed", error=f"{type(exc).__name__}: {exc}"[:400], message="failed")
        except Exception as exc:  # noqa: BLE001 - falha inesperada é reportada ao usuário, não silenciada
            job.update(status="failed", error=f"unexpected error: {type(exc).__name__}: {exc}"[:400], message="failed")

    def _latest_raw(self, pid: str, eid: str) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
        for m in self.store.reports():
            if m["project_id"] == pid and m.get("experiment_id") == eid and m["kind"] == "audit":
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
