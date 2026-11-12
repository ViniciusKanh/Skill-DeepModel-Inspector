"""Persistência local (JSON) de configurações, projetos e relatórios.

Tudo é gravado no diretório de trabalho da aplicação (``workspace/`` por padrão ou
``DMI_APP_HOME``). Nenhum dado sai da máquina. Os arquivos analisados nunca são alterados.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from deepmodel_inspector.security.guard import SecurityError, is_sensitive, within_roots

REPO_ROOT = Path(__file__).resolve().parents[2]


def now() -> str:
    """Data/hora UTC em ISO-8601."""
    t = dt.datetime.now(dt.UTC)
    return t.strftime("%Y-%m-%dT%H:%M:%S") + f".{t.microsecond // 1000:03d}Z"


def new_id(prefix: str) -> str:
    """Identificador curto e único."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


LIVE_PROJECT: dict[str, Any] = {"id": "live", "name": "Live models", "root": "", "demo": False, "experiments": []}
LIVE_ID = "prj-live"


def slugify(text: str) -> str:
    """Nome de pasta seguro a partir de um rótulo."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.").lower()
    return (s or "model")[:60]


class Store:
    """Armazenamento thread-safe em arquivos JSON."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = Path(home or os.environ.get("DMI_APP_HOME") or REPO_ROOT / "workspace").resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "reports").mkdir(exist_ok=True)
        self._lock = threading.RLock()

    # ------------------------------------------------------------ util
    def _read(self, name: str, default: Any) -> Any:
        p = self.home / name
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def _write(self, name: str, data: Any) -> None:
        p = self.home / name
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        tmp.replace(p)

    # ------------------------------------------------------------ settings
    def settings(self) -> dict[str, Any]:
        """Configurações com padrões seguros (raiz autorizada: diretório do produto)."""
        with self._lock:
            s = self._read("settings.json", {})
            env_roots = [r for r in os.environ.get("DMI_DEFAULT_ROOTS", "").split(os.pathsep) if r.strip()]
            s.setdefault("allowed_roots", env_roots or [str(REPO_ROOT)])
            if str(self.home) not in s["allowed_roots"]:  # o workspace do app (modelos ao vivo) é sempre legível
                s["allowed_roots"] = [*s["allowed_roots"], str(self.home)]
            s.setdefault("reports_dir", str(self.home / "reports"))
            s.setdefault("max_records", 200_000)
            s.setdefault("max_mb", 200.0)
            return s

    def save_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        """Valida e grava configurações (raízes existentes, sem diretórios sensíveis)."""
        roots = []
        for r in data.get("allowed_roots") or []:
            p = Path(r).expanduser().resolve()
            if not p.is_dir():
                raise SecurityError(f"authorized root is not an existing directory: {r}")
            if is_sensitive(p) or p == Path(p.anchor):
                raise SecurityError(f"refusing to authorize this directory: {r}")
            roots.append(str(p))
        if not roots:
            raise SecurityError("at least one authorized root is required")
        rd = Path(data.get("reports_dir") or self.home / "reports").expanduser().resolve()
        if not (within_roots(rd, [Path(r) for r in roots]) or within_roots(rd, [self.home])):
            raise SecurityError("reports directory must be inside an authorized root or the app workspace")
        with self._lock:
            s = self.settings()
            s.update(
                {
                    "allowed_roots": roots,
                    "reports_dir": str(rd),
                    "max_records": int(data.get("max_records", s["max_records"])),
                    "max_mb": float(data.get("max_mb", s["max_mb"])),
                }
            )
            self._write("settings.json", s)
            return s

    # ------------------------------------------------------------ projects
    def projects(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read("projects.json", [])

    def project(self, pid: str) -> dict[str, Any]:
        for p in self.projects():
            if p["id"] == pid:
                return p
        raise KeyError(f"project not found: {pid}")

    def save_project(self, proj: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            items = [p for p in self.projects() if p["id"] != proj["id"]]
            items.append(proj)
            self._write("projects.json", items)
            return proj

    def delete_project(self, pid: str) -> None:
        """Remove apenas o registro do projeto (arquivos do usuário não são tocados)."""
        with self._lock:
            self._write("projects.json", [p for p in self.projects() if p["id"] != pid])

    # ------------------------------------------------------------ projeto "Live models"
    def live_project(self) -> dict[str, Any]:
        """Projeto onde cada modelo conectado vira um experimento (transcrições e relatórios)."""
        root = self.home / "live_models"
        root.mkdir(parents=True, exist_ok=True)
        with self._lock:
            try:
                return self.project(LIVE_ID)
            except KeyError:
                proj = {
                    "id": LIVE_ID,
                    "name": "Live models",
                    "root": str(root),
                    "demo": False,
                    "created": now(),
                    "experiments": [],
                    "inventory": [],
                }
                return self.save_project(proj)

    def attach_experiment(self, label: str, key: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Garante um experimento (e pasta) no projeto Live models; ``key`` identifica o modelo/repositório."""
        with self._lock:
            proj = self.live_project()
            exp = next((e for e in proj["experiments"] if e.get("key") == key), None)
            if exp is None:
                folder = slugify(label)
                used = {e["items"][0] for e in proj["experiments"] if e.get("items")}
                base, n = folder, 2
                while folder in used:
                    folder, n = f"{base}-{n}", n + 1
                (Path(proj["root"]) / folder).mkdir(parents=True, exist_ok=True)
                exp = {"id": new_id("exp"), "name": label, "items": [folder], "created": now(), "key": key}
                proj["experiments"].append(exp)
                self.save_project(proj)
            return proj, exp

    def attach_target(self, t: dict[str, Any]) -> dict[str, Any]:
        _, exp = self.attach_experiment(t["name"], t.get("key") or f"{t['base_url']}|{t['model']}")
        t.update(project_id=LIVE_ID, experiment_id=exp["id"], folder=exp["items"][0])
        return t

    # ------------------------------------------------------------ alvos (modelos ao vivo)
    def targets(self) -> list[dict[str, Any]]:
        """Alvos registrados. Chaves de API NUNCA são gravadas (apenas o nome da variável de ambiente)."""
        with self._lock:
            ts = self._read("targets.json", [])
            if any("experiment_id" not in t for t in ts):  # migração: todo alvo vira experimento
                ts = [t if "experiment_id" in t else self.attach_target(t) for t in ts]
                self._write("targets.json", ts)
            return ts

    def target(self, tid: str) -> dict[str, Any]:
        for t in self.targets():
            if t["id"] == tid:
                return t
        raise KeyError(f"target not found: {tid}")

    def save_target(self, t: dict[str, Any]) -> dict[str, Any]:
        assert "api_key" not in t
        with self._lock:
            if "experiment_id" not in t:
                self.attach_target(t)
            self._write("targets.json", [x for x in self.targets() if x["id"] != t["id"]] + [t])
            return t

    def delete_target(self, tid: str) -> None:
        with self._lock:
            self._write("targets.json", [x for x in self.targets() if x["id"] != tid])

    # ------------------------------------------------------------ reports
    def save_report(self, meta: dict[str, Any], report: dict[str, Any], raw: list[dict[str, Any]]) -> None:
        with self._lock:
            path = self.home / "reports" / f"{meta['id']}.json"
            path.write_text(
                json.dumps({"meta": meta, "report": report, "raw": raw}, ensure_ascii=False, default=str),
                encoding="utf-8",
            )

    def report(self, rid: str) -> dict[str, Any]:
        if not rid.replace("-", "").isalnum():
            raise KeyError("invalid report id")
        p = self.home / "reports" / f"{rid}.json"
        if not p.exists():
            raise KeyError(f"report not found: {rid}")
        return json.loads(p.read_text(encoding="utf-8"))

    def reports(self) -> list[dict[str, Any]]:
        out = []
        for p in (self.home / "reports").glob("rep-*.json"):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8"))["meta"])
            except (OSError, ValueError, KeyError):
                continue
        return sorted(out, key=lambda m: m["created"], reverse=True)
