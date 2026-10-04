from datetime import datetime
from zoneinfo import ZoneInfo


LOCAL_TIMEZONE = ZoneInfo("Europe/London")


def detect_upcoming_departure(
    context: dict,
    warning_minutes: int = 30,
) -> dict | None:
    """
    Identify a possible upcoming departure.

    This detector deliberately does not decide whether the user
    should be interrupted. It only identifies a situation that
    may deserve further judgement.
    """

    user = context.get("user", {})
    schedule = context.get("schedule", {})

    if user.get("home") is not True:
        return None

    event = schedule.get("next_timed_event")

    if not event:
        return None

    if event.get("all_day"):
        return None

    start_value = event.get("start")

    if not start_value:
        return None

    now = datetime.now(LOCAL_TIMEZONE)
    start = datetime.fromisoformat(start_value)

    minutes_until = int(
        (start - now).total_seconds() / 60
    )

    if minutes_until < 0:
        return None

    if minutes_until > warning_minutes:
        return None

    return {
        "type": "possible_upcoming_departure",
        "priority": "candidate",
        "reason": "timed_event_approaching_while_user_home",
        "event": {
            "summary": event.get("summary"),
            "start": event.get("start"),
            "location": event.get("location"),
            "calendar": event.get("calendar"),
        },
        "context": {
            "minutes_until_event": minutes_until,
            "user_home": True,
            "user_area": user.get("area"),
        },
    }
