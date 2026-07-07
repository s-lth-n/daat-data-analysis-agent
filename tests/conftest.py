"""
conftest.py — Place this in ~/ta-data-analyst/tests/
Automatically adds backend/ to Python path so tests can import tools, agents, etc.
"""

import sys
from pathlib import Path

import pytest

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))


@pytest.fixture(autouse=True)
def _pin_default_language(monkeypatch):
    """
    detect_language()'s fallback now reads settings.default_language (the single
    source of truth). The live runtime launches from backend/ (see
    scripts/run_dev.sh), where no .env is loaded, so that default is "en".
    Pytest, however, runs from the repo root where a local .env may set
    TA_DEFAULT_LANGUAGE=id and leak into the process. Pin the setting to "en"
    here so the whole suite reflects real runtime config regardless of a
    developer's local .env. Tests that exercise the wiring re-patch it explicitly.
    """
    from config import settings
    monkeypatch.setattr(settings, "default_language", "en")
