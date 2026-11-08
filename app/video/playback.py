"""Fixed HA endpoints for bounded readiness and verified movie playback."""
import asyncio
from datetime import datetime, timezone
import math
import re

from app.adapters.homeassistant import ha_client
from app.adapters.jellyfin import normalise

APPLE_TV = "media_player.living_room_3"
APPLE_REMOTE = "remote.living_room"
SONY_TV = "media_player.sony_kdl_55w905a"
WAKE_AUTOMATION = "automation.wake_apple_tv_and_launch_jellyfin"
TV_POWER = "sensor.spare_sonoff_plug_power"
STANDBY_WATTS = 5
POWER_MAX_AGE_SECONDS = 180
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

    async def automation(self):
        state = await self.client.get_state(WAKE_AUTOMATION)
        attributes = state.get("attributes", {})
        if state.get("state") != "on" or type(attributes.get("current")) is not int:
            raise VideoNotReady()
        return attributes

    @staticmethod
    def observed_movie(apple, movie):
        attrs = apple["attributes"]
        if (str(attrs.get("app_name", "")).casefold() != "infuse"
                or attrs.get("app_id") not in {None, "", "com.firecore.infuse"}):
            return False, False
        content_id = attrs.get("media_content_id")
        exact_id = content_id in (deep_link(movie.tmdb_id, play=False), deep_link(movie.tmdb_id, play=True))
        title = attrs.get("media_title")
        exact_title = isinstance(title, str) and normalise(title) == normalise(movie.title)
        return exact_title, exact_id and (not title or exact_title)

    async def complete(self, movie, source, before, mutate, *, command_accepted):
        """Observe the launch and allow at most one contextual Select and one Play."""
        evidence = {"command_accepted": command_accepted, "title_observed": False,
                    "playing_observed": False, "identity_verified": False, "progress_verified": False}
        previous_position = None
        paused = None
        selected = played = False
        for attempt in range(VERIFY_ATTEMPTS):
            states = await self.snapshot()
            apple, sony = states
            if (sony["state"] not in {"on", "idle", "playing", "paused"}
                    or sony["attributes"].get("source") != source):
                break
            attrs = apple["attributes"]
            title, exact_id = self.observed_movie(apple, movie)
            playing = apple["state"] == "playing" and (title or exact_id)
            evidence["title_observed"] |= title
            evidence["playing_observed"] |= playing
            evidence["identity_verified"] |= playing and exact_id
            position = attrs.get("media_position")
            valid_position = (playing and exact_id and type(position) in (int, float)
                              and math.isfinite(position) and position >= 0)
            if valid_position and previous_position is not None and position > previous_position:
                evidence["progress_verified"] = True
                break
            previous_position = position if valid_position else None

            # A changed, stable paused target is the only follow-up candidate.
            # The PoC's initial paused title had no duration or position. An
            # identified loaded player instead needs the explicit Play action.
            observed = fingerprint(states)
            if (command_accepted and not evidence["playing_observed"] and apple["state"] == "paused"
                    and title and (not attrs.get("media_content_id") or exact_id)
                    and observed != fingerprint(before)):
                duration = attrs.get("media_duration")
                loaded = type(duration) in (int, float) and math.isfinite(duration) and duration > 0
                candidate = (observed, duration, position is None)
                if candidate == paused:
                    if (await self.automation())["current"]:
                        break
                    latest = await self.snapshot()
                    fresh = latest[0]["attributes"]
                    if (fingerprint(latest) != observed or fresh.get("media_duration") != duration
                            or (fresh.get("media_position") is None) != (position is None)):
                        break
                    if loaded and not played:
                        await mutate(self.client.call_service, "media_player", "media_play", {"entity_id": APPLE_TV})
                        played = True
                    elif (duration is None and position is None and not attrs.get("media_content_type")
                          and not selected and not played):
                        await mutate(self.client.call_service, "remote", "send_command",
                                     {"entity_id": APPLE_REMOTE, "command": "select"})
                        selected = True
                paused = candidate
            else:
                paused = None
            if attempt + 1 < VERIFY_ATTEMPTS:
                await asyncio.sleep(POLL_SECONDS)
        return evidence
