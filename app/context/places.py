"""
Semantic place discovery and normalisation for Jarvis.

Home Assistant owns geographic zone detection.

By default, every HA zone automatically becomes a Jarvis
semantic place using its entity ID and friendly name.

Configuration exists only for exceptions:
- multiple HA zones representing one real-world place
- HA helper zones that do not represent real-world places
"""

import asyncio
from time import monotonic

from app.adapters.homeassistant import ha_client


PLACE_CACHE_SECONDS = 300

_place_cache: dict | None = None
_place_cache_at: float | None = None
_place_cache_lock = asyncio.Lock()


PLACE_GROUPS = {
    "gym": {
        "name": "Gym",
        "zones": {
            "gym1",
            "gym2",
        },
    },

    "theatre_train": {
        "name": "Theatre Train",
        "zones": {
            "threatre_train",
            "threatre_train_alternate_location",
        },
    },
}


IGNORED_ZONES = {
    "wider_than_school_run_or_lous",
}


def normalise_zone_id(
    entity_id: str,
) -> str | None:
    """
    Convert zone.foo to foo.
    """

    if not entity_id.startswith("zone."):
        return None

    return entity_id.split(
        ".",
        1,
    )[1]


def configured_place_for_zone(
    zone_id: str,
) -> dict | None:
    """
    Return a configured semantic aggregation for a zone,
    when one exists.
    """

    for place_id, definition in PLACE_GROUPS.items():
        if zone_id in definition["zones"]:
            return {
                "id": place_id,
                "name": definition["name"],
                "source":
                    "configured_aggregate",
            }

    return None


async def discover_places(
    force_refresh: bool = False,
) -> dict:
    """
    Discover HA zones and normalise them into Jarvis places.

    Ordinary HA zones require no Jarvis configuration.

    The registry is cached because HA zone configuration
    changes infrequently compared with Observer cycles.
    """

    global _place_cache
    global _place_cache_at

    now = monotonic()

    if (
        not force_refresh
        and _place_cache is not None
        and _place_cache_at is not None
        and now - _place_cache_at
        < PLACE_CACHE_SECONDS
    ):
        return _place_cache

    async with _place_cache_lock:
        now = monotonic()

        if (
            not force_refresh
            and _place_cache is not None
            and _place_cache_at is not None
            and now - _place_cache_at
            < PLACE_CACHE_SECONDS
        ):
            return _place_cache

        states = await ha_client.get_states()

    places: dict[str, dict] = {}
    ignored: list[dict] = []

    for state in states:
        entity_id = state.get(
            "entity_id",
            "",
        )

        zone_id = normalise_zone_id(
            entity_id
        )

        if zone_id is None:
            continue

        attributes = state.get(
            "attributes",
            {},
        )

        friendly_name = attributes.get(
            "friendly_name"
        ) or zone_id.replace(
            "_",
            " ",
        ).title()

        if zone_id in IGNORED_ZONES:
            ignored.append(
                {
                    "zone": zone_id,
                    "entity_id": entity_id,
                    "name": friendly_name,
                    "reason":
                        "configured_ignore",
                }
            )
            continue

        configured = (
            configured_place_for_zone(
                zone_id
            )
        )

        if configured is not None:
            place_id = configured["id"]

            place = places.setdefault(
                place_id,
                {
                    "id": place_id,
                    "name":
                        configured["name"],
                    "zones": [],
                    "state_names": [],
                    "source":
                        configured["source"],
                },
            )

            place["zones"].append(
                zone_id
            )

            place["state_names"].append(
                friendly_name
            )

            continue

        places[zone_id] = {
            "id": zone_id,
            "name": friendly_name,
            "zones": [
                zone_id,
            ],
            "state_names": [
                friendly_name,
            ],
            "source":
                "home_assistant",
        }

    result = {
        "places": sorted(
            places.values(),
            key=lambda item:
                item["name"].casefold(),
        ),
        "ignored_zones": sorted(
            ignored,
            key=lambda item:
                item["name"].casefold(),
        ),
    }

    _place_cache = result
    _place_cache_at = monotonic()

    return result


async def resolve_semantic_place(
    zone: str | None,
) -> dict:
    """
    Resolve an HA person state to a Jarvis semantic place.
    """

    if not zone:
        return {
            "available": False,
            "id": None,
            "name": None,
            "zone": zone,
            "reason": "zone_unknown",
        }

    raw_zone = zone.strip()
    zone_key = raw_zone.casefold()
    zone_id = zone_key.replace(" ", "_")

    registry = await discover_places()

    for ignored in registry["ignored_zones"]:
        ignored_names = {
            ignored["zone"].casefold(),
            ignored["name"].casefold(),
        }

        if (
            zone_key in ignored_names
            or zone_id in ignored_names
        ):
            return {
                "available": False,
                "id": None,
                "name": None,
                "zone": ignored["zone"],
                "reason": "zone_ignored",
            }

    for place in registry["places"]:
        zone_ids = {
            value.casefold()
            for value in place["zones"]
        }

        state_names = {
            value.casefold()
            for value in place.get(
                "state_names",
                [],
            )
        }

        if (
            zone_key not in zone_ids
            and zone_id not in zone_ids
            and zone_key not in state_names
        ):
            continue

        matched_zone = next(
            (
                value
                for value in place["zones"]
                if value.casefold() in {
                    zone_key,
                    zone_id,
                }
            ),
            None,
        )

        return {
            "available": True,
            "id": place["id"],
            "name": place["name"],
            "zone": matched_zone or raw_zone,
            "source": place["source"],
            "reason":
                "semantic_place_match",
        }

    return {
        "available": False,
        "id": None,
        "name": None,
        "zone": zone_id,
        "reason": "unmapped_zone",
    }
