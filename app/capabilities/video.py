"""Bounded, default-off movie workflow; request ownership never falls through."""
import asyncio
import os
import time

from app.adapters.homeassistant import HomeAssistantError
from app.adapters.jellyfin import CatalogueUnavailable, jellyfin_client
from app.capabilities.models import CapabilityResult
from app.video.intents import recognise
from app.video.playback import VideoNotReady, VideoPlayback, fingerprint

DEADLINE_SECONDS = 12.0
PLAY_DEADLINE_SECONDS = 18.0
PLAYBACK_RESERVE_SECONDS = 4.0
CONFIRM_SECONDS = 60.0
CACHE_SECONDS = 300.0
MAX_REQUESTS = 128


def reply(status, speech, intent, **data):
    return CapabilityResult(True, status in {"prepared", "playing"}, "video", "bounded_video",
                            {"status": status, **data}, {
        "operation_status": status, "speech": speech, "operation": intent.operation,
        "title": intent.title, "year": intent.year, "room": intent.room,
        "continue_conversation": status == "confirmation_required",
    })


def context(request):
    return (request.origin, request.user_context, request.conversation_id,
            request.satellite, request.listener)


def room_for(intent, request):
    room = intent.room or request.area or "living room"
    room = room.casefold().replace("_", " ").strip()
    return "living room" if room in {"living room", "lounge"} else None


def receipt(result, intent):
    """A deduplicated operation is historical evidence, never a fresh state check."""
    outcome = result.result["status"]
    status = "uncertain" if outcome == "uncertain" else "already_processed"
    return reply(status, "This request was already processed. Its recorded outcome was " + outcome.replace("_", " ") +
                 ". No command was resent and playback was not checked again.", intent,
                 receipt={"recorded_outcome": outcome, "fresh_verification": False})


class VideoCapability:
    def __init__(self, catalogue=jellyfin_client, playback=None):
        self.catalogue = catalogue
        self.playback = playback or VideoPlayback()
        self.lock = asyncio.Lock()
        self.requests = {}
        self.pending = {}
        # A possibly delivered command blocks further commands until operator reconciliation.
        self.uncertain = False

    async def handle(self, request):
        intent = recognise(request.text)
        if intent is None:
            return CapabilityResult(False, False, None, "not_claimed")
        if os.environ.get("VIDEO_ENABLED", "false").lower() != "true":
            return reply("disabled", "Video playback is currently disabled.", intent)
        if intent.operation == "invalid" or not request.request_id:
            return reply("invalid_request", "Give one film, an optional year and a supported TV target.", intent)
        key = context(request), request.request_id
        signature = request.text, request.area
        started = False
        reserved = False
        try:
            timeout = PLAY_DEADLINE_SECONDS if intent.operation == "play" else DEADLINE_SECONDS
            async with asyncio.timeout(timeout) as budget:
                async with self.lock:
                    now = time.monotonic()
                    self.requests = {k: v for k, v in self.requests.items() if v[0] > now}
                    self.pending = {k: v for k, v in self.pending.items() if v[0] > now}
                    if key in self.requests:
                        _, original, result = self.requests[key]
                        return receipt(result, intent) if original == signature else reply(
                            "request_conflict", "That request ID was already used for a different request.", intent)
                    if len(self.requests) >= MAX_REQUESTS:
                        return reply("busy", "Video request capacity is full. No command was sent.", intent)
                    # Reserve before any I/O. Cancellation leaves a terminal, non-retryable receipt.
                    result = reply("uncertain", "The request was interrupted. Check the TV before trying again.", intent)
                    self.requests[key] = now + CACHE_SECONDS, signature, result
                    reserved = True
                    if intent.operation == "cancel":
                        self.pending.pop(context(request), None)
                        result = reply("cancelled", "Video takeover cancelled. No command was sent.", intent)
                    elif self.uncertain:
                        result = reply("uncertain", "Playback state needs operator verification. No further command was sent.", intent)
                    else:
                        async def mutate(action, *args):
                            nonlocal started
                            started = self.uncertain = True
                            await action(*args)
                        result = await self.execute(intent, request, mutate, budget.when())
                    self.requests[key] = time.monotonic() + CACHE_SECONDS, signature, result
                    return result
        except (TimeoutError, HomeAssistantError, CatalogueUnavailable, VideoNotReady, ValueError, TypeError):
            result = reply("uncertain" if started else "unavailable",
                           "I could not verify the TV request. Check the TV. I will not retry." if started else
                           "Video is unavailable or the TV is not ready. No playback command was sent.", intent)
            # Do not extend or overwrite another request's receipt on a lock-wait timeout.
            if reserved:
                self.requests[key] = time.monotonic() + CACHE_SECONDS, signature, result
            return result

    async def execute(self, intent, request, mutate, deadline):
        caller = context(request)
        pending = self.pending.pop(caller, None)
        approved = intent.operation == "confirm"
        source = os.environ.get("VIDEO_TV_SOURCE", "")
        if approved:
            if not pending or not request.conversation_id or not request.origin:
                return reply("confirmation_expired", "No current video takeover exists in this conversation.", intent)
            _, intent, expected_movie, expected_view, expected_source = pending
            if source != expected_source:
                return reply("state_changed", "TV configuration changed. Start a new video request.", intent)
        if room_for(intent, request) is None:
            return reply("unsupported_room", "Only the living room TV is configured for video.", intent)
        status, movie, choices = await self.catalogue.lookup(intent.title, intent.year)
        if status != "resolved":
            return reply(status, "Please give a unique film title and year." if status == "ambiguous" else
                         "I could not find that exact film in the movie library.", intent, choices=choices)
        if approved and movie != expected_movie:
            return reply("state_changed", "The catalogue result changed. Start a new video request.", intent)
        if intent.operation == "prepare":
            await self.playback.ready(source)
            return reply("prepared", "The film is resolved and the TV is ready. No playback was requested.",
                         intent, movie=movie.as_dict())
        if not source.strip() or len(source) > 100:
            raise VideoNotReady()
        states = await self.playback.snapshot()
        apple, sony = states
        if sony["state"] != "off" and sony["attributes"].get("source") != source:
            raise VideoNotReady()
        if approved and fingerprint(states) != expected_view:
            return reply("state_changed", "Viewing changed since confirmation was requested. Start again.", intent)
        if not approved and self.playback.occupied(states):
            if request.conversation_id and request.origin:
                self.pending[caller] = (time.monotonic() + CONFIRM_SECONDS, intent, movie,
                                        fingerprint(states), source)
                speech = (f"The TV may be in use. Replace viewing with {movie.title} ({movie.year}) in the living room? "
                          "Say confirm video takeover within 60 seconds.")
            else:
                speech = "The TV may be in use. A stable conversation is required for explicit video takeover confirmation."
            return reply("confirmation_required", speech, intent)
        waking = sony["state"] == "off" or apple["state"] in {"off", "standby"}
        if waking:
            async with asyncio.timeout_at(deadline - PLAYBACK_RESERVE_SECONDS):
                states = await self.playback.wake(states, source, mutate)
        if (await self.playback.automation())["current"]:
            raise VideoNotReady()
        # Never treat changed viewing as consent.
        if fingerprint(await self.playback.snapshot()) != fingerprint(states):
            if waking:
                raise VideoNotReady()
            return reply("state_changed", "Viewing changed before playback. No command was sent.", intent)
        if waking and asyncio.get_running_loop().time() >= deadline - PLAYBACK_RESERVE_SECONDS:
            raise VideoNotReady()
        await mutate(self.playback.launch, movie)
        if not await self.playback.verify(movie, source):
            return reply("uncertain", "I sent the request but could not verify playback. Check the TV; I will not retry.", intent)
        self.uncertain = False
        return reply("playing", "Verified the requested film is playing on the living room TV.",
                     intent, movie=movie.as_dict())


video_capability = VideoCapability()
