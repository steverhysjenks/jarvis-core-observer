import asyncio

from app.behaviour.departures import build_departure_observations


async def test():
    result = await build_departure_observations(days=28)

    print("CONFIRMED PHYSICAL DEPARTURES")
    print("=============================")

    for d in result["departures"]:
        if d["confidence"] != "high":
            continue

        physical = d["door"]["closed_at"]
        offset = d["door"]["offset_seconds"]

        print(
            d["weekday"][:3],
            physical,
            "->",
            d["destination_state"],
            f"(geofence +{offset}s)",
        )


asyncio.run(test())
