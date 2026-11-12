"""Inicializador da versão instalável (Windows/Linux) do DeepModel Inspector.

Define o diretório de trabalho do usuário (fora da pasta de instalação), escolhe uma porta
livre em 127.0.0.1, inicia a API local (que também serve a interface) e abre o navegador.
Nada é exposto na rede: o servidor escuta somente em localhost.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def app_home() -> Path:
    """Pasta de dados do usuário: %LOCALAPPDATA%\\DeepModelInspector (Windows) ou ~/.local/share."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "DeepModelInspector"


def free_port(preferred: int = 8765) -> int:
    """Usa a porta preferida se estiver livre; caso contrário, uma porta efêmera."""
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("no free local port")


def main() -> int:
    home = app_home()
    (home / "workspace").mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DMI_APP_HOME", str(home / "workspace"))
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    # Raízes autorizadas padrão: exemplos incluídos + pasta do usuário (editável em Settings).
    os.environ.setdefault("DMI_DEFAULT_ROOTS", os.pathsep.join([str(bundle / "examples"), str(Path.home())]))
    if not getattr(sys, "frozen", False):
        sys.path[:0] = [str(bundle), str(bundle / "src")]

    import uvicorn

    from backend.api.main import create_app

    port = free_port(int(os.environ.get("DMI_PORT", "8765")))
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))

    def open_browser() -> None:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.1)
        if "--no-browser" not in sys.argv:
            webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    print(f"DeepModel Inspector running at {url}  (data: {home})")
    print("Close this window to stop the app.")
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
