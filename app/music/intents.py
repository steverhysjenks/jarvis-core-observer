from dataclasses import dataclass
from typing import Literal


ControlCommand = Literal[
    "stop",
    "pause",
    "resume",
    "next",
    "restart",
    "previous",
]


@dataclass(frozen=True)
class MusicControlIntent:
    command: ControlCommand


# Deliberately conservative.
#
# These are phrases whose meaning is sufficiently unambiguous that
# an LLM is unnecessary.
CONTROL_PHRASES: dict[str, ControlCommand] = {
    # Stop
    "stop": "stop",
    "stop music": "stop",
    "stop the music": "stop",
    "stop this": "stop",
    "stop playing": "stop",

    # Pause
    "pause": "pause",
    "pause music": "pause",
    "pause the music": "pause",
    "pause this": "pause",

    # Resume
    "resume": "resume",
    "resume music": "resume",
    "resume the music": "resume",
    "carry on": "resume",
    "continue": "resume",
    "continue playing": "resume",

    # Next
    "skip": "next",
    "skip this": "next",
    "skip this song": "next",
    "next": "next",
    "next song": "next",
    "next track": "next",

    # Restart current
    "restart": "restart",
    "restart this": "restart",
    "restart this song": "restart",
    "restart this track": "restart",
    "play this again": "restart",
    "repeat this song": "restart",
    "repeat this track": "restart",

    # Previous.
    #
    # Recognised here, but execution remains blocked until
    # true Music Assistant queue navigation is implemented.
    "previous": "previous",
    "previous song": "previous",
    "previous track": "previous",
    "last song": "previous",
    "last track": "previous",
}


def _normalise(text: str) -> str:
    return " ".join(
        text.strip().casefold().rstrip(".!?").split()
    )


def parse_music_control(
    text: str,
) -> MusicControlIntent | None:
    phrase = _normalise(text)

    command = CONTROL_PHRASES.get(phrase)

    if command is None:
        return None

    return MusicControlIntent(command=command)


async def handle_music_control(
    text: str,
    area: str,
) -> dict | None:
    """
    Parse and execute an unambiguous music control phrase.

    Returns None when the text is not a deterministic control
    intent, allowing the caller to continue to semantic routing.
    """

    intent = parse_music_control(text)

    if intent is None:
        return None

    from app.music.control import control_music

    return await control_music(
        area,
        intent.command,
    )
