"""Bounded, default-off movie workflow; request ownership never falls through."""
import asyncio
import logging
import os
import re
from pathlib import Path
import time

from app.adapters.homeassistant import HomeAssistantError
from app.adapters.jellyfin import CatalogueUnavailable, Movie, jellyfin_client
from app.capabilities.models import CapabilityResult
from app.video.intents import recognise
from app.video.playback import VideoNotReady, VideoPlayback, fingerprint

DEADLINE_SECONDS = 12.0
PLAY_DEADLINE_SECONDS = 18.0
COLD_PLAY_DEADLINE_SECONDS = 44.0
PLAYBACK_RESERVE_SECONDS = 6.0
VIDEO_HOLD_PATH = Path("/var/lib/jarvis-core/video-uncertain")
CACHE_SECONDS = 300.0
MAX_REQUESTS = 128

logger = logging.getLogger("uvicorn.error").getChild("jarvis.video")


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
    room = intent.room or "living room"
    room = room.casefold().replace("_", " ").replace("-", " ").strip()
    return "living room" if room in {"living room", "lounge"} else None


def receipt(result, intent):
    """A deduplicated operation is historical evidence, never a fresh state check."""
    outcome = result.result["status"]
    status = "uncertain" if outcome == "uncertain" else "already_processed"
    return reply(status, "This request was already processed. Its recorded outcome was " + outcome.replace("_", " ") +
                 ". No command was resent and playback was not checked again.", intent,
                 receipt={"recorded_outcome": outcome, "fresh_verification": False})


class VideoCapability:
    def __init__(self, catalogue=jellyfin_client, playback=None, *, hold_path=None):
        self.catalogue = catalogue
        self.playback = playback or VideoPlayback()
        self.lock = asyncio.Lock()
        self.requests = {}
        # A possibly delivered command blocks further commands until operator reconciliation.
        self.uncertain = False
        self.hold_path = hold_path

    def held(self):
        if self.uncertain:
            return True
        if self.hold_path is None:
            return False
        try:
            self.hold_path.lstat()
        except FileNotFoundError:
            return False
        return True

    def persist_hold(self):
        if self.hold_path is not None:
            with self.hold_path.open("x", encoding="utf-8") as marker:
                marker.write("A media command may have been sent. Reconcile before clearing.\n")
                marker.flush()
                os.fsync(marker.fileno())
            self.sync_hold_directory()

    def sync_hold_directory(self):
        fd = os.open(self.hold_path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    async def handle(self, request, *, intent=None, expected_movie: Movie | None = None, max_seconds=None):
        intent = intent or recognise(request.text)
        if intent is None or (request._video_deadline == "extended-v1" and intent.operation != "play"):
            return CapabilityResult(False, False, None, "not_claimed")
        if os.environ.get("VIDEO_ENABLED", "false").lower() != "true":
            return reply("disabled", "Video playback is currently disabled.", intent)
        if intent.operation == "invalid" or not request.request_id:
            return reply("invalid_request", "Give one film, an optional year and a supported TV target.", intent)
        key = context(request), request.request_id
        signature = request.text, request.area
        started = False
        reserved = False
        evidence = dict.fromkeys(("command_accepted", "title_observed", "playing_observed",
                                  "identity_verified", "progress_verified"), False)
        try:
            extended = request._video_deadline == "extended-v1" and intent.operation == "play"
            timeout = (COLD_PLAY_DEADLINE_SECONDS if extended else
                       PLAY_DEADLINE_SECONDS if intent.operation == "play" else DEADLINE_SECONDS)
            if max_seconds is not None:
                timeout = min(timeout, max_seconds)
            async with asyncio.timeout(timeout) as budget:
                async with self.lock:
                    now = time.monotonic()
                    self.requests = {k: v for k, v in self.requests.items() if v[0] > now}
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
                        result = reply("cancelled", "Video takeover cancelled. No command was sent.", intent)
                    elif intent.operation == "confirm":
                        result = reply("confirmation_expired", "No video takeover is awaiting confirmation.", intent)
                    elif intent.operation == "play" and self.held():
                        result = reply("uncertain", "Playback state needs operator verification. No further command was sent.", intent)
                    else:
                        async def mutate(action, *args):
                            nonlocal started
                            if not started:
                                self.persist_hold()
                                started = self.uncertain = True
                            await action(*args)
                        result = await self.execute(intent, request, mutate, budget.when(), evidence, expected_movie)
                    if result.result["status"] == "playing" and started:
                        if self.hold_path is not None:
                            self.hold_path.unlink()
                            self.sync_hold_directory()
                        self.uncertain = False
                    if result.result["status"] == "video_deadline_required":
                        # This is a mutation-free offer, not an executed operation.
                        self.requests.pop(key)
                        return result
                    self.requests[key] = time.monotonic() + CACHE_SECONDS, signature, result
                    return result
        except (OSError, HomeAssistantError, CatalogueUnavailable, VideoNotReady, ValueError, TypeError) as exc:
            request_id = request.request_id
            logger.warning(
                "Video operation stopped request_id=%s operation=%s extended_deadline=%s mutation_started=%s reason=%s",
                request_id if isinstance(request_id, str) and re.fullmatch(r"[a-f0-9]{32}", request_id) else "-",
                intent.operation, extended, started,
                exc.reason if isinstance(exc, VideoNotReady) else type(exc).__name__,
            )
            result = reply("uncertain" if started else "unavailable",
                           "I could not verify the TV request. Check the TV. I will not retry." if started else
                           "Video is unavailable or the TV is not ready. No playback command was sent.", intent,
                           **({"playback_evidence": evidence} if started else {}))
            # Do not extend or overwrite another request's receipt on a lock-wait timeout.
            if reserved:
                self.requests[key] = time.monotonic() + CACHE_SECONDS, signature, result
            return result

    async def execute(self, intent, request, mutate, deadline, evidence, expected_movie=None):
        source = os.environ.get("VIDEO_TV_SOURCE", "")
        if room_for(intent, request) is None:
            return reply("unsupported_room", "Only the living room TV is configured for video.", intent)
        status, movie, choices = await self.catalogue.lookup(intent.title, intent.year)
        if expected_movie is not None and (status != "resolved" or movie != expected_movie):
            return reply("candidate_changed", "The film match changed. Please request it again.", intent)
        if status != "resolved":
            return reply(status, "Please give a unique film title and year." if status == "ambiguous" else
                         "I could not find that exact film in the movie library.", intent, choices=choices)
        if intent.operation == "prepare":
            await self.playback.ready(source)
            return reply("prepared", "The film is resolved and the TV is ready. No playback was requested.",
                         intent, movie=movie.as_dict())
        if not source.strip() or len(source) > 100:
            raise VideoNotReady("tv_source_invalid")
        states = await self.playback.snapshot()
        apple, sony = states
        waking = sony["state"] == "off" or apple["state"] in {"off", "standby"}
        needs_input = sony["attributes"].get("source") != source
        if waking:
            if request._video_deadline != "extended-v1" or intent.operation != "play":
                if request._video_deadline == "negotiate-v1" and intent.operation == "play":
                    return reply("video_deadline_required", "The TV needs the cold-start budget.", intent,
                                 request_id=request.request_id)
                raise VideoNotReady("extended_deadline_required")
            async with asyncio.timeout_at(deadline - PLAYBACK_RESERVE_SECONDS):
                states = await self.playback.wake(states, source, mutate)
        elif needs_input:
            states = await self.playback.wake(states, source, mutate)
        if (await self.playback.automation())["current"]:
            raise VideoNotReady("wake_automation_active")
        # Never treat changed viewing as consent.
        if fingerprint(await self.playback.snapshot()) != fingerprint(states):
            if waking or needs_input:
                raise VideoNotReady("device_state_changed")
            return reply("state_changed", "Viewing changed before playback. No command was sent.", intent)
        if waking and asyncio.get_running_loop().time() >= deadline - PLAYBACK_RESERVE_SECONDS:
            raise VideoNotReady("wake_budget_exhausted")
        apple = states[0]
        title, exact_id = self.playback.observed_movie(apple, movie)
        already_playing = apple["state"] == "playing" and (exact_id or (title and not apple["attributes"].get("media_content_id")))
        if not already_playing:
            await mutate(self.playback.launch, movie)
            evidence["command_accepted"] = True
        await self.playback.complete(movie, source, states, mutate, evidence)
        if evidence["identity_verified"] and evidence["progress_verified"]:
            return reply("playing", "Verified the requested film is playing on the living room TV.",
                         intent, movie=movie.as_dict(), playback_evidence=evidence)
        speech = ("Infuse reports the requested title playing, but I could not verify its identity and progress."
                  if evidence["playing_observed"] else
                  "I could not verify playback. Check the TV. I will not retry.")
        return reply("uncertain", speech, intent, playback_evidence=evidence)


video_capability = VideoCapability(hold_path=VIDEO_HOLD_PATH)
