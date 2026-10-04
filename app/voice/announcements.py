from app.adapters.homeassistant import (
    ha_client,
)
from app.context.user import (
    build_user_context,
)
from app.voice.routing import (
    resolve_voice_target,
)


async def announce_to_user(
    message: str,
    preannounce: bool = True,
) -> dict:
    """
    Announce a message to the primary user at their current
    stable semantic location.

    Voice output fails closed when the user's room location
    is unavailable or has not remained stable long enough.

    This is an explicit capability only. The Observer does
    not call this function while operating in shadow mode.
    """

    user = await build_user_context()

    location = user.get(
        "location",
        {},
    )

    area = location.get("area")
    stable = location.get(
        "stable",
        False,
    )

    stable_for_seconds = location.get(
        "stable_for_seconds"
    )

    if user.get("home") is not True:
        return {
            "announced": False,
            "message": message,
            "reason": "primary_user_not_home",
            "location": location,
        }

    if not stable:
        return {
            "announced": False,
            "message": message,
            "reason": "user_location_not_stable",
            "location": {
                "area": area,
                "stable": stable,
                "stable_for_seconds":
                    stable_for_seconds,
            },
        }

    target = resolve_voice_target(
        area
    )

    if not target["available"]:
        return {
            "announced": False,
            "message": message,
            "reason": target["reason"],
            "location": location,
            "target": target,
        }

    response = await ha_client.call_service(
        "assist_satellite",
        "announce",
        {
            "entity_id":
                target["entity_id"],
            "message":
                message,
            "preannounce":
                preannounce,
        },
    )

    return {
        "announced": True,
        "message": message,
        "reason": "announcement_sent",
        "location": {
            "area": area,
            "stable": stable,
            "stable_for_seconds":
                stable_for_seconds,
        },
        "target": target,
        "ha_response": response,
    }


async def announce_to_satellite(
    message: str,
    satellite: str | None,
    preannounce: bool = True,
) -> dict:
    """
    Announce a reactive response to the satellite that
    originated the interaction.

    The supplied entity must be one of Jarvis's explicitly
    configured voice endpoints. Arbitrary HA entities are
    never accepted.
    """

    from app.voice.routing import VOICE_TARGETS

    allowed_targets = set(
        VOICE_TARGETS.values()
    )

    if (
        not satellite
        or satellite not in allowed_targets
    ):
        return {
            "announced": False,
            "message": message,
            "reason":
                "invalid_source_satellite",
            "target": {
                "available": False,
                "entity_id": satellite,
            },
        }

    area = next(
        (
            area_name
            for area_name, entity_id
            in VOICE_TARGETS.items()
            if entity_id == satellite
        ),
        None,
    )

    response = await ha_client.call_service(
        "assist_satellite",
        "announce",
        {
            "entity_id": satellite,
            "message": message,
            "preannounce": preannounce,
        },
    )

    return {
        "announced": True,
        "message": message,
        "reason":
            "reactive_announcement_sent",
        "location": {
            "area": area,
            "source":
                "interaction_endpoint",
        },
        "target": {
            "available": True,
            "area": area,
            "entity_id": satellite,
            "reason":
                "source_satellite",
        },
        "ha_response": response,
    }
