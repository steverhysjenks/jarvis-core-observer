import asyncio

from app.behaviour.routines import (
    learn_departure_routines,
    build_actionable_routines,
)


async def test():
    learned = await learn_departure_routines(
        days=28
    )

    actionable = build_actionable_routines(
        learned["routines"]
    )

    print("ACTIONABLE DEPARTURE ROUTINES")
    print("=============================")

    if not actionable:
        print("None")
        return

    for routine in actionable:
        percentage = round(
            routine["recurrence"] * 100
        )

        print()
        print(
            routine["weekday"],
            routine["typical_time"],
            f'[{routine["confidence"].upper()}]',
        )

        print(
            "  recurrence:",
            f'{routine["observed_days"]}/'
            f'{routine["opportunities"]}',
            f"({percentage}%)",
        )

        print(
            "  source cluster:",
            routine["source_cluster"][
                "typical_time"
            ],
        )

        print(
            "  source range:",
            routine["source_cluster"][
                "range"
            ]["earliest"],
            "-",
            routine["source_cluster"][
                "range"
            ]["latest"],
        )

        print(
            "  deviation:",
            routine["source_cluster"][
                "deviation_minutes"
            ],
            "minutes",
        )


asyncio.run(test())
