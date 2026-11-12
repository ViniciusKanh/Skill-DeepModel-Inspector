# -*- mode: python ; coding: utf-8 -*-
# Especificação PyInstaller (modo onedir): executável + pasta _internal com backend, motor,
# interface compilada (frontend/dist) e exemplos. Gerar com: pyinstaller desktop/deepmodel.spec
from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(ROOT), str(ROOT / "src")],
    datas=[
        (str(ROOT / "frontend" / "dist"), "frontend/dist"),
        (str(ROOT / "examples"), "examples"),
        (str(ROOT / "docs" / "limitations.md"), "docs"),
    ],
    hiddenimports=[
        "backend.api.main", "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    ],
    excludes=["mypy", "tkinter", "matplotlib", "numpy", "torch", "transformers", "pytest", "playwright"],
    noarchive=False,
)
pyz = PYZ(a.pure)
icon = ROOT / "desktop" / "icon.ico"
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="DeepModelInspector", console=True,
    icon=str(icon) if icon.exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="DeepModelInspector")
