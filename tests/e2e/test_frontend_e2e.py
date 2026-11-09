"""Testes ponta a ponta do frontend real (build de produção servido pela API) com Playwright.

Fluxo DEMO completo: carregar demo → auditoria → páginas → investigação → evidência →
exportação. Também verifica estados de erro, efeitos CRT e responsividade. As capturas
de tela são gravadas em docs/screenshots/ a partir da aplicação em execução.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "frontend" / "dist"
SHOTS = ROOT / "docs" / "screenshots"
pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not (DIST / "index.html").exists(), reason="frontend not built")]


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory, synth: Path):
    import backend.api.main as m
    from backend.services.store import Store

    m.EXAMPLES = synth
    ws = tmp_path_factory.mktemp("ws")
    store = Store(ws)
    store.save_settings({"allowed_roots": [str(synth)], "reports_dir": str(ws / "reports")})
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(m.create_app(store), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    th.join(5)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def no_hscroll(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def shot(page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"))


def test_demo_flow_all_pages(server, browser):
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, accept_downloads=True)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(server)
    page.get_by_role("button", name="Load demo lab").click()
    page.get_by_text("No analysis yet").wait_for()
    page.get_by_role("button", name="Run audit").click()
    page.get_by_text("Alerts & insights").wait_for(timeout=60000)
    page.get_by_text("DEMO MODE").first.wait_for()
    assert page.get_by_text("Evaluation records present verbatim in training").first.is_visible()
    shot(page, "01-dashboard")

    checks = [
        ("Training Diagnostics", "Convergence & stability checks", "02-training"),
        ("Dataset Quality", "Dataset split & contamination", "03-dataset"),
        ("Tokenizer Efficiency", "Tokenizer comparison", "04-tokenizer"),
        ("Generation Behavior", "Generation examples", "05-generation"),
        ("Experiment Comparison", "Hyperparameter differences", "06-compare"),
    ]
    for nav, marker, name in checks:
        page.get_by_role("link", name=nav).click()
        page.get_by_role("heading", name=marker).first.wait_for(timeout=20000)
        page.wait_for_timeout(700)
        assert no_hscroll(page), name
        shot(page, name)

    # Gráfico interativo: alternar série e verificar estatística do intervalo
    page.get_by_role("link", name="Training Diagnostics").click()
    page.get_by_text("Series (selected range)").first.wait_for()
    page.get_by_role("button", name="Val loss").first.click()
    assert page.get_by_role("button", name="Val loss").first.get_attribute("aria-pressed") == "false"

    # Investigação de causa raiz
    page.get_by_role("link", name="Root-Cause Investigation").click()
    box = page.get_by_label("Investigation question")
    box.fill("Why is my model repeating the same responses?")
    page.get_by_role("button", name="Send question").click()
    page.get_by_text("Root-cause chain (hypothesis tree)").wait_for(timeout=30000)
    page.get_by_text("Observed problem(s) confirmed by the data").first.wait_for()
    h = box.bounding_box()
    assert h and h["height"] <= 48  # campo compacto
    shot(page, "07-investigate")
    page.locator("button:has-text('Degenerate repetition')").first.click()
    page.get_by_role("dialog").get_by_role("button", name="Preview source file").click()
    page.get_by_role("dialog").get_by_text("SOURCE FILE PREVIEW").wait_for()
    page.keyboard.press("Escape")
    box.fill("Is my fine-tuning dataset contaminated?")
    page.get_by_role("button", name="Send question").click()
    page.locator("button:has-text('Evaluation records present verbatim')").first.wait_for(timeout=30000)
    page.locator("button:has-text('Evaluation records present verbatim')").first.click()
    page.get_by_role("dialog").get_by_text("SUPPORTING RECORDS").wait_for()
    page.get_by_role("dialog").get_by_text("EVIDENCE").first.wait_for()
    shot(page, "08-evidence-modal")
    page.keyboard.press("Escape")
    with page.expect_download() as dl:
        page.get_by_role("link", name="HTML").click()
    content = Path(dl.value.path()).read_text(encoding="utf-8")
    assert "<!doctype html>" in content and "Root Cause Investigation" in content

    # Relatórios
    page.get_by_role("link", name="Reports").click()
    page.locator("ul button").first.click()
    page.get_by_text("Executive summary").wait_for()
    with page.expect_download() as dl:
        page.get_by_role("link", name="Download Markdown").click()
    assert "# DeepModel Inspector Report" in Path(dl.value.path()).read_text(encoding="utf-8")
    shot(page, "09-reports")

    page.get_by_role("link", name="Projects & Experiments").click()
    page.get_by_text("File inventory").wait_for()
    shot(page, "10-projects")
    page.get_by_role("link", name="Settings").click()
    page.get_by_text("Known limitations").wait_for()
    page.wait_for_timeout(500)
    shot(page, "11-settings")
    page.get_by_role("switch", name="CRT effects (scanlines, glow)").click()
    assert "fx-off" in page.evaluate("document.documentElement.className")
    assert not errors, errors
    ctx.close()


def test_error_states(server, browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.route("**/api/**", lambda r: r.abort())
    page.goto(server)
    page.get_by_text("Backend offline").first.wait_for()
    page.get_by_text("The local API is not reachable").wait_for()
    shot(page, "12-backend-offline")
    ctx.close()


@pytest.mark.parametrize("w,h", [(1920, 1080), (1440, 900), (1366, 768), (390, 844)])
def test_responsive(server, browser, w, h):
    ctx = browser.new_context(viewport={"width": w, "height": h})
    page = ctx.new_page()
    page.goto(server)
    page.get_by_role("button", name="Load demo lab").click()
    page.get_by_text("DEMO MODE").first.wait_for()
    for path, marker in (
        ("/", "Alerts & insights"),
        ("/investigate", "Investigation conversation"),
        ("/dataset", "Text length distribution"),
    ):
        page.goto(server + path)
        page.get_by_role("heading", name=marker).first.wait_for(timeout=20000)
        page.wait_for_timeout(400)
        assert no_hscroll(page), (w, path)
    if w in (1366, 390):
        page.goto(server + "/")
        page.get_by_text("Alerts & insights").first.wait_for()
        page.wait_for_timeout(500)
        shot(page, f"13-dashboard-{w}x{h}")
    ctx.close()
