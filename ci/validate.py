"""Static repository checks: no application imports, execution, or bytecode writes."""
import argparse
import ast
import configparser
import hashlib
import json
import re
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
        "ci/package_release.py", "ci/deploy.py", "deployment/remote.py",
        "deployment/readiness.py", "deployment/health.py", "docs/cd.md",
        "ci/deployment_policy.py", "ci/test_deployment.py",
        "deployment/acceptance.py", "tests/production/run.py", "tests/production/policy.py",
        "tests/production/safety_plugin.py", "tests/production/pytest.ini", "tests/production/requirements.txt",
    )
    for name in required:
        if not (ROOT / name).is_file():
            raise ValueError(f"Missing required repository file: {name}")
    paths = list((ROOT / "app").rglob("*.py")) + list((ROOT / "tests").rglob("*.py"))
    paths += list(ROOT.glob("test_*.py")) + [ROOT / "conftest.py"] + list((ROOT / "ci").glob("*.py")) + list((ROOT / "deployment").glob("*.py"))
    for path in paths:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    manifest = json.loads((ROOT / "docs/production-baseline-hashes.json").read_text())
    expected = {row["path"]: row["production_sha256"] for row in manifest["files"]}
    actual = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in (ROOT / "app").rglob("*.py")
    }
    if len(expected) != 67 or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in expected.values()):
        raise ValueError("Historical baseline evidence is malformed")
    # Historical evidence only: approved changes/additions/deletions are allowed.
    changed = sorted(name for name in actual.keys() & expected.keys() if actual[name] != expected[name])
    added, removed = sorted(actual.keys() - expected.keys()), sorted(expected.keys() - actual.keys())
    print(f"Historical baseline delta (informational): {len(changed)} changed, {len(added)} added, {len(removed)} removed")
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
        from deployment_policy import PACKAGE_RULE, RULES
        pipeline = yaml.safe_load((ROOT / ".gitlab-ci.yml").read_text())
        if pipeline["stages"] != ["validate", "test", "package", "deploy", "acceptance"]:
            raise ValueError("Unexpected CI/CD stage sequence")
        if pipeline["default"]["image"] != "python:3.13-slim" or pipeline["default"]["tags"] != ["docker"]:
            raise ValueError("Expected Python 3.13 image and docker runner tag")
        if set(pipeline) != {"stages", "variables", "default", "validate", "regression", "package_release", ".cd",
                             "production_preflight", "bootstrap_production", "deploy_production", "production_acceptance"}:
            raise ValueError("Unexpected pipeline job/configuration")
        if pipeline["variables"] != {"JARVIS_OPERATION": "deploy"}:
            raise ValueError("Only the non-secret deployment operation default belongs in YAML")
        package = pipeline["package_release"]
        if set(package["needs"]) != {"validate", "regression"} or package["rules"] != [{"if": PACKAGE_RULE}, {"when": "never"}]:
            raise ValueError("Only a validated protected-main commit can be packaged")
        cd = pipeline[".cd"]
        prerequisites = {n if isinstance(n, str) else n["job"] for n in cd["needs"]}
        if prerequisites != {"package_release", "validate", "regression"}:
            raise ValueError("CD must depend on validation, regression and exact-commit artifacts")
        if cd["resource_group"] != "jarvis-core-lxc122" or cd["interruptible"] is not False or cd["allow_failure"] is not False:
            raise ValueError("Serialized, noninterruptible, blocking manual CD is required")
        if cd["environment"]["name"] != "production" or cd["environment"]["deployment_tier"] != "production":
            raise ValueError("CD credentials/approvals must use the production environment")
        for name in ("production_preflight", "bootstrap_production", "deploy_production"):
            job = pipeline[name]
            if job["extends"] != ".cd" or job["rules"] != [{"if": RULES[name], "when": "manual"}, {"when": "never"}]:
                raise ValueError(f"Unsafe production approval/branch rules: {name}")
        if any("environment" in pipeline[name] for name in ("validate", "regression", "package_release")):
            raise ValueError("CI jobs must not receive production-environment-scoped credentials")
        acceptance = pipeline["production_acceptance"]
        if (acceptance["extends"] != ".cd" or acceptance["stage"] != "acceptance"
                or acceptance["rules"] != [{"if": RULES["deploy_production"], "when": "on_success"}, {"when": "never"}]
                or acceptance["environment"]["name"] != "production"
                or acceptance["script"] != ["python -B ci/deploy.py acceptance"]):
            raise ValueError("Unsafe post-deployment production acceptance rules")
        if {n["job"] for n in acceptance["needs"]} != {"deploy_production", "package_release", "validate", "regression"}:
            raise ValueError("Acceptance must follow successful validated deployment")
        if not next(n["artifacts"] for n in acceptance["needs"] if n["job"] == "deploy_production"):
            raise ValueError("Acceptance must retrieve successful deployment evidence")
        if pipeline["deploy_production"].get("artifacts") != {
                "when": "on_success", "expire_in": "7 days", "paths": ["results/deployment.json"]}:
            raise ValueError("Deployment must publish its successful release receipt")
        if acceptance["artifacts"]["when"] != "always" or acceptance["artifacts"]["reports"]["junit"] != "results/production.xml":
            raise ValueError("Production JUnit must be returned even on failure")
        reports = pipeline["regression"]["artifacts"]
        if reports["when"] != "always" or reports["reports"]["junit"] != "results/*.xml":
            raise ValueError("Always-upload JUnit reporting is required")
    print(f"Validated syntax/configuration for {len(paths)} Python files and {len(approved)} approved test modules; {len(actual)} current application hashes recorded")
    if not ci:
        print("Local static checks only; Python 3.13 and YAML parsing are checked by CI")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci", action="store_true")
    validate(parser.parse_args().ci)
