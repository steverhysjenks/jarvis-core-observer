import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.adapters.homeassistant import ha_client


LOCAL_TIMEZONE = ZoneInfo("Europe/London")

# Primary-user identity.
# These describe who Jarvis serves, rather than room infrastructure.
PERSON_ENTITY = "person.steve"

# Current Bermuda semantic entities.
# These are optional capabilities: their loss must not break user context.
BERMUDA_TRACKER = "device_tracker.my_phone_bermuda_tracker"
BERMUDA_AREA = "sensor.my_phone_area"
BERMUDA_FLOOR = "sensor.my_phone_floor"
BERMUDA_DISTANCE = "sensor.my_phone_distance"


def usable_state(state: dict | None) -> str | None:
    if state is None:
        return None

    value = state.get("state")

    if value in (None, "unknown", "unavailable"):
        return None

    return value


def as_float(value: str | None) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


LOCATION_STABILITY_SECONDS = 20


def state_age_seconds(
    state: dict | None,
    now: datetime,
) -> float | None:
    """
    Return how long the current HA state has remained unchanged.
    """

    if state is None:
        return None

    last_changed = state.get(
        "last_changed"
    )

    if not last_changed:
        return None

    try:
        changed_at = datetime.fromisoformat(
            last_changed
        )
    except (TypeError, ValueError):
        return None

    return max(
        0.0,
        (
            now
            - changed_at.astimezone(
                LOCAL_TIMEZONE
            )
        ).total_seconds(),
    )


async def build_user_context() -> dict:
    now = datetime.now(
        LOCAL_TIMEZONE
    )

    (
        person,
        tracker,
        area,
        floor,
        distance,
    ) = await asyncio.gather(
        ha_client.get_state_optional(PERSON_ENTITY),
        ha_client.get_state_optional(BERMUDA_TRACKER),
        ha_client.get_state_optional(BERMUDA_AREA),
        ha_client.get_state_optional(BERMUDA_FLOOR),
        ha_client.get_state_optional(BERMUDA_DISTANCE),
    )

    person_state = usable_state(person)
    tracker_state = usable_state(tracker)
    area_state = usable_state(area)
    floor_state = usable_state(floor)
    distance_m = as_float(usable_state(distance))

    home = person_state == "home"

    presence_available = person_state is not None

    room_location_available = (
        home
        and tracker_state is not None
        and area_state is not None
    )

    # Room-level location is irrelevant when the primary user
    # is not currently home.
    if not home:
        area_state = None
        floor_state = None
        distance_m = None

    area_stable_for_seconds = (
        state_age_seconds(
            area,
            now,
        )
        if room_location_available
        else None
    )

    area_stable = (
        area_stable_for_seconds is not None
        and area_stable_for_seconds
        >= LOCATION_STABILITY_SECONDS
    )

    return {
        "generated_at": now.isoformat(),
        "home": home if presence_available else None,
        "location": {
            "area": area_state,
            "floor": floor_state,
            "distance_m": distance_m,
            "source": (
                "bermuda"
                if room_location_available
                else None
            ),
            "stable": (
                area_stable
                if room_location_available
                else False
            ),
            "stable_for_seconds": (
                round(
                    area_stable_for_seconds,
                    1,
                )
                if area_stable_for_seconds
                is not None
                else None
            ),
        },
        "capabilities": {
            "presence": presence_available,
            "room_location": room_location_available,
        },
        "evidence": {
            "person_state": person_state,
            "bermuda_tracker_state": tracker_state,
        },
    }
