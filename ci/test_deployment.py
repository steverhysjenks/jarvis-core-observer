"""Standard-library CD unit tests: temp files and mocked commands only.

No application imports, network, subprocess execution, production reads/writes,
real systemd, sudo, SSH or SQLite connections are permitted by this runner.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


remote = load("cd_remote_tests", ROOT / "deployment/remote.py")
health = load("cd_health_tests", ROOT / "deployment/health.py")
readiness = load("cd_readiness_tests", ROOT / "deployment/readiness.py")
import deploy as transport
import package_release as package
import deployment_policy as policy


class SafeTemporaryDirectory:
    """Clean using absolute paths so audit checks work on Linux dir-fd platforms too."""
    def __init__(self, **arguments):
        self.name = tempfile.mkdtemp(**arguments)

    def cleanup(self):
        directory = Path(self.name).resolve()
        if not directory.is_relative_to(SAFE_ROOT):
            raise RuntimeError("Refusing cleanup outside the unit-test temporary root")
        for parent, directories, files in os.walk(directory, topdown=False, followlinks=False):
            for name in files:
                (Path(parent) / name).unlink()
            for name in directories:
                path = Path(parent) / name
                path.unlink() if path.is_symlink() else path.rmdir()
        directory.rmdir()

    def __enter__(self):
        return self.name

    def __exit__(self, *exception):
        self.cleanup()


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.scratch = SafeTemporaryDirectory(dir=SAFE_ROOT)
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name)
        self.current_path = self.base / "current"
        self.current_path.mkdir()
        (self.current_path / "original.py").write_text("original baseline")
        self.store = self.base / "releases"
        self.store.mkdir()
        self.previous = self.store / "old"
        self.previous.mkdir()
        (self.previous / "original.py").write_text("old release")
        self.candidate = self.store / "new"
        self.candidate.mkdir()
        (self.candidate / "main.py").write_text("new release")
        self.env = self.base / "config" / "jarvis.env"
        self.env.parent.mkdir()
        self.env.write_bytes(b"private-placeholder\n")
        self.state = self.base / "state"
        self.state.mkdir()
        (self.state / "jarvis.db").write_bytes(b"sqlite-state-sentinel")
        (self.state / "unrelated.bin").write_bytes(b"preserve-all-state")
        self.current = MagicMock(spec=Path)
        self.current.__fspath__.return_value = str(self.current_path)
        self.current.is_symlink.return_value = True
        self.current.resolve.return_value = self.previous
        self.current.stat.side_effect = self.current_path.stat
        self.current.exists.side_effect = lambda: self.current_path.exists() or self.current.is_symlink()
        self.current.unlink.side_effect = lambda: setattr(self.current.is_symlink, "return_value", False)
        self.commands = Mock()
        self.preflight = Mock(return_value=("0.7.0", "live"))
        self.prepare = Mock()
        self.checker = Mock()
        self.verify = Mock()
        self.activation = Mock(side_effect=self.activate)
        fixtures = {
            "CURRENT": self.current, "RELEASES": self.store, "ENVIRONMENT": self.env, "STATE": self.state,
            "run": self.commands, "preflight": self.preflight, "prepare": self.prepare,
            "health_module": Mock(return_value=self.checker), "verify": self.verify,
            "extract": Mock(return_value=(self.candidate, {"application_version": "0.7.1"})),
            "switch": self.activation,
        }
        context = patch.multiple(remote, **fixtures)
        context.start()
        self.addCleanup(context.stop)
        self.original_state = {str(p.relative_to(self.base)): p.read_bytes() for p in [self.env, *self.state.iterdir()]}
        self.addCleanup(self.assert_preserved_state)

    def assert_preserved_state(self):
        for name, content in self.original_state.items():
            self.assertEqual((self.base / name).read_bytes(), content)

    def activate(self, target):
        self.current.is_symlink.return_value = True
        self.current.resolve.return_value = target

    def bootstrap_layout(self):
        self.current.is_symlink.return_value = False
        self.current.resolve.return_value = self.current_path

    def test_release_success_stops_switches_restarts_and_verifies(self):
        events = []
        self.commands.side_effect = lambda *args, **kwargs: events.append(args[1])
        self.activation.side_effect = lambda target: (events.append("switch"), self.activate(target))
        self.verify.side_effect = lambda *args: events.append("verify")
        remote.deploy("a" * 40, self.base / "unused", "unused")
        self.assertEqual(events, ["stop", "switch", "restart", "verify"])
        self.verify.assert_called_once_with(self.checker, "0.7.1", "live")
        self.assertEqual(self.current.resolve(), self.candidate)
        self.assertTrue(self.previous.is_dir())

    def test_release_refuses_real_directory_before_preparation(self):
        self.bootstrap_layout()
        with self.assertRaisesRegex(RuntimeError, "separate approved bootstrap"):
            remote.deploy("a" * 40, self.base / "unused", "unused")
        self.commands.assert_not_called()
        self.prepare.assert_not_called()

    def test_preparation_failure_never_stops_or_switches(self):
        self.prepare.side_effect = RuntimeError("preparation failed")
        with self.assertRaisesRegex(RuntimeError, "preparation failed"):
            remote.deploy("a" * 40, self.base / "unused", "unused")
        self.commands.assert_not_called()
        self.activation.assert_not_called()

    def test_health_failure_restores_previous_release_and_stays_failed(self):
        self.verify.side_effect = [RuntimeError("new health failed"), None]
        with self.assertRaisesRegex(RuntimeError, "new health failed"):
            remote.deploy("a" * 40, self.base / "unused", "unused")
        self.assertEqual(self.current.resolve(), self.previous)
        self.assertEqual([call.args[1] for call in self.commands.call_args_list], ["stop", "restart", "stop", "restart"])
        self.assertEqual(self.verify.call_args.args, (self.checker, "0.7.0", "live"))
        self.assertTrue(self.candidate.is_dir())

    def test_restart_failure_restores_and_verifies_previous(self):
        starts = 0
        def commands(*args, **kwargs):
            nonlocal starts
            if args[1] == "restart":
                starts += 1
                if starts == 1:
                    raise RuntimeError("restart failed")
        self.commands.side_effect = commands
        with self.assertRaisesRegex(RuntimeError, "restart failed"):
            remote.deploy("a" * 40, self.base / "unused", "unused")
        self.assertEqual(self.current.resolve(), self.previous)
        self.verify.assert_called_once_with(self.checker, "0.7.0", "live")

    def test_failed_rollback_reports_critical(self):
        self.verify.side_effect = RuntimeError("health failed")
        with self.assertRaisesRegex(RuntimeError, "CRITICAL"):
            remote.deploy("a" * 40, self.base / "unused", "unused")
        self.assertEqual(self.current.resolve(), self.previous)

    def test_bootstrap_requires_explicit_phrase(self):
        with self.assertRaisesRegex(RuntimeError, "approval phrase"):
            remote.bootstrap("a" * 40, self.base / "unused", "unused", "wrong")
        self.preflight.assert_not_called()
        self.commands.assert_not_called()

    def test_bootstrap_refuses_existing_symlink(self):
        with self.assertRaisesRegex(RuntimeError, "Already bootstrapped"):
            remote.bootstrap("a" * 40, self.base / "unused", "unused", remote.APPROVAL)
        self.commands.assert_not_called()

    def test_bootstrap_preserves_original_directory_contents(self):
        self.bootstrap_layout()
        remote.bootstrap("a" * 40, self.base / "unused", "unused", remote.APPROVAL)
        self.assertFalse(self.current_path.exists())
        self.assertTrue(self.current.is_symlink())
        self.assertEqual((self.current.resolve() / "original.py").read_text(), "original baseline")
        self.prepare.assert_not_called()
        self.verify.assert_called_once_with(self.checker, "0.7.0", "live")

    def test_bootstrap_health_failure_restores_real_directory(self):
        self.bootstrap_layout()
        self.verify.side_effect = [RuntimeError("bootstrap health failed"), None]
        with self.assertRaisesRegex(RuntimeError, "bootstrap health failed"):
            remote.bootstrap("a" * 40, self.base / "unused", "unused", remote.APPROVAL)
        self.assertFalse(self.current.is_symlink())
        self.assertEqual((self.current_path / "original.py").read_text(), "original baseline")

    def test_bootstrap_interruption_after_rename_restores_original(self):
        self.bootstrap_layout()
        actual_rename = os.rename
        calls = 0
        def interrupted_rename(source, target):
            nonlocal calls
            calls += 1
            actual_rename(source, target)
            if calls == 1:
                raise RuntimeError("interrupted after atomic rename")
        with patch.object(remote.os, "rename", side_effect=interrupted_rename):
            with self.assertRaisesRegex(RuntimeError, "interrupted after atomic rename"):
                remote.bootstrap("a" * 40, self.base / "unused", "unused", remote.APPROVAL)
        self.assertEqual((self.current_path / "original.py").read_text(), "original baseline")
        self.assertEqual(calls, 2)

    def test_bootstrap_recovery_never_overwrites_unexpected_directory(self):
        self.bootstrap_layout()
        def interference(target):
            self.current_path.mkdir()
            (self.current_path / "unexpected.txt").write_text("do not overwrite")
            raise RuntimeError("unexpected interference")
        self.activation.side_effect = interference
        with self.assertRaisesRegex(RuntimeError, "CRITICAL"):
            remote.bootstrap("a" * 40, self.base / "unused", "unused", remote.APPROVAL)
        self.assertEqual((self.current_path / "unexpected.txt").read_text(), "do not overwrite")
        self.assertTrue(any((p / "original.py").exists() for p in self.store.glob("bootstrap-*")))

    def test_switch_rejects_targets_outside_store_or_symlink_targets(self):
        actual_switch = ORIGINAL_SWITCH
        with self.assertRaisesRegex(RuntimeError, "Unsafe"):
            actual_switch(self.current_path)
        target = Mock(spec=Path)
        target.is_symlink.return_value = True
        with self.assertRaisesRegex(RuntimeError, "Unsafe"):
            actual_switch(target)
        self.commands.assert_not_called()

    def test_switch_uses_atomic_replace(self):
        temporary = MagicMock(spec=Path)
        temporary.is_symlink.return_value = False
        self.current.with_name.return_value = temporary
        with patch.object(remote.os, "replace") as replace:
            ORIGINAL_SWITCH(self.candidate)
            temporary.symlink_to.assert_called_once_with(self.candidate)
            replace.assert_called_once_with(temporary, self.current)

    def test_atomic_switch_with_real_temporary_symlinks(self):
        current = self.base / "active"
        try:
            current.symlink_to(self.previous, target_is_directory=True)
        except OSError as error:
            if getattr(error, "winerror", None) == 1314:
                self.skipTest("Windows user lacks symlink privilege; Linux CI runs this check")
            raise
        with patch.object(remote, "CURRENT", current):
            ORIGINAL_SWITCH(self.candidate)
        self.assertEqual(current.resolve(), self.candidate)
        self.assertTrue(self.previous.is_dir())
        self.assertFalse(list(self.base.glob(".jarvis-core-link-*")))

    def test_process_identity_and_cwd_gate_health_checks(self):
        with patch.object(remote, "service_process", return_value=(self.candidate, 1001, 1001)), patch.object(remote, "runtime_identity", return_value=(1001, 1001)):
            with self.assertRaisesRegex(RuntimeError, "activated release"):
                ORIGINAL_VERIFY(self.checker, "0.7.0", "live")
        with patch.object(remote, "service_process", return_value=(self.previous, 0, 0)), patch.object(remote, "runtime_identity", return_value=(1001, 1001)):
            with self.assertRaisesRegex(RuntimeError, "identity"):
                ORIGINAL_VERIFY(self.checker, "0.7.0", "live")
        self.checker.wait.assert_not_called()

    def test_prepare_uses_release_venv_and_sandbox_not_application_server(self):
        with patch.object(remote, "runtime_identity", return_value=(1001, 1001)), patch.object(remote.os, "chown", create=True), patch.object(remote.os, "chmod"):
            ORIGINAL_PREPARE(self.candidate)
        commands = [call.args for call in self.commands.call_args_list]
        self.assertEqual(commands[0], ("/usr/bin/python3.13", "-m", "venv", str(self.candidate / ".venv")))
        sandbox = commands[-1]
        for option in ("--property=User=jarvis", "--property=Group=jarvis", "--property=PrivateNetwork=yes", "--property=ProtectSystem=strict", "--property=InaccessiblePaths=/etc/jarvis-core /var/lib/jarvis-core"):
            self.assertIn(option, sandbox)
        self.assertIn("-i", sandbox)
        self.assertNotIn("systemctl", sandbox)
        self.assertFalse(any("EnvironmentFile=" in arg for arg in sandbox))

    def archive(self, entries):
        path = self.base / "bundle.tar.gz"
        with tarfile.open(path, "w:gz") as bundle:
            for name, data in entries:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_archive_extracts_only_release_files_and_checks_hashes(self):
        files = {"app/main.py": b"# validated code", "requirements.txt": b""}
        metadata = {"commit": "a" * 40, "application_version": "0.7.0", "files": {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}}
        archive, digest = self.archive([*files.items(), ("RELEASE.json", json.dumps(metadata).encode())])
        destination, result = ORIGINAL_EXTRACT(archive, digest, "a" * 40)
        self.assertEqual(result, metadata)
        self.assertEqual((destination / "app/main.py").read_bytes(), files["app/main.py"])
        self.assertEqual(destination.parent, self.store)

    def test_archive_digest_failure_creates_no_release(self):
        archive, _ = self.archive([("app/main.py", b"code")])
        before = set(self.store.iterdir())
        with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
            ORIGINAL_EXTRACT(archive, "0" * 64, "a" * 40)
        self.assertEqual(set(self.store.iterdir()), before)

    def test_archive_traversal_and_duplicate_paths_are_rejected(self):
        for entries, message in [([("app/../../../escape.py", b"bad")], "Unsafe"),
                                 ([("app/main.py", b"a"), ("app/main.py", b"b")], "Duplicate")]:
            archive, digest = self.archive(entries)
            with self.assertRaisesRegex(RuntimeError, message):
                ORIGINAL_EXTRACT(archive, digest, "a" * 40)
        self.assertFalse((self.base / "escape.py").exists())


class HealthTests(unittest.TestCase):
    def test_first_successful_cycle_is_required(self):
        good = {"status": "healthy", "service": "jarvis-core", "version": "0.7.0"}
        status = {"running": True, "mode": "live", "last_error": None, "cycles_completed": 1, "last_cycle_completed": "time"}
        with patch.object(health, "get", side_effect=[good, status]), patch.object(health.time, "monotonic", return_value=0):
            health.wait("0.7.0", "live")
        status["cycles_completed"] = 0
        with patch.object(health, "get", side_effect=[good, status]), patch.object(health.time, "monotonic", side_effect=[0, 0, 181]), patch.object(health.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "verification failed"):
                health.wait("0.7.0", "live")

    def test_wrong_version_mode_or_observer_error_fails(self):
        for version, mode, error in [("wrong", "live", None), ("0.7.0", "shadow", None), ("0.7.0", "live", "failure")]:
            good = {"status": "healthy", "service": "jarvis-core", "version": version}
            status = {"running": True, "mode": mode, "last_error": error, "cycles_completed": 1, "last_cycle_completed": "time"}
            with patch.object(health, "get", side_effect=[good, status]), patch.object(health.time, "monotonic", side_effect=[0, 0, 181]), patch.object(health.time, "sleep"):
                with self.assertRaisesRegex(RuntimeError, "verification failed"):
                    health.wait("0.7.0", "live")

    def test_probe_uses_loopback_only(self):
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(b'{"status":"healthy"}')
        with patch.object(health.OPENER, "open", return_value=response) as opener:
            self.assertEqual(health.get("/health"), {"status": "healthy"})
            opener.assert_called_once_with("http://127.0.0.1:8000/health", timeout=5)

    def test_readiness_blocks_database_network_and_process_events(self):
        for event in ("sqlite3.connect", "socket.connect", "subprocess.Popen"):
            with self.assertRaisesRegex(RuntimeError, "Readiness forbids"):
                readiness.reject_side_effects(event, ())


class CredentialPolicyTests(unittest.TestCase):
    def environment(self):
        return {"CI_COMMIT_BRANCH": "main", "CI_COMMIT_REF_PROTECTED": "true",
                "CI_ENVIRONMENT_NAME": "production", "CI_PIPELINE_SOURCE": "push", "JARVIS_OPERATION": "deploy"}

    def test_feature_unprotected_and_merge_request_contexts_are_rejected(self):
        for overrides in ({"CI_COMMIT_BRANCH": "feature/jarvis-core-cd", "CI_COMMIT_REF_PROTECTED": "false"},
                          {"CI_COMMIT_REF_PROTECTED": "false"}, {"CI_PIPELINE_SOURCE": "merge_request_event"},
                          {"CI_ENVIRONMENT_NAME": "review"}, {"CI_COMMIT_BRANCH": ""}):
            environment = self.environment() | overrides
            with self.assertRaisesRegex(RuntimeError, "protected-main"):
                policy.require_production_context(environment, "deploy")

    def test_rejected_transport_never_reads_credentials_or_runs_git(self):
        for overrides in ({"CI_COMMIT_BRANCH": "feature/test"}, {"CI_PIPELINE_SOURCE": "merge_request_event"}):
            with patch.dict(os.environ, self.environment() | overrides, clear=True), patch.object(transport, "validated_sha") as sha, patch.object(transport, "git") as git:
                with self.assertRaisesRegex(RuntimeError, "protected-main"):
                    transport.main("deploy")
                sha.assert_not_called()
                git.assert_not_called()

    def test_allowed_deployment_and_explicit_bootstrap_contexts(self):
        policy.require_production_context(self.environment(), "deploy")
        policy.require_production_context(self.environment() | {"CI_PIPELINE_SOURCE": "web", "JARVIS_OPERATION": "bootstrap"}, "bootstrap")
        with self.assertRaisesRegex(RuntimeError, "separately approved"):
            policy.require_production_context(self.environment() | {"JARVIS_OPERATION": "bootstrap"}, "bootstrap")

    def test_yaml_production_rules_match_the_reviewed_policy(self):
        # Local stdlib check of the literal rule lines; CI also uses full PyYAML parsing.
        text = (ROOT / ".gitlab-ci.yml").read_text()
        for name, rule in policy.RULES.items():
            block = text.split(f"\n{name}:\n", 1)[1].split("\n\n", 1)[0]
            self.assertIn("extends: .cd", block)
            self.assertIn(f"- if: '{rule}'", block)
            self.assertIn("when: manual", block)
            self.assertIn("- when: never", block)
        for name in ("validate", "regression", "package_release"):
            block = text.split(f"\n{name}:\n", 1)[1].split("\n\n", 1)[0]
            self.assertNotIn("environment:", block)
        self.assertNotIn("JARVIS_SSH_PRIVATE_KEY:", text)
        self.assertNotIn("JARVIS_SSH_KNOWN_HOSTS:", text)


class HarnessSafetyTests(unittest.TestCase):
    def test_process_network_and_database_events_are_blocked_without_io(self):
        for event, arguments in (
                ("subprocess.Popen", ("blocked", (), None, None)),
                ("socket.connect", (None, ("127.0.0.1", 0))),
                ("sqlite3.connect", (":memory:",))):
            with self.assertRaisesRegex(RuntimeError, "blocked real"):
                sys.audit(event, *arguments)

    def test_outside_temporary_mutations_are_blocked_without_io(self):
        with self.assertRaisesRegex(RuntimeError, "outside temporary"):
            sys.audit("os.mkdir", str(ROOT / "unit-test-must-not-create"), 0o755, -1)


ORIGINAL_SWITCH = remote.switch
ORIGINAL_VERIFY = remote.verify
ORIGINAL_PREPARE = remote.prepare
ORIGINAL_EXTRACT = remote.extract
SAFE_ROOT = None


def install_test_safety(temporary, report):
    forbidden = [Path(name).resolve() for name in ("/opt", "/etc/jarvis-core", "/var/lib/jarvis-core", "/proc")]
    def within(path, directory):
        return path == directory or path.is_relative_to(directory)
    def check_write(value):
        if isinstance(value, (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(value)).resolve()
            if not within(path, temporary) and not (report and within(path, report.parent)):
                raise RuntimeError("CD unit tests blocked filesystem mutation outside temporary/report paths")
    def audit(event, arguments):
        if event.startswith("socket.") and event not in {"socket.__new__"} or event in {
                "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork", "os.forkpty", "sqlite3.connect"}:
            raise RuntimeError("CD unit tests blocked real network/process/database access")
        if event == "open" and not isinstance(arguments[0], int):
            path = Path(os.fsdecode(arguments[0])).resolve()
            if any(within(path, directory) for directory in forbidden):
                raise RuntimeError("CD unit tests blocked production path access")
            mode, flags = arguments[1], arguments[2]
            if (mode and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                check_write(arguments[0])
        if event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.chown"}:
            check_write(arguments[0])
        if event in {"os.rename", "os.link"}:
            check_write(arguments[0]); check_write(arguments[1])
        if event == "os.symlink":
            check_write(arguments[1])
    sys.addaudithook(audit)


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *arguments, **keywords):
        super().__init__(*arguments, **keywords)
        self.outcomes = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes.append((test, None, None))

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.outcomes.append((test, "failure", self._exc_info_to_string(error, test)))

    def addError(self, test, error):
        super().addError(test, error)
        self.outcomes.append((test, "error", self._exc_info_to_string(error, test)))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcomes.append((test, "skipped", reason))


def main():
    global SAFE_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--junitxml")
    options = parser.parse_args()
    report = Path(options.junitxml).resolve() if options.junitxml else None
    if report and not report.is_relative_to(ROOT / "results"):
        raise RuntimeError("JUnit output must be under repository results/")
    with SafeTemporaryDirectory(prefix="jarvis-cd-units-") as temporary:
        SAFE_ROOT = Path(temporary).resolve()
        install_test_safety(SAFE_ROOT, report)
        suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
        if report:
            report.parent.mkdir(exist_ok=True)
            root = ET.Element("testsuite", name="deployment-units", tests=str(result.testsRun),
                              failures=str(len(result.failures)), errors=str(len(result.errors)), skipped=str(len(result.skipped)))
            for test, kind, details in result.outcomes:
                case = ET.SubElement(root, "testcase", classname=test.__class__.__name__, name=test._testMethodName)
                if kind:
                    ET.SubElement(case, kind).text = details
            ET.ElementTree(root).write(report, encoding="utf-8", xml_declaration=True)
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())