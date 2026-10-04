import asyncio
import copy
import json
from datetime import datetime

from app.observer.context import (
    build_observer_context,
)
from app.judgement.qwen import (
    judge_candidate,
)


ROUTINE = {
    "weekday": "Wednesday",
    "typical_time": "15:14",
    "confidence": "strong",
    "recurrence": 1.0,
    "observed_days": 4,
    "opportunities": 4,
    "source_range": {
        "earliest": "15:02",
        "latest": "15:17",
    },
    "deviation_minutes": 4.8,
}


def make_candidate(
    time_string,
    minutes_from_expected,
):
    return {
        "type": "routine_departure_deviation",
        "priority": "candidate",
        "reason":
            "user_home_during_expected_departure_window",
        "routine": copy.deepcopy(
            ROUTINE
        ),
        "current": {
            "time":
                f"2026-09-30T{time_string}:00+01:00",
            "minutes_from_expected":
                minutes_from_expected,
            "user_home": True,
            "user_area": "Office area",
        },
    }


async def run_case(
    name,
    base_observer,
    time_string,
    minutes_from_expected,
    *,
    home=True,
    calendar_event=None,
):
    observer = copy.deepcopy(
        base_observer
    )

    observer["local_time"] = {
        "timezone": "Europe/London",
        "date": "2026-09-30",
        "time": f"{time_string}:00",
        "utc_offset": "+0100",
        "dst": True,
    }

    observer["user"]["home"] = home
    observer["user"]["area"] = (
        "Office area"
        if home
        else None
    )

    if calendar_event is not None:
        observer["schedule"][
            "next_timed_event"
        ] = calendar_event
    else:
        observer["schedule"][
            "next_timed_event"
        ] = None

    candidate = make_candidate(
        time_string,
        minutes_from_expected,
    )

    candidate["current"][
        "user_home"
    ] = home

    result = await judge_candidate(
        observer,
        candidate,
    )

    print()
    print(name)
    print("=" * len(name))

    print(
        json.dumps(
            result["judgement"],
            indent=2,
        )
    )


async def main():
    observer = (
        await build_observer_context()
    )

    await run_case(
        "APPROACHING - 15:08",
        observer,
        "15:08",
        -6,
    )

    await run_case(
        "EXPECTED TIME - 15:14",
        observer,
        "15:14",
        0,
    )

    await run_case(
        "SLIGHTLY LATE - 15:20",
        observer,
        "15:20",
        6,
    )

    await run_case(
        "CLEARLY LATE - 15:30",
        observer,
        "15:30",
        16,
    )

    calendar_event = {
        "calendar": "calendar.test",
        "calendar_name": "Test",
        "summary": "School pickup",
        "start":
            "2026-09-30T15:30:00+01:00",
        "end":
            "2026-09-30T16:00:00+01:00",
        "all_day": False,
        "location": "School",
        "status": "upcoming",
        "starts_in_minutes": 10,
    }

    await run_case(
        "LATE + CALENDAR - 15:20",
        observer,
        "15:20",
        6,
        calendar_event=calendar_event,
    )

    await run_case(
        "ALREADY AWAY - 15:20",
        observer,
        "15:20",
        6,
        home=False,
    )


asyncio.run(main())
