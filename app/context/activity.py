from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo

from app.adapters.homeassistant import (
    HomeAssistantError,
    ha_client,
)


LOCAL_TIMEZONE = ZoneInfo("Europe/London")

GARMIN_ACTIVITY_CALENDAR = (
    "calendar.garmin_activities"
)

DEFAULT_LOOKBACK_DAYS = 90

# HA calendar queries are deliberately bounded.
# This also avoids relying on behaviour of very large
# calendar API windows.
QUERY_CHUNK_DAYS = 28


def _event_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=LOCAL_TIMEZONE
        )

    return parsed.astimezone(LOCAL_TIMEZONE)


def _description_fields(
    description: str | None,
) -> dict[str, str]:
    fields = {}

    if not description:
        return fields

    for line in description.splitlines():
        if ":" not in line:
            continue

        key, value = line.split(":", 1)

        fields[
            key.strip().lower()
        ] = value.strip()

    return fields


def _first_field(
    fields: dict[str, str],
    *names: str,
) -> str | None:
    for name in names:
        value = fields.get(name)

        if value is not None:
            return value

    return None


def _number(
    value: str | None,
) -> float | None:
    if not value:
        return None

    # Garmin CSV values can contain thousands
    # separators, for example 4,170 steps.
    cleaned = value.replace(",", "")

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        cleaned,
    )

    if not match:
        return None

    return float(match.group(0))


def _integer(
    value: str | None,
) -> int | None:
    number = _number(value)

    if number is None:
        return None

    return int(round(number))


def _duration_seconds(
    value: str | None,
) -> float | None:
    if not value:
        return None

    # Historical CSV bootstrap:
    #   00:36:26
    #   00:06:18.3
    match = re.fullmatch(
        r"(\d+):(\d{2}):(\d{2}(?:\.\d+)?)",
        value,
    )

    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = float(match.group(3))

        return round(
            hours * 3600
            + minutes * 60
            + seconds,
            3,
        )

    # Live Garmin automation:
    #   35m 12s
    #   1h 5m 2s
    hours_match = re.search(
        r"(\d+(?:\.\d+)?)\s*h",
        value,
        re.IGNORECASE,
    )

    minutes_match = re.search(
        r"(\d+(?:\.\d+)?)\s*m",
        value,
        re.IGNORECASE,
    )

    seconds_match = re.search(
        r"(\d+(?:\.\d+)?)\s*s",
        value,
        re.IGNORECASE,
    )

    if not any(
        (
            hours_match,
            minutes_match,
            seconds_match,
        )
    ):
        return None

    hours = (
        float(hours_match.group(1))
        if hours_match
        else 0
    )

    minutes = (
        float(minutes_match.group(1))
        if minutes_match
        else 0
    )

    seconds = (
        float(seconds_match.group(1))
        if seconds_match
        else 0
    )

    return round(
        hours * 3600
        + minutes * 60
        + seconds,
        3,
    )


def normalise_activity_event(
    event: dict,
) -> dict | None:
    start_value = event.get("start", {})

    if isinstance(start_value, dict):
        start_value = (
            start_value.get("dateTime")
            or start_value.get("date")
        )

    end_value = event.get("end", {})

    if isinstance(end_value, dict):
        end_value = (
            end_value.get("dateTime")
            or end_value.get("date")
        )

    if not start_value:
        return None

    # Garmin activities are timed rather than
    # all-day events.
    if "T" not in start_value:
        return None

    start = _event_datetime(start_value)

    end = (
        _event_datetime(end_value)
        if end_value
        else None
    )

    fields = _description_fields(
        event.get("description")
    )

    # Historical ICS and the live automation use
    # slightly different labels. Both are accepted.
    activity_type = _first_field(
        fields,
        "activity",
        "activity type",
    )

    if not activity_type:
        return None

    duration_seconds = _duration_seconds(
        _first_field(
            fields,
            "duration",
            "activity duration",
        )
    )

    if (
        duration_seconds is None
        and end is not None
    ):
        duration_seconds = round(
            (end - start).total_seconds(),
            3,
        )

    elapsed_seconds = _duration_seconds(
        fields.get("elapsed time")
    )

    moving_seconds = _duration_seconds(
        fields.get("moving time")
    )

    distance_miles = _number(
        fields.get("distance")
    )

    return {
        "activity_id": _first_field(
            fields,
            "garmin activity id",
            "import key",
        ),
        "activity_id_source": (
            "garmin"
            if fields.get(
                "garmin activity id"
            )
            else (
                "import"
                if fields.get("import key")
                else None
            )
        ),
        "activity_type": activity_type,
        "title": event.get("summary"),
        "start": start.isoformat(),
        "end": (
            end.isoformat()
            if end is not None
            else None
        ),
        "date": start.date().isoformat(),
        "weekday": start.strftime("%A"),
        "local_time": start.strftime(
            "%H:%M:%S"
        ),
        "minutes_after_midnight": (
            start.hour * 60
            + start.minute
        ),
        "duration_seconds":
            duration_seconds,
        "duration_minutes": (
            round(
                duration_seconds / 60,
                1,
            )
            if duration_seconds is not None
            else None
        ),
        "elapsed_seconds":
            elapsed_seconds,
        "moving_seconds":
            moving_seconds,
        "distance_miles":
            distance_miles,
        "steps": _integer(
            fields.get("steps")
        ),
        "calories": _integer(
            fields.get("calories")
        ),
        "average_hr": _integer(
            fields.get("average hr")
        ),
        "max_hr": _integer(
            _first_field(
                fields,
                "max hr",
                "maximum hr",
            )
        ),
        "location": _first_field(
            fields,
            "location",
        ),
        "source": _first_field(
            fields,
            "source",
        ),
        "calendar_uid":
            event.get("uid"),
    }


async def _get_calendar_window(
    start: datetime,
    end: datetime,
) -> list[dict]:
    return await ha_client.get_calendar_events(
        GARMIN_ACTIVITY_CALENDAR,
        start,
        end,
    )


async def _get_calendar_history(
    start: datetime,
    end: datetime,
) -> list[dict]:
    events = []

    cursor = start

    while cursor < end:
        chunk_end = min(
            cursor + timedelta(
                days=QUERY_CHUNK_DAYS
            ),
            end,
        )

        chunk = await _get_calendar_window(
            cursor,
            chunk_end,
        )

        events.extend(chunk)

        cursor = chunk_end

    return events


async def get_activity_history(
    days: int = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> dict:
    if now is None:
        now = datetime.now(
            LOCAL_TIMEZONE
        )
    else:
        now = now.astimezone(
            LOCAL_TIMEZONE
        )

    start = now - timedelta(
        days=days
    )

    try:
        events = await _get_calendar_history(
            start,
            now,
        )
    except HomeAssistantError as exc:
        return {
            "available": False,
            "calendar":
                GARMIN_ACTIVITY_CALENDAR,
            "window_days": days,
            "window_start":
                start.isoformat(),
            "window_end":
                now.isoformat(),
            "activity_count": 0,
            "activities": [],
            "error": str(exc),
        }

    activities = []

    # Chunk boundaries should not normally duplicate
    # events, but deduplicate defensively using calendar
    # UID where available.
    seen = set()

    for event in events:
        uid = event.get("uid")

        if uid and uid in seen:
            continue

        activity = normalise_activity_event(
            event
        )

        if activity is None:
            continue

        if uid:
            seen.add(uid)

        activities.append(activity)

    activities.sort(
        key=lambda item: item["start"]
    )

    today = now.date().isoformat()

    today_activities = [
        activity
        for activity in activities
        if activity["date"] == today
    ]

    activity_types = sorted(
        {
            activity["activity_type"]
            for activity in activities
        }
    )

    return {
        "available": True,
        "calendar":
            GARMIN_ACTIVITY_CALENDAR,
        "window_days": days,
        "window_start":
            start.isoformat(),
        "window_end":
            now.isoformat(),
        "query_chunk_days":
            QUERY_CHUNK_DAYS,
        "activity_count": len(
            activities
        ),
        "activity_types":
            activity_types,
        "today": {
            "activity_count": len(
                today_activities
            ),
            "activities":
                today_activities,
        },
        "activities": activities,
    }
