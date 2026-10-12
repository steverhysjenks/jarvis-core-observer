import json

import app.observer.resolver as resolver


def entry(
    candidate_type="routine_departure_deviation",
    payload=None,
):
    return {
        "candidate_key": "routine:test",
        "candidate_type": candidate_type,
        "candidate_json": json.dumps(
            payload or {
                "type":
                    "routine_departure_deviation"
            }
        ),
    }


def test_routine_stays_open_while_user_home(
    monkeypatch,
):
    called = False

    def fake_mark(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        resolver,
        "mark_resolved",
        fake_mark,
    )

    result = resolver.resolve_routine_departure(
        entry(),
        {
            "user": {
                "home": True,
            }
        },
    )

    assert result is None
    assert called is False


def test_routine_resolves_when_user_leaves(
    monkeypatch,
):
    def fake_mark(key, reason):
        return {
            "candidate_key": key,
            "status": "resolved",
            "resolved_at":
                "2026-10-05T18:00:00+01:00",
            "resolution_reason": reason,
        }

    monkeypatch.setattr(
        resolver,
        "mark_resolved",
        fake_mark,
    )

    result = resolver.resolve_routine_departure(
        entry(),
        {
            "user": {
                "home": False,
            }
        },
    )

    assert result["resolved"] is True
    assert (
        result["reason"]
        == "primary_user_no_longer_home"
    )


def test_unknown_candidate_type_fails_closed(
    monkeypatch,
):
    monkeypatch.setattr(
        resolver,
        "open_entries",
        lambda: [
            entry(candidate_type="future_unknown_type")
        ],
    )

    result = resolver.resolve_open_situations(
        {
            "user": {
                "home": False,
            }
        }
    )

    assert result == []


def test_malformed_persisted_candidate_fails_closed(
    monkeypatch,
):
    broken = entry()
    broken["candidate_json"] = "{broken-json"

    monkeypatch.setattr(
        resolver,
        "open_entries",
        lambda: [broken],
    )

    result = resolver.resolve_open_situations(
        {
            "user": {
                "home": False,
            }
        }
    )

    assert result == []
