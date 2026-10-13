"""Privileged deployment controller. Execution is ONLY for approved GitLab CD.

No environment file or SQLite contents are read/changed by this controller.
"""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tarfile
import time
import uuid

CURRENT = Path("/opt/jarvis-core")
RELEASES = Path("/opt/jarvis-releases")
ENVIRONMENT = Path("/etc/jarvis-core/jarvis.env")
STATE = Path("/var/lib/jarvis-core")
SERVICE = "jarvis-core"
APPROVAL = "MIGRATE_REAL_DIRECTORY_LXC122"
CLEAN_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}


def runtime_identity():
    import pwd
    import grp
    return pwd.getpwnam("jarvis").pw_uid, grp.getgrnam("jarvis").gr_gid


def service_process():
    pid = int(run("systemctl", "show", SERVICE, "--property=MainPID", "--value", capture=True).strip())
    status = Path(f"/proc/{pid}/status").read_text()
    uid = int(re.search(r"^Uid:\s+(\d+)", status, re.M)[1])
    gid = int(re.search(r"^Gid:\s+(\d+)", status, re.M)[1])
    return Path(f"/proc/{pid}/cwd").resolve(), uid, gid


def run(*command, timeout=120, capture=False):
    return subprocess.run(command, check=True, timeout=timeout, env=CLEAN_ENV,
                          text=True, stdout=subprocess.PIPE if capture else None).stdout


def health_module(path):
    spec = importlib.util.spec_from_file_location("release_health", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def installed_health():
    # Supplied controller carries its own trusted health checker in the bundle;
    # callers provide this module after safe extraction into an upload scratch area.
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(endpoint):
        with opener.open(f"http://127.0.0.1:8000{endpoint}", timeout=5) as response:
            return json.load(response)
    return get("/health"), get("/observer/status")


def preflight():
    if os.geteuid() != 0 or sys.version_info[:2] != (3, 13):
        raise RuntimeError("Controller requires noninteractive sudo and Python 3.13")
    if Path("/etc/os-release").read_text().find('VERSION_ID="13"') < 0:
        raise RuntimeError("Expected Debian 13")
    uid, gid = runtime_identity()
    if not ENVIRONMENT.is_file() or not STATE.is_dir() or not (STATE / "jarvis.db").is_file():
        raise RuntimeError("Existing environment and SQLite state must be present")
    if ENVIRONMENT.stat().st_mode & 0o007:
        raise RuntimeError("Environment file permissions expose secrets to other users; resolve separately")
    for name, expected in (("User", "jarvis"), ("Group", "jarvis"), ("WorkingDirectory", str(CURRENT))):
        if run("systemctl", "show", SERVICE, f"--property={name}", "--value", capture=True).strip() != expected:
            raise RuntimeError(f"Unexpected service {name}")
    executable = run("systemctl", "show", SERVICE, "--property=ExecStart", "--value", capture=True)
    if "/opt/jarvis-core/.venv/bin/uvicorn" not in executable or "--workers" in executable or "--reload" in executable:
        raise RuntimeError("Service must use the expected single-instance Uvicorn executable")
    environment_files = run("systemctl", "show", SERVICE, "--property=EnvironmentFiles", "--value", capture=True)
    if str(ENVIRONMENT) not in environment_files:
        raise RuntimeError("Service must retain the production environment file")
    run("systemctl", "is-active", "--quiet", SERVICE)
    _, actual_uid, actual_gid = service_process()
    if (actual_uid, actual_gid) != (uid, gid):
        raise RuntimeError("Running service does not use jarvis:jarvis")
    if not CURRENT.is_dir() or os.path.ismount(CURRENT):
        raise RuntimeError("Application path is missing or is a mount point")
    if not (CURRENT / ".venv/bin/uvicorn").is_file():
        raise RuntimeError("Existing virtual environment is missing")
    vfs = os.statvfs("/opt")
    free = vfs.f_bavail * vfs.f_frsize
    if free < 2 * 1024**3:
        raise RuntimeError("At least 2 GiB free space is required; review release storage")
    if Path("/opt").stat().st_uid != 0 or Path("/opt").stat().st_mode & 0o022:
        raise RuntimeError("/opt must be root-owned and not group/world writable")
    if RELEASES.exists():
        if RELEASES.is_symlink() or not RELEASES.is_dir() or RELEASES.stat().st_uid != 0 or RELEASES.stat().st_mode & 0o022:
            raise RuntimeError("Release store must be a root-owned real directory")
        if RELEASES.stat().st_dev != CURRENT.stat().st_dev:
            raise RuntimeError("Bootstrap/release store must be on the same filesystem")
    if CURRENT.is_symlink() and CURRENT.resolve().parent != RELEASES:
        raise RuntimeError("Active symlink is not a direct child of the managed release store")
    health, observer = installed_health()
    if (health.get("status") != "healthy" or health.get("service") != "jarvis-core"
            or observer.get("running") is not True or observer.get("last_error") is not None
            or observer.get("cycles_completed", 0) < 1 or not observer.get("last_cycle_completed")):
        raise RuntimeError("Current service must be healthy before deployment")
    if observer.get("mode") not in {"live", "shadow"}:
        raise RuntimeError("Unknown current Observer mode")
    print(json.dumps({"operation": "read-only-preflight", "layout": "symlink" if CURRENT.is_symlink() else "real-directory",
                      "free_bytes": free, "runtime_identity": "jarvis:jarvis", "python": "3.13",
                      "version": health["version"], "observer_mode": observer["mode"]}))
    return health["version"], observer["mode"]


@contextmanager
def host_lock():
    import fcntl
    # Extra serialization against another controller outside this GitLab project.
    descriptor = os.open("/run/lock/jarvis-core-deploy.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "r+") as lock:
        details = os.fstat(lock.fileno())
        if not stat.S_ISREG(details.st_mode) or details.st_uid != 0 or details.st_nlink != 1 or details.st_mode & 0o077:
            raise RuntimeError("Unsafe deployment lock file")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def switch(target):
    if target.is_symlink() or target.parent != RELEASES or not target.is_dir() or target.resolve().parent != RELEASES.resolve():
        raise RuntimeError("Unsafe symlink target")
    temporary = CURRENT.with_name(f".jarvis-core-link-{uuid.uuid4().hex}")
    try:
        temporary.symlink_to(target)
        os.replace(temporary, CURRENT)
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def extract(bundle_path, digest, sha):
    if hashlib.sha256(bundle_path.read_bytes()).hexdigest() != digest:
        raise RuntimeError("Uploaded archive digest mismatch")
    RELEASES.mkdir(mode=0o755, exist_ok=True)
    destination = RELEASES / f"{sha}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    destination.mkdir(mode=0o755)
    with tarfile.open(bundle_path) as bundle:
        entries = bundle.getmembers()
        names = [entry.name for entry in entries]
        if len(names) != len(set(names)):
            raise RuntimeError("Duplicate archive paths")
        for entry in entries:
            allowed = (entry.name in {"requirements.txt", "RELEASE.json", "deployment/readiness.py", "deployment/health.py"}
                       or entry.name.startswith("app/") and entry.name.endswith(".py"))
            relative = Path(entry.name)
            if not allowed or not entry.isfile() or relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError("Unsafe/unexpected archive entry")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.extractfile(entry).read())
        metadata = json.loads((destination / "RELEASE.json").read_text())
        if metadata["commit"] != sha or set(names) != set(metadata["files"]) | {"RELEASE.json"}:
            raise RuntimeError("Release manifest path/commit mismatch")
        for name, expected in metadata["files"].items():
            if hashlib.sha256((destination / name).read_bytes()).hexdigest() != expected:
                raise RuntimeError("Extracted release hash mismatch")
    return destination, metadata


def prepare(destination):
    run("/usr/bin/python3.13", "-m", "venv", str(destination / ".venv"))
    python = str(destination / ".venv/bin/python")
    run(python, "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir",
        "-r", str(destination / "requirements.txt"), timeout=1200)
    run(python, "-m", "pip", "check")
    gid = runtime_identity()[1]
    # Release only: root owns code/venv; jarvis reads/executes and cannot modify code.
    for root, directories, files in os.walk(destination):
        os.chown(root, 0, gid)
        os.chmod(root, (stat.S_IMODE(os.stat(root).st_mode) & 0o755) | 0o050)
        for name in directories + files:
            path = Path(root) / name
            os.chown(path, 0, gid, follow_symlinks=False)
            if not path.is_symlink():
                mode = stat.S_IMODE(path.stat().st_mode) & 0o755
                os.chmod(path, mode | 0o040 | (0o010 if mode & 0o100 else 0))
    # No EnvironmentFile, no application server, no ASGI lifespan. Fail closed if
    # this LXC does not permit systemd private-network/read-only namespace setup.
    run("systemd-run", "--quiet", "--wait", "--pipe", "--collect",
        f"--unit=jarvis-readiness-{uuid.uuid4().hex[:12]}",
        "--property=User=jarvis", "--property=Group=jarvis", "--property=NoNewPrivileges=yes",
        "--property=ProtectSystem=strict", "--property=ProtectHome=yes",
        "--property=PrivateNetwork=yes", "--property=PrivateTmp=yes",
        "--property=InaccessiblePaths=/etc/jarvis-core /var/lib/jarvis-core",
        "--property=RuntimeMaxSec=120",
        f"--property=WorkingDirectory={destination}",
        "/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "LANG=C.UTF-8", "HOME=/nonexistent",
        python, "-I", "-B", str(destination / "deployment/readiness.py"), timeout=120)


def verify(checker, version, mode):
    run("systemctl", "is-active", "--quiet", SERVICE)
    cwd, uid, gid = service_process()
    if cwd != CURRENT.resolve():
        raise RuntimeError("Service process is not running from the activated release")
    if (uid, gid) != runtime_identity():
        raise RuntimeError("Activated service identity is not jarvis:jarvis")
    checker.wait(version, mode)

def deploy(sha, bundle_path, digest):
    old_version, mode = preflight()
    if not CURRENT.is_symlink():
        raise RuntimeError("Real-directory migration requires the separate approved bootstrap operation")
    previous = CURRENT.resolve(strict=True)
    destination, metadata = extract(bundle_path, digest, sha)
    prepare(destination)
    checker = health_module(destination / "deployment/health.py")
    try:
        run("systemctl", "stop", SERVICE)
        switch(destination)
        run("systemctl", "restart", SERVICE)
        verify(checker, metadata["application_version"], mode)
    except BaseException:
        print("Activation failed; restoring the previous application release", file=sys.stderr)
        try:
            run("systemctl", "stop", SERVICE)
            switch(previous)
            run("systemctl", "restart", SERVICE)
            verify(checker, old_version, mode)
            print("Previous release restored and verified; deployment remains FAILED", file=sys.stderr)
        except BaseException as recovery:
            raise RuntimeError("CRITICAL: automatic application rollback failed; operator recovery required") from recovery
        raise
    print(json.dumps({"activated_commit": sha, "release": str(destination), "previous": str(previous)}))


def bootstrap(sha, bundle_path, digest, approval):
    if approval != APPROVAL:
        raise RuntimeError("Explicit bootstrap approval phrase is required")
    version, mode = preflight()
    if CURRENT.is_symlink():
        raise RuntimeError("Already bootstrapped; use normal deployment")
    if RELEASES.exists() and RELEASES.stat().st_dev != CURRENT.stat().st_dev:
        raise RuntimeError("Cannot move baseline across filesystems")
    # Extract the trusted checker, but do NOT install/activate the pipeline release.
    tools, _ = extract(bundle_path, digest, sha)
    checker = health_module(tools / "deployment/health.py")
    previous = RELEASES / f"bootstrap-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    try:
        run("systemctl", "stop", SERVICE)
        os.rename(CURRENT, previous)
        switch(previous)
        run("systemctl", "restart", SERVICE)
        verify(checker, version, mode)
    except BaseException:
        print("Bootstrap failed; restoring original real-directory layout", file=sys.stderr)
        try:
            run("systemctl", "stop", SERVICE)
            # Inspect the filesystem, not a boolean set after rename: interruption
            # can happen after the atomic move but before bookkeeping executes.
            if previous.is_dir():
                if CURRENT.is_symlink():
                    CURRENT.unlink()
                elif CURRENT.exists():
                    raise RuntimeError("Refusing to overwrite an unexpected bootstrap recovery path")
                os.rename(previous, CURRENT)
            run("systemctl", "restart", SERVICE)
            verify(checker, version, mode)
        except BaseException as recovery:
            raise RuntimeError("CRITICAL: bootstrap recovery failed; operator intervention required") from recovery
        raise
    print(json.dumps({"bootstrap_complete": True, "preserved_baseline": str(previous), "active": str(CURRENT)}))


def interrupted(signum, frame):
    raise RuntimeError(f"Deployment interrupted by signal {signum}")


def main():
    action, sha, archive, digest, *approval = sys.argv[1:]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("Invalid commit SHA")
    if action == "preflight":
        preflight()
        return
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    with host_lock():
        if action == "deploy":
            deploy(sha, Path(archive), digest)
        elif action == "bootstrap":
            bootstrap(sha, Path(archive), digest, approval[0] if approval else "")
        else:
            raise RuntimeError("Unknown operation")


if __name__ == "__main__":
    main()