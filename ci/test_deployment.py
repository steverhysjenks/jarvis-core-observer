"""Standard-library CD unit tests: temp files and mocked commands only.

No application imports, network, subprocess execution, production reads/writes,
real systemd, sudo, SSH or SQLite connections are permitted by this runner.
"""
import argparse
from contextlib import ExitStack
import errno
import hashlib
import posixpath
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
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
production_policy = load("production_acceptance_policy_tests", ROOT / "tests/production/policy.py")
acceptance = load("production_acceptance_controller_tests", ROOT / "deployment/acceptance.py")
production_runner = load("production_runner_diagnostic_tests", ROOT / "tests/production/run.py")


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
        self.current.stat.side_effect = self.previous.stat
        self.current.exists.side_effect = lambda: self.current_path.exists() or self.current.is_symlink()
        self.current.unlink.side_effect = self.restore_link_state
        self.clock = 0.0
        clock = patch.object(remote.time, "monotonic", side_effect=lambda: self.clock)
        sleeper = patch.object(remote.time, "sleep", side_effect=self.advance_clock)
        clock.start(); sleeper.start()
        self.addCleanup(clock.stop); self.addCleanup(sleeper.stop)
        self.commands = Mock()
        self.preflight = Mock(return_value=("0.7.0", "live"))
        self.prepare = Mock()
        self.checker = Mock()
        self.verify = Mock()
        self.activation = Mock(side_effect=self.activate)
        fixtures = {
            "CURRENT": self.current, "RELEASES": self.store, "ENVIRONMENT": self.env, "STATE": self.state,
            "run": self.commands, "preflight": self.preflight, "prepare": self.prepare,
            "service_state": Mock(return_value={"User": "jarvis", "Group": "jarvis", "ActiveState": "active", "SubState": "running"}),
            "health_module": Mock(return_value=self.checker), "verify": self.verify,
            "extract": Mock(return_value=(self.candidate, {"application_version": "0.7.1"})),
            "switch": self.activation,
        }
        context = patch.multiple(remote, **fixtures)
        context.start()
        self.addCleanup(context.stop)
        self.original_state = {str(p.relative_to(self.base)): p.read_bytes() for p in [self.env, *self.state.iterdir()]}
        self.addCleanup(self.assert_preserved_state)

    def advance_clock(self, seconds):
        self.clock += seconds

    def assert_preserved_state(self):
        for name, content in self.original_state.items():
            self.assertEqual((self.base / name).read_bytes(), content)

    def restore_link_state(self):
        self.current.is_symlink.return_value = False
        self.current.resolve.return_value = self.current_path
        self.current.stat.side_effect = self.current_path.stat

    def activate(self, target):
        self.current.is_symlink.return_value = True
        self.current.resolve.return_value = target
        self.current.stat.side_effect = target.stat

    def bootstrap_layout(self):
        self.current.is_symlink.return_value = False
        self.current.resolve.return_value = self.current_path
        self.current.stat.side_effect = self.current_path.stat

    def test_release_success_stops_switches_restarts_and_verifies(self):
        events = []
        self.commands.side_effect = lambda *args, **kwargs: events.append(args[1])
        self.activation.side_effect = lambda target: (events.append("switch"), self.activate(target))
        self.verify.side_effect = lambda *args: events.append("verify")
        remote.deploy("a" * 40, self.base / "unused", "unused")
        self.assertEqual(events, ["stop", "switch", "restart", "verify"])
        self.verify.assert_called_once_with(self.checker, "0.7.1", "live", self.candidate)
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
        self.assertEqual(self.verify.call_args.args, (self.checker, "0.7.0", "live", self.previous))
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
        self.verify.assert_called_once_with(self.checker, "0.7.0", "live", self.previous)

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
        self.verify.assert_called_once_with(self.checker, "0.7.0", "live", self.current.resolve())

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

    def process(self, directory, *, cwd=None, pid=4242, uid=1001, gid=1001):
        details = directory.stat()
        return {"pid": pid, "cwd": str(directory) if cwd is None else cwd,
                "device": details.st_dev, "inode": details.st_ino, "mode": details.st_mode,
                "uid": uid, "gid": gid}

    def test_process_identity_and_cwd_gate_health_checks(self):
        for process, message in ((self.process(self.candidate, cwd=str(self.previous)), "activated release"),
                                 (self.process(self.previous, uid=123, gid=456), "identity")):
            with patch.object(remote, "service_process", return_value=process), patch.object(remote, "runtime_identity", return_value=(1001, 1001)):
                with self.assertRaisesRegex(RuntimeError, message):
                    ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous)
        self.checker.wait.assert_not_called()

    def test_directory_identity_accepts_namespace_alias_not_wrong_directory(self):
        # Same dev/inode is valid even when a proc magic-link uses another spelling.
        process = self.process(self.previous, cwd="namespace-alias-for-release")
        with patch.object(remote, "service_process", return_value=process), patch.object(remote, "runtime_identity", return_value=(1001, 1001)):
            ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous)
        self.checker.wait.assert_called_once_with("0.7.0", "live")

    def test_mismatch_diagnostics_include_pid_actual_and_expected_paths(self):
        process = self.process(self.candidate)
        with patch.object(remote, "service_process", return_value=process), patch.object(remote, "runtime_identity", return_value=(1001, 1001)):
            with self.assertRaises(RuntimeError) as result:
                ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous)
        for value in ("pid=4242", repr(str(self.candidate)), repr(str(self.previous)), "actual_directory_id"):
            self.assertIn(value, str(result.exception))

    def test_health_failure_and_pid_change_still_fail_verification(self):
        process = self.process(self.previous)
        with patch.object(remote, "runtime_identity", return_value=(1001, 1001)), patch.object(remote, "service_process", return_value=process):
            self.checker.wait.side_effect = RuntimeError("bad health")
            with self.assertRaisesRegex(RuntimeError, "health verification failed"):
                ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous)
        self.checker.wait.side_effect = None
        with patch.object(remote, "runtime_identity", return_value=(1001, 1001)), patch.object(remote, "service_process", side_effect=[process, process, self.process(self.previous, pid=4243)]):
            with self.assertRaisesRegex(RuntimeError, "MainPID changed"):
                ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous)

    def test_transient_root_same_pid_settles_before_health(self):
        root = self.process(self.previous, pid=11516, uid=0, gid=0)
        ready = self.process(self.previous, pid=11516)
        with patch.object(remote, "runtime_identity", return_value=(1001, 1001)), patch.object(remote, "service_process", side_effect=[root, ready, ready, ready]) as probe:
            ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous, startup_timeout=2)
        self.assertEqual(probe.call_count, 4)
        self.assertEqual(self.clock, 1.0)
        self.checker.wait.assert_called_once_with("0.7.0", "live")

    def test_permanently_root_process_times_out_with_full_diagnostics(self):
        root = self.process(self.previous, pid=11508, uid=0, gid=0)
        with patch.object(remote, "runtime_identity", return_value=(1001, 1001)), patch.object(remote, "service_process", return_value=root):
            with self.assertRaisesRegex(RuntimeError, "startup verification timed out") as result:
                ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous, startup_timeout=2)
        for detail in ("pid=11508", "actual_uid=0", "actual_gid=0", repr(str(self.previous)), "expected_release="):
            self.assertIn(detail, str(result.exception))
        self.assertEqual(self.clock, 2.0)
        self.checker.wait.assert_not_called()

    def test_changing_mainpid_during_startup_requires_new_stable_pair(self):
        first = self.process(self.previous, pid=11508)
        final = self.process(self.previous, pid=11516)
        with patch.object(remote, "runtime_identity", return_value=(1001, 1001)), patch.object(remote, "service_process", side_effect=[first, final, final, final]):
            ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous)
        self.assertEqual(self.clock, 1.0)
        self.checker.wait.assert_called_once()

    def test_starting_systemd_state_waits_for_running_and_stable_identity(self):
        running = {"User": "jarvis", "Group": "jarvis", "ActiveState": "active", "SubState": "running"}
        starting = running | {"ActiveState": "activating", "SubState": "start"}
        with patch.object(remote, "service_state", side_effect=[starting, running, running]), patch.object(remote, "service_process", return_value=self.process(self.previous)), patch.object(remote, "runtime_identity", return_value=(1001, 1001)):
            ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous)
        self.assertEqual(self.clock, 1.0)
        self.checker.wait.assert_called_once()

    def test_unexpected_nonroot_uid_and_root_unit_are_terminal(self):
        with patch.object(remote, "runtime_identity", return_value=(1001, 1001)), patch.object(remote, "service_process", return_value=self.process(self.previous, uid=123, gid=456)):
            with self.assertRaisesRegex(RuntimeError, "identity is not jarvis"):
                ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous)
        self.assertEqual(self.clock, 0)
        with patch.object(remote, "service_state", return_value={"User": "root", "Group": "root"}), patch.object(remote, "service_process") as probe:
            with self.assertRaisesRegex(RuntimeError, "Terminal security failure"):
                ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous)
            probe.assert_not_called()
        self.checker.wait.assert_not_called()

    def test_healthy_application_cannot_override_wrong_release_path(self):
        self.checker.wait.return_value = None
        with patch.object(remote, "runtime_identity", return_value=(1001, 1001)), patch.object(remote, "service_process", return_value=self.process(self.candidate)):
            with self.assertRaisesRegex(RuntimeError, "not running from the activated release"):
                ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous)
        self.assertEqual(self.clock, 0)
        self.checker.wait.assert_not_called()

    def test_rollback_restart_polls_transient_root_before_verifying_restored_layout(self):
        self.bootstrap_layout()
        self.checker.wait.side_effect = [RuntimeError("new health failed"), None]
        samples = 0
        def sample(**unused):
            nonlocal samples
            samples += 1
            directory = self.current.resolve()
            return self.process(directory, pid=11508 if samples <= 2 else 11516,
                                uid=0 if samples == 3 else 1001, gid=0 if samples == 3 else 1001)
        with patch.object(remote, "verify", side_effect=ORIGINAL_VERIFY), patch.object(remote, "service_process", side_effect=sample), patch.object(remote, "runtime_identity", return_value=(1001, 1001)):
            with self.assertRaises(remote.DeploymentFailure):
                remote.bootstrap("a" * 40, self.base / "unused", "unused", remote.APPROVAL)
        self.assertFalse(self.current.is_symlink())
        self.assertEqual((self.current_path / "original.py").read_text(), "original baseline")
        self.assertEqual(self.checker.wait.call_count, 2)
        self.assertEqual(samples, 6)

    def test_expired_probe_budget_times_out_instead_of_accepting_late_identity(self):
        def late(**unused):
            self.clock = 3
            return self.process(self.previous)
        with patch.object(remote, "service_process", side_effect=late), patch.object(remote, "runtime_identity", return_value=(1001, 1001)):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous, startup_timeout=2)
        self.checker.wait.assert_not_called()

    def test_timeout_and_interval_must_be_finite_positive(self):
        for timeout, interval in ((0, 0.5), (float("inf"), 0.5), (float("nan"), 0.5), (2, 0), (2, float("inf"))):
            with self.assertRaises(ValueError):
                ORIGINAL_VERIFY(self.checker, "0.7.0", "live", self.previous, startup_timeout=timeout, poll_interval=interval)

    def test_bootstrap_activation_and_recovery_use_real_verifier(self):
        self.bootstrap_layout()
        def process(**unused):
            return self.process(self.current.resolve())
        with patch.object(remote, "verify", side_effect=ORIGINAL_VERIFY), patch.object(remote, "service_process", side_effect=process), patch.object(remote, "runtime_identity", return_value=(1001, 1001)):
            remote.bootstrap("a" * 40, self.base / "unused", "unused", remote.APPROVAL)
        self.assertTrue(self.current.is_symlink())
        self.assertEqual((self.current.resolve() / "original.py").read_text(), "original baseline")

    def test_bootstrap_recovery_to_real_directory_uses_real_verifier(self):
        self.bootstrap_layout()
        self.checker.wait.side_effect = [RuntimeError("new health failed"), None]
        with patch.object(remote, "verify", side_effect=ORIGINAL_VERIFY), patch.object(remote, "service_process", side_effect=lambda **unused: self.process(self.current.resolve())), patch.object(remote, "runtime_identity", return_value=(1001, 1001)):
            with self.assertRaises(remote.DeploymentFailure):
                remote.bootstrap("a" * 40, self.base / "unused", "unused", remote.APPROVAL)
        self.assertFalse(self.current.is_symlink())
        self.assertEqual((self.current_path / "original.py").read_text(), "original baseline")
        self.assertEqual(self.checker.wait.call_count, 2)

    def test_bootstrap_rollback_verification_failure_reports_restored_layout(self):
        self.bootstrap_layout()
        self.verify.side_effect = RuntimeError("verification failed")
        with self.assertRaises(remote.RollbackVerificationFailure) as result:
            remote.bootstrap("a" * 40, self.base / "unused", "unused", remote.APPROVAL)
        self.assertIn("original directory restored and service restarted", str(result.exception))
        self.assertFalse(self.current.is_symlink())
        self.assertEqual((self.current_path / "original.py").read_text(), "original baseline")

    def test_rollback_action_and_verification_errors_are_distinct(self):
        self.verify.side_effect = RuntimeError("new verification failed")
        with self.assertRaises(remote.RollbackVerificationFailure) as verification:
            remote.deploy("a" * 40, self.base / "unused", "unused")
        self.assertIn("previous release restored and service restarted", str(verification.exception))
        self.verify.side_effect = RuntimeError("activation failed")
        calls = 0
        def fail_recovery(*arguments, **keywords):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("rollback stop failed")
        self.commands.side_effect = fail_recovery
        with self.assertRaises(remote.RollbackActionFailure) as actions:
            remote.deploy("a" * 40, self.base / "unused", "unused")
        self.assertIn("rollback actions failed", str(actions.exception))
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


class ProcessInspectionTests(unittest.TestCase):
    def setUp(self):
        cwd = patch.object(remote, "startup_cwd", return_value="<pre-exec cwd>")
        cwd.start()
        self.addCleanup(cwd.stop)

    STATUS = "Uid:\t1001\t1001\t1001\t1001\nGid:\t1001\t1001\t1001\t1001\n"
    DIRECTORY = {"cwd": "read-only-namespace-alias", "device": 7, "inode": 42, "mode": 0o40755}

    def test_old_non_strict_resolution_hides_permission_denied(self):
        # Reproduce Linux realpath behavior without touching proc or any filesystem.
        with patch.object(posixpath.os, "lstat", side_effect=PermissionError(errno.EACCES, "denied")):
            self.assertEqual(posixpath.realpath("/proc/4242/cwd", strict=False), "/proc/4242/cwd")
            with self.assertRaises(PermissionError):
                posixpath.realpath("/proc/4242/cwd", strict=True)

    def test_proc_permission_denied_retries_fixed_read_only_probe_as_jarvis(self):
        with patch.object(remote.os, "readlink", side_effect=PermissionError(errno.EACCES, "denied")), patch.object(remote, "run", return_value=json.dumps(self.DIRECTORY)) as command:
            self.assertEqual(remote.process_directory(4242), self.DIRECTORY)
        self.assertEqual(command.call_args.args[:5], ("/usr/sbin/runuser", "-u", "jarvis", "--", "/usr/bin/python3.13"))
        self.assertEqual(command.call_args.args[-1], "4242")
        self.assertEqual(command.call_args.kwargs, {"timeout": 15, "capture": True})
        self.assertNotIn("app", remote.CWD_PROBE)

    def test_missing_process_does_not_fallback_or_mask_the_error(self):
        with patch.object(remote.os, "readlink", side_effect=FileNotFoundError(errno.ENOENT, "gone")), patch.object(remote, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "pid=4242"):
                remote.process_directory(4242)
        command.assert_not_called()

    def test_failed_same_user_probe_reports_inspection_failure(self):
        with patch.object(remote.os, "readlink", side_effect=PermissionError(errno.EPERM, "denied")), patch.object(remote, "run", side_effect=RuntimeError("probe failed")):
            with self.assertRaisesRegex(RuntimeError, "Cannot inspect service cwd even as jarvis: pid=4242"):
                remote.process_directory(4242)

    def test_service_snapshot_uses_effective_identity_and_stable_mainpid(self):
        with patch.object(remote, "run", return_value="4242"), patch.object(remote.Path, "read_text", return_value=self.STATUS), patch.object(remote, "runtime_identity", return_value=(1001, 1001)), patch.object(remote, "process_directory", return_value=self.DIRECTORY):
            process = remote.service_process()
        self.assertEqual(process, self.DIRECTORY | {"pid": 4242, "uid": 1001, "gid": 1001})

    def test_wrong_effective_uid_blocks_cwd_probe(self):
        status = self.STATUS.replace("1001\t1001", "1001\t0", 1)
        with patch.object(remote, "run", return_value="4242"), patch.object(remote.Path, "read_text", return_value=status), patch.object(remote, "runtime_identity", return_value=(1001, 1001)), patch.object(remote, "process_directory") as probe:
            with self.assertRaisesRegex(RuntimeError, "identity is not jarvis:jarvis"):
                remote.service_process()
            probe.assert_not_called()

    def test_changed_pid_and_deleted_cwd_fail_closed(self):
        for values, directory, message in ((["4242", "4243"], self.DIRECTORY, "MainPID changed"),
                                           (["4242"], self.DIRECTORY | {"cwd": "old-release (deleted)"}, "Invalid/deleted")):
            with patch.object(remote, "run", side_effect=values), patch.object(remote.Path, "read_text", return_value=self.STATUS), patch.object(remote, "runtime_identity", return_value=(1001, 1001)), patch.object(remote, "process_directory", return_value=directory):
                with self.assertRaisesRegex(RuntimeError, message):
                    remote.service_process()

    def test_real_status_parser_reproduces_same_pid_root_to_jarvis_transition(self):
        root_status = "Uid:\t0\t0\t0\t0\nGid:\t0\t0\t0\t0\n"
        final_status = "Uid:\t999\t999\t999\t999\nGid:\t991\t991\t991\t991\n"
        with patch.object(remote, "run", return_value="11516"), patch.object(remote.Path, "read_text", side_effect=[root_status, final_status]), patch.object(remote, "runtime_identity", return_value=(999, 991)), patch.object(remote, "process_directory", return_value=self.DIRECTORY) as probe:
            with self.assertRaises(remote.StartupPending) as pending:
                remote.service_process()
            self.assertEqual(pending.exception.snapshot["pid"], 11516)
            self.assertEqual((pending.exception.snapshot["uid"], pending.exception.snapshot["gid"]), (0, 0))
            probe.assert_not_called()
            ready = remote.service_process()
            self.assertEqual((ready["pid"], ready["uid"], ready["gid"]), (11516, 999, 991))

    def test_budget_caps_query_timeout_and_rejects_expiry(self):
        with patch.object(remote.time, "monotonic", return_value=4.5), patch.object(remote, "run", return_value="4242") as command:
            self.assertEqual(remote.main_pid(deadline=5), 4242)
            self.assertEqual(command.call_args.kwargs["timeout"], 0.5)
        with patch.object(remote.time, "monotonic", return_value=5):
            with self.assertRaises(remote.StartupPending):
                remote.startup_budget(5, 15)

    def test_zero_mainpid_is_rejected_before_any_proc_read(self):
        with patch.object(remote, "run", return_value="0"), patch.object(remote.Path, "read_text") as read:
            with self.assertRaisesRegex(RuntimeError, "no running MainPID"):
                remote.service_process()
            read.assert_not_called()


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


class ProductionAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.scratch = SafeTemporaryDirectory(dir=SAFE_ROOT)
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name)
        self.sha = "a" * 40
        self.release = self.base / "releases" / "validated"
        (self.release / "app").mkdir(parents=True)
        (self.release / "app/main.py").write_bytes(b"# validated source")
        self.hashes = {"app/main.py": hashlib.sha256(b"# validated source").hexdigest()}
        (self.release / "RELEASE.json").write_text(json.dumps({"commit": self.sha, "files": self.hashes}))
        current = Mock(spec=Path)
        current.is_symlink.return_value = True
        current.resolve.return_value = self.release
        self.deployment = Mock(CURRENT=current, RELEASES=self.release.parent)
        self.endpoints = {"ha": "http://ha.invalid:8123", "music": "http://music.invalid:8095",
                          "ollama": "http://127.0.0.1:11434", "jarvis": "http://127.0.0.1:8000"}

    def test_setup_subprocess_failures_report_stage_exit_code_without_output(self):
        stages = ["test-venv-creation", "test-dependency-installation", "active-runtime-inspection"]
        for index, stage in enumerate(stages):
            diagnostics = acceptance.Diagnostics()
            error = subprocess.CalledProcessError(7, ["secret-placeholder"], output="secret-placeholder", stderr="secret-placeholder")
            responses = [subprocess.CompletedProcess([], 0) for _ in range(index)] + [error]
            with self.subTest(stage=stage), patch.object(acceptance.subprocess, "run", side_effect=responses) as commands:
                with self.assertRaises(subprocess.CalledProcessError):
                    acceptance.execute(self.deployment, self.base, self.release, self.sha, diagnostics)
                value = json.loads(diagnostics.message())
                self.assertEqual(value["operation"], stage)
                self.assertEqual(value["exit_code"], 7)
                self.assertEqual(value["exception"], "CalledProcessError")
                self.assertFalse(value["tests_started"])
                self.assertFalse(value["junit_produced"])
                self.assertNotIn("secret-placeholder", diagnostics.message())
                self.assertTrue(all(c.kwargs["stderr"] == subprocess.DEVNULL for c in commands.call_args_list))

    def test_transient_launch_failure_is_not_claimed_as_started_tests(self):
        workspace = self.base / "launch"
        workspace.mkdir()
        diagnostics = acceptance.Diagnostics()
        responses = [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 0),
                     subprocess.CompletedProcess([], 0, stdout=str(self.release / ".venv/lib")),
                     subprocess.CompletedProcess([], 203)]
        self.deployment.runtime_identity.return_value = (999, 991)
        self.deployment.CLEAN_ENV = {}
        with patch.object(acceptance.subprocess, "run", side_effect=responses), \
                patch.object(acceptance.os, "chown", create=True), \
                patch.object(acceptance, "stop_test_unit") as stop:
            self.assertEqual(acceptance.execute(self.deployment, workspace, self.release, self.sha, diagnostics), 203)
            stop.assert_called_once()
        diagnostics.runner_status(workspace)
        value = json.loads(diagnostics.message())
        self.assertEqual(value["operation"], "transient-unit-execution")
        self.assertEqual(value["exit_code"], 203)
        self.assertIsNone(value["tests_started"])
        self.assertEqual(value["runner_operation"], "not-started")
        self.assertFalse(value["junit_produced"])

    def test_timeout_classification_and_runner_markers_are_sanitized(self):
        diagnostics = acceptance.Diagnostics()
        with self.assertRaises(subprocess.TimeoutExpired):
            diagnostics.step("test-dependency-installation", Mock(side_effect=subprocess.TimeoutExpired("secret-placeholder", 300, output="secret-placeholder")))
        self.assertEqual(json.loads(diagnostics.message())["classification"], "operation-timeout")
        (self.base / "results").mkdir()
        marker = self.base / "results/runner-status.json"
        marker.write_text(json.dumps({"operation": "secret-placeholder", "exception": "secret-placeholder",
                                      "tests_started": True, "pytest_started": True, "payload": "secret-placeholder"}))
        diagnostics.runner_status(self.base)
        self.assertTrue(json.loads(diagnostics.message())["tests_started"])
        self.assertNotIn("secret-placeholder", diagnostics.message())
        marker.write_text(json.dumps({"operation": "pytest-import", "exception": "ModuleNotFoundError",
                                      "tests_started": False, "pytest_started": False}))
        diagnostics.runner_status(self.base)
        self.assertEqual(json.loads(diagnostics.message())["runner_operation"], "pytest-import")
        self.assertEqual(json.loads(diagnostics.message())["runner_exception"], "ModuleNotFoundError")

    def test_transport_diagnostics_do_not_confuse_remote_exit_with_test_failure(self):
        value = json.loads(transport.transport_failure(
            subprocess.CalledProcessError(1, "secret-placeholder", stderr="secret-placeholder"),
            {"operation": "remote-acceptance-exit-status", "junit_retrieved": True}))
        self.assertEqual(value["operation"], "remote-acceptance-exit-status")
        self.assertEqual(value["exit_code"], 1)
        self.assertTrue(value["junit_retrieved"])
        self.assertIsNone(value["tests_started"])
        self.assertNotIn("secret-placeholder", json.dumps(value))

    def test_cleanup_does_not_relabel_original_failure_and_reports_secondary_failure(self):
        diagnostics = acceptance.Diagnostics()
        original = subprocess.TimeoutExpired("secret-placeholder", 660)
        with self.assertRaises(subprocess.TimeoutExpired):
            diagnostics.step("transient-unit-execution", Mock(side_effect=original))
        diagnostics.step("transient-unit-cleanup", Mock(return_value=None))
        diagnostics.record(original)
        value = json.loads(diagnostics.message())
        self.assertEqual(value["operation"], "transient-unit-execution")
        self.assertIsNone(value["secondary_failure"])
        with self.assertRaises(acceptance.AcceptanceUnitStillRunning):
            diagnostics.step("transient-unit-cleanup", Mock(side_effect=acceptance.AcceptanceUnitStillRunning("secret-placeholder")))
        value = json.loads(diagnostics.message())
        self.assertEqual(value["secondary_failure"]["operation"], "transient-unit-cleanup")
        self.assertNotIn("secret-placeholder", diagnostics.message())

    def test_controller_fallback_junit_contains_safe_setup_diagnostics(self):
        workspace = self.base / "setup-failure"
        workspace.mkdir()
        self.deployment.host_lock.return_value = MagicMock()
        self.deployment.CLEAN_ENV = {}
        with patch.object(acceptance.sys, "argv", ["acceptance.py", self.sha, str(self.base / "tests.tar.gz"), "digest", str(self.release)]), \
                patch.object(acceptance.sys, "version_info", (3, 13)), \
                patch.object(acceptance.os, "geteuid", return_value=0, create=True), \
                patch.object(acceptance, "controller", return_value=self.deployment), \
                patch.object(acceptance.tempfile, "mkdtemp", return_value=str(workspace)), \
                patch.object(acceptance, "unpack", return_value={"application_files": self.hashes}), \
                patch.object(acceptance, "running_release", return_value=42), \
                patch.object(acceptance.subprocess, "run", side_effect=[subprocess.CompletedProcess([], 0), subprocess.CalledProcessError(1, "secret-placeholder", stderr="secret-placeholder")]):
            self.assertEqual(acceptance.main(), 1)
        report = (self.base / "production.xml").read_text()
        self.assertIn("test-dependency-installation", report)
        self.assertIn("CalledProcessError", report)
        self.assertIn('"tests_started": false', report)
        self.assertNotIn("secret-placeholder", report)
        cases = list(ET.parse(self.base / "production.xml").getroot().iter("testcase"))
        self.assertEqual(len(cases), 1)
        self.assertIn("test-dependency-installation", cases[0].find("failure").text)

    def test_runner_failure_and_first_test_marker_do_not_record_secrets(self):
        import ast
        (self.base / "results").mkdir()
        status = {"operation": "pytest-import", "tests_started": False, "pytest_started": False}
        with patch.object(production_runner, "__file__", str(self.base / "runner.py")), \
                patch.object(production_runner, "STATUS", status), \
                patch.object(production_runner, "main", side_effect=ModuleNotFoundError("secret-placeholder")):
            self.assertEqual(production_runner.entrypoint(), 1)
        marker = self.base / "results/runner-status.json"
        self.assertEqual(json.loads(marker.read_text())["exception"], "ModuleNotFoundError")
        tree = ast.parse((ROOT / "tests/production/safety_plugin.py").read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "pytest_runtest_logstart")
        namespace = {"ROOT": self.base, "json": json}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "safe-start-marker", "exec"), namespace)
        namespace["pytest_runtest_logstart"]("secret-placeholder", ("secret-placeholder", 1, "secret-placeholder"))
        self.assertTrue(json.loads(marker.read_text())["tests_started"])
        self.assertNotIn("secret-placeholder", marker.read_text())

    def test_active_commit_and_files_must_match_validated_bundle(self):
        self.assertEqual(acceptance.active_release(self.deployment, self.sha, self.hashes), self.release)
        with self.assertRaisesRegex(RuntimeError, "pipeline commit"):
            acceptance.active_release(self.deployment, "b" * 40, self.hashes)
        (self.release / "app/main.py").write_bytes(b"unreviewed edit")
        with self.assertRaisesRegex(RuntimeError, "integrity failure"):
            acceptance.active_release(self.deployment, self.sha, self.hashes)

    def test_extra_application_module_is_rejected(self):
        (self.release / "app/extra.py").write_bytes(b"unexpected")
        with self.assertRaisesRegex(RuntimeError, "module set"):
            acceptance.active_release(self.deployment, self.sha, self.hashes)

    def test_same_commit_in_another_release_is_not_deployment_evidence(self):
        with self.assertRaisesRegex(RuntimeError, "deployment instance"):
            acceptance.active_release(self.deployment, self.sha, self.hashes, str(self.base / "releases/other"))
        self.assertEqual(acceptance.active_release(self.deployment, self.sha, self.hashes, str(self.release)), self.release)

    def test_deployment_receipt_rejects_failed_missing_and_unrelated_jobs(self):
        release = "/opt/jarvis-releases/" + self.sha + "-release"
        receipt = {"commit": self.sha, "pipeline": "42", "job": "51", "status": "success", "release": release}
        self.assertEqual(transport.deployment_receipt(receipt, self.sha, "42"), release)
        for update in ({"status": "failed"}, {"status": "skipped"}, {"pipeline": "41"},
                       {"commit": "b" * 40}, {"job": ""}, {"release": "/var/lib/jarvis-core"}):
            with self.subTest(update=update), self.assertRaises(RuntimeError):
                transport.deployment_receipt(receipt | update, self.sha, "42")
        with self.assertRaises(RuntimeError):
            transport.deployment_receipt({}, self.sha, "42")

    def test_running_service_must_use_release_inode_identity_and_stable_pid(self):
        info = self.release.stat()
        valid = {"device": info.st_dev, "inode": info.st_ino, "pid": 42, "uid": 999, "gid": 991}
        self.deployment.runtime_identity.return_value = (999, 991)
        self.deployment.service_process.return_value = valid
        self.assertEqual(acceptance.running_release(self.deployment, self.release), 42)
        for update in ({"inode": info.st_ino + 1}, {"uid": 0}, {"gid": 0}):
            self.deployment.service_process.return_value = valid | update
            with self.assertRaisesRegex(RuntimeError, "identity or release"):
                acceptance.running_release(self.deployment, self.release)
        self.deployment.service_process.side_effect = [valid, valid | {"pid": 43}]
        with self.assertRaisesRegex(RuntimeError, "MainPID changed"):
            acceptance.running_release(self.deployment, self.release)

    def test_junit_rejects_skipped_empty_failed_and_nonzero_execution(self):
        produced, report = self.base / "produced.xml", self.base / "report.xml"
        produced.write_text('<testsuite tests="1"><testcase name="ok"/></testsuite>')
        self.assertEqual(acceptance.collect_report(produced, report, 0), 0)
        for xml, result in [
                ('<testsuite tests="1" skipped="1"><testcase name="skip"><skipped/></testcase></testsuite>', 0),
                ('<testsuite tests="0"/>', 0),
                ('<testsuite tests="1" failures="1"><testcase name="failed"><failure/></testcase></testsuite>', 0),
                ('<testsuite tests="1"><testcase name="ok"/></testsuite>', 1),
                ('<testsuite tests="2"><testcase name="incomplete"/></testsuite>', 0)]:
            with self.subTest(xml=xml, result=result):
                produced.write_text(xml)
                self.assertEqual(acceptance.collect_report(produced, report, result), 1)
                self.assertTrue(list(ET.parse(report).getroot().iter("failure")))

    def test_late_verification_failure_preserves_test_results(self):
        report = self.base / "report.xml"
        report.write_text('<testsuite tests="1" failures="1"><testcase name="original"><failure>sanitized</failure></testcase></testsuite>')
        acceptance.failure_report(report, preserve=True)
        cases = list(ET.parse(report).getroot().iter("testcase"))
        self.assertEqual([c.get("name") for c in cases], ["original", "acceptance_execution"])

    def test_cleanup_checks_only_transient_unit_and_requires_no_process(self):
        unit = "jarvis-acceptance-fixture"
        def response(args, **kwargs):
            if args[1] == "show":
                return Mock(stdout="LoadState=loaded\nActiveState=inactive\nMainPID=0\n", returncode=0)
            return Mock(returncode=0)
        with patch.object(acceptance.subprocess, "run", side_effect=response) as commands:
            acceptance.stop_test_unit(self.deployment, unit)
            self.assertTrue(all(call.args[0][2] == unit for call in commands.call_args_list))
            self.assertFalse(any("jarvis-core" in arg for call in commands.call_args_list for arg in call.args[0]))
        with patch.object(acceptance.subprocess, "run", side_effect=[Mock(returncode=0), Mock(stdout="LoadState=loaded\nActiveState=active\nMainPID=123", returncode=0)]):
            with self.assertRaises(acceptance.AcceptanceUnitStillRunning):
                acceptance.stop_test_unit(self.deployment, unit)
        with patch.object(acceptance.subprocess, "run", side_effect=[Mock(returncode=5), Mock(stdout="LoadState=not-found\nActiveState=inactive\nMainPID=0", returncode=1)]):
            acceptance.stop_test_unit(self.deployment, unit)
        with patch.object(acceptance.subprocess, "run", side_effect=[Mock(returncode=5), Mock(stdout="", returncode=1)]):
            with self.assertRaises(acceptance.AcceptanceUnitStillRunning):
                acceptance.stop_test_unit(self.deployment, unit)

    def test_acceptance_holds_host_lock_and_retains_junit_on_late_identity_failure(self):
        workspace = self.base / "acceptance-work"
        (workspace / "results").mkdir(parents=True)
        archive = self.base / "tests.tar.gz"
        lock = MagicMock()
        self.deployment.host_lock.return_value = lock
        def execute(*args):
            lock.__enter__.assert_called_once()
            lock.__exit__.assert_not_called()
            (workspace / "results/production.xml").write_text(
                '<testsuite tests="1"><testcase name="completed_test"/></testsuite>')
            return 0
        with patch.object(acceptance.sys, "argv", ["acceptance.py", self.sha, str(archive), "digest", str(self.release)]), \
                patch.object(acceptance.sys, "version_info", (3, 13)), \
                patch.object(acceptance.os, "geteuid", return_value=0, create=True), \
                patch.object(acceptance, "controller", return_value=self.deployment), \
                patch.object(acceptance.tempfile, "mkdtemp", return_value=str(workspace)), \
                patch.object(acceptance, "unpack", return_value={"application_files": self.hashes}), \
                patch.object(acceptance, "execute", side_effect=execute), \
                patch.object(acceptance, "running_release", side_effect=[42, 43]), \
                patch.object(acceptance.shutil, "rmtree") as cleanup:
            self.assertEqual(acceptance.main(), 1)
            # Never delete an arbitrary supplied directory, application release or state.
            cleanup.assert_not_called()
        lock.__exit__.assert_called_once()
        report = ET.parse(self.base / "production.xml").getroot()
        self.assertIn("completed_test", [case.get("name") for case in report.iter("testcase")])
        self.assertTrue(list(report.iter("failure")))

    def test_failed_acceptance_fetches_junit_and_fetch_failure_retains_remote_report(self):
        artifact = self.base / "release-artifacts"
        artifact.mkdir()
        sources = {"runner.py": b"# runner"}
        controllers = {"acceptance.py": b"# acceptance", "remote.py": b"# remote"}
        with patch.object(package, "test_files", return_value=dict(sources)), \
                patch.object(package, "release_files", return_value={"app/main.py": b"# validated source"}), \
                patch.object(package, "git", return_value=controllers["acceptance.py"]):
            identity = package.write_test_bundle(artifact, self.sha)
        (artifact / "remote.py").write_bytes(controllers["remote.py"])
        identity.update(commit=self.sha, controller_sha256=hashlib.sha256(controllers["remote.py"]).hexdigest())
        (artifact / "identity.json").write_text(json.dumps(identity))
        (self.base / "results").mkdir()
        release = "/opt/jarvis-releases/" + self.sha + "-receipt"
        (self.base / "results/deployment.json").write_text(json.dumps(
            {"commit": self.sha, "pipeline": "42", "job": "51", "status": "success", "release": release}))
        (self.base / "key").write_text("dummy offline fixture")
        (self.base / "hosts").write_text("dummy offline fixture")
        environment = {"CI_COMMIT_BRANCH": "main", "CI_COMMIT_REF_PROTECTED": "true", "CI_ENVIRONMENT_NAME": "production",
                       "CI_PIPELINE_SOURCE": "push", "JARVIS_OPERATION": "deploy", "CI_PIPELINE_ID": "42",
                       "JARVIS_SSH_PRIVATE_KEY": str(self.base / "key"), "JARVIS_SSH_KNOWN_HOSTS": str(self.base / "hosts")}
        for fetch_failure in (False, True):
            calls = []
            def command(args, **kwargs):
                calls.append(args)
                if args[0] == "ssh" and "sudo -n" in args[-1]:
                    self.assertTrue(args[-1].endswith(release))
                    return subprocess.CompletedProcess(args, 1)
                if args[0] == "scp" and args[-2].endswith("/production.xml"):
                    if fetch_failure:
                        raise OSError("mock fetch failure")
                    acceptance.failure_report(Path(args[-1]))
                return subprocess.CompletedProcess(args, 0)
            with self.subTest(fetch_failure=fetch_failure), ExitStack() as patches:
                patches.enter_context(patch.dict(transport.os.environ, environment, clear=True))
                patches.enter_context(patch.object(transport, "ROOT", self.base))
                patches.enter_context(patch.object(transport, "validated_sha", return_value=self.sha))
                patches.enter_context(patch.object(transport, "git", side_effect=lambda *a: controllers[a[-1].split("/")[-1]]))
                patches.enter_context(patch.object(transport, "test_files", return_value=sources))
                patches.enter_context(patch.object(transport, "release_files", return_value={"app/main.py": b"# validated source"}))
                patches.enter_context(patch.object(transport.tempfile, "TemporaryDirectory", side_effect=lambda **k: SafeTemporaryDirectory(dir=self.base)))
                patches.enter_context(patch.object(transport.subprocess, "run", side_effect=command))
                with self.assertRaises((subprocess.CalledProcessError, OSError)):
                    transport.main("acceptance")
            self.assertTrue(any(a[0] == "scp" and a[-2].endswith("/production.xml") for a in calls))
            cleanup = calls[-1][-1]
            self.assertEqual("/production.xml" in cleanup, not fetch_failure)
            self.assertEqual("rmdir" in cleanup, not fetch_failure)

    def test_exact_commit_test_bundle_retains_behavioural_source_without_approval(self):
        source = {"tests/regression/test_qwen_live.py": b"# archived, never auto-collected",
                  "tests/regression/test_context_live.py": b"# approved read-only source"}
        with patch.object(package, "test_files", return_value=source), patch.object(package, "release_files", return_value={"app/main.py": b"# validated source"}), patch.object(package, "git", return_value=b"# validated acceptance controller"):
            identity = package.write_test_bundle(self.base, self.sha)
        self.assertEqual(identity["tests_archive_sha256"], hashlib.sha256((self.base / "tests.tar.gz").read_bytes()).hexdigest())
        workspace = self.base / "tests-work"
        workspace.mkdir()
        manifest = acceptance.unpack(self.base / "tests.tar.gz", identity["tests_archive_sha256"], self.sha, workspace)
        self.assertEqual(manifest["application_files"], self.hashes)
        self.assertEqual((workspace / "tests/regression/test_qwen_live.py").read_bytes(), source["tests/regression/test_qwen_live.py"])
        self.assertNotIn("test_qwen_live.py", production_policy.APPROVED)
        self.assertNotIn("test_isolation_guards.py", production_policy.APPROVED)
        self.assertEqual((self.release / "app/main.py").read_bytes(), b"# validated source")

    def test_live_collection_guard_excludes_behavioural_and_unreviewed_before_import(self):
        import ast
        profile = self.base / "profile"
        directory = profile / "tests/regression"
        directory.mkdir(parents=True)
        approved = directory / "test_context_live.py"
        approved.write_text("import pytest\npytestmark = pytest.mark.live\n")
        behavioural = directory / "test_qwen_live.py"
        behavioural.write_text("raise RuntimeError('must never import')\n")
        module = ast.parse((ROOT / "tests/production/safety_plugin.py").read_text())
        function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "safe_module")
        namespace = {"ROOT": profile, "APPROVED": production_policy.APPROVED, "Path": Path, "ast": ast}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "collection-guard", "exec"), namespace)
        self.assertTrue(namespace["safe_module"](approved))
        self.assertFalse(namespace["safe_module"](behavioural))
        self.assertFalse(namespace["safe_module"](directory / "test_unreviewed.py"))
        approved.write_text("import pytest\npytestmark = pytest.mark.behavioural\n")
        self.assertFalse(namespace["safe_module"](approved))

    def test_acceptance_bundle_cannot_write_application_files(self):
        with patch.object(package, "test_files", return_value={"app/main.py": b"overwrite forbidden"}), patch.object(package, "release_files", return_value={"app/main.py": b"# validated source"}), patch.object(package, "git", return_value=b"# controller"):
            identity = package.write_test_bundle(self.base, self.sha)
        workspace = self.base / "unpack"
        workspace.mkdir()
        with self.assertRaisesRegex(RuntimeError, "Unsafe acceptance bundle"):
            acceptance.unpack(self.base / "tests.tar.gz", identity["tests_archive_sha256"], self.sha, workspace)
        self.assertEqual((self.release / "app/main.py").read_bytes(), b"# validated source")

    def test_test_sources_are_read_from_commit_objects(self):
        calls = []
        def git(*arguments):
            calls.append(arguments)
            if arguments[0] == "ls-tree":
                return b"tests/regression/test_context_live.py\ntests/regression/test_qwen_live.py\n"
            return arguments[-1].encode()
        with patch.object(package, "git", side_effect=git):
            result = package.test_files(self.sha)
        self.assertIn("production_safety.py", result)
        self.assertTrue(all(call[1].startswith(self.sha + ":") for call in calls if call[0] == "show"))
        self.assertFalse(any("HEAD" in call for call in calls))

    def test_readonly_http_policy_blocks_actions_generation_and_other_hosts(self):
        allowed = [("GET", "http://ha.invalid:8123/api/states", b""),
                   ("GET", "http://127.0.0.1:11434/api/tags", b""),
                   ("GET", "http://127.0.0.1:8000/observer/status", b""),
                   ("POST", "http://music.invalid:8095/api", b'{"command":"music/genres/library_items","args":{"limit":1}}')]
        denied = [("POST", "http://ha.invalid:8123/api/services/tts/speak", b"{}"),
                  ("POST", "http://127.0.0.1:11434/api/chat", b"{}"),
                  ("POST", "http://127.0.0.1:8000/request", b"{}"),
                  ("GET", "http://unexpected.invalid/api/states", b""),
                  ("POST", "http://music.invalid:8095/api", b'{"command":"players/play","args":{"limit":1}}')]
        for method, url, payload in allowed:
            self.assertTrue(production_policy.readonly_request(method, url, payload, self.endpoints))
        for method, url, payload in denied:
            self.assertFalse(production_policy.readonly_request(method, url, payload, self.endpoints))

    def test_production_sqlite_requires_exact_readonly_uri(self):
        workspace = self.base / "work"
        self.assertTrue(production_policy.readonly_sqlite(production_policy.PRODUCTION_DATABASE, uri=True, workspace=workspace))
        self.assertFalse(production_policy.readonly_sqlite(production_policy.PRODUCTION_DATABASE, uri=False, workspace=workspace))
        self.assertFalse(production_policy.readonly_sqlite("/var/lib/jarvis-core/jarvis.db", uri=False, workspace=workspace))
        self.assertFalse(production_policy.readonly_sqlite("file:/var/lib/jarvis-core/jarvis.db?mode=rw", uri=True, workspace=workspace))
        self.assertTrue(production_policy.readonly_sqlite(workspace / "temporary.db", uri=False, workspace=workspace))

    def test_five_behavioural_cases_are_excluded_before_collection(self):
        import ast
        tree = ast.parse((ROOT / "tests/regression/test_qwen_live.py").read_text())
        functions = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name.startswith("test_")]
        count = 0
        for function in functions:
            dimensions = [len(ast.literal_eval(d.args[1])) for d in function.decorator_list
                          if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "parametrize"]
            count += dimensions[0] if dimensions else 1
        self.assertEqual(count, 5)
        self.assertTrue({"test_qwen_live.py", "test_isolation_guards.py"}.isdisjoint(production_policy.APPROVED))

    def test_acceptance_context_rejects_feature_mr_and_wrong_environment(self):
        environment = {"CI_COMMIT_BRANCH": "main", "CI_COMMIT_REF_PROTECTED": "true",
                       "CI_ENVIRONMENT_NAME": "production", "CI_PIPELINE_SOURCE": "push", "JARVIS_OPERATION": "deploy"}
        policy.require_production_context(environment, "acceptance")
        for values in ({"CI_COMMIT_BRANCH": "feature/test"}, {"CI_PIPELINE_SOURCE": "merge_request_event"}, {"CI_ENVIRONMENT_NAME": "review"}, {"JARVIS_OPERATION": "bootstrap"}):
            with self.assertRaises(RuntimeError):
                policy.require_production_context(environment | values, "acceptance")

    def test_acceptance_job_waits_for_manual_success_and_shares_resource_group(self):
        text = (ROOT / ".gitlab-ci.yml").read_text()
        block = text.split("\nproduction_acceptance:\n", 1)[1]
        self.assertIn("extends: .cd", block)
        self.assertIn("job: deploy_production", block)
        self.assertIn("when: on_success", block)
        self.assertIn("junit: results/production.xml", block)
        self.assertIn(f"- if: '{policy.RULES['deploy_production']}'", block)

    def test_failure_report_is_generic_and_does_not_contain_live_details(self):
        report = self.base / "result.xml"
        acceptance.failure_report(report)
        tree = ET.parse(report)
        self.assertEqual(tree.getroot().get("failures"), "1")
        self.assertNotIn("private-placeholder", report.read_text())


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
    with SafeTemporaryDirectory(dir=ROOT, prefix=".cd-unit-") as temporary:
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
