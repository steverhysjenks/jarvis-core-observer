from typing import Literal

from app.adapters.homeassistant import ha_client
from app.music.targets import resolve_target


MusicCommand = Literal[
    "stop",
    "pause",
    "resume",
    "next",
    "previous",
    "restart",
]

ALLOWED_COMMANDS = {
    "stop",
    "pause",
    "resume",
    "next",
    "previous",
    "restart",
}

SERVICE_MAP = {
    "stop": "media_stop",
    "pause": "media_pause",
    "resume": "media_play",
    "next": "media_next_track",
}


async def control_music(
    area: str,
    command: MusicCommand,
) -> dict:
    """
    Perform a bounded deterministic playback operation.

    Semantic area names are resolved internally. Raw Home
    Assistant entity IDs are never accepted from callers.
    """

    if command not in ALLOWED_COMMANDS:
        raise ValueError(
            f"Unsupported music command: {command}"
        )

    target = resolve_target(area)

    if command == "previous":
        raise ValueError(
            "Previous track is not yet safely implemented"
        )

    if command == "restart":
        await ha_client.call_service(
            "media_player",
            "media_seek",
            {
                "entity_id": target.entity_id,
                "seek_position": 0,
            },
        )

    else:
        service = SERVICE_MAP[command]

        await ha_client.call_service(
            "media_player",
            service,
            {
                "entity_id": target.entity_id,
            },
        )

    return {
        "command": command,
        "target_area": target.area,
        "target_name": target.name,
    }
