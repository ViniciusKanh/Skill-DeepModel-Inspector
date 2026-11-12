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
    import importlib.util as iu

    spec = iu.spec_from_file_location("fls", ROOT / "examples" / "fake_llm_server.py")
    fake = iu.module_from_spec(spec)
    spec.loader.exec_module(fake)
    fsrv, fport = fake.start(0)
    app = m.create_app(store)
    hspec = iu.spec_from_file_location("fake_hf_hub", ROOT / "examples" / "fake_hf_hub.py")
    fhub = iu.module_from_spec(hspec)
    hspec.loader.exec_module(fhub)
    hsrv, app.state.jobs.hub_url = fhub.start()  # Hub do Hugging Face simulado (offline)
    app.state.local_servers = [
        {
            "id": "ollama",
            "label": "Ollama (simulated in tests)",
            "port": fport,
            "base_url": f"http://127.0.0.1:{fport}/v1",
            "help": "-",
        },
        {
            "id": "lmstudio",
            "label": "LM Studio",
            "port": 9,
            "base_url": "http://127.0.0.1:9/v1",
            "help": "Start the server.",
        },
    ]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    th.join(5)
    fsrv.shutdown()
    hsrv.shutdown()


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


def test_model_lab_and_monitor(server, browser):
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(server + "/lab")
    page.get_by_role("button", name="Simulated demo").click()
    page.get_by_text("SIMULATED MODEL").first.wait_for()
    page.get_by_role("button", name="Test connection").click()
    page.get_by_text("Connected ·").wait_for(timeout=20000)
    page.get_by_role("button", name="Inspect", exact=True).click()
    page.get_by_role("heading", name="Behaviour scorecard").wait_for(timeout=60000)
    assert page.get_by_text("Model followed instructions embedded in a document").first.is_visible()
    log = page.get_by_role("log", name="Inspection console").inner_text()
    assert "FAIL" in log and "analyzing" in log
    shot(page, "14-model-lab")
    page.get_by_label("Question about this inspection").fill("Is my model vulnerable to prompt injection?")
    page.get_by_role("button", name="Ask").click()
    page.get_by_text("Observed problem(s) confirmed by the data").first.wait_for(timeout=20000)
    assert no_hscroll(page)
    page.get_by_role("heading", name="Probe transcript").scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    shot(page, "15-model-lab-transcript")
    page.get_by_role("button", name="Open in Dashboard").click()
    page.get_by_text("Alerts & insights").wait_for(timeout=20000)
    assert page.get_by_text("Model followed instructions embedded in a document").first.is_visible()
    page.goto(server + "/projects")
    page.get_by_role("button", name="Load demo").click()
    page.get_by_role("heading", name="Experiments — DEMO — Synthetic LLM Lab").wait_for()
    page.get_by_role("link", name="Production Monitor").click()
    page.get_by_label("Log folder").fill("synthetic_production")
    page.get_by_label("Period").select_option("week")
    page.get_by_role("button", name="Run monitor").click()
    page.get_by_role("heading", name="Quality signals per period").wait_for(timeout=30000)
    assert page.get_by_text("Degenerate repetition above threshold").first.is_visible()
    page.get_by_role("heading", name="Model health history (live probes)").wait_for()
    page.wait_for_timeout(600)
    assert no_hscroll(page)
    shot(page, "16-production-monitor")
    assert not errors, errors
    ctx.close()


def test_connect_wizard_local(server, browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(server + "/lab")
    page.get_by_role("button", name="On this computer").click()
    page.get_by_text("Ollama (simulated in tests)").wait_for(timeout=15000)
    page.get_by_text("not running").first.wait_for()
    shot(page, "17-connect-wizard-detect")
    page.get_by_role("button", name="Use").click()
    page.get_by_label("Model", exact=True).select_option("demo-good")
    page.get_by_role("button", name="Connect & test").click()
    page.get_by_text("Connected to demo-good").wait_for(timeout=20000)
    assert page.get_by_role("button", name="Select Ollama (simulated in tests) · demo-good").count() == 1
    ctx.close()


def test_hf_hub_inspection_without_download(server, browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(server + "/lab")
    page.get_by_role("button", name="Hugging Face model").click()
    page.get_by_label("Hugging Face repository").fill("bad/pickle-model")
    shot(page, "18-hf-hub-wizard")
    page.get_by_role("button", name="Inspect files (no download)").click()
    page.get_by_text("Alerts & insights").wait_for(timeout=30000)
    page.get_by_text("Weights only in pickle format").first.wait_for()
    page.wait_for_timeout(500)
    assert no_hscroll(page)
    shot(page, "19-hf-hub-dashboard")
    page.goto(server + "/lab")
    page.get_by_role("button", name="Hugging Face model").click()
    page.get_by_label("Hugging Face repository").fill("good/chat-model")
    page.get_by_role("button", name="Run it online (HF Inference Providers) and probe behaviour").click()
    assert page.get_by_label("Base URL").first.input_value() == "https://router.huggingface.co/v1"
    assert page.get_by_label("Model", exact=True).first.input_value() == "good/chat-model"
    assert not errors, errors
    ctx.close()
