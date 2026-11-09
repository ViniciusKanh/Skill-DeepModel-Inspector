"""Fixtures: gera os dados sintéticos reproduzíveis em diretório temporário."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_synth", ROOT / "examples" / "generate_synthetic.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def synth(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Diretório com todos os cenários sintéticos."""
    d = tmp_path_factory.mktemp("synth")
    _load_generator().generate(d)
    return d


@pytest.fixture(autouse=True)
def _allow_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Executa a partir da raiz temporária de testes (raiz autorizada padrão = cwd)."""
    monkeypatch.chdir(tmp_path_factory.getbasetemp())


def rules(result: dict) -> set[str]:
    return {f["rule"] for f in result["findings"]}
