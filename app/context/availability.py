from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.adapters.homeassistant import ha_client


LOCAL_TIMEZONE = ZoneInfo("Europe/London")

WORK_FREE_BUSY_CALENDAR = "calendar.work_free_busy"
ANNUAL_LEAVE_CALENDAR = "calendar.annual_leave"
WORKDAY_CALENDAR = "calendar.workday_sensor_calendar"


AVAILABILITY_PRIORITY = {
    "free": 1,
    "tentative": 2,
    "busy": 3,
    "away": 4,
}


def _parse_event_time(
    value: dict,
    *,
    end: bool = False,
) -> datetime:
    if "dateTime" in value:
        return datetime.fromisoformat(
            value["dateTime"]
        ).astimezone(LOCAL_TIMEZONE)

    if "date" in value:
        parsed = datetime.fromisoformat(
            value["date"]
        )

        return parsed.replace(
            tzinfo=LOCAL_TIMEZONE
        )

    raise ValueError(
        f"Unsupported calendar time: {value!r}"
    )


def _event_contains(
    event: dict,
    moment: datetime,
) -> bool:
    start = _parse_event_time(
        event["start"]
    )
    end = _parse_event_time(
        event["end"],
        end=True,
    )

    return start <= moment < end


def _normalise_status(
    event: dict,
) -> str | None:
    summary = (
        event.get("summary")
        or ""
    ).strip().casefold()

    if summary in AVAILABILITY_PRIORITY:
        return summary

    return None


def _resolve_overlapping_status(
    events: list[dict],
    moment: datetime,
) -> tuple[str, list[dict]]:
    active = []

    for event in events:
        status = _normalise_status(event)

        if status is None:
            continue

        if not _event_contains(
            event,
            moment,
        ):
            continue

        active.append({
            "status": status,
            "start": _parse_event_time(
                event["start"]
            ).isoformat(),
            "end": _parse_event_time(
                event["end"],
                end=True,
            ).isoformat(),
        })

    if not active:
        return "unknown", []

    strongest = max(
        active,
        key=lambda item:
            AVAILABILITY_PRIORITY[
                item["status"]
            ],
    )

    return strongest["status"], active


async def _calendar_active(
    entity_id: str,
    moment: datetime,
) -> bool:
    start = moment - timedelta(days=1)
    end = moment + timedelta(days=1)

    events = await ha_client.get_calendar_events(
        entity_id,
        start,
        end,
    )

    return any(
        _event_contains(event, moment)
        for event in events
    )


async def build_availability_context(
    moment: datetime | None = None,
) -> dict:
    if moment is None:
        moment = datetime.now(
            LOCAL_TIMEZONE
        )
    else:
        moment = moment.astimezone(
            LOCAL_TIMEZONE
        )

    start = moment - timedelta(hours=1)
    end = moment + timedelta(hours=8)

    work_events = (
        await ha_client.get_calendar_events(
            WORK_FREE_BUSY_CALENDAR,
            start,
            end,
        )
    )

    work_status, evidence = (
        _resolve_overlapping_status(
            work_events,
            moment,
        )
    )

    on_leave = await _calendar_active(
        ANNUAL_LEAVE_CALENDAR,
        moment,
    )

    workday = await _calendar_active(
        WORKDAY_CALENDAR,
        moment,
    )

    normal_working_day = moment.weekday() < 5

    if not normal_working_day:
        work_expectation = "not_applicable"
    elif on_leave:
        work_expectation = "suspended_leave"
    elif not workday:
        work_expectation = "suspended_holiday"
    else:
        work_expectation = "applicable"

    return {
        "generated_at":
            datetime.now(
                LOCAL_TIMEZONE
            ).isoformat(),

        "at": moment.isoformat(),

        "work": {
            "normal_working_day":
                normal_working_day,
            "ha_workday": workday,
            "on_leave": on_leave,
            "expectation":
                work_expectation,
            "calendar_status":
                work_status,
        },

        "evidence": {
            "active_free_busy":
                evidence,
        },

        "capabilities": {
            "workday_context": True,
            "leave_context": True,
            "work_availability": True,
        },
    }
