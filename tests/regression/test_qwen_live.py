import copy

import pytest

from app.judgement.qwen import (
    judge_candidate,
)
from app.observer.context import (
    build_observer_context,
)


pytestmark = [
    pytest.mark.live,
    pytest.mark.behavioural,
]


def candidate():
    return {
        "type": "activity_opportunity",
        "activity": {
            "type": "walk",
            "typical_time": "lunchtime",
            "typical_duration_minutes": 35,
            "typical_distance_miles": 2.0,
        },
        "opportunity": {
            "free_minutes": 60,
            "required_minutes": 35,
            "free_start": "12:00",
            "free_end": "13:00",
        },
        "constraints": {
            "family": {
                "permitted": True,
                "children_with_me": False,
                "allowed_with_children": True,
            },
        },
        "today": {
            "matching_activity_completed": False,
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        "busy",
        "away",
        "free",
        "tentative",
    ],
)
async def test_qwen_accepts_work_semantics(
    status,
):
    observer = (
        await build_observer_context()
    )

    observer = copy.deepcopy(observer)

    observer["schedule"]["work"][
        "calendar_status"
    ] = status

    result = await judge_candidate(
        observer,
        candidate(),
    )

    assert result.get(
        "judgement_error"
    ) is None

    judgement = result["judgement"]

    assert judgement["decision"] in {
        "ignore",
        "monitor",
        "interrupt",
    }

    assert (
        0.0
        <= judgement["confidence"]
        <= 1.0
    )

    facts = result["candidate"]["facts"]

    assert (
        facts["work_calendar_status"]
        == status
    )


@pytest.mark.asyncio
async def test_qwen_away_does_not_override_home():
    observer = (
        await build_observer_context()
    )

    observer = copy.deepcopy(observer)

    observer["user"]["home"] = True

    observer["schedule"]["work"][
        "calendar_status"
    ] = "away"

    result = await judge_candidate(
        observer,
        candidate(),
    )

    assert result.get(
        "judgement_error"
    ) is None

    facts = result["candidate"]["facts"]

    assert facts[
        "user_currently_home"
    ] is True

    assert facts[
        "work_calendar_status"
    ] == "away"
