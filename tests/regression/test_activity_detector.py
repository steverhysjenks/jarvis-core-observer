from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import app.observer.detectors.activity as activity


TZ = ZoneInfo("Europe/London")


def behaviour(activity_type="Walking"):
    return {
        "activity_type": activity_type,
        "day_type": "weekday",
        "typical_time": "12:30",
        "typical_activity": {
            "duration_minutes": 30,
            "distance_miles": 2.0,
        },
        "window": {
            "start": "12:00",
            "end": "14:00",
        },
    }


def analysis(
    activity_type="Walking",
    today=None,
):
    return {
        "available": True,
        "today_activities": today or [],
        "qualified_behaviours": [
            behaviour(activity_type)
        ],
    }


def context(
    *,
    home=True,
    events=None,
    calendar_capability=True,
    child_capability=True,
    children=False,
):
    return {
        "user": {
            "home": home,
        },
        "schedule": {
            "events": [] if events is None else events,
        },
        "capabilities": {
            "calendar": calendar_capability,
        },
        "household": {
            "family": {
                "capabilities": {
                    "child_presence":
                        child_capability,
                },
                "children": {
                    "any_with_me": children,
                },
            },
        },
    }


NOW = datetime(
    2026, 10, 5, 12, 15,
    tzinfo=TZ,
)


@pytest.mark.asyncio
async def test_away_user_has_no_opportunity(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return analysis()

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    result = await activity.detect_activity_opportunities(
        context(home=False),
        now=NOW,
    )

    assert result == []


@pytest.mark.asyncio
async def test_unavailable_behaviour_fails_closed(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return {
            "available": False,
        }

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    result = await activity.detect_activity_opportunities(
        context(),
        now=NOW,
    )

    assert result == []


@pytest.mark.asyncio
async def test_missing_calendar_evidence_fails_closed(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return analysis()

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    ctx = context()
    ctx["schedule"]["events"] = None

    result = await activity.detect_activity_opportunities(
        ctx,
        now=NOW,
    )

    assert result == []


@pytest.mark.asyncio
async def test_calendar_capability_unavailable_fails_closed(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return analysis()

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    result = await activity.detect_activity_opportunities(
        context(calendar_capability=False),
        now=NOW,
    )

    assert result == []


@pytest.mark.asyncio
async def test_known_empty_calendar_can_create_opportunity(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return analysis()

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    result = await activity.detect_activity_opportunities(
        context(events=[]),
        now=NOW,
    )

    assert len(result) == 1
    assert result[0]["type"] == "activity_opportunity"
    assert result[0]["activity"]["type"] == "Walking"


@pytest.mark.asyncio
async def test_completed_activity_suppresses_opportunity(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return analysis(
            today=[
                {
                    "activity_type": "Walking",
                    "duration_minutes": 20,
                }
            ]
        )

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    result = await activity.detect_activity_opportunities(
        context(),
        now=NOW,
    )

    assert result == []


@pytest.mark.asyncio
async def test_less_than_half_typical_duration_not_satisfied(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return analysis(
            today=[
                {
                    "activity_type": "Walking",
                    "duration_minutes": 14,
                }
            ]
        )

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    result = await activity.detect_activity_opportunities(
        context(),
        now=NOW,
    )

    assert len(result) == 1


@pytest.mark.asyncio
async def test_calendar_commitment_can_remove_opportunity(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return analysis()

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    events = [
        {
            "calendar": "calendar.main",
            "all_day": False,
            "start":
                "2026-10-05T12:15:00+01:00",
            "end":
                "2026-10-05T14:00:00+01:00",
        }
    ]

    result = await activity.detect_activity_opportunities(
        context(events=events),
        now=NOW,
    )

    assert result == []


@pytest.mark.asyncio
async def test_nonblocking_calendar_does_not_remove_opportunity(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return analysis()

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    events = [
        {
            "calendar": "calendar.work_free_busy",
            "all_day": False,
            "start":
                "2026-10-05T12:15:00+01:00",
            "end":
                "2026-10-05T14:00:00+01:00",
        }
    ]

    result = await activity.detect_activity_opportunities(
        context(events=events),
        now=NOW,
    )

    assert len(result) == 1


@pytest.mark.asyncio
async def test_walking_allowed_with_children(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return analysis("Walking")

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    result = await activity.detect_activity_opportunities(
        context(children=True),
        now=NOW,
    )

    assert len(result) == 1
    assert (
        result[0]["constraints"]["family"]["permitted"]
        is True
    )


@pytest.mark.asyncio
async def test_walking_allowed_when_family_context_unknown(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return analysis("Walking")

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    result = await activity.detect_activity_opportunities(
        context(
            child_capability=False,
            children=None,
        ),
        now=NOW,
    )

    assert len(result) == 1

    assert (
        result[0]["constraints"]["family"]["reason"]
        == "permitted_family_context_optional"
    )


@pytest.mark.asyncio
async def test_other_activity_blocked_with_children(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return analysis("Cycling")

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    result = await activity.detect_activity_opportunities(
        context(children=True),
        now=NOW,
    )

    assert result == []


@pytest.mark.asyncio
async def test_other_activity_fails_closed_without_family_context(
    monkeypatch,
):
    async def fake_analysis(**kwargs):
        return analysis("Cycling")

    monkeypatch.setattr(
        activity,
        "analyse_activity_behaviour",
        fake_analysis,
    )

    result = await activity.detect_activity_opportunities(
        context(
            child_capability=False,
            children=None,
        ),
        now=NOW,
    )

    assert result == []
