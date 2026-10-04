AREA_ALIASES = {
    "office": "office",
    "office area": "office",
    "kitchen": "kitchen",
    "master bedroom": "master_bedroom",
    "my bedroom": "master_bedroom",
}


def canonical_area(
    area: str | None,
) -> str | None:
    if not area:
        return None

    key = " ".join(
        area.strip().casefold().split()
    )

    return AREA_ALIASES.get(key)
