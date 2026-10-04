import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.adapters.homeassistant import ha_client


LOCAL_TIMEZONE = ZoneInfo("Europe/London")

PRIMARY_ENTRANCE_ENTITY = "binary_sensor.front_door_opening"
PRIMARY_USER_ENTITY = "person.steve"

# A geofence transition and physical door event will rarely occur
# at exactly the same time.
DOOR_CORRELATION_MINUTES = 10


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(
        LOCAL_TIMEZONE
    )


def extract_door_cycles(
    history: list[dict],
) -> list[dict]:
    """
    Convert raw contact history into complete open/close cycles.

    The first HA record is a baseline and is not treated as an
    event.
    """

    cycles = []
    opened_at = None

    for item in history[1:]:
        state = item.get("state")
        changed = item.get("last_changed")

        if not changed:
            continue

        timestamp = parse_time(changed)

        if state == "on":
            opened_at = timestamp

        elif state == "off" and opened_at is not None:
            cycles.append(
                {
                    "opened_at": opened_at,
                    "closed_at": timestamp,
                }
            )
            opened_at = None

    return cycles


def extract_home_exits(
    history: list[dict],
) -> list[dict]:
    """
    Find transitions where the primary user leaves the HA home
    zone.

    A transition from 'home' to either not_home or a named zone
    counts as leaving home.
    """

    exits = []

    if not history:
        return exits

    previous_state = history[0].get("state")

    for item in history[1:]:
        state = item.get("state")
        changed = item.get("last_changed")

        if not changed:
            continue

        if state in (None, "unknown", "unavailable"):
            continue

        if previous_state == "home" and state != "home":
            exits.append(
                {
                    "time": parse_time(changed),
                    "from": previous_state,
                    "to": state,
                }
            )

        previous_state = state

    return exits


def correlate_departures(
    exits: list[dict],
    door_cycles: list[dict],
) -> list[dict]:
    observations = []

    tolerance = timedelta(
        minutes=DOOR_CORRELATION_MINUTES
    )

    used_exit_indexes = set()

    for cycle in door_cycles:
        physical_departure = cycle["closed_at"]

        candidates = []

        for index, exit_event in enumerate(exits):
            if index in used_exit_indexes:
                continue

            exit_time = exit_event["time"]

            distance = abs(
                exit_time - physical_departure
            )

            if distance <= tolerance:
                candidates.append(
                    (
                        distance,
                        index,
                        exit_event,
                    )
                )

        if not candidates:
            continue

        candidates.sort(
            key=lambda item: item[0]
        )

        distance, index, exit_event = candidates[0]

        used_exit_indexes.add(index)

        observations.append(
            {
                "type": "user_departure",
                "time": physical_departure.isoformat(),
                "date": physical_departure.date().isoformat(),
                "weekday": physical_departure.strftime("%A"),
                "local_time": physical_departure.strftime("%H:%M:%S"),
                "destination_state": exit_event["to"],
                "confidence": "high",
                "evidence": [
                    "primary_entrance_used",
                    "user_left_home_zone",
                ],
                "door": {
                    "opened_at": cycle[
                        "opened_at"
                    ].isoformat(),
                    "closed_at": cycle[
                        "closed_at"
                    ].isoformat(),
                    "offset_seconds": int(
                        distance.total_seconds()
                    ),
                },
                "geofence": {
                    "transition_at": exit_event[
                        "time"
                    ].isoformat(),
                    "from": exit_event["from"],
                    "to": exit_event["to"],
                },
            }
        )

    return observations


async def build_departure_observations(
    days: int = 28,
) -> dict:
    now = datetime.now(LOCAL_TIMEZONE)
    start = now - timedelta(days=days)

    door_history, user_history = await asyncio.gather(
        ha_client.get_history(
            PRIMARY_ENTRANCE_ENTITY,
            start,
            end=now,
        ),
        ha_client.get_history(
            PRIMARY_USER_ENTITY,
            start,
            end=now,
        ),
    )

    door_cycles = extract_door_cycles(
        door_history
    )

    exits = extract_home_exits(
        user_history
    )

    departures = correlate_departures(
        exits,
        door_cycles,
    )

    return {
        "generated_at": now.isoformat(),
        "window": {
            "days": days,
            "start": start.isoformat(),
            "end": now.isoformat(),
        },
        "summary": {
            "door_cycles": len(door_cycles),
            "home_exits": len(exits),
            "departure_observations": len(
                departures
            ),
            "high_confidence": sum(
                1
                for item in departures
                if item["confidence"] == "high"
            ),
            "medium_confidence": sum(
                1
                for item in departures
                if item["confidence"] == "medium"
            ),
        },
        "departures": departures,
    }
