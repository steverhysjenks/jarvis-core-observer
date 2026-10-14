"""Explicit LXC-only pytest entrypoint; never invoked by offline CI."""
import json
import os
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent
    commit, release, runtime_site = sys.argv[1:]
    import pwd
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
    import pytest
    return pytest.main([str(root / "tests/regression"), "-c", str(root / "pytest.ini"),
                        "--confcutdir", str(root), "-p", "pytest_asyncio.plugin", "-p", "production_safety",
                        "--junitxml", str(root / "results/production.xml")])


if __name__ == "__main__":
    raise SystemExit(main())