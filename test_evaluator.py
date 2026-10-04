import asyncio
import json

from app.observer.evaluator import (
    evaluate_candidate,
)
from app.storage.ledger import (
    recent_entries,
)


observer = {
    "generated_at":
        "2026-09-30T15:30:00+01:00",
    "local_time": {
        "timezone": "Europe/London",
        "date": "2026-09-30",
        "time": "15:30:00",
        "utc_offset": "+0100",
        "dst": True,
    },
    "user": {
        "home": True,
        "area": "Office area",
        "floor": "Ground Floor",
        "location_source": "bermuda",
    },
    "environment": {
        "home_mode": "Home",
    },
    "schedule": {
        "happening_now": [],
        "next_timed_event": None,
        "today_all_day": [],
    },
    "recent_activity": {
        "window_hours": 2,
        "timeline": [],
        "event_count": 0,
    },
}


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
            "earliest": "15:11",
            "latest": "15:17",
        },
        "deviation_minutes": 3.0,
    },
    "current": {
        "time":
            "2026-09-30T15:30:00+01:00",
        "minutes_from_expected": 16.0,
        "user_home": True,
        "user_area": "Office area",
    },
}


async def main():
    result = await evaluate_candidate(
        observer,
        candidate,
        mode="shadow",
    )

    print("=== EVALUATION ===")
    print(
        json.dumps(
            result,
            indent=2,
        )
    )

    print()
    print("=== LEDGER ===")
    print(
        json.dumps(
            recent_entries(),
            indent=2,
        )
    )


asyncio.run(main())
