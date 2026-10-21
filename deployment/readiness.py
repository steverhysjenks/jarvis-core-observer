"""Import-only readiness, as jarvis in a transient sandbox. Never start ASGI lifespan."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

def verify_routes(application):
    # FastAPI 0.141 uses lazy included routers, which need not have .path.
    # Its public schema resolves direct and included routes without starting ASGI.
    paths = set(application.openapi()["paths"])
    required = {"/health", "/observer/status", "/nutrition/summary/today", "/nutrition/summary/history"}
    if not required <= paths:
        raise RuntimeError("Required post-activation endpoints are missing")


def reject_side_effects(event, arguments):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr",
                 "socket.sendto", "socket.sendmsg", "socket.bind", "sqlite3.connect",
                 "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork", "os.forkpty"}:
        raise RuntimeError("Readiness forbids network, database and subprocess side effects")


def main():
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError("Release interpreter must be Python 3.13")
    import pwd
    if os.geteuid() != pwd.getpwnam("jarvis").pw_uid:
        raise RuntimeError("Readiness must run as jarvis")
    os.environ.update({
        "HA_URL": "http://ha.invalid", "HA_TOKEN": "readiness-placeholder",
        "MUSIC_ASSISTANT_URL": "http://music.invalid", "MUSIC_ASSISTANT_TOKEN": "readiness-placeholder",
        "OLLAMA_URL": "http://ollama.invalid", "JUDGEMENT_MODEL": "readiness-only",
        "OBSERVER_MODE": "shadow", "JARVIS_CORE_API_KEY": "readiness-placeholder",
    })
    sys.addaudithook(reject_side_effects)
    for path in (ROOT / "app").rglob("*.py"):
        compile(path.read_text(), str(path), "exec")
    sys.path.insert(0, str(ROOT))
    from app.main import app
    from app.observer.runner import get_observer_status
    verify_routes(app)
    if get_observer_status()["running"]:
        raise RuntimeError("Readiness must not start an Observer")
    print("Readiness passed: imports/routes checked; no server or Observer lifespan started")


if __name__ == "__main__":
    main()
