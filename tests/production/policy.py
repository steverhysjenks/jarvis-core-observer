"""Reviewable production acceptance policy; pure functions, no network access."""
import json
from pathlib import Path
from urllib.parse import urlsplit

DETERMINISTIC = {
    "test_action_executor.py", "test_action_policy.py", "test_activity_detector.py",
    "test_areas.py", "test_availability.py", "test_bounded_judgement.py",
    "test_departure_behaviour.py", "test_detector_orchestration.py", "test_enrichment.py",
    "test_evaluator_integration.py", "test_import_contracts.py", "test_judgement_contract.py",
    "test_ledger_lifecycle.py", "test_observer_cycle.py", "test_replay.py", "test_resolver.py",
    "test_routine_math.py", "test_voice_routing.py", "test_waste_detector.py",
}
APPROVED = DETERMINISTIC | {"test_context_live.py", "test_observer_live.py", "test_production_integrations.py"}
EXCLUDED = {"test_qwen_live.py", "test_isolation_guards.py"}
PRODUCTION_DATABASE = "file:/var/lib/jarvis-core/jarvis.db?mode=ro"


def origin(value):
    url = urlsplit(str(value))
    return url.scheme, url.hostname, url.port or (443 if url.scheme == "https" else 80)


def readonly_request(method, url, content, endpoints):
    parsed = urlsplit(str(url))
    if parsed.username or parsed.password or parsed.scheme not in {"http", "https"}:
        return False
    target, path = origin(url), parsed.path
    if target == origin(endpoints["jarvis"]):
        return method == "GET" and path in {"/health", "/observer/status", "/context/observer"}
    if target == origin(endpoints["ha"]):
        return method == "GET" and (path in {"/api/", "/api/states"} or
                                    path.startswith(("/api/states/", "/api/calendars/", "/api/history/period/")))
    if target == origin(endpoints["ollama"]):
        return method == "GET" and path == "/api/tags"
    if target == origin(endpoints["music"]) and method == "POST" and path == "/api":
        try:
            payload = json.loads(content)
            return (payload.get("command") == "music/genres/library_items"
                    and isinstance(payload.get("args"), dict)
                    and 1 <= int(payload["args"].get("limit", 0)) <= 100)
        except (ValueError, TypeError, AttributeError):
            return False
    return False


def readonly_sqlite(database, *, uri, workspace):
    if str(database) == PRODUCTION_DATABASE:
        return uri
    if str(database) == ":memory:":
        return True
    if str(database).startswith("file:"):
        return False
    return Path(database).resolve().is_relative_to(Path(workspace).resolve())