"""Create a minimal release from Git objects at the validated pipeline SHA."""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def validated_sha():
    sha = os.environ.get("CI_COMMIT_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("A full GitLab pipeline commit SHA is required")
    if os.environ.get("CI_COMMIT_BRANCH") != "main" or os.environ.get("CI_COMMIT_REF_PROTECTED") != "true":
        raise RuntimeError("Release operations require protected main")
    if os.environ.get("CI_PIPELINE_SOURCE") not in {"push", "web"}:
        raise RuntimeError("Only protected-main push/web pipelines are accepted")
    if git("rev-parse", "HEAD").decode().strip() != sha:
        raise RuntimeError("Checkout is not the validated pipeline commit")
    if git("diff", "HEAD", "--") or git("diff", "--cached", "--"):
        raise RuntimeError("Tracked working-tree/index changes are forbidden")
    if git("ls-files", "--others", "--exclude-standard", "--", "app", "tests", "ci", "deployment"):
        raise RuntimeError("Untracked source/test/deployment files are forbidden in release jobs")
    return sha


def release_files(sha):
    paths = git("ls-tree", "-r", "--name-only", sha, "app").decode().splitlines()
    paths = [name for name in paths if name.endswith(".py")]
    paths += ["requirements.txt", "deployment/readiness.py", "deployment/health.py"]
    return {name: git("show", f"{sha}:{name}") for name in sorted(paths)}


def test_files(sha):
    paths = git("ls-tree", "-r", "--name-only", sha, "tests/regression").decode().splitlines()
    files = {name: git("show", f"{sha}:{name}") for name in paths if name.endswith(".py")}
    mappings = {"production_safety.py": "tests/production/safety_plugin.py",
                "acceptance_policy.py": "tests/production/policy.py",
                "pytest.ini": "tests/production/pytest.ini", "requirements.txt": "tests/production/requirements.txt",
                "runner.py": "tests/production/run.py",
                "tests/regression/test_production_integrations.py": "tests/production/test_integrations.py"}
    files.update({target: git("show", f"{sha}:{source}") for target, source in mappings.items()})
    return files


def write_test_bundle(output, sha):
    files = test_files(sha)
    manifest = {"commit": sha, "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
                "application_files": {name: hashlib.sha256(data).hexdigest() for name, data in release_files(sha).items()}}
    files["TEST_RELEASE.json"] = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    archive = output / "tests.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for name, data in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode = len(data), 0o644
            bundle.addfile(entry, io.BytesIO(data))
    controller = git("show", f"{sha}:deployment/acceptance.py")
    (output / "acceptance.py").write_bytes(controller)
    return {"tests_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "acceptance_controller_sha256": hashlib.sha256(controller).hexdigest()}


def main():
    sha = validated_sha()
    files = release_files(sha)
    tree = ast.parse(files["app/main.py"].decode())
    versions = [ast.literal_eval(k.value) for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == "FastAPI"
                for k in n.keywords if k.arg == "version"]
    if len(versions) != 1 or not isinstance(versions[0], str):
        raise RuntimeError("Cannot establish the release application version")
    metadata = {"commit": sha, "application_version": versions[0],
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files["RELEASE.json"] = (json.dumps(metadata, sort_keys=True) + "\n").encode()
    output = ROOT / "release-artifacts"
    output.mkdir(exist_ok=True)
    archive = output / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for name, data in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode = len(data), 0o644
            bundle.addfile(entry, io.BytesIO(data))
    controller = git("show", f"{sha}:deployment/remote.py")
    (output / "remote.py").write_bytes(controller)
    identity = {"commit": sha, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "controller_sha256": hashlib.sha256(controller).hexdigest()}
    identity.update(write_test_bundle(output, sha))
    (output / "identity.json").write_text(json.dumps(identity, sort_keys=True) + "\n")
    print(f"Packaged exact validated commit {sha}; no working-tree files included")


if __name__ == "__main__":
    main()