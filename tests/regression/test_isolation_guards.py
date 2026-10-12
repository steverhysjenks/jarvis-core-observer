"""Exercise the infrastructure guards without contacting any service."""
from contextlib import closing
import socket
import sqlite3
import subprocess
import sys

import pytest


def test_network_resolution_is_blocked():
    with pytest.raises(RuntimeError, match="isolation blocked"):
        socket.getaddrinfo("ha.invalid", 8123)


def test_production_sqlite_is_blocked():
    with pytest.raises(RuntimeError, match="non-temporary SQLite"):
        sqlite3.connect("/var/lib/jarvis-core/jarvis.db")


def test_subprocess_escape_is_blocked():
    with pytest.raises(RuntimeError, match="isolation blocked"):
        subprocess.run([sys.executable, "-c", "pass"], check=True)


def test_temporary_sqlite_is_allowed(tmp_path):
    with closing(sqlite3.connect(tmp_path / "guard-check.db")) as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)

def test_required_audit_events_are_blocked_without_io():
    import conftest
    conftest.verify_isolation()


def test_sqlite_uri_is_blocked_without_io():
    with pytest.raises(RuntimeError, match="SQLite URI"):
        sys.audit("sqlite3.connect", "file:/var/lib/jarvis-core/jarvis.db")


def test_unsafe_modules_are_rejected_before_import():
    import conftest
    for name in ("test_context_live.py", "test_observer_live.py", "test_qwen_live.py", "test_unreviewed.py"):
        assert not conftest.safe_module(conftest.ROOT / "tests" / "regression" / name)
    assert not conftest.safe_module(conftest.ROOT / "test_ledger.py")


def test_explicit_unsafe_test_arguments_are_rejected():
    from types import SimpleNamespace
    import conftest
    for relative in ("test_ledger.py", "tests/regression/test_qwen_live.py"):
        configuration = SimpleNamespace(args=[str(conftest.ROOT / relative)])
        with pytest.raises(pytest.UsageError, match="before collection"):
            conftest.pytest_configure(configuration)


def test_storage_and_service_configuration_are_isolated():
    from pathlib import Path
    import os
    import conftest
    from app.config import settings
    from app.storage import deliveries, ledger
    assert Path(ledger.DATABASE_PATH).resolve().is_relative_to(conftest.ISOLATION_ROOT)
    assert Path(deliveries.DATABASE_PATH).resolve().is_relative_to(conftest.ISOLATION_ROOT)
    assert settings.ha_url == "http://ha.invalid"
    assert settings.music_assistant_url == "http://music.invalid"
    assert settings.ollama_url == "http://ollama.invalid"
    assert settings.ha_token == "isolated-test-placeholder"
    assert settings.music_assistant_token == "isolated-test-placeholder"
    assert settings.observer_mode == "shadow"
    assert os.environ["JARVIS_CORE_API_KEY"] == "isolated-test-placeholder"