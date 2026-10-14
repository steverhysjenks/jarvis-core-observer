"""Explicit LXC-only pytest entrypoint; never invoked by offline CI."""
import json
import os
from pathlib import Path
import sys

STATUS = {"operation": "runner-initialization", "tests_started": False, "pytest_started": False}


def write_status():
    # Fixed labels only: no config, exception messages, node IDs or live payloads.
    path = Path(__file__).resolve().parent / "results/runner-status.json"
    path.write_text(json.dumps(STATUS, sort_keys=True))


def main():
    write_status()
    root = Path(__file__).resolve().parent
    commit, release, runtime_site = sys.argv[1:]
    import pwd
    STATUS["operation"] = "runtime-verification"
    write_status()
    if os.geteuid() != pwd.getpwnam("jarvis").pw_uid or sys.version_info[:2] != (3, 13):
        raise RuntimeError("Acceptance requires jarvis and Python 3.13")
    manifest = json.loads((root / "TEST_RELEASE.json").read_text())
    if manifest["commit"] != commit or json.loads((Path(release) / "RELEASE.json").read_text())["commit"] != commit:
        raise RuntimeError("Acceptance/application commit mismatch")
    for name in ("PYTEST_ADDOPTS", "PYTHONPATH", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(name, None)
    os.environ.update({"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1",
                       "JARVIS_ACCEPTANCE_COMMIT": commit, "JARVIS_ACCEPTANCE_RELEASE": release})
    # Test tooling first; application dependencies come from its actual active venv.
    sys.path.append(runtime_site)
    sys.path.insert(0, release)
    sys.path.insert(0, str(root))
    STATUS["operation"] = "pytest-import"
    write_status()
    import pytest
    STATUS.update(operation="pytest-execution", pytest_started=True)
    write_status()
    return pytest.main([str(root / "tests/regression"), "-c", str(root / "pytest.ini"),
                        "--confcutdir", str(root), "-p", "pytest_asyncio.plugin", "-p", "production_safety",
                        "--junitxml", str(root / "results/production.xml")])


def entrypoint():
    try:
        return main()
    except Exception as error:
        # Controller reads the last safe stage marker; raw tracebacks never escape.
        name = type(error).__name__
        STATUS["exception"] = name if name in {"RuntimeError", "ImportError", "ModuleNotFoundError", "OSError", "PermissionError"} else "Exception"
        try:
            write_status()
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(entrypoint())
