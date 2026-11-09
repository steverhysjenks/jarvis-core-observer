"""Deterministic ownership for generic media play and bounded follow-up choices."""
import asyncio
from dataclasses import dataclass
import os
import time

from app.adapters.homeassistant import HomeAssistantError
from app.adapters.jellyfin import CatalogueUnavailable, Movie
from app.capabilities.models import CapabilityResult
from app.capabilities.video import context, video_capability
from app.context.areas import canonical_area
from app.music import service as music
from app.music.intents import parse_music_control
from app.music.models import ResolvedMusicCandidate
from app.music.targets import TARGETS
from app.video.intents import VideoIntent, recognise

CHOICE_SECONDS = 60
RECEIPT_SECONDS = 300
MAX_ENTRIES = 128
PROBE_SECONDS = 5
SHORT_SECONDS = 18
HANDOFF_SECONDS = 10
REPLIES = {"the film": "video", "the movie": "video", "the music": "music",
           "the song": "music", "cancel": "cancel", "cancel media": "cancel"}


@dataclass(frozen=True)
class Choice:
    expires: float
    intent: VideoIntent
    movie: Movie
    music: ResolvedMusicCandidate
    area: str | None


@dataclass
class Receipt:
    expires: float
    signature: tuple
    video: tuple[VideoIntent, Movie, float] | None = None


def response(status, speech, *, continuing=False):
    return CapabilityResult(True, False, "media", "bounded_media", metadata={
        "operation_status": status, "speech": speech, "continue_conversation": continuing,
    })


def bare_intent(text):
    if parse_music_control(text) is not None:
        return None
    intent = recognise(text, allow_unknown=True)
    if intent and intent.operation == "play" and not intent.explicit:
        return intent
    return None


class MediaCoordinator:
    def __init__(self):
        self.pending = {}
        self.receipts = {}
        self.probing = {}

    def prune(self):
        now = time.monotonic()
        self.pending = {key: value for key, value in self.pending.items() if value.expires > now}
        self.receipts = {key: value for key, value in self.receipts.items() if value.expires > now}

    def forget(self, request):
        key = context(request)
        self.pending.pop(key, None)
        self.probing.pop(key, None)

    def reserve(self, request):
        if not request.request_id:
            return response("invalid_request", "Please make a new media request.")
        key = context(request), request.request_id
        if key in self.receipts:
            return response("already_processed", "That media request was already processed.")
        if len(self.receipts) >= MAX_ENTRIES:
            return response("busy", "Media requests are busy. Please try later.")
        receipt = Receipt(time.monotonic() + RECEIPT_SECONDS, (request.text, request.area))
        self.receipts[key] = receipt
        return receipt

    async def video(self, request, intent, movie, receipt, *, deadline=None):
        remaining = None if deadline is None else deadline - asyncio.get_running_loop().time()
        if remaining is not None and remaining <= 0:
            return response("unavailable", "Media selection timed out. Please make a new request.")
        result = await video_capability.handle(request, intent=intent, expected_movie=movie, max_seconds=remaining)
        if result.metadata.get("operation_status") == "video_deadline_required":
            receipt.video = intent, movie, time.monotonic() + HANDOFF_SECONDS
        return result

    async def resume(self, request):
        self.prune()
        receipt = self.receipts.get((context(request), request.request_id))
        if receipt is None:
            return None
        if (receipt.signature != (request.text, request.area) or receipt.video is None
                or receipt.video[2] <= time.monotonic()):
            # Router requires an extended reply to remain in the video domain.
            return CapabilityResult(True, False, "video", "bounded_video", metadata={
                "operation_status": "already_processed", "speech": "That video request is no longer pending.",
            })
        intent, movie, _ = receipt.video
        receipt.video = None
        return await self.video(request, intent, movie, receipt)

    async def play_music(self, request, session, candidate, deadline):
        area = canonical_area(request.area)
        if area not in TARGETS:
            return response("unavailable", "I found the music, but there is no configured speaker for this request.")
        try:
            async with asyncio.timeout_at(deadline):
                result = await music.play_candidate(session, candidate.candidate_id, area)
        except (HomeAssistantError, TimeoutError, ValueError, TypeError):
            return response("uncertain", "I could not verify the music command. Check the speaker before trying again.")
        return CapabilityResult(True, True, "music", "semantic_music_explicit",
                                {"handled": True, "selection": "exact_match", **result})

    async def answer(self, request, *, nutrition_followup):
        self.prune()
        phrase = request.text.strip().casefold().rstrip(".!?").strip()
        selected = REPLIES.get(phrase)
        if selected is None:
            return None
        key = context(request)
        pending = self.pending.get(key)
        if (key, request.request_id) in self.receipts:
            return response("already_processed", "That media request was already processed.")
        if pending is None:
            if phrase == "cancel":
                return None
            return response("choice_required", "Please make a fresh request naming the film or the music.")
        if phrase == "cancel" and nutrition_followup(request):
            return response("clarification_required", "Say cancel media or nutrition cancel.", continuing=True)
        receipt = self.reserve(request)
        if isinstance(receipt, CapabilityResult):
            return receipt
        self.pending.pop(key)
        if selected == "cancel":
            return response("cancelled", "Media choice cancelled.")
        if pending.area != request.area:
            return response("candidate_changed", "The media context changed. Please make a fresh request.")
        if selected == "video":
            return await self.video(request, pending.intent, pending.movie, receipt)
        deadline = asyncio.get_running_loop().time() + SHORT_SECONDS
        try:
            async with asyncio.timeout(PROBE_SECONDS):
                session, candidate = await music.probe_exact(pending.intent.title)
        except (HomeAssistantError, TimeoutError, ValueError, TypeError, AttributeError):
            return response("unavailable", "I could not check the music match. Please make a fresh request.")
        if candidate is None or (
            candidate.uri, candidate.media_type, candidate.name, candidate.artist, candidate.album
        ) != (
            pending.music.uri, pending.music.media_type, pending.music.name, pending.music.artist, pending.music.album
        ):
            return response("candidate_changed", "The music match changed. Please make a fresh request.")
        return await self.play_music(request, session, candidate, deadline)

    async def play(self, request, intent):
        self.prune()
        receipt = self.reserve(request)
        if isinstance(receipt, CapabilityResult):
            return receipt
        self.forget(request)
        key = context(request)
        self.probing[key] = receipt
        deadline = asyncio.get_running_loop().time() + SHORT_SECONDS
        async def film_probe():
            try:
                async with asyncio.timeout(PROBE_SECONDS):
                    return await video_capability.catalogue.lookup(intent.title, intent.year)
            except (CatalogueUnavailable, TimeoutError):
                return None
        async def music_probe():
            try:
                async with asyncio.timeout(PROBE_SECONDS):
                    return await music.probe_exact(intent.title)
            except (HomeAssistantError, TimeoutError, ValueError, TypeError, AttributeError):
                return None
        try:
            film, audio = await asyncio.gather(film_probe(), music_probe())
            if self.probing.get(key) is not receipt:
                return response("superseded", "A newer media request replaced this one.")
        finally:
            if self.probing.get(key) is receipt:
                self.probing.pop(key)
        if film is None or audio is None:
            return response("unavailable", "I could not check both media catalogues. Please request a film or music explicitly.")
        status, movie, _ = film
        session, candidate = audio
        if status == "ambiguous":
            return response("clarification_required", "I found multiple film editions. Please request the film with its year, or name the music explicitly.")
        if movie is not None and candidate is not None:
            if not (request.user_context and request.conversation_id and request.origin == "home_assistant"):
                return response("choice_required", "I found a film and a music match. Please make a fresh request naming the film or the music explicitly.")
            if len(self.pending) >= MAX_ENTRIES:
                return response("busy", "Media choices are busy. Please request the film or music explicitly.")
            self.pending[context(request)] = Choice(time.monotonic() + CHOICE_SECONDS, intent, movie, candidate, request.area)
            return response("clarification_required", "I found a film and a music match. Would you like the film or the music?", continuing=True)
        if movie is not None:
            return await self.video(request, intent, movie, receipt, deadline=deadline)
        if candidate is not None:
            return await self.play_music(request, session, candidate, deadline)
        return None


media_coordinator = MediaCoordinator()
