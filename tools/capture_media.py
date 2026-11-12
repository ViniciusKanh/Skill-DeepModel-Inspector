"""Gera a mídia da documentação a partir do app REAL em execução: capturas, vídeo e GIF do tour.

Fluxo: dados sintéticos → API local + interface compilada → servidor LLM simulado e Hub HF
simulado (offline) → Playwright percorre as telas gravando vídeo → ffmpeg gera MP4 e GIF →
README.md é atualizado entre os marcadores ``<!-- MEDIA:START -->`` e ``<!-- MEDIA:END -->``.

Uso: ``python tools/capture_media.py [--no-video] [--no-readme]``
Requisitos: ``pip install -e . fastapi uvicorn playwright`` + ``playwright install chromium``;
``npm run build`` em ``frontend/``; ffmpeg no PATH (opcional: sem ele, só capturas e WebM).
Nada é enviado para a internet: todos os servidores escutam em 127.0.0.1.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ROOT / "docs" / "images" / "screens"
MEDIA = ROOT / "docs" / "media"
README = ROOT / "README.md"
START, END = "<!-- MEDIA:START -->", "<!-- MEDIA:END -->"
VIEW = {"width": 1600, "height": 900}

sys.path[:0] = [str(ROOT), str(ROOT / "src")]


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def start_stack(tmp: Path) -> tuple[str, list[Any]]:
    """Sobe API + UI, servidor LLM simulado e Hub simulado; devolve (url, objetos para encerrar)."""
    import uvicorn

    import backend.api.main as m
    from backend.services.store import Store

    synth = tmp / "examples"
    _load("gen_synth", ROOT / "examples" / "generate_synthetic.py").generate(synth)
    m.EXAMPLES = synth
    store = Store(tmp / "workspace")
    store.save_settings({"allowed_roots": [str(synth)], "reports_dir": str(tmp / "workspace" / "reports")})
    fsrv, fport = _load("fake_llm", ROOT / "examples" / "fake_llm_server.py").start(0)
    hsrv, hub_url = _load("fake_hub", ROOT / "examples" / "fake_hf_hub.py").start()
    app = m.create_app(store)
    app.state.jobs.hub_url = hub_url
    app.state.local_servers = [
        {
            "id": "ollama",
            "label": "Ollama (simulated)",
            "port": fport,
            "base_url": f"http://127.0.0.1:{fport}/v1",
            "help": "-",
        },
    ]
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}", [srv, fsrv, hsrv]


def tour(url: str, video_dir: Path | None) -> Path | None:
    """Percorre as telas, salva capturas e (opcionalmente) grava o vídeo do tour."""
    from playwright.sync_api import sync_playwright

    SCREENS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        opts: dict[str, Any] = {"viewport": VIEW}
        if video_dir:
            opts.update(record_video_dir=str(video_dir), record_video_size=VIEW)
        ctx = b.new_context(**opts)
        page = ctx.new_page()

        def shot(name: str, wait: int = 700) -> None:
            page.wait_for_timeout(wait)
            page.screenshot(path=str(SCREENS / f"{name}.png"))
            print(f"  screenshot {name}.png")

        page.goto(url)
        page.get_by_role("button", name="Load demo lab").click()
        page.get_by_text("No analysis yet").wait_for()
        page.get_by_role("button", name="Run audit").click()
        page.get_by_text("Alerts & insights").wait_for(timeout=90000)
        shot("01-dashboard", 1200)
        for nav, marker, name in (
            ("Training Diagnostics", "Convergence & stability checks", "02-training"),
            ("Dataset Quality", "Dataset split & contamination", "03-dataset"),
            ("Tokenizer Efficiency", "Tokenizer comparison", "04-tokenizer"),
            ("Generation Behavior", "Generation examples", "05-generation"),
            ("Experiment Comparison", "Hyperparameter differences", "06-compare"),
        ):
            page.get_by_role("link", name=nav).click()
            page.get_by_role("heading", name=marker).first.wait_for(timeout=30000)
            shot(name)
        page.get_by_role("link", name="Root-Cause Investigation").click()
        page.get_by_label("Investigation question").fill("Why is my model repeating the same responses?")
        page.get_by_role("button", name="Send question").click()
        page.get_by_text("Root-cause chain (hypothesis tree)").wait_for(timeout=30000)
        shot("07-investigate")
        page.get_by_role("link", name="Reports").click()
        page.locator("ul button").first.click()
        page.get_by_text("Executive summary").wait_for()
        shot("08-reports")
        page.get_by_role("link", name="Projects & Experiments").click()
        page.get_by_text("File inventory").wait_for()
        shot("09-projects")
        page.get_by_role("link", name="Settings").click()
        page.get_by_text("Known limitations").wait_for()
        shot("10-settings")

        page.get_by_role("link", name="Model Lab (live)").click()
        page.get_by_role("button", name="On this computer").click()
        page.get_by_text("Ollama (simulated)").wait_for(timeout=15000)
        shot("15-connect-wizard")
        page.get_by_role("button", name="Use").click()
        page.get_by_label("Model", exact=True).first.select_option("demo-flawed")
        page.get_by_role("button", name="Connect & test").click()
        page.get_by_text("Connected to demo-flawed").wait_for(timeout=20000)
        page.get_by_role("button", name="Inspect", exact=True).click()
        page.get_by_role("heading", name="Behaviour scorecard").wait_for(timeout=90000)
        shot("11-model-lab", 1000)
        page.get_by_role("heading", name="Probe transcript").scroll_into_view_if_needed()
        shot("12-model-lab-transcript")
        page.get_by_role("button", name="Open in Dashboard").click()
        page.get_by_text("Alerts & insights").wait_for(timeout=20000)
        page.wait_for_timeout(800)

        page.get_by_role("link", name="Model Lab (live)").click()
        page.get_by_role("button", name="Hugging Face model").click()
        page.get_by_label("Hugging Face repository").fill("good/chat-model")
        page.get_by_role("button", name="Inspect files (no download)").click()
        page.get_by_text("Hugging Face model card").wait_for(timeout=30000)
        shot("14-hf-hub", 1000)

        page.get_by_role("link", name="Production Monitor").click()
        page.get_by_label("Select project").select_option(label="◆ DEMO — Synthetic LLM Lab")
        page.get_by_label("Log folder").fill("synthetic_production")
        page.get_by_label("Period").select_option("week")
        page.get_by_role("button", name="Run monitor").click()
        page.get_by_role("heading", name="Quality signals per period").wait_for(timeout=30000)
        shot("13-production-monitor", 1000)

        video = page.video
        ctx.close()
        b.close()
        return Path(video.path()) if video_dir and video else None


def encode(webm: Path) -> list[str]:
    """Converte o WebM em MP4 (H.264) e GIF otimizado (paleta), acelerado 2x."""
    MEDIA.mkdir(parents=True, exist_ok=True)
    ff = shutil.which("ffmpeg")
    if not ff:
        shutil.copy(webm, MEDIA / "tour.webm")
        print("  ffmpeg not found: kept docs/media/tour.webm (no MP4/GIF)")
        return ["tour.webm"]
    run = lambda *a: subprocess.run([ff, "-y", "-loglevel", "error", *a], check=True)  # noqa: E731
    run(
        "-i",
        str(webm),
        "-vf",
        "setpts=0.5*PTS,scale=1280:-2",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "28",
        "-movflags",
        "+faststart",
        str(MEDIA / "tour.mp4"),
    )
    pal = MEDIA / "_palette.png"
    flt = "setpts=0.33*PTS,fps=6,scale=880:-1:flags=lanczos"
    run("-i", str(webm), "-vf", f"{flt},palettegen=max_colors=96:stats_mode=diff", str(pal))
    run(
        "-i",
        str(webm),
        "-i",
        str(pal),
        "-lavfi",
        f"{flt}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4",
        str(MEDIA / "tour.gif"),
    )
    pal.unlink(missing_ok=True)
    return ["tour.gif", "tour.mp4"]


def update_readme(files: list[str]) -> bool:
    """Reescreve apenas o bloco entre os marcadores de mídia do README."""
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print("  README markers not found; README unchanged")
        return False
    stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    lines = [START, "", '<div align="center">', ""]
    if "tour.gif" in files:
        lines.append(
            '<img src="docs/media/tour.gif" alt="DeepModel Inspector tour: demo audit, investigation, Model Lab, Hugging Face, monitor" width="100%" />'
        )
    if "tour.mp4" in files:
        lines.append("\n▶️ [Full-quality video (MP4)](docs/media/tour.mp4)")
    elif "tour.webm" in files:
        lines.append("\n▶️ [Tour video (WebM)](docs/media/tour.webm)")
    lines += [
        "",
        f"<sub>Captured automatically from the running app on {stamp} (synthetic demo data, simulated model "
        "server and simulated Hugging Face Hub; analyses are real).</sub>",
        "",
        "</div>",
        "",
        END,
    ]
    new = text[: text.index(START)] + "\n".join(lines) + text[text.index(END) + len(END) :]
    if new != text:
        README.write_text(new, encoding="utf-8", newline="\n")
    return new != text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--no-readme", action="store_true")
    a = ap.parse_args(argv)
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        print("frontend/dist missing: run `npm run build` in frontend/ first", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="dmi-media-") as t:
        tmp = Path(t)
        url, servers = start_stack(tmp)
        print(f"app running at {url}")
        try:
            webm = tour(url, None if a.no_video else tmp / "video")
        finally:
            servers[0].should_exit = True
            for s in servers[1:]:
                s.shutdown()
        files = encode(webm) if webm else []
        if files:
            print("  media:", ", ".join(f"docs/media/{f} ({(MEDIA / f).stat().st_size / 1e6:.1f} MB)" for f in files))
        if not a.no_readme and files:
            print("  README updated" if update_readme(files) else "  README already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
