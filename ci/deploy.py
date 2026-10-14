"""Controlled SSH transport. Never run this script as local validation."""
import ast
import hashlib
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid

from package_release import ROOT, git, release_files, test_files, validated_sha
from deployment_policy import require_production_context

HOST = "ansible@192.168.0.62"
APPROVAL = "MIGRATE_REAL_DIRECTORY_LXC122"


def deployment_receipt(value, sha, pipeline):
    if (not re.fullmatch(r"[1-9][0-9]*", pipeline)
            or value.get("commit") != sha or value.get("pipeline") != pipeline
            or not re.fullmatch(r"[1-9][0-9]*", str(value.get("job", "")))
            or value.get("status") != "success"):
        raise RuntimeError("Missing or unrelated successful deployment receipt")
    release = value.get("release", "")
    if (not re.fullmatch(r"/opt/jarvis-releases/[A-Za-z0-9_-]+", release)
            or not release.startswith(f"/opt/jarvis-releases/{sha}-")):
        raise RuntimeError("Invalid deployed release identity")
    return release


def main(action):
    if action not in {"preflight", "bootstrap", "deploy", "acceptance"}:
        raise RuntimeError("Unknown operation")
    require_production_context(os.environ, action)
    sha = validated_sha()
    # Refuse an old manual pipeline after main has moved; revalidate a fresh pipeline.
    latest = git("ls-remote", "origin", "refs/heads/main").decode().split() if action != "acceptance" else [sha]
    if not latest or latest[0] != sha:
        raise RuntimeError("main has moved; run and approve a new validated pipeline")
    if action == "bootstrap" and os.environ.get("JARVIS_BOOTSTRAP_APPROVAL") != APPROVAL:
        raise RuntimeError("Separate bootstrap approval phrase is required")
    artifact = ROOT / "release-artifacts"
    identity = json.loads((artifact / "identity.json").read_text())
    accepting = action == "acceptance"
    expected_release = None
    if accepting:
        expected_release = deployment_receipt(
            json.loads((ROOT / "results/deployment.json").read_text()), sha, os.environ["CI_PIPELINE_ID"])
    archive = artifact / ("tests.tar.gz" if accepting else "release.tar.gz")
    controller_name = "acceptance.py" if accepting else "remote.py"
    controller = artifact / controller_name
    archive_key = "tests_archive_sha256" if accepting else "archive_sha256"
    controller_key = "acceptance_controller_sha256" if accepting else "controller_sha256"
    manifest_name = "TEST_RELEASE.json" if accepting else "RELEASE.json"
    if identity["commit"] != sha or hashlib.sha256(archive.read_bytes()).hexdigest() != identity[archive_key]:
        raise RuntimeError("Release artifact identity/integrity failure")
    trusted_controller = git("show", f"{sha}:deployment/{controller_name}")
    if controller.read_bytes() != trusted_controller or hashlib.sha256(trusted_controller).hexdigest() != identity[controller_key]:
        raise RuntimeError("Controller is not from the validated commit")
    # Independently compare artifact content with the commit, not just artifact metadata.
    expected = test_files(sha) if accepting else release_files(sha)
    with tarfile.open(archive) as bundle:
        entries = bundle.getmembers()
        if len(entries) != len(expected) + 1 or {e.name for e in entries} != set(expected) | {manifest_name}:
            raise RuntimeError("Unexpected release artifact entries")
        for entry in entries:
            if not entry.isfile():
                raise RuntimeError("Non-regular archive entry")
            data = bundle.extractfile(entry).read()
            if entry.name in expected and data != expected[entry.name]:
                raise RuntimeError("Artifact differs from validated commit")
            if entry.name == manifest_name:
                metadata = json.loads(data)
                if not accepting:
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
    if accepting:
        if metadata.get("application_files") != {name: hashlib.sha256(data).hexdigest() for name, data in release_files(sha).items()}:
            raise RuntimeError("Acceptance application hash manifest differs from commit")
        remote_controller = (artifact / "remote.py").read_bytes()
        if remote_controller != git("show", f"{sha}:deployment/remote.py") or hashlib.sha256(remote_controller).hexdigest() != identity["controller_sha256"]:
            raise RuntimeError("Acceptance dependency controller differs from commit")
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
        def ssh(command, check=True, capture=False):
            return subprocess.run(["ssh", *options, HOST, command], check=check,
                                  text=True, stdout=subprocess.PIPE if capture else None)
        ssh(f"umask 077 && mkdir {shlex.quote(incoming)}")
        report_collected = not accepting
        try:
            sources = [str(controller), str(archive)] + ([str(artifact / "remote.py")] if accepting else [])
            subprocess.run(["scp", *options, *sources, f"{HOST}:{incoming}/"], check=True)
            command = ["sudo", "-n", "/usr/bin/python3.13", "-B", f"{incoming}/{controller_name}"]
            command += [sha, f"{incoming}/{archive.name}", identity[archive_key]] if accepting else [action, sha, f"{incoming}/{archive.name}", identity[archive_key]]
            if accepting:
                command.append(expected_release)
            if action == "bootstrap":
                command.append(APPROVAL)
            result = ssh(shlex.join(command), check=not accepting, capture=action == "deploy")
            if action == "deploy":
                # Written only after the controller exits successfully, including health verification.
                activated = json.loads(result.stdout.splitlines()[-1])
                receipt = {"commit": activated["activated_commit"], "release": activated["release"],
                           "pipeline": os.environ["CI_PIPELINE_ID"], "job": os.environ["CI_JOB_ID"], "status": "success"}
                deployment_receipt(receipt, sha, os.environ["CI_PIPELINE_ID"])
                (ROOT / "results").mkdir(exist_ok=True)
                (ROOT / "results/deployment.json").write_text(json.dumps(receipt))
            if accepting:
                results = ROOT / "results"
                results.mkdir(exist_ok=True)
                subprocess.run(["scp", *options, f"{HOST}:{incoming}/production.xml", str(results / "production.xml")], check=True)
                report_collected = True
                result.check_returncode()
        finally:
            # Only the unique upload directory is removed, never any release or state.
            names = ["remote.py", "acceptance.py", "release.tar.gz", "tests.tar.gz"]
            if report_collected:
                names.append("production.xml")
            else:
                print(f"Report retrieval failed; sanitized report retained at {incoming}/production.xml", file=sys.stderr)
            cleanup = [incoming + "/" + name for name in names]
            ssh("rm -f -- " + " ".join(shlex.quote(p) for p in cleanup)
                + (" && rmdir -- " + shlex.quote(incoming) if report_collected else ""), check=False)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Specify preflight, bootstrap, deploy or acceptance")
    if sys.argv[1] != "acceptance":
        main(sys.argv[1])
    else:
        try:
            main("acceptance")
        except Exception as error:
            # Preserve fetched test failures; provide safe JUnit for transport/setup errors.
            import xml.etree.ElementTree as ET
            report = ROOT / "results/production.xml"
            report.parent.mkdir(exist_ok=True)
            if not report.exists():
                suite = ET.Element("testsuite", name="production-acceptance", tests="1", failures="1")
                ET.SubElement(ET.SubElement(suite, "testcase", name="acceptance_transport"), "failure").text = "Acceptance transport/setup failed; live details withheld"
                ET.ElementTree(suite).write(report, encoding="utf-8", xml_declaration=True)
            print(f"Production acceptance failed ({type(error).__name__}); JUnit artifact retained", file=sys.stderr)
            raise SystemExit(1)
