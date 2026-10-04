VOICE_TARGETS = {
    "Office area":
        "assist_satellite."
        "office_voice_assistant_assist_satellite",

    "Kitchen":
        "assist_satellite."
        "kitchen_voice_assistant_assist_satellite",

    "Master Bedroom":
        "assist_satellite."
        "my_bedroom_voice_assistant_assist_satellite",
}


def resolve_voice_target(
    area: str | None,
) -> dict:
    """
    Resolve a semantic Bermuda area to a voice endpoint.

    Voice routing is deliberately explicit. An area without a
    configured endpoint does not silently fall back to another
    room.
    """

    if not area:
        return {
            "available": False,
            "area": area,
            "entity_id": None,
            "reason": "user_area_unknown",
        }

    entity_id = VOICE_TARGETS.get(area)

    if entity_id is None:
        return {
            "available": False,
            "area": area,
            "entity_id": None,
            "reason": "no_voice_endpoint_for_area",
        }

    return {
        "available": True,
        "area": area,
        "entity_id": entity_id,
        "reason": "exact_area_match",
    }
