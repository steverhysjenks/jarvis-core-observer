"""Static repository checks: no application imports, execution, or bytecode writes."""
import argparse
import ast
import configparser
import hashlib
import json
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]


def validate(ci=False):
    required = (
        ".gitlab-ci.yml", "requirements.txt", "requirements-test.txt", "pytest.ini",
        "conftest.py", "README.md", "config/jarvis.env.example",
        "deployment/systemd/jarvis-core.service", "docs/production-baseline.md",
        "docs/production-baseline-hashes.json", "ci/run_offline.py",
        "tests/regression/test_isolation_guards.py",
    )
    for name in required:
        if not (ROOT / name).is_file():
            raise ValueError(f"Missing required repository file: {name}")
    paths = list((ROOT / "app").rglob("*.py")) + list((ROOT / "tests").rglob("*.py"))
    paths += list(ROOT.glob("test_*.py")) + [ROOT / "conftest.py"] + list((ROOT / "ci").glob("*.py"))
    for path in paths:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    manifest = json.loads((ROOT / "docs/production-baseline-hashes.json").read_text())
    expected = {row["path"]: row["production_sha256"] for row in manifest["files"]}
    actual = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in (ROOT / "app").rglob("*.py")
    }
    if len(expected) != 67 or actual != expected:
        raise ValueError("Application source differs from the adopted 67-file production baseline")
    if list((ROOT / "tests").rglob("conftest.py")):
        raise ValueError("Unreviewed nested pytest configuration is blocked")
    tree = ast.parse((ROOT / "conftest.py").read_text())
    top_calls = [n.value for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]
    if not any(isinstance(n.func, ast.Attribute) and n.func.attr == "addaudithook" for n in top_calls):
        raise ValueError("The isolation audit hook must be installed before collection")
    if not any(isinstance(n.func, ast.Name) and n.func.id == "verify_isolation" for n in top_calls):
        raise ValueError("The installed safety hooks must be checked before collection")
    approved = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "SAFE_MODULES" for t in n.targets))
    if "test_isolation_guards.py" not in approved:
        raise ValueError("Safety tests must be approved")
    for name in approved:
        path = ROOT / "tests" / "regression" / name
        if not path.is_file():
            raise ValueError(f"Missing approved test module: {name}")
        module = ast.parse(path.read_text())
        if any(isinstance(n, ast.Attribute) and n.attr in {"live", "behavioural"} for n in ast.walk(module)):
            raise ValueError(f"Live/behavioural test cannot be approved: {name}")
    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    needed = {"isolation_audit", "verify_isolation", "safe_module", "pytest_configure",
              "pytest_ignore_collect", "pytest_collection_modifyitems", "isolated_storage"}
    if not needed <= functions:
        raise ValueError("Required safety hooks are missing")
    config = configparser.ConfigParser(interpolation=None)
    config.read(ROOT / "pytest.ini")
    options = shlex.split(config["pytest"]["addopts"])
    if config["pytest"]["testpaths"].strip() != "tests/regression":
        raise ValueError("Default test collection must be the reviewed regression directory")
    if "--strict-markers" not in options or "not live and not behavioural" not in options:
        raise ValueError("Strict markers and unsafe-marker exclusion are required")
    if ci:
        if sys.version_info[:2] != (3, 13):
            raise ValueError("CI must use Python 3.13")
        import yaml
        pipeline = yaml.safe_load((ROOT / ".gitlab-ci.yml").read_text())
        if pipeline["stages"] != ["validate", "test"]:
            raise ValueError("Only validation and testing stages are permitted")
        if pipeline["default"]["image"] != "python:3.13-slim" or pipeline["default"]["tags"] != ["docker"]:
            raise ValueError("Expected Python 3.13 image and docker runner tag")
        if set(pipeline) != {"stages", "default", "validate", "regression"}:
            raise ValueError("Unexpected pipeline job/configuration")
        reports = pipeline["regression"]["artifacts"]
        if reports["when"] != "always" or reports["reports"]["junit"] != "results/*.xml":
            raise ValueError("Always-upload JUnit reporting is required")
    print(f"Validated {len(paths)} Python files, {len(actual)} application hashes and {len(approved)} approved test modules")
    if not ci:
        print("Local static checks only; Python 3.13 and YAML parsing are checked by CI")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci", action="store_true")
    validate(parser.parse_args().ci)