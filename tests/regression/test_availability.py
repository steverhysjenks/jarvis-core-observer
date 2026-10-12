from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.context.availability import (
    _resolve_overlapping_status,
)


TZ = ZoneInfo("Europe/London")


def dt(hour, minute=0):
    return datetime(
        2026,
        10,
        6,
        hour,
        minute,
        tzinfo=TZ,
    )


def event(status, start, end):
    return {
        "summary": status,
        "start": {
            "dateTime": start.isoformat(),
        },
        "end": {
            "dateTime": end.isoformat(),
        },
    }


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["Free"], "free"),
        (["Free", "Tentative"], "tentative"),
        (["Free", "Busy"], "busy"),
        (["Free", "Away"], "away"),
        (
            ["Free", "Tentative", "Busy"],
            "busy",
        ),
        (
            ["Free", "Tentative", "Busy", "Away"],
            "away",
        ),
    ],
)
def test_work_status_precedence(statuses, expected):
    events = [
        event(
            status,
            dt(8),
            dt(17),
        )
        for status in statuses
    ]

    resolved, evidence = (
        _resolve_overlapping_status(
            events,
            dt(12),
        )
    )

    assert resolved == expected
    assert len(evidence) == len(statuses)


def test_event_outside_window_is_not_active():
    events = [
        event(
            "Busy",
            dt(8),
            dt(9),
        )
    ]

    resolved, evidence = (
        _resolve_overlapping_status(
            events,
            dt(12),
        )
    )

    assert resolved == "unknown"
    assert evidence == []


def test_unknown_summary_does_not_become_free():
    events = [
        event(
            "Something Strange",
            dt(8),
            dt(17),
        )
    ]

    resolved, evidence = (
        _resolve_overlapping_status(
            events,
            dt(12),
        )
    )

    assert resolved == "unknown"
    assert evidence == []


def test_end_time_is_exclusive():
    events = [
        event(
            "Busy",
            dt(8),
            dt(9),
        )
    ]

    resolved, _ = (
        _resolve_overlapping_status(
            events,
            dt(9),
        )
    )

    assert resolved == "unknown"
