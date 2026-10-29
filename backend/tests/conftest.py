from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SPATIALTRACE_MODE", "mock")
    monkeypatch.setenv("OFFLINE_SNAPSHOTS", "0")
    monkeypatch.setenv("SPATIALTRACE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_API_KEY", "YOUR_HACKATHON_API_KEY")

    from core.providers import get_model_client
    from core.settings import reset_settings
    from database import init_db

    reset_settings()
    get_model_client.cache_clear()
    init_db()
    yield tmp_path
    get_model_client.cache_clear()
    reset_settings()
