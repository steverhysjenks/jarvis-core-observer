import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.adapters.homeassistant import ha_client
from app.context.places import discover_places


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


def build_zone_place_map(
    registry: dict,
) -> dict[str, dict]:
    """
    Build a lookup from raw HA zone ID to semantic place.
    """

    mapping = {}

    for place in registry.get("places", []):
        place_value = {
            "id": place["id"],
            "name": place["name"],
            "source": place["source"],
        }

        for zone in place.get("zones", []):
            mapping[zone.casefold()] = (
                place_value
            )

        for state_name in place.get(
            "state_names",
            [],
        ):
            mapping[
                state_name.casefold()
            ] = place_value

    return mapping


def derive_place_visits(
    history: list[dict],
    registry: dict,
    window_end: datetime,
) -> list[dict]:
    """
    Derive continuous semantic place visits from HA person history.

    Multiple HA zones that map to the same semantic place are
    treated as one continuous visit.

    Raw person history remains available separately.
    """

    if not history:
        return []

    zone_map = build_zone_place_map(
        registry
    )

    visits = []

    current_place = None
    current_zone = None
    arrived_at = None
    arrival_observed = False

    def semantic_place(
        state: str | None,
    ) -> dict | None:
        if (
            state is None
            or state in (
                "not_home",
                "unknown",
                "unavailable",
            )
        ):
            return None

        return zone_map.get(
            state.casefold()
        )

    def close_visit(
        departed_at: datetime,
    ) -> None:
        nonlocal current_place
        nonlocal current_zone
        nonlocal arrived_at
        nonlocal arrival_observed

        if (
            current_place is None
            or arrived_at is None
        ):
            return

        duration_seconds = max(
            0.0,
            (
                departed_at - arrived_at
            ).total_seconds(),
        )

        visits.append(
            {
                "place": {
                    "id": current_place["id"],
                    "name": current_place["name"],
                    "source": current_place["source"],
                },
                "arrival": arrived_at.isoformat(),
                "arrival_observed": arrival_observed,
                "departure": departed_at.isoformat(),
                "departure_observed": True,
                "duration_seconds": round(
                    duration_seconds,
                    1,
                ),
                "duration_minutes": round(
                    duration_seconds / 60,
                    1,
                ),
                "initial_zone": current_zone,
            }
        )

        current_place = None
        current_zone = None
        arrived_at = None
        arrival_observed = False

    for index, item in enumerate(history):
        state = item.get("state")

        if state in (
            None,
            "unknown",
            "unavailable",
        ):
            continue

        changed_at_raw = item.get(
            "last_changed"
        )

        if not changed_at_raw:
            continue

        changed_at = (
            datetime.fromisoformat(
                changed_at_raw
            )
            .astimezone(LOCAL_TIMEZONE)
        )

        place = semantic_place(state)

        if place is None:
            close_visit(changed_at)
            continue

        if current_place is None:
            current_place = place
            current_zone = state
            arrived_at = changed_at
            arrival_observed = index != 0
            continue

        if place["id"] == current_place["id"]:
            # A raw zone transition inside the same semantic
            # place does not end the visit.
            continue

        close_visit(changed_at)

        current_place = place
        current_zone = state
        arrived_at = changed_at
        arrival_observed = True

    if (
        current_place is not None
        and arrived_at is not None
    ):
        duration_seconds = max(
            0.0,
            (
                window_end - arrived_at
            ).total_seconds(),
        )

        visits.append(
            {
                "place": {
                    "id": current_place["id"],
                    "name": current_place["name"],
                    "source": current_place["source"],
                },
                "arrival": arrived_at.isoformat(),
                "arrival_observed": arrival_observed,
                "departure": None,
                "departure_observed": False,
                "duration_seconds": round(
                    duration_seconds,
                    1,
                ),
                "duration_minutes": round(
                    duration_seconds / 60,
                    1,
                ),
                "initial_zone": current_zone,
                "current": True,
            }
        )

    return visits


async def build_history_context(
    hours: int = 24,
) -> dict:
    now = datetime.now(LOCAL_TIMEZONE)
    start = now - timedelta(hours=hours)

    entrance_history, user_history = await asyncio.gather(
        ha_client.get_history(
            PRIMARY_ENTRANCE_ENTITY,
            start,
            now,
        ),
        ha_client.get_history(
            PRIMARY_USER_ENTITY,
            start,
            now,
        ),
    )

    entrance_events = normalise_entrance_history(
        entrance_history
    )

    user_events = normalise_user_history(
        user_history
    )

    place_registry = await discover_places()

    place_visits = derive_place_visits(
        user_history,
        place_registry,
        now,
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
        "place_visits": place_visits,
        "summary": {
            "entrance_events": len(entrance_events),
            "user_events": len(user_events),
            "place_visits": len(place_visits),
            "total_events": len(timeline),
        },
        "capabilities": {
            "entrance_history": True,
            "user_presence_history": True,
            "room_history": False,
        },
    }
