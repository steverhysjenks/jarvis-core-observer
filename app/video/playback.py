"""Fixed HA endpoints for bounded readiness and verified movie playback."""
import asyncio
from datetime import datetime, timezone
import math
import re

from app.adapters.homeassistant import ha_client

APPLE_TV = "media_player.living_room_3"
SONY_TV = "media_player.sony_kdl_55w905a"
WAKE_AUTOMATION = "automation.wake_apple_tv_and_launch_jellyfin"
TV_POWER = "sensor.spare_sonoff_plug_power"
STANDBY_WATTS = 5
POWER_MAX_AGE_SECONDS = 180
SOURCE_MAX_AGE_SECONDS = 30
WAKE_POLL_SECONDS = 0.5
WAKE_REFRESH_DELAY_SECONDS = 2.0
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


def recently_reported(state, max_age):
    try:
        reported = datetime.fromisoformat(state["last_reported"])
        return 0 <= (datetime.now(timezone.utc) - reported).total_seconds() <= max_age
    except (KeyError, TypeError, ValueError):
        return False


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
        if apple["state"] not in {"off", "standby", "idle"} or sony["state"] in {"playing", "paused"}:
            return True
        return (sony["state"] != "off" and sony["attributes"].get("assumed_state") is True
                and not recently_reported(sony, SOURCE_MAX_AGE_SECONDS))

    async def automation(self):
        state = await self.client.get_state(WAKE_AUTOMATION)
        attributes = state.get("attributes", {})
        if state.get("state") != "on" or type(attributes.get("current")) is not int:
            raise VideoNotReady()
        return attributes

    async def verify_standby(self, sony):
        if not sony["attributes"].get("assumed_state"):
            return
        state = await self.client.get_state(TV_POWER)
        try:
            watts = float(state["state"])
        except (KeyError, TypeError, ValueError) as exc:
            raise VideoNotReady() from exc
        if (state.get("attributes", {}).get("unit_of_measurement") != "W"
                or not recently_reported(state, POWER_MAX_AGE_SECONDS)
                or not 0 <= watts <= STANDBY_WATTS):
            raise VideoNotReady()

    async def wake(self, states, source, mutate):
        """Reuse the Sony-triggered Apple TV/Infuse automation for cold starts."""
        _, sony = states
        cold = sony["state"] == "off"
        automation = await self.automation()
        if automation["current"]:
            raise VideoNotReady()
        if cold:
            await self.verify_standby(sony)
        if fingerprint(await self.snapshot()) != fingerprint(states):
            raise VideoNotReady()
        await mutate(self.client.call_service, "media_player", "turn_on",
                     {"entity_id": SONY_TV if cold else APPLE_TV})
        selected = False
        refresh_after = asyncio.get_running_loop().time() + WAKE_REFRESH_DELAY_SECONDS if cold else None
        while True:
            states = await self.snapshot()
            apple, sony = states
            if apple["state"] in {"playing", "paused"} or sony["state"] in {"playing", "paused"}:
                raise VideoNotReady()
            current = await self.automation()
            triggered = current.get("last_triggered")
            automation_finished = not current["current"] and (
                not cold or (triggered and triggered != automation.get("last_triggered")))
            if sony["state"] in {"on", "idle"} and apple["state"] == "idle" and automation_finished:
                actual = sony["attributes"].get("source")
                if actual == source:
                    return states
                if cold and actual and not selected and source in sony["attributes"].get("source_list", []):
                    selected = True
                    await mutate(self.client.call_service, "media_player", "select_source",
                                 {"entity_id": SONY_TV, "source": source})
            if (refresh_after is not None and sony["state"] == "off"
                    and asyncio.get_running_loop().time() >= refresh_after):
                # Sony polls slowly in standby. Refresh its status once after wake.
                refresh_after = None
                await self.client.call_service("homeassistant", "update_entity", {"entity_id": SONY_TV})
            await asyncio.sleep(WAKE_POLL_SECONDS)

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
