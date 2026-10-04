import asyncio
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.adapters.homeassistant import HomeAssistantError, ha_client


LOCAL_TIMEZONE = ZoneInfo("Europe/London")


def normalise_event(calendar: dict, event: dict) -> dict:
    start = event.get("start", {})
    end = event.get("end", {})

    return {
        "calendar": calendar["entity_id"],
        "calendar_name": calendar["attributes"].get(
            "friendly_name",
            calendar["entity_id"],
        ),
        "summary": event.get("summary"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start,
        "location": event.get("location"),
        "uid": event.get("uid"),
    }


def event_datetime(value: str, all_day: bool) -> datetime:
    if all_day:
        parsed_date = date.fromisoformat(value)
        return datetime.combine(
            parsed_date,
            time.min,
            tzinfo=LOCAL_TIMEZONE,
        )

    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)

    return parsed.astimezone(LOCAL_TIMEZONE)


def classify_events(events: list[dict], now: datetime) -> dict:
    happening_now = []
    upcoming_timed = []
    all_day_context = []

    for event in events:
        start = event_datetime(
            event["start"],
            event["all_day"],
        )
        end = event_datetime(
            event["end"],
            event["all_day"],
        )

        if start <= now < end:
            enriched = {
                **event,
                "status": "happening_now",
            }

            if event["all_day"]:
                all_day_context.append(enriched)
            else:
                happening_now.append(enriched)

        elif start > now:
            enriched = {
                **event,
                "status": "upcoming",
            }

            if event["all_day"]:
                all_day_context.append(enriched)
            else:
                enriched["starts_in_minutes"] = round(
                    (start - now).total_seconds() / 60
                )
                upcoming_timed.append(enriched)

    return {
        "happening_now": happening_now,
        "next_timed_event": (
            upcoming_timed[0]
            if upcoming_timed
            else None
        ),
        "upcoming_timed": upcoming_timed,
        "all_day_context": all_day_context,
    }


async def get_calendar_events(
    calendar: dict,
    start: datetime,
    end: datetime,
) -> list[dict]:
    try:
        events = await ha_client.get_calendar_events(
            calendar["entity_id"],
            start,
            end,
        )
    except HomeAssistantError:
        return []

    return [
        normalise_event(calendar, event)
        for event in events
    ]


async def build_calendar_context(days: int = 7) -> dict:
    now = datetime.now(LOCAL_TIMEZONE)
    end = now + timedelta(days=days)

    calendars = await ha_client.get_entities_by_domain(
        "calendar"
    )

    results = await asyncio.gather(
        *[
            get_calendar_events(calendar, now, end)
            for calendar in calendars
        ]
    )

    events = [
        event
        for calendar_events in results
        for event in calendar_events
    ]

    events.sort(
        key=lambda event: event_datetime(
            event["start"],
            event["all_day"],
        )
    )

    temporal = classify_events(events, now)

    return {
        "generated_at": now.isoformat(),
        "window": {
            "start": now.isoformat(),
            "end": end.isoformat(),
            "days": days,
        },
        "calendar_count": len(calendars),
        "event_count": len(events),
        "temporal": temporal,
        "events": events,
    }
