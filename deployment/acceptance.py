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


class Diagnostics:
    """Only fixed labels and numeric codes; never exception text or command output."""
    def __init__(self):
        self.operation = "controller-initialization"
        self.failure = None
        self.failure_error = None
        self.secondary_failure = None
        self.tests_started = False
        self.pytest_started = False
        self.junit_produced = False
        self.runner_operation = "not-started"
        self.runner_exception = "None"

    def step(self, operation, function, *args, **kwargs):
        self.operation = operation
        try:
            return function(*args, **kwargs)
        except Exception as error:
            self.record(error)
            raise

    def record(self, error):
        if error is self.failure_error:
            return
        code = error.returncode if isinstance(error, subprocess.CalledProcessError) else None
        if isinstance(error, subprocess.CalledProcessError):
            kind = "subprocess-nonzero-exit"
        elif isinstance(error, subprocess.TimeoutExpired):
            kind = "operation-timeout"
        elif isinstance(error, FileNotFoundError):
            kind = "required-file-or-executable-missing"
        elif isinstance(error, PermissionError):
            kind = "permission-denied"
        elif isinstance(error, RuntimeError):
            kind = "identity-or-safety-check"
        else:
            kind = "operation-error"
        name = type(error).__name__
        if name not in {"CalledProcessError", "TimeoutExpired", "FileNotFoundError", "PermissionError",
                        "RuntimeError", "AcceptanceUnitStillRunning", "ValueError", "ParseError", "OSError"}:
            name = "Exception"
        failure = {"operation": self.operation, "exception": name, "exit_code": code, "classification": kind}
        if self.failure is None:
            self.failure = failure
            self.failure_error = error
        elif failure != self.failure:
            self.secondary_failure = failure

    def runner_status(self, workspace):
        if workspace is None:
            return
        self.junit_produced = (workspace / "results/production.xml").is_file()
        try:
            value = json.loads((workspace / "results/runner-status.json").read_text())
            if not isinstance(value, dict):
                return
            for field in ("tests_started", "pytest_started"):
                if isinstance(value.get(field), bool):
                    setattr(self, field, value[field])
            if value.get("operation") in {"runner-initialization", "runtime-verification", "pytest-import", "pytest-execution"}:
                self.runner_operation = value["operation"]
            if value.get("exception") in {"RuntimeError", "ImportError", "ModuleNotFoundError", "OSError", "PermissionError", "Exception"}:
                self.runner_exception = value["exception"]
        except (OSError, ValueError, TypeError):
            pass

    def message(self):
        value = self.failure or {"operation": self.operation, "exception": "None", "exit_code": None,
                                 "classification": "regression-results-rejected"}
        return json.dumps(value | {"tests_started": self.tests_started, "pytest_started": self.pytest_started,
                                  "junit_produced": self.junit_produced, "runner_operation": self.runner_operation,
                                  "runner_exception": self.runner_exception,
                                  "secondary_failure": self.secondary_failure}, sort_keys=True)


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


def failure_report(path, *, preserve=False, diagnostic=None):
    suite = ET.Element("testsuite", name="production-acceptance", tests="1", failures="1")
    ET.SubElement(ET.SubElement(suite, "testcase", name="acceptance_execution"), "failure").text = (
        diagnostic or "Production acceptance failed before complete safe results were available; inspect through approved operations")
    if preserve and path.is_file():
        try:
            previous = ET.parse(path).getroot()
            # Replace our existing fallback's message rather than duplicating its
            # testcase ID: GitLab can keep only the first duplicate testcase.
            for existing in previous.iter("testsuite"):
                if existing.get("name") == "production-acceptance":
                    for case in existing.findall("testcase"):
                        failure = case.find("failure")
                        if case.get("name") == "acceptance_execution" and failure is not None:
                            if diagnostic is not None:
                                failure.text = diagnostic
                            ET.ElementTree(previous).write(path, encoding="utf-8", xml_declaration=True)
                            return
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


def execute(deployment, workspace, release, sha, diagnostics=None):
    diagnostics = diagnostics or Diagnostics()
    python = workspace / ".venv/bin/python"
    diagnostics.step("test-venv-creation", subprocess.run,
                     ["/usr/bin/python3.13", "-m", "venv", str(workspace / ".venv")],
                     check=True, timeout=120, env=deployment.CLEAN_ENV,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    diagnostics.step("test-dependency-installation", subprocess.run,
                   [str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir",
                    "-r", str(workspace / "requirements.txt")], check=True, timeout=300,
                   env=deployment.CLEAN_ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    runtime_site = diagnostics.step("active-runtime-inspection", subprocess.run,
                                  [str(release / ".venv/bin/python"), "-I", "-B", "-c",
                                   "import sysconfig; print(sysconfig.get_path('purelib'))"],
                                  check=True, timeout=120, env=deployment.CLEAN_ENV, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.strip()
    if not Path(runtime_site).resolve().is_relative_to(release / ".venv"):
        raise RuntimeError("Unexpected active runtime dependency path")
    diagnostics.operation = "scratch-permission-setup"
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
        diagnostics.tests_started = diagnostics.pytest_started = None  # Unknown until the runner's marker is read.
        result = diagnostics.step("transient-unit-execution", subprocess.run,
                                  command, check=False, timeout=660, env=deployment.CLEAN_ENV,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode:
            diagnostics.record(subprocess.CalledProcessError(result.returncode, "<withheld>"))
        return result.returncode
    finally:
        # This is the acceptance transient unit, never jarvis-core.service.
        diagnostics.step("transient-unit-cleanup", stop_test_unit, deployment, unit)


def main():
    sha, archive_name, digest, expected_release = sys.argv[1:]
    archive = Path(archive_name)
    report = archive.parent / "production.xml"
    failure_report(report)  # Safe fallback exists even if setup/preflight later fails.
    workspace = None
    retain_workspace = False
    diagnostics = Diagnostics()
    try:
        if os.geteuid() != 0 or sys.version_info[:2] != (3, 13) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise RuntimeError("Acceptance requires approved root controller/Python 3.13/commit identity")
        deployment = diagnostics.step("deployment-controller-import", controller)
        diagnostics.operation = "host-lock"
        with deployment.host_lock():
            diagnostics.step("read-only-preflight", deployment.preflight)
            diagnostics.operation = "scratch-creation"
            workspace = Path(tempfile.mkdtemp(prefix="jarvis-acceptance-", dir="/var/tmp"))
            manifest = diagnostics.step("test-bundle-verification", unpack, archive, digest, sha, workspace)
            release = diagnostics.step("active-release-verification", active_release, deployment, sha, manifest["application_files"], expected_release)
            pid = diagnostics.step("running-service-verification", running_release, deployment, release)
            result = execute(deployment, workspace, release, sha, diagnostics)
            diagnostics.runner_status(workspace)
            produced = workspace / "results/production.xml"
            result = diagnostics.step("junit-result-validation", collect_report, produced, report, result)
            if result and diagnostics.failure is None:
                diagnostics.failure = {"operation": "junit-result-validation", "exception": "None", "exit_code": None,
                                       "classification": "regression-results-rejected"}
            diagnostics.step("final-release-verification", active_release, deployment, sha, manifest["application_files"], expected_release)
            diagnostics.operation = "final-service-verification"
            if running_release(deployment, release) != pid:
                raise RuntimeError("Running application restarted during acceptance")
            report.chmod(0o644)  # Sanitized XML readable by ansible for scp.
            if result:
                failure_report(report, preserve=True, diagnostic=diagnostics.message())
                print("Production acceptance diagnostics: " + diagnostics.message(), file=sys.stderr)
            return 0 if result == 0 else 1
    except Exception as error:
        # No raw live payloads, config contents, stdout or tracebacks reach GitLab.
        diagnostics.record(error)
        diagnostics.runner_status(workspace)
        print("Production acceptance diagnostics: " + diagnostics.message(), file=sys.stderr)
        retain_workspace = isinstance(error, AcceptanceUnitStillRunning)
        if retain_workspace and workspace is not None:
            print(f"Acceptance scratch retained for approved inspection: {workspace}", file=sys.stderr)
        if workspace is not None and (workspace / "results/production.xml").is_file():
            try:
                collect_report(workspace / "results/production.xml", report, 1)
            except (ET.ParseError, OSError, ValueError):
                pass
        failure_report(report, preserve=True, diagnostic=diagnostics.message())
        report.chmod(0o644)
        return 1
    finally:
        if workspace is not None and not retain_workspace:
            # Only this freshly created fixed-prefix acceptance scratch directory.
            if workspace.parent == Path("/var/tmp") and workspace.name.startswith("jarvis-acceptance-"):
                try:
                    shutil.rmtree(workspace)
                except OSError as error:
                    diagnostics.operation = "scratch-cleanup"
                    diagnostics.record(error)
                    failure_report(report, preserve=True, diagnostic=diagnostics.message())
                    report.chmod(0o644)
                    print("Production acceptance cleanup diagnostics: " + diagnostics.message(), file=sys.stderr)
                    return 1


if __name__ == "__main__":
    raise SystemExit(main())
