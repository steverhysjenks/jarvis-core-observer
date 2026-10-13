"""Privileged deployment controller. Execution is ONLY for approved GitLab CD.

No environment file or SQLite contents are read/changed by this controller.
"""
from contextlib import contextmanager
import errno
import hashlib
import importlib.util
import json
import math
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


class StartupPending(RuntimeError):
    """A narrowly retryable startup observation; never a successful verification."""
    def __init__(self, message, snapshot=None):
        super().__init__(message)
        self.snapshot = snapshot or {}


def startup_budget(deadline, maximum):
    if deadline is None:
        return maximum
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise StartupPending("Startup inspection deadline exhausted")
    return min(maximum, remaining)


def service_state(*, deadline=None):
    value = run("systemctl", "show", SERVICE, "--property=User", "--property=Group",
                "--property=ActiveState", "--property=SubState", timeout=startup_budget(deadline, 5), capture=True)
    return dict(line.split("=", 1) for line in value.splitlines() if "=" in line)


def startup_cwd(pid):
    # Diagnostics only: never run the jarvis fallback for an unverified identity.
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError as error:
        return f"<unavailable: {type(error).__name__}>"


def transitional_identity(uids, gids, uid, gid):
    return (len(uids) == 4 and len(gids) == 4
            and all(value in {0, uid} for value in uids)
            and all(value in {0, gid} for value in gids)
            and (any(value != uid for value in uids) or any(value != gid for value in gids)))


class DeploymentFailure(RuntimeError):
    """Activation failed, but the old release/layout was restored and verified."""


class RollbackActionFailure(RuntimeError):
    """The stop/restore/restart recovery operations did not complete."""


class RollbackVerificationFailure(RuntimeError):
    """Recovery operations completed, but restored-service verification failed."""


# Fixed, read-only stdlib probe; no app imports, environment or SQLite access.
CWD_PROBE = (
    "import json,os,sys; p='/proc/'+str(int(sys.argv[1]))+'/cwd'; "
    "c=os.readlink(p); s=os.stat(p); "
    "print(json.dumps({'cwd':c,'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode}))"
)


def main_pid(*, deadline=None):
    pid = int(run("systemctl", "show", SERVICE, "--property=MainPID", "--value", timeout=startup_budget(deadline, 5), capture=True).strip())
    if pid <= 0:
        raise StartupPending(f"Service has no running MainPID: pid={pid}", {"pid": pid, "cwd": "<not available>"})
    return pid


def process_directory(pid, *, deadline=None):
    link = f"/proc/{pid}/cwd"
    try:
        cwd = os.readlink(link)
        details = os.stat(link)
        return {"cwd": cwd, "device": details.st_dev, "inode": details.st_ino, "mode": details.st_mode}
    except OSError as error:
        if error.errno == errno.ENOENT:
            raise StartupPending(f"Service process disappeared while inspecting cwd: pid={pid}", {"pid": pid, "cwd": "<process disappeared>"}) from error
        if error.errno not in {errno.EACCES, errno.EPERM}:
            raise RuntimeError(f"Cannot inspect service cwd: pid={pid}, proc_link={link}, error={type(error).__name__}") from error
        # LXC root can lack CAP_SYS_PTRACE for a different-UID process. Read as
        # the already-verified jarvis identity, rather than weakening the check.
        try:
            return json.loads(run("/usr/sbin/runuser", "-u", "jarvis", "--",
                                  "/usr/bin/python3.13", "-I", "-B", "-c", CWD_PROBE, str(pid),
                                  timeout=startup_budget(deadline, 15), capture=True))
        except subprocess.TimeoutExpired as fallback:
            raise StartupPending(f"Service cwd probe timed out: pid={pid}", {"pid": pid, "cwd": "<probe timed out>"}) from fallback
        except StartupPending:
            raise
        except Exception as fallback:
            raise RuntimeError(f"Cannot inspect service cwd even as jarvis: pid={pid}, proc_link={link}, error={type(fallback).__name__}") from fallback


def service_process(*, deadline=None):
    pid = main_pid(deadline=deadline)
    try:
        status = Path(f"/proc/{pid}/status").read_text()
        uids = tuple(map(int, re.search(r"^Uid:\s+(.+)$", status, re.M)[1].split()))
        gids = tuple(map(int, re.search(r"^Gid:\s+(.+)$", status, re.M)[1].split()))
    except FileNotFoundError as error:
        raise StartupPending(f"Service process disappeared before identity inspection: pid={pid}", {"pid": pid, "cwd": "<process disappeared>"}) from error
    except (OSError, TypeError, ValueError) as error:
        raise RuntimeError(f"Cannot inspect service identity: pid={pid}, error={type(error).__name__}") from error
    uid, gid = runtime_identity()
    if len(uids) != 4 or len(gids) != 4 or any(value != uid for value in uids) or any(value != gid for value in gids):
        message = f"Service identity is not jarvis:jarvis: pid={pid}, actual_uids={uids}, actual_gids={gids}, expected_uid={uid}, expected_gid={gid}"
        if transitional_identity(uids, gids, uid, gid):
            raise StartupPending(message, {"pid": pid, "uid": uids[1], "gid": gids[1],
                                           "uids": uids, "gids": gids, "cwd": startup_cwd(pid)})
        raise RuntimeError(message)
    directory = process_directory(pid, deadline=deadline)
    if not isinstance(directory, dict):
        raise RuntimeError(f"Invalid cwd inspection payload: pid={pid}")
    if (not isinstance(directory.get("cwd"), str) or not directory["cwd"]
            or directory["cwd"].endswith(" (deleted)")
            or not isinstance(directory.get("device"), int) or not isinstance(directory.get("inode"), int)
            or not stat.S_ISDIR(directory.get("mode", 0))):
        raise RuntimeError(f"Invalid/deleted service cwd: pid={pid}, actual_cwd={directory.get('cwd')!r}")
    observed_pid = main_pid(deadline=deadline)
    if observed_pid != pid:
        raise StartupPending(f"Service MainPID changed while inspecting cwd: initial_pid={pid}, observed_pid={observed_pid}",
                             {**directory, "pid": pid, "uid": uid, "gid": gid})
    return {**directory, "pid": pid, "uid": uid, "gid": gid}

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
    process = service_process()
    actual_uid, actual_gid = process["uid"], process["gid"]
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


def verify(checker, version, mode, expected_release, *, startup_timeout=30, poll_interval=0.5):
    expected = Path(os.fspath(expected_release)).resolve(strict=True)
    expected_stat = expected.stat()
    if not stat.S_ISDIR(expected_stat.st_mode):
        raise RuntimeError(f"Expected release is not a directory: expected_release={expected}")
    expected_identity = (expected_stat.st_dev, expected_stat.st_ino)
    active_stat = CURRENT.stat()
    if (active_stat.st_dev, active_stat.st_ino) != expected_identity:
        raise RuntimeError(f"Active application path does not identify expected release: active={CURRENT}, expected_release={expected}")
    def inspect(*, allow_startup=False, deadline=None):
        try:
            process = service_process(deadline=deadline) if deadline is not None else service_process()
        except StartupPending as pending:
            if allow_startup:
                raise
            raise RuntimeError(f"Settled service became unready during final verification: pid={pending.snapshot.get('pid', '<unknown>')}, actual_uid={pending.snapshot.get('uid', '<unknown>')}, actual_gid={pending.snapshot.get('gid', '<unknown>')}, actual_cwd={pending.snapshot.get('cwd', '<unknown>')!r}, expected_release={expected}; {pending}") from pending
        except RuntimeError as error:
            raise RuntimeError(f"Service verification inspection failed: expected_release={expected}; {error}") from error
        diagnostics = (f"pid={process['pid']}, actual_cwd={process['cwd']!r}, expected_release={str(expected)!r}, "
                       f"actual_directory_id={(process['device'], process['inode'])}, expected_directory_id={expected_identity}")
        uid, gid = runtime_identity()
        if (process["uid"], process["gid"]) != (uid, gid):
            if allow_startup and process["uid"] in {0, uid} and process["gid"] in {0, gid}:
                raise StartupPending(f"Activated service identity is not jarvis:jarvis: {diagnostics}", process)
            raise RuntimeError(f"Activated service identity is not jarvis:jarvis: {diagnostics}")
        # Kernel directory identity, not a textual path or non-strict proc resolve.
        # Read-only bind mounts / namespace aliases may legitimately spell cwd differently.
        if (process["device"], process["inode"]) != expected_identity:
            raise RuntimeError(f"Service process is not running from the activated release: {diagnostics}")
        return process
    if not math.isfinite(startup_timeout) or not math.isfinite(poll_interval) or startup_timeout <= 0 or poll_interval <= 0:
        raise ValueError("Startup timeout and polling interval must be positive and finite")
    deadline = time.monotonic() + startup_timeout
    stable = None
    last = {"pid": "<not sampled>", "uid": "<unknown>", "gid": "<unknown>", "cwd": "<unknown>"}
    reason = "no stable process sample"
    while True:
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Service startup verification timed out after {startup_timeout}s: pid={last.get('pid', '<unknown>')}, "
                               f"actual_uid={last.get('uid', '<unknown>')}, actual_gid={last.get('gid', '<unknown>')}, "
                               f"actual_cwd={last.get('cwd', '<unknown>')!r}, expected_release={str(expected)!r}; pending={reason}")
        try:
            state = service_state(deadline=deadline)
            if state.get("User") != "jarvis" or state.get("Group") != "jarvis":
                raise RuntimeError(f"Terminal security failure: configured service identity is not jarvis:jarvis; expected_release={expected}")
            if state.get("ActiveState") not in {"activating", "active"}:
                raise RuntimeError(f"Terminal service startup failure: state={state.get('ActiveState')}, substate={state.get('SubState')}, expected_release={expected}")
            process = inspect(allow_startup=True, deadline=deadline)
            last = process
            if state.get("ActiveState") == "active" and state.get("SubState") == "running":
                if stable is not None and process["pid"] == stable["pid"] and time.monotonic() < deadline:
                    before = process
                    break
                reason = "waiting for a second matching valid MainPID sample"
                stable = process
            else:
                stable = None
                reason = "systemd startup transition has not completed"
        except StartupPending as pending:
            stable = None
            last = pending.snapshot or last
            reason = str(pending)
        except subprocess.TimeoutExpired as pending:
            stable = None
            reason = "systemd inspection exceeded remaining startup budget"
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(poll_interval, remaining))
    try:
        checker.wait(version, mode)
    except Exception as error:
        raise RuntimeError(f"Service health verification failed: pid={before['pid']}, actual_cwd={before['cwd']!r}, expected_release={expected}; {error}") from error
    after = inspect()
    if after["pid"] != before["pid"]:
        raise RuntimeError(f"Service MainPID changed during health verification: initial_pid={before['pid']}, pid={after['pid']}, actual_cwd={after['cwd']!r}, expected_release={expected}")
    active_stat = CURRENT.stat()
    if (active_stat.st_dev, active_stat.st_ino) != expected_identity:
        raise RuntimeError(f"Active release changed during health verification: pid={after['pid']}, expected_release={expected}")

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
        verify(checker, metadata["application_version"], mode, destination)
    except BaseException as activation:
        print("Activation failed; restoring the previous application release", file=sys.stderr)
        try:
            run("systemctl", "stop", SERVICE)
            switch(previous)
            run("systemctl", "restart", SERVICE)
        except BaseException as recovery:
            raise RollbackActionFailure(f"CRITICAL: deployment rollback actions failed; original_failure={activation}; recovery_error={recovery}") from recovery
        try:
            verify(checker, old_version, mode, previous)
        except BaseException as recovery:
            raise RollbackVerificationFailure(f"CRITICAL: previous release restored and service restarted, but rollback verification failed; original_failure={activation}; verification_error={recovery}") from recovery
        raise DeploymentFailure(f"Deployment unsuccessful; previous release restored and verified; original_failure={activation}") from activation
    print(json.dumps({"activated_commit": sha, "release": str(destination), "previous": str(previous)}))


def bootstrap(sha, bundle_path, digest, approval):
    if approval != APPROVAL:
        raise RuntimeError("Explicit bootstrap approval phrase is required")
    version, mode = preflight()
    if CURRENT.is_symlink():
        raise RuntimeError("Already bootstrapped; use normal deployment")
    if RELEASES.exists() and RELEASES.stat().st_dev != CURRENT.stat().st_dev:
        raise RuntimeError("Cannot move baseline across filesystems")
    tools, _ = extract(bundle_path, digest, sha)
    checker = health_module(tools / "deployment/health.py")
    previous = RELEASES / f"bootstrap-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    try:
        run("systemctl", "stop", SERVICE)
        os.rename(CURRENT, previous)
        switch(previous)
        run("systemctl", "restart", SERVICE)
        verify(checker, version, mode, previous)
    except BaseException as activation:
        print("Bootstrap failed; restoring original real-directory layout", file=sys.stderr)
        try:
            run("systemctl", "stop", SERVICE)
            if previous.is_dir():
                if CURRENT.is_symlink():
                    CURRENT.unlink()
                elif CURRENT.exists():
                    raise RuntimeError("Refusing to overwrite an unexpected bootstrap recovery path")
                os.rename(previous, CURRENT)
            run("systemctl", "restart", SERVICE)
        except BaseException as recovery:
            raise RollbackActionFailure(f"CRITICAL: bootstrap rollback actions failed; original_failure={activation}; recovery_error={recovery}") from recovery
        try:
            if CURRENT.is_symlink():
                raise RuntimeError("Bootstrap recovery did not restore the real-directory layout")
            verify(checker, version, mode, CURRENT)
        except BaseException as recovery:
            raise RollbackVerificationFailure(f"CRITICAL: original directory restored and service restarted, but bootstrap rollback verification failed; original_failure={activation}; verification_error={recovery}") from recovery
        raise DeploymentFailure(f"Bootstrap unsuccessful; original directory restored and verified; original_failure={activation}") from activation
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