"""Fail-closed collection and infrastructure isolation for the adopted baseline."""
import ast
import os
from pathlib import Path
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parent
_temporary_storage = tempfile.TemporaryDirectory(prefix="jarvis-tests-")
ISOLATION_ROOT = Path(_temporary_storage.name).resolve()
SAFE_MODULES = {
    "test_nutrition.py",
    "test_action_executor.py", "test_action_policy.py", "test_activity_detector.py",
    "test_areas.py", "test_availability.py", "test_bounded_judgement.py",
    "test_departure_behaviour.py", "test_detector_orchestration.py",
    "test_enrichment.py", "test_evaluator_integration.py", "test_import_contracts.py",
    "test_judgement_contract.py", "test_ledger_lifecycle.py", "test_observer_cycle.py",
    "test_replay.py", "test_resolver.py", "test_routine_math.py",
    "test_voice_routing.py", "test_waste_detector.py", "test_isolation_guards.py",
}

# Override inherited live configuration BEFORE application imports/collection.
os.environ.update({
    "HA_URL": "http://ha.invalid", "HA_TOKEN": "isolated-test-placeholder",
    "MUSIC_ASSISTANT_URL": "http://music.invalid",
    "MUSIC_ASSISTANT_TOKEN": "isolated-test-placeholder",
    "OLLAMA_URL": "http://ollama.invalid", "JUDGEMENT_MODEL": "test-only",
    "OBSERVER_MODE": "shadow", "JARVIS_CORE_API_KEY": "isolated-test-placeholder",
    "NUTRITION_ENABLED": "false",
})


def isolation_audit(event, args):
    # Audit hooks cannot be undone by a test's monkeypatch fixture.
    if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
                 "socket.gethostbyaddr", "socket.sendto", "socket.sendmsg", "socket.bind",
                 "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork", "os.forkpty"}:
        raise RuntimeError("Jarvis test isolation blocked network/process access")
    if event == "sqlite3.connect":
        database = args[0]
        if database == ":memory:":
            return
        if not isinstance(database, (str, bytes, os.PathLike)):
            raise RuntimeError("Jarvis test isolation blocked unknown SQLite target")
        database = os.fsdecode(database)
        if database.startswith("file:"):
            raise RuntimeError("Jarvis test isolation blocked SQLite URI")
        if not Path(database).resolve().is_relative_to(ISOLATION_ROOT):
            raise RuntimeError("Jarvis test isolation blocked non-temporary SQLite")


sys.addaudithook(isolation_audit)


def verify_isolation():
    """Verify installed hooks with synthetic events before any application import.

    sys.audit emits an event only: these checks never open a socket, database,
    or subprocess even when a guard is broken.
    """
    checks = (
        ("socket.connect", (None, ("127.0.0.1", 0))),
        ("socket.getaddrinfo", ("ha.invalid", 8123, 0, 0, 0)),
        ("socket.sendto", (None, ("127.0.0.1", 0))),
        ("sqlite3.connect", ("/var/lib/jarvis-core/jarvis.db",)),
        ("sqlite3.connect", ("file:/var/lib/jarvis-core/jarvis.db",)),
        ("subprocess.Popen", ("blocked", (), None, None)),
    )
    for event, arguments in checks:
        try:
            sys.audit(event, *arguments)
        except RuntimeError as error:
            if "Jarvis test isolation blocked" not in str(error):
                raise
        else:
            raise RuntimeError(f"Required isolation guard failed: {event}")


verify_isolation()


def safe_module(path):
    path = Path(path).resolve()
    if path.parent != ROOT / "tests" / "regression" or path.name not in SAFE_MODULES:
        return False
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return not any(isinstance(node, ast.Attribute) and node.attr in {"live", "behavioural"}
                   for node in ast.walk(tree))


def pytest_ignore_collect(collection_path, config):
    path = Path(collection_path)
    if path.is_dir():
        return path.name in {"app", ".git", ".venv", "venv", "docs"}
    return path.suffix == ".py" and path.name.startswith("test_") and not safe_module(path)


def pytest_configure(config):
    # Explicit file arguments can bypass pytest_ignore_collect: reject them here.
    for argument in config.args:
        path = Path(str(argument).split("::", 1)[0]).resolve()
        if path.is_file() and not safe_module(path):
            raise pytest.UsageError("Unsafe/unreviewed test file blocked before collection")
        if path.is_dir() and path not in {ROOT, ROOT / "tests", ROOT / "tests" / "regression"}:
            raise pytest.UsageError("Only the reviewed regression directory may be collected")
    if config.option.basetemp is not None:
        raise pytest.UsageError("Custom --basetemp is blocked by test isolation")
    config.option.basetemp = str(ISOLATION_ROOT / "pytest")
    from app.storage import deliveries, ledger
    ledger.DATABASE_PATH = ISOLATION_ROOT / "collection-ledger.db"
    deliveries.DATABASE_PATH = ISOLATION_ROOT / "collection-deliveries.db"


def pytest_collection_modifyitems(items):
    if os.environ.get("JARVIS_CI_FULL_SUITE") == "1":
        collected = {Path(item.path).name for item in items}
        if collected != SAFE_MODULES:
            raise pytest.UsageError("Approved regression module coverage is incomplete")
    for item in items:
        if not safe_module(item.path) or any(item.get_closest_marker(m) for m in ("live", "behavioural")):
            raise pytest.UsageError("Unsafe test reached collection; execution blocked")


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch, tmp_path):
    from app.storage import deliveries, ledger
    monkeypatch.setattr(ledger, "DATABASE_PATH", tmp_path / "ledger.db")
    monkeypatch.setattr(deliveries, "DATABASE_PATH", tmp_path / "deliveries.db")
