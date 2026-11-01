"""Fixed HA endpoints; one internally constructed command, no retries or wake-up."""
import asyncio
import math
import re

from app.adapters.homeassistant import ha_client

APPLE_TV = "media_player.living_room_3"
SONY_TV = "media_player.sony_kdl_55w905a"
POLL_SECONDS = 0.25
VERIFY_ATTEMPTS = 12


class VideoNotReady(Exception):
    pass


def deep_link(tmdb_id, *, play):
    if not isinstance(tmdb_id, str) or not re.fullmatch(r"[1-9][0-9]{0,9}", tmdb_id):
        raise ValueError("Verified numeric TMDB ID required")
    return "infuse://movie/" + tmdb_id + ("?play" if play else "")


def fingerprint(states):
    # Ignore routine position/timestamp updates while binding approval to viewing identity.
    return tuple((s["state"], *(s["attributes"].get(k) for k in
                 ("app_id", "app_name", "media_content_id", "media_title", "source"))) for s in states)


class VideoPlayback:
    def __init__(self, client=ha_client):
        self.client = client

    async def snapshot(self):
        states = []
        for entity in (APPLE_TV, SONY_TV):
            value = await self.client.get_state(entity)
            if (not isinstance(value, dict) or value.get("entity_id") != entity
                    or value.get("state") not in {"off", "standby", "on", "idle", "playing", "paused"}
                    or not isinstance(value.get("attributes"), dict)):
                raise VideoNotReady()
            states.append(value)
        return states

    @staticmethod
    def occupied(states):
        apple, sony = states
        # An on TV can be showing content HA cannot identify. Never infer an empty room.
        return sony["state"] != "off" or apple["state"] not in {"off", "standby", "idle"}

    async def ready(self, source):
        if not isinstance(source, str) or not source.strip() or len(source) > 100:
            raise VideoNotReady()
        for attempt in range(3):
            states = await self.snapshot()
            apple, sony = states
            if (apple["state"] in {"idle", "on", "paused", "playing"}
                    and sony["state"] in {"on", "idle", "playing", "paused"}
                    and sony["attributes"].get("source") == source):
                return states
            if attempt < 2:
                await asyncio.sleep(POLL_SECONDS)
        raise VideoNotReady()

    async def launch(self, movie):
        await self.client.call_service("media_player", "play_media", {
            "entity_id": APPLE_TV, "media_content_type": "url",
            "media_content_id": deep_link(movie.tmdb_id, play=True),
        })

    async def verify(self, movie, source):
        """Require actual matching item, app, playing state and advancing position."""
        previous = None
        for attempt in range(VERIFY_ATTEMPTS):
            apple, sony = await self.snapshot()
            attrs = apple["attributes"]
            position = attrs.get("media_position")
            valid = (apple["state"] == "playing" and str(attrs.get("app_name", "")).casefold() == "infuse"
                     and attrs.get("media_content_id") in {deep_link(movie.tmdb_id, play=False),
                                                           deep_link(movie.tmdb_id, play=True)}
                     and sony["state"] in {"on", "idle", "playing", "paused"}
                     and sony["attributes"].get("source") == source
                     and type(position) in {int, float} and math.isfinite(position) and position >= 0)
            if valid and previous is not None and position > previous:
                return True
            previous = position if valid else None
            if attempt + 1 < VERIFY_ATTEMPTS:
                await asyncio.sleep(POLL_SECONDS)
        return False
