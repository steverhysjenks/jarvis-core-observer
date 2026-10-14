"""LXC acceptance controller: only invoked after approved successful deployment."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
import xml.etree.ElementTree as ET


def controller():
    spec = importlib.util.spec_from_file_location("validated_deployment", Path(__file__).with_name("remote.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def active_release(deployment, sha, expected_files, expected_release=None):
    if not deployment.CURRENT.is_symlink():
        raise RuntimeError("Acceptance requires a successfully deployed managed release")
    release = deployment.CURRENT.resolve(strict=True)
    if release.parent != deployment.RELEASES:
        raise RuntimeError("Unexpected active release location")
    if expected_release is not None and str(release) != expected_release:
        raise RuntimeError("Active release is not the successful deployment instance")
    metadata = json.loads((release / "RELEASE.json").read_text())
    if metadata["commit"] != sha or metadata["files"] != expected_files:
        raise RuntimeError("Active application does not match the tested pipeline commit")
    for name, digest in expected_files.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or hashlib.sha256((release / path).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Active application source integrity failure")
    application = {p.relative_to(release).as_posix() for p in (release / "app").rglob("*.py")}
    if application != {n for n in expected_files if n.startswith("app/") and n.endswith(".py")}:
        raise RuntimeError("Active application module set differs from validated commit")
    return release


def running_release(deployment, release):
    expected = release.stat()
    first = deployment.service_process()
    second = deployment.service_process()
    uid, gid = deployment.runtime_identity()
    for process in (first, second):
        if ((process["uid"], process["gid"]) != (uid, gid)
                or (process["device"], process["inode"]) != (expected.st_dev, expected.st_ino)):
            raise RuntimeError("Running service identity or release directory mismatch")
    if first["pid"] != second["pid"]:
        raise RuntimeError("Service MainPID changed during acceptance inspection")
    return second["pid"]


def unpack(archive, digest, sha, workspace):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise RuntimeError("Test bundle digest mismatch")
    allowed = {"TEST_RELEASE.json", "production_safety.py", "acceptance_policy.py", "pytest.ini", "requirements.txt", "runner.py"}
    with tarfile.open(archive) as bundle:
        entries = bundle.getmembers()
        if len({entry.name for entry in entries}) != len(entries):
            raise RuntimeError("Duplicate acceptance bundle paths")
        for entry in entries:
            relative = Path(entry.name)
            if (not entry.isfile() or relative.is_absolute() or ".." in relative.parts
                    or not (entry.name in allowed or entry.name.startswith("tests/regression/") and entry.name.endswith(".py"))):
                raise RuntimeError("Unsafe acceptance bundle path")
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.extractfile(entry).read())
    manifest = json.loads((workspace / "TEST_RELEASE.json").read_text())
    actual = {p.relative_to(workspace).as_posix() for p in workspace.rglob("*") if p.is_file()}
    if manifest["commit"] != sha or actual != set(manifest["files"]) | {"TEST_RELEASE.json"}:
        raise RuntimeError("Acceptance bundle commit/path mismatch")
    for name, expected in manifest["files"].items():
        if hashlib.sha256((workspace / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Acceptance source hash mismatch")
    return manifest


def failure_report(path, *, preserve=False):
    suite = ET.Element("testsuite", name="production-acceptance", tests="1", failures="1")
    ET.SubElement(ET.SubElement(suite, "testcase", name="acceptance_execution"), "failure").text = (
        "Production acceptance failed before complete safe results were available; inspect through approved operations")
    if preserve and path.is_file():
        try:
            previous = ET.parse(path).getroot()
            root = ET.Element("testsuites")
            root.extend(list(previous) if previous.tag == "testsuites" else [previous])
            root.append(suite)
            suite = root
        except (ET.ParseError, OSError):
            pass
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def collect_report(produced, report, result):
    if not produced.is_file():
        failure_report(report)
        return 1
    parsed = ET.parse(produced)
    shutil.copyfile(produced, report)
    suites = list(parsed.getroot().iter("testsuite"))
    cases = list(parsed.getroot().iter("testcase"))
    invalid = (not suites or not cases
               or sum(int(s.get("tests", "0")) for s in suites) != len(cases)
               or any(int(s.get("failures", "0")) or int(s.get("errors", "0"))
                      or int(s.get("skipped", "0")) for s in suites)
               or any(list(c.iter("failure")) or list(c.iter("error")) or list(c.iter("skipped")) for c in cases))
    if result != 0 or invalid:
        failure_report(report, preserve=True)
        return 1
    return 0


class AcceptanceUnitStillRunning(RuntimeError):
    """Scratch must be retained if the transient unit's termination is uncertain."""


def stop_test_unit(deployment, unit):
    try:
        subprocess.run(["systemctl", "stop", unit], check=False, timeout=30, env=deployment.CLEAN_ENV,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        state = subprocess.run(["systemctl", "show", unit, "--property=LoadState",
                                "--property=ActiveState", "--property=MainPID"],
                               check=False, timeout=10, env=deployment.CLEAN_ENV, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        properties = dict(line.split("=", 1) for line in state.stdout.splitlines() if "=" in line)
        # --collect can remove the finished unit before this probe. Accept a confirmed
        # not-found unit with no process, never an empty/failed inspection response.
        if (properties.get("ActiveState") not in {"inactive", "failed"}
                or properties.get("MainPID") != "0"
                or not (state.returncode == 0 or state.returncode == 1 and properties.get("LoadState") == "not-found")):
            raise RuntimeError("Acceptance unit termination is unverified")
    except Exception as error:
        raise AcceptanceUnitStillRunning("Acceptance unit termination is unverified; scratch retained") from error


def execute(deployment, workspace, release, sha):
    python = workspace / ".venv/bin/python"
    deployment.run("/usr/bin/python3.13", "-m", "venv", str(workspace / ".venv"))
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir",
                    "-r", str(workspace / "requirements.txt")], check=True, timeout=300,
                   env=deployment.CLEAN_ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    runtime_site = deployment.run(str(release / ".venv/bin/python"), "-I", "-B", "-c",
                                  "import sysconfig; print(sysconfig.get_path('purelib'))", capture=True).strip()
    if not Path(runtime_site).resolve().is_relative_to(release / ".venv"):
        raise RuntimeError("Unexpected active runtime dependency path")
    uid, gid = deployment.runtime_identity()
    os.chown(workspace, 0, gid)
    workspace.chmod(0o750)
    # New scratch code/tooling only. Never chmod/chown application or state files.
    for parent, directories, files in os.walk(workspace):
        os.chown(parent, 0, gid)
        os.chmod(parent, (os.stat(parent).st_mode & 0o755) | 0o050)
        for name in files:
            path = Path(parent) / name
            if not path.is_symlink():
                mode = path.stat().st_mode & 0o755
                os.chown(path, 0, gid)
                path.chmod(mode | 0o040 | (0o010 if mode & 0o100 else 0))
    for directory in (workspace / "work", workspace / "results"):
        directory.mkdir()
        os.chown(directory, uid, gid)
        directory.chmod(0o700)
    unit = f"jarvis-acceptance-{uuid.uuid4().hex[:12]}"
    command = ["systemd-run", "--quiet", "--wait", "--pipe", "--collect", f"--unit={unit}",
               "--property=User=jarvis", "--property=Group=jarvis", "--property=NoNewPrivileges=yes",
               "--property=ProtectSystem=strict", "--property=ProtectHome=yes", "--property=PrivateTmp=yes",
               f"--property=ReadWritePaths={workspace / 'work'} {workspace / 'results'}",
               f"--property=EnvironmentFile={deployment.ENVIRONMENT}", "--property=RuntimeMaxSec=600",
               f"--property=WorkingDirectory={workspace}", f"--setenv=HOME={workspace / 'work'}",
               "--setenv=PYTEST_DISABLE_PLUGIN_AUTOLOAD=1", "--setenv=PYTHONDONTWRITEBYTECODE=1",
               str(python), "-I", "-B", str(workspace / "runner.py"), sha, str(release), runtime_site]
    try:
        return subprocess.run(command, check=False, timeout=660, env=deployment.CLEAN_ENV,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    finally:
        # This is the acceptance transient unit, never jarvis-core.service.
        stop_test_unit(deployment, unit)


def main():
    sha, archive_name, digest, expected_release = sys.argv[1:]
    archive = Path(archive_name)
    report = archive.parent / "production.xml"
    failure_report(report)  # Safe fallback exists even if setup/preflight later fails.
    workspace = None
    retain_workspace = False
    try:
        if os.geteuid() != 0 or sys.version_info[:2] != (3, 13) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise RuntimeError("Acceptance requires approved root controller/Python 3.13/commit identity")
        deployment = controller()
        with deployment.host_lock():
            deployment.preflight()
            workspace = Path(tempfile.mkdtemp(prefix="jarvis-acceptance-", dir="/var/tmp"))
            manifest = unpack(archive, digest, sha, workspace)
            release = active_release(deployment, sha, manifest["application_files"], expected_release)
            pid = running_release(deployment, release)
            result = execute(deployment, workspace, release, sha)
            produced = workspace / "results/production.xml"
            result = collect_report(produced, report, result)
            active_release(deployment, sha, manifest["application_files"], expected_release)
            if running_release(deployment, release) != pid:
                raise RuntimeError("Running application restarted during acceptance")
            report.chmod(0o644)  # Sanitized XML readable by ansible for scp.
            return 0 if result == 0 else 1
    except Exception as error:
        # No raw live payloads, config contents, stdout or tracebacks reach GitLab.
        print(f"Production acceptance failed ({type(error).__name__}); sanitized JUnit report available", file=sys.stderr)
        retain_workspace = isinstance(error, AcceptanceUnitStillRunning)
        if retain_workspace and workspace is not None:
            print(f"Acceptance scratch retained for approved inspection: {workspace}", file=sys.stderr)
        if workspace is not None and (workspace / "results/production.xml").is_file():
            try:
                collect_report(workspace / "results/production.xml", report, 1)
            except (ET.ParseError, OSError, ValueError):
                pass
        failure_report(report, preserve=True)
        report.chmod(0o644)
        return 1
    finally:
        if workspace is not None and not retain_workspace:
            # Only this freshly created fixed-prefix acceptance scratch directory.
            if workspace.parent == Path("/var/tmp") and workspace.name.startswith("jarvis-acceptance-"):
                try:
                    shutil.rmtree(workspace)
                except OSError:
                    failure_report(report, preserve=True)
                    report.chmod(0o644)
                    print("Acceptance scratch cleanup failed; operator cleanup required", file=sys.stderr)
                    return 1


if __name__ == "__main__":
    raise SystemExit(main())
