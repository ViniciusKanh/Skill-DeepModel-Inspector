"""Persistência local (JSON) de configurações, projetos e relatórios.

Tudo é gravado no diretório de trabalho da aplicação (``workspace/`` por padrão ou
``DMI_APP_HOME``). Nenhum dado sai da máquina. Os arquivos analisados nunca são alterados.
"""

from __future__ import annotations

import datetime as dt
import json
import os
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
            s.setdefault("allowed_roots", [str(REPO_ROOT)])
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
