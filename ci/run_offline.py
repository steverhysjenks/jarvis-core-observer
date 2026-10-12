"""Run reviewed pytest tests in child processes without inherited CI/service secrets.

This sanitises Python test processes. It does NOT disable the container network.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError("Offline CI regression requires Python 3.13")
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jarvis-ci-") as temporary:
        # Allowlist rather than removing a few known secrets from os.environ.
        # No GitLab project/group/job variables, proxy settings or service tokens pass through.
        environment = {
            "PATH": os.defpath,
            "HOME": temporary,
            "TMPDIR": temporary,
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
        common = [sys.executable, "-I", "-B", "-m", "pytest", "-c", str(ROOT / "pytest.ini"),
                  "--confcutdir", str(ROOT), "-p", "pytest_asyncio.plugin"]
        # Guard failures stop execution before the wider regression suite starts.
        guard = subprocess.run(
            common + ["tests/regression/test_isolation_guards.py", "--junitxml", str(results / "guards.xml")],
            cwd=ROOT, env=environment, check=False,
        )
        if guard.returncode:
            return guard.returncode
        environment["JARVIS_CI_FULL_SUITE"] = "1"
        suite = subprocess.run(
            common + ["tests/regression", "--junitxml", str(results / "regression.xml")],
            cwd=ROOT, env=environment, check=False,
        )
        return suite.returncode


if __name__ == "__main__":
    raise SystemExit(main())