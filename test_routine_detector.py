import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.observer.context import build_observer_context
from app.observer.detectors.routine_departure import (
    detect_routine_departure_deviation,
)


TZ = ZoneInfo("Europe/London")


async def run_test(label, test_time):
    context = await build_observer_context()

    # Force home=true for deterministic testing.
    # We're testing detector logic here, not HA presence.
    context.setdefault("user", {})
    context["user"]["home"] = True

    result = (
        await detect_routine_departure_deviation(
            context,
            now=test_time,
        )
    )

    print()
    print(label)
    print("=" * len(label))
    print("Test time:", test_time)
    print("Candidates:", len(result))

    for candidate in result:
        print(candidate)


async def main():
    # Wednesday's learned routine is ~15:14.

    await run_test(
        "BEFORE WINDOW",
        datetime(
            2026, 9, 30,
            14, 50,
            tzinfo=TZ,
        ),
    )

    await run_test(
        "APPROACHING ROUTINE",
        datetime(
            2026, 9, 30,
            15, 8,
            tzinfo=TZ,
        ),
    )

    await run_test(
        "PAST EXPECTED DEPARTURE",
        datetime(
            2026, 9, 30,
            15, 20,
            tzinfo=TZ,
        ),
    )

    await run_test(
        "STALE",
        datetime(
            2026, 9, 30,
            16, 0,
            tzinfo=TZ,
        ),
    )


asyncio.run(main())
