"""Explicit production profile: preserved real settings, read-only external access."""
import ast
import json
import importlib.abc
import os
from pathlib import Path
import sqlite3
import sys

import httpx
import pytest
from acceptance_policy import APPROVED, PRODUCTION_DATABASE, readonly_request, readonly_sqlite

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"


class NoApplicationServer(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"app.main", "uvicorn"}:
            raise RuntimeError("Acceptance must not import an ASGI server or start its lifespan")


sys.meta_path.insert(0, NoApplicationServer())


def safe_module(path):
    path = Path(path).resolve()
    if path.parent != ROOT / "tests/regression" or path.name not in APPROVED:
        return False
    tree = ast.parse(path.read_text())
    return not any(isinstance(n, ast.Attribute) and n.attr == "behavioural" for n in ast.walk(tree))


def audit(event, args):
    if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork", "os.forkpty", "socket.bind"}:
        raise RuntimeError("Production acceptance forbids processes and servers")
    if event == "sqlite3.connect" and not readonly_sqlite(args[0], uri=True, workspace=WORK):
        raise RuntimeError("Production acceptance blocked unsafe SQLite")


sys.addaudithook(audit)


def pytest_configure(config):
    if os.environ.get("JARVIS_ACCEPTANCE_COMMIT") is None:
        raise pytest.UsageError("Production acceptance requires its approved versioned runner")
    for argument in config.args:
        path = Path(str(argument).split("::", 1)[0]).resolve()
        if path.is_file() and not safe_module(path):
            raise pytest.UsageError("Unreviewed/behavioural acceptance module blocked")
        if path.is_dir() and path != ROOT / "tests/regression":
            raise pytest.UsageError("Unexpected production collection path")
    config.option.basetemp = str(WORK / "pytest")
    from app.config import settings
    endpoints = {"ha": settings.ha_url, "music": settings.music_assistant_url,
                 "ollama": settings.ollama_url, "jarvis": "http://127.0.0.1:8000"}
    original_async, original_sync = httpx.AsyncClient._send_single_request, httpx.Client._send_single_request
    async def async_send(client, request):
        if not readonly_request(request.method, request.url, request.content, endpoints):
            raise RuntimeError("Production acceptance blocked non-read-only HTTP")
        return await original_async(client, request)
    def sync_send(client, request):
        if not readonly_request(request.method, request.url, request.content, endpoints):
            raise RuntimeError("Production acceptance blocked non-read-only HTTP")
        return original_sync(client, request)
    httpx.AsyncClient._send_single_request, httpx.Client._send_single_request = async_send, sync_send
    original_connect = sqlite3.connect
    def connect(database, *args, **kwargs):
        if not readonly_sqlite(database, uri=kwargs.get("uri", False), workspace=WORK):
            raise RuntimeError("Production acceptance blocked SQLite mutation target")
        connection = original_connect(database, *args, **kwargs)
        if str(database) == PRODUCTION_DATABASE:
            connection.execute("PRAGMA query_only=ON")
            allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
            connection.set_authorizer(lambda action, *unused: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
        return connection
    sqlite3.connect = connect
    from app.storage import ledger, deliveries
    ledger.DATABASE_PATH, deliveries.DATABASE_PATH = WORK / "ledger.db", WORK / "deliveries.db"
    from app.observer import runner
    async def no_observer(*args, **kwargs):
        raise RuntimeError("Production acceptance cannot start an Observer loop")
    runner.observer_loop = no_observer


def pytest_ignore_collect(collection_path, config):
    path = Path(collection_path)
    return path.is_file() and path.name.startswith("test_") and not safe_module(path)


def pytest_collection_modifyitems(items):
    for item in items:
        if not safe_module(item.path) or item.get_closest_marker("behavioural"):
            raise pytest.UsageError("Unsafe acceptance test reached collection")
    if {Path(item.path).name for item in items} != APPROVED:
        raise pytest.UsageError("Acceptance did not collect every approved module")


def pytest_runtest_logstart(nodeid, location):
    status = ROOT / "results/runner-status.json"
    value = json.loads(status.read_text())
    value["tests_started"] = True
    status.write_text(json.dumps(value, sort_keys=True))


@pytest.fixture(autouse=True)
def temporary_storage(monkeypatch, tmp_path):
    from app.storage import ledger, deliveries
    monkeypatch.setattr(ledger, "DATABASE_PATH", tmp_path / "ledger.db")
    monkeypatch.setattr(deliveries, "DATABASE_PATH", tmp_path / "deliveries.db")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    report.sections, report.user_properties = [], []
    if report.failed:
        report.longrepr = f"Acceptance failed: {item.nodeid}; detailed live payload/trace withheld"


def pytest_collectreport(report):
    report.sections = []
    if report.failed:
        report.longrepr = "Production acceptance collection failed; details withheld"
@pytest.hookimpl(tryfirst=True)
def pytest_runtest_logreport(report):
    report.sections, report.user_properties = [], []
    if report.failed:
        report.longrepr = f"Acceptance failed: {report.nodeid}; detailed live payload/trace withheld"
    elif report.skipped:
        report.longrepr = ("production-acceptance", 0, "Skipped: acceptance test skipped")
