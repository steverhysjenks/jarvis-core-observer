import json

from app.judgement.qwen import (
    build_judgement_context,
)


def make_observer(event_count=500):
    events = [
        {
            "summary": f"Event {i}",
            "description": "x" * 200,
        }
        for i in range(event_count)
    ]

    return {
        "local_time": {
            "timezone": "Europe/London",
            "date": "2026-10-05",
            "time": "18:00:00",
        },
        "user": {
            "home": True,
            "area": "Office area",
        },
        "environment": {
            "home_mode": "Home",
        },
        "schedule": {
            "happening_now": [],
            "next_timed_event": None,
            "today_all_day": [],
            "work": {
                "normal_working_day": True,
                "ha_workday": True,
                "on_leave": False,
                "expectation": "applicable",
                "calendar_status": "free",
            },
            "events": events,
        },
        "recent_activity": {
            "window_hours": 2,
            "timeline": [],
            "event_count": 0,
        },
    }


def test_full_calendar_not_sent_to_qwen():
    observer = make_observer()

    bounded = build_judgement_context(
        observer
    )

    assert "events" not in bounded["schedule"]


def test_required_schedule_semantics_retained():
    bounded = build_judgement_context(
        make_observer()
    )

    assert "happening_now" in bounded["schedule"]
    assert "next_timed_event" in bounded["schedule"]
    assert "today_all_day" in bounded["schedule"]
    assert "work" in bounded["schedule"]


def test_large_observer_does_not_expand_judge_context():
    small = json.dumps(
        build_judgement_context(
            make_observer(1)
        )
    )

    huge = json.dumps(
        build_judgement_context(
            make_observer(1000)
        )
    )

    assert len(huge) == len(small)


def test_judgement_context_stays_small():
    bounded = json.dumps(
        build_judgement_context(
            make_observer(1000)
        ),
        separators=(",", ":"),
    )

    assert len(
        bounded.encode("utf-8")
    ) < 8192
