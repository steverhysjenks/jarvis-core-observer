import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.adapters.homeassistant import ha_client


LOCAL_TIMEZONE = ZoneInfo("Europe/London")

PRIMARY_ENTRANCE_ENTITY = "binary_sensor.front_door_opening"
PRIMARY_USER_ENTITY = "person.steve"


def local_timestamp(value: str) -> str:
    return (
        datetime.fromisoformat(value)
        .astimezone(LOCAL_TIMEZONE)
        .isoformat()
    )


def normalise_entrance_history(
    history: list[dict],
) -> list[dict]:
    events = []

    # The first HA history record establishes the state at the
    # beginning of the requested period. It is not necessarily
    # a transition that occurred at that moment.
    for item in history[1:]:
        state = item.get("state")

        if state == "on":
            event_type = "entrance_opened"
        elif state == "off":
            event_type = "entrance_closed"
        else:
            continue

        events.append(
            {
                "time": local_timestamp(item["last_changed"]),
                "type": event_type,
                "source": "primary_entrance",
            }
        )

    return events


def normalise_user_history(
    history: list[dict],
) -> list[dict]:
    events = []

    # As above, skip HA's baseline record.
    previous_state = (
        history[0].get("state")
        if history
        else None
    )

    for item in history[1:]:
        state = item.get("state")

        if state in (None, "unknown", "unavailable"):
            previous_state = state
            continue

        if state == previous_state:
            continue

        if state == "home":
            event_type = "user_arrived_home"
        elif state == "not_home":
            event_type = "user_away"
        else:
            event_type = "user_entered_zone"

        events.append(
            {
                "time": local_timestamp(item["last_changed"]),
                "type": event_type,
                "from": previous_state,
                "to": state,
                "source": "primary_user",
            }
        )

        previous_state = state

    return events


async def build_history_context(
    hours: int = 24,
) -> dict:
    now = datetime.now(LOCAL_TIMEZONE)
    start = now - timedelta(hours=hours)

    entrance_history, user_history = await asyncio.gather(
        ha_client.get_history(
            PRIMARY_ENTRANCE_ENTITY,
            start,
        ),
        ha_client.get_history(
            PRIMARY_USER_ENTITY,
            start,
        ),
    )

    entrance_events = normalise_entrance_history(
        entrance_history
    )

    user_events = normalise_user_history(
        user_history
    )

    timeline = entrance_events + user_events
    timeline.sort(key=lambda event: event["time"])

    return {
        "generated_at": now.isoformat(),
        "window": {
            "hours": hours,
            "start": start.isoformat(),
            "end": now.isoformat(),
        },
        "timeline": timeline,
        "summary": {
            "entrance_events": len(entrance_events),
            "user_events": len(user_events),
            "total_events": len(timeline),
        },
        "capabilities": {
            "entrance_history": True,
            "user_presence_history": True,
            "room_history": False,
        },
    }
