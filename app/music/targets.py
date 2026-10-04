from dataclasses import dataclass


@dataclass(frozen=True)
class MusicTarget:
    area: str
    entity_id: str
    name: str


# Deliberately explicit allow-list.
#
# Qwen and other reasoning layers use semantic area names.
# Home Assistant entity IDs remain infrastructure details.
TARGETS = {
    "kitchen": MusicTarget(
        area="kitchen",
        entity_id="media_player.kitchen_2",
        name="Kitchen",
    ),
    "office": MusicTarget(
        area="office",
        entity_id="media_player.office_voice_assistant_2",
        name="Office Echo",
    ),
}


def resolve_target(area: str) -> MusicTarget:
    key = area.strip().casefold()

    target = TARGETS.get(key)

    if target is None:
        raise ValueError(
            f"Unknown music target area: {area}"
        )

    return target
