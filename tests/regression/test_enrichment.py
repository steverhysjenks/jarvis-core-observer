from app.observer.enrichment import (
    enrich_candidate,
)


def observer(work_status="busy"):
    return {
        "user": {
            "home": True,
            "area": "Office area",
        },
        "schedule": {
            "work": {
                "normal_working_day": True,
                "ha_workday": True,
                "on_leave": False,
                "expectation": "applicable",
                "calendar_status": work_status,
            },
            "next_timed_event": None,
            "events": [],
        },
        "capabilities": {
            "calendar": True,
        },
    }


def test_work_context_becomes_candidate_facts():
    candidate = {
        "type": "test_context",
    }

    enriched = enrich_candidate(
        observer("busy"),
        candidate,
    )

    facts = enriched["facts"]

    assert facts[
        "user_currently_home"
    ] is True

    assert facts["user_area"] == "Office area"

    assert facts[
        "work_normal_working_day"
    ] is True

    assert facts[
        "work_ha_workday"
    ] is True

    assert facts[
        "work_on_leave"
    ] is False

    assert facts[
        "work_expectation"
    ] == "applicable"

    assert facts[
        "work_calendar_status"
    ] == "busy"


def test_away_does_not_change_home_state():
    enriched = enrich_candidate(
        observer("away"),
        {
            "type": "test_context",
        },
    )

    facts = enriched["facts"]

    assert facts[
        "work_calendar_status"
    ] == "away"

    assert facts[
        "user_currently_home"
    ] is True


def test_free_does_not_change_home_state():
    enriched = enrich_candidate(
        observer("free"),
        {
            "type": "test_context",
        },
    )

    facts = enriched["facts"]

    assert facts[
        "work_calendar_status"
    ] == "free"

    assert facts[
        "user_currently_home"
    ] is True
