from datetime import datetime
from zoneinfo import ZoneInfo

from app.behaviour.departures import (
    extract_door_cycles,
    extract_home_exits,
    correlate_departures,
)

TZ = ZoneInfo("Europe/London")


def iso(hour, minute, second=0):
    return datetime(
        2026, 10, 5,
        hour, minute, second,
        tzinfo=TZ,
    ).isoformat()


def test_door_baseline_not_treated_as_event():
    history = [
        {
            "state": "off",
            "last_changed": iso(8, 0),
        },
        {
            "state": "on",
            "last_changed": iso(8, 10),
        },
        {
            "state": "off",
            "last_changed": iso(8, 11),
        },
    ]

    cycles = extract_door_cycles(history)

    assert len(cycles) == 1
    assert cycles[0]["opened_at"].minute == 10
    assert cycles[0]["closed_at"].minute == 11


def test_unclosed_door_does_not_create_cycle():
    history = [
        {
            "state": "off",
            "last_changed": iso(8, 0),
        },
        {
            "state": "on",
            "last_changed": iso(8, 10),
        },
    ]

    assert extract_door_cycles(history) == []


def test_home_to_not_home_is_exit():
    history = [
        {
            "state": "home",
            "last_changed": iso(8, 0),
        },
        {
            "state": "not_home",
            "last_changed": iso(8, 12),
        },
    ]

    exits = extract_home_exits(history)

    assert len(exits) == 1
    assert exits[0]["from"] == "home"
    assert exits[0]["to"] == "not_home"


def test_home_to_named_zone_is_exit():
    history = [
        {
            "state": "home",
            "last_changed": iso(8, 0),
        },
        {
            "state": "School",
            "last_changed": iso(8, 12),
        },
    ]

    exits = extract_home_exits(history)

    assert len(exits) == 1
    assert exits[0]["to"] == "School"


def test_unknown_state_does_not_create_exit():
    history = [
        {
            "state": "home",
            "last_changed": iso(8, 0),
        },
        {
            "state": "unknown",
            "last_changed": iso(8, 10),
        },
    ]

    assert extract_home_exits(history) == []


def test_door_cycle_plus_exit_creates_high_confidence_departure():
    cycles = [
        {
            "opened_at": datetime(
                2026, 10, 5, 8, 10,
                tzinfo=TZ,
            ),
            "closed_at": datetime(
                2026, 10, 5, 8, 11,
                tzinfo=TZ,
            ),
        }
    ]

    exits = [
        {
            "time": datetime(
                2026, 10, 5, 8, 12,
                tzinfo=TZ,
            ),
            "from": "home",
            "to": "School",
        }
    ]

    result = correlate_departures(
        exits,
        cycles,
    )

    assert len(result) == 1

    departure = result[0]

    assert departure["type"] == "user_departure"
    assert departure["confidence"] == "high"
    assert departure["destination_state"] == "School"

    assert "primary_entrance_used" in (
        departure["evidence"]
    )

    assert "user_left_home_zone" in (
        departure["evidence"]
    )

    # Physical door close owns departure time.
    assert departure["local_time"] == "08:11:00"


def test_door_cycle_without_exit_is_not_departure():
    cycles = [
        {
            "opened_at": datetime(
                2026, 10, 5, 8, 10,
                tzinfo=TZ,
            ),
            "closed_at": datetime(
                2026, 10, 5, 8, 11,
                tzinfo=TZ,
            ),
        }
    ]

    assert correlate_departures(
        [],
        cycles,
    ) == []


def test_exit_without_door_cycle_is_not_high_confidence_departure():
    exits = [
        {
            "time": datetime(
                2026, 10, 5, 8, 12,
                tzinfo=TZ,
            ),
            "from": "home",
            "to": "School",
        }
    ]

    assert correlate_departures(
        exits,
        [],
    ) == []
