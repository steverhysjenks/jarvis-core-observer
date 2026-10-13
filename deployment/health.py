"""Post-restart checks against loopback only; never import application code."""
import json
import time
import urllib.request

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(endpoint):
    with OPENER.open(f"http://127.0.0.1:8000{endpoint}", timeout=5) as response:
        return json.load(response)


def wait(version, mode, timeout=180):
    deadline = time.monotonic() + timeout
    last = "not ready"
    while time.monotonic() < deadline:
        try:
            health, observer = get("/health"), get("/observer/status")
            if (health.get("status") == "healthy" and health.get("service") == "jarvis-core"
                    and health.get("version") == version and observer.get("running") is True
                    and observer.get("mode") == mode and observer.get("last_error") is None
                    and observer.get("cycles_completed", 0) >= 1
                    and observer.get("last_cycle_completed")):
                return
            last = "health/version/mode/first successful Observer cycle not ready"
        except Exception as error:
            last = type(error).__name__
        time.sleep(2)
    raise RuntimeError(f"Post-activation verification failed: {last}")