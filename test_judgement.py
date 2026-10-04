import asyncio
import json

from app.observer.context import (
    build_observer_context,
)
from app.judgement.qwen import (
    judge_candidate,
)


async def test():
    observer = await build_observer_context()

    observer["local_time"] = {
        "timezone": "Europe/London",
        "date": "2026-09-30",
        "time": "15:20:00",
        "utc_offset": "+0100",
        "dst": True,
    }

    observer["user"]["home"] = True
    observer["user"]["area"] = "Office area"

    candidate = {
        "type": "routine_departure_deviation",
        "priority": "candidate",
        "reason":
            "user_home_during_expected_departure_window",
        "routine": {
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
        },
        "current": {
            "time":
                "2026-09-30T15:20:00+01:00",
            "minutes_from_expected": 6.0,
            "user_home": True,
            "user_area": "Office area",
        },
    }

    result = await judge_candidate(
        observer,
        candidate,
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


asyncio.run(test())
