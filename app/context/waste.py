import asyncio
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from app.adapters.homeassistant import ha_client


LOCAL_TIMEZONE = ZoneInfo("Europe/London")

# These are currently the Home Assistant calendar capabilities
# providing waste collection information.
WASTE_CALENDARS = (
    "calendar.bins",
    "calendar.bins_2",
)

# Explicit household knowledge:
# bins may be put outside from 19:00 on the evening
# before collection.
PUT_OUT_FROM = time(hour=19, minute=0)


async def build_waste_context(
    days: int = 7,
    now: datetime | None = None,
) -> dict:
    if now is None:
        now = datetime.now(LOCAL_TIMEZONE)
    else:
        now = now.astimezone(LOCAL_TIMEZONE)

    end = now + timedelta(days=days)

    results = await asyncio.gather(
        *[
            ha_client.get_calendar_events(
                entity_id,
                now,
                end,
            )
            for entity_id in WASTE_CALENDARS
        ],
        return_exceptions=True,
    )

    collections = []

    for entity_id, result in zip(
        WASTE_CALENDARS,
        results,
    ):
        if isinstance(result, Exception):
            continue

        for event in result:
            start = event.get("start", {})
            collection_date = start.get("date")

            # Waste collection events are expected to be
            # all-day calendar events.
            if not collection_date:
                continue

            collections.append(
                {
                    "calendar": entity_id,
                    "date": collection_date,
                    "type": event.get("summary"),
                    "uid": event.get("uid"),
                }
            )

    collections.sort(
        key=lambda item: (
            item["date"],
            item["type"] or "",
        )
    )

    if not collections:
        return {
            "next_collection": None,
            "preparation_window": None,
        }

    next_date = collections[0]["date"]

    same_day = [
        item
        for item in collections
        if item["date"] == next_date
    ]

    collection_date = datetime.fromisoformat(
        next_date
    ).date()

    preparation_date = (
        collection_date - timedelta(days=1)
    )

    preparation_start = datetime.combine(
        preparation_date,
        PUT_OUT_FROM,
        tzinfo=LOCAL_TIMEZONE,
    )

    collection_start = datetime.combine(
        collection_date,
        time.min,
        tzinfo=LOCAL_TIMEZONE,
    )

    window_active = (
        preparation_start
        <= now
        < collection_start
    )

    return {
        "next_collection": {
            "date": next_date,
            "types": [
                item["type"]
                for item in same_day
            ],
            "sources": [
                item["calendar"]
                for item in same_day
            ],
        },
        "preparation_window": {
            "starts": preparation_start.isoformat(),
            "ends": collection_start.isoformat(),
            "active": window_active,
            "put_out_from": PUT_OUT_FROM.strftime(
                "%H:%M"
            ),
        },
    }
