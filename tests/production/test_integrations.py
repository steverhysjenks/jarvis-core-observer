"""Approved read-only checks against the active application's real integrations."""
from contextlib import closing
import sqlite3
import httpx
import pytest
from acceptance_policy import PRODUCTION_DATABASE

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_home_assistant_authenticated_state_read():
    from app.adapters.homeassistant import ha_client
    assert isinstance(await ha_client.get_states(), list)


@pytest.mark.asyncio
async def test_music_assistant_catalogue_read():
    from app.adapters.music_assistant_native import music_assistant_native
    assert isinstance(await music_assistant_native.genres(limit=1), list)


@pytest.mark.asyncio
async def test_local_llm_configured_model_is_available():
    from app.config import settings
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        response = await client.get(settings.ollama_url.rstrip("/") + "/api/tags")
        response.raise_for_status()
    assert settings.judgement_model in {m.get("name") for m in response.json()["models"]}


@pytest.mark.asyncio
async def test_running_observer_is_healthy():
    from app.config import settings
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        response = await client.get("http://127.0.0.1:8000/observer/status")
        response.raise_for_status()
    status = response.json()
    assert status["running"] is True
    assert status["mode"] == settings.observer_mode
    assert status["last_error"] is None
    assert status["cycles_completed"] >= 1


def test_production_sqlite_schema_is_readable_without_writes():
    with closing(sqlite3.connect(PRODUCTION_DATABASE, uri=True)) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"attention_ledger", "attention_observations"} <= tables
        # Delivery history is initialized lazily by the application, not by tests.
        if "announcement_deliveries" in tables:
            assert connection.execute("SELECT count(*) FROM announcement_deliveries").fetchone()[0] >= 0


@pytest.mark.asyncio
async def test_jarvis_health_and_context_api():
    from pathlib import Path
    import json
    import os
    release = json.loads((Path(os.environ["JARVIS_ACCEPTANCE_RELEASE"]) / "RELEASE.json").read_text())
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        response = await client.get("http://127.0.0.1:8000/health")
        response.raise_for_status()
        assert response.json()["status"] == "healthy"
        assert response.json()["version"] == release["application_version"]
        context = await client.get("http://127.0.0.1:8000/context/observer")
        context.raise_for_status()
        assert "schedule" in context.json()