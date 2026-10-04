import asyncio

from app.behaviour.routines import learn_departure_routines


async def test():
    result = await learn_departure_routines(
        days=28
    )

    print("LEARNED DEPARTURE ROUTINES")
    print("==========================")

    print(
        "Window:",
        result.get("window_start"),
        "->",
        result.get("window_end"),
    )

    for routine in result["routines"]:
        print()
        print(
            routine["day_type"].upper(),
            routine["typical_time"],
            f'[{routine["confidence"].upper()}]',
        )

        print(
            "  range:",
            routine["observed_range"]["earliest"],
            "-",
            routine["observed_range"]["latest"],
        )

        print(
            "  samples:",
            routine["samples"],
        )

        print(
            "  deviation:",
            routine[
                "standard_deviation_minutes"
            ],
            "minutes",
        )

        print(
            "  qualifying weekdays:",
            routine["qualifying_weekdays"],
        )

        print("  recurrence:")

        for weekday, details in (
            routine["weekday_recurrence"].items()
        ):
            marker = (
                "*"
                if details["qualifies"]
                else " "
            )

            percentage = round(
                details["recurrence"] * 100
            )

            print(
                f"   {marker} {weekday:<9}",
                f'{details["observed_days"]}/'
                f'{details["opportunities"]}',
                f"({percentage}%)",
                "typical",
                details["typical_time"],
            )

        print("  observations:")

        for observation in routine["observations"]:
            print(
                "   ",
                observation["date"],
                observation["weekday"][:3],
                observation["time"],
            )


asyncio.run(test())
