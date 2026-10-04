import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.context.calendar import build_calendar_context
from app.context.family import build_family_context
from app.context.history import build_history_context
from app.context.home import build_home_context
from app.context.user import build_user_context
from app.context.waste import build_waste_context


LOCAL_TIMEZONE = ZoneInfo("Europe/London")
OBSERVER_HISTORY_HOURS = 2


def all_day_events_for_today(
    events: list[dict],
    today: date,
) -> list[dict]:
    relevant = []

    for event in events:
        if not event.get("all_day"):
            continue

        start = date.fromisoformat(event["start"])
        end = date.fromisoformat(event["end"])

        # Calendar all-day end dates are exclusive.
        if start <= today < end:
            relevant.append(event)

    return relevant


async def build_observer_context() -> dict:
    (
        home,
        user,
        family,
        calendar,
        history,
        waste,
    ) = await asyncio.gather(
        build_home_context(),
        build_user_context(),
        build_family_context(),
        build_calendar_context(days=7),
        build_history_context(
            hours=OBSERVER_HISTORY_HOURS
        ),
        build_waste_context(days=7),
    )

    now = datetime.now(LOCAL_TIMEZONE)
    temporal = calendar["temporal"]

    today_context = all_day_events_for_today(
        calendar["events"],
        now.date(),
    )

    return {
        "generated_at": now.isoformat(),
        "local_time": {
            "timezone": "Europe/London",
            "date": now.date().isoformat(),
            "time": now.strftime("%H:%M:%S"),
            "utc_offset": now.strftime("%z"),
            "dst": bool(now.dst()),
        },
        "user": {
            "home": user["home"],
            "area": user["location"]["area"],
            "floor": user["location"]["floor"],
            "location_source": user["location"]["source"],
        },
        "environment": {
            "home_mode": home["home"]["mode"],
        },
        "schedule": {
            "happening_now": (
                temporal["happening_now"]
            ),
            "next_timed_event": (
                temporal["next_timed_event"]
            ),
            "today_all_day": today_context,
            "events": calendar["events"],
        },
        "household": {
            "family": family,
            "waste": waste,
        },
        "recent_activity": {
            "window_hours": (
                OBSERVER_HISTORY_HOURS
            ),
            "timeline": history["timeline"],
            "event_count": history[
                "summary"
            ]["total_events"],
        },
        "capabilities": {
            **user["capabilities"],
            "calendar": True,
            "waste_schedule": (
                waste["next_collection"]
                is not None
            ),
            "semantic_history": True,
            "entrance_history": (
                history["capabilities"][
                    "entrance_history"
                ]
            ),
            "user_presence_history": (
                history["capabilities"][
                    "user_presence_history"
                ]
            ),
            "room_history": (
                history["capabilities"][
                    "room_history"
                ]
            ),
        },
    }


async def build_observer_snapshot() -> dict:
    from app.observer.detectors import (
        run_detectors,
    )

    context = await build_observer_context()

    candidates = await run_detectors(
        context
    )

    return {
        **context,
        "attention": {
            "candidate_count": len(
                candidates
            ),
            "candidates": candidates,
        },
    }
