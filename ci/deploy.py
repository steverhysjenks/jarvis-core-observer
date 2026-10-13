"""Controlled SSH transport. Never run this script as local validation."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid

from package_release import ROOT, git, release_files, validated_sha
from deployment_policy import require_production_context

HOST = "ansible@192.168.0.62"
APPROVAL = "MIGRATE_REAL_DIRECTORY_LXC122"


def main(action):
    if action not in {"preflight", "bootstrap", "deploy"}:
        raise RuntimeError("Unknown operation")
    require_production_context(os.environ, action)
    sha = validated_sha()
    # Refuse an old manual pipeline after main has moved; revalidate a fresh pipeline.
    latest = git("ls-remote", "origin", "refs/heads/main").decode().split()
    if not latest or latest[0] != sha:
        raise RuntimeError("main has moved; run and approve a new validated pipeline")
    if action == "bootstrap" and os.environ.get("JARVIS_BOOTSTRAP_APPROVAL") != APPROVAL:
        raise RuntimeError("Separate bootstrap approval phrase is required")
    artifact = ROOT / "release-artifacts"
    identity = json.loads((artifact / "identity.json").read_text())
    archive = artifact / "release.tar.gz"
    controller = artifact / "remote.py"
    if identity["commit"] != sha or hashlib.sha256(archive.read_bytes()).hexdigest() != identity["archive_sha256"]:
        raise RuntimeError("Release artifact identity/integrity failure")
    trusted_controller = git("show", f"{sha}:deployment/remote.py")
    if controller.read_bytes() != trusted_controller or hashlib.sha256(trusted_controller).hexdigest() != identity["controller_sha256"]:
        raise RuntimeError("Controller is not from the validated commit")
    # Independently compare artifact content with the commit, not just artifact metadata.
    expected = release_files(sha)
    with tarfile.open(archive) as bundle:
        entries = bundle.getmembers()
        if len(entries) != len(expected) + 1 or {e.name for e in entries} != set(expected) | {"RELEASE.json"}:
            raise RuntimeError("Unexpected release artifact entries")
        for entry in entries:
            if not entry.isfile():
                raise RuntimeError("Non-regular archive entry")
            data = bundle.extractfile(entry).read()
            if entry.name in expected and data != expected[entry.name]:
                raise RuntimeError("Artifact differs from validated commit")
            if entry.name == "RELEASE.json":
                metadata = json.loads(data)
                tree = ast.parse(expected["app/main.py"].decode())
                versions = [ast.literal_eval(k.value) for n in ast.walk(tree) if isinstance(n, ast.Call)
                            and isinstance(n.func, ast.Name) and n.func.id == "FastAPI"
                            for k in n.keywords if k.arg == "version"]
                if versions != [metadata["application_version"]]:
                    raise RuntimeError("Artifact version differs from commit")
                if metadata["commit"] != sha or metadata["files"] != {
                    n: hashlib.sha256(d).hexdigest() for n, d in expected.items()
                }:
                    raise RuntimeError("Invalid release manifest")
    private_key = Path(os.environ.get("JARVIS_SSH_PRIVATE_KEY", ""))
    known_hosts = Path(os.environ.get("JARVIS_SSH_KNOWN_HOSTS", ""))
    if not private_key.is_file() or not known_hosts.is_file():
        raise RuntimeError("Protected SSH key and verified known_hosts file variables are required")
    with tempfile.TemporaryDirectory(prefix="jarvis-ssh-") as directory:
        key, hosts = Path(directory) / "key", Path(directory) / "known_hosts"
        shutil.copyfile(private_key, key)
        shutil.copyfile(known_hosts, hosts)
        key.chmod(0o600)
        hosts.chmod(0o600)
        options = ["-F", "/dev/null", "-i", str(key), "-o", f"UserKnownHostsFile={hosts}",
                   "-o", "GlobalKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=yes",
                   "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ForwardAgent=no",
                   "-o", "ClearAllForwardings=yes", "-o", "PasswordAuthentication=no",
                   "-o", "KbdInteractiveAuthentication=no", "-o", "ConnectTimeout=10"]
        if action == "preflight":
            # Execute verified controller from stdin: no upload, lock file or release writes.
            command = shlex.join(["sudo", "-n", "/usr/bin/python3.13", "-B", "-", "preflight", sha, "-", "-"])
            subprocess.run(["ssh", *options, HOST, command], input=trusted_controller, check=True)
            return
        incoming = f"/tmp/jarvis-ci-{sha}-{uuid.uuid4().hex}"
        def ssh(command, check=True):
            return subprocess.run(["ssh", *options, HOST, command], check=check)
        ssh(f"umask 077 && mkdir {shlex.quote(incoming)}")
        try:
            subprocess.run(["scp", *options, str(controller), str(archive), f"{HOST}:{incoming}/"], check=True)
            command = ["sudo", "-n", "/usr/bin/python3.13", "-B", f"{incoming}/remote.py",
                       action, sha, f"{incoming}/release.tar.gz", identity["archive_sha256"]]
            if action == "bootstrap":
                command.append(APPROVAL)
            ssh(shlex.join(command))
        finally:
            # Only the unique upload directory is removed, never any release or state.
            ssh(f"rm -f -- {shlex.quote(incoming + '/remote.py')} {shlex.quote(incoming + '/release.tar.gz')} && rmdir -- {shlex.quote(incoming)}", check=False)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Specify preflight, bootstrap or deploy")
    main(sys.argv[1])