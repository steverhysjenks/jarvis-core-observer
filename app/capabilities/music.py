from app.capabilities.models import CapabilityResult
from app.context.areas import canonical_area
from app.music.intents import handle_music_control
from app.music.semantic import classify_music_request
from app.music.service import (
    play_descriptive,
    play_explicit,
)
from app.music.retrieval import retrieve_semantic_session
from app.voice.requests import VoiceRequest


class MusicCapability:
    """Bounded Music Assistant capability."""

    async def handle(
        self,
        request: VoiceRequest,
    ) -> CapabilityResult:
        area = canonical_area(request.area)

        # Fast deterministic control path.
        if area is not None:
            music_result = await handle_music_control(
                request.text,
                area,
            )

            if music_result is not None:
                return CapabilityResult(
                    claimed=True,
                    handled=True,
                    domain="music",
                    path="deterministic",
                    result=music_result,
                )

        # Semantic classification describes the request only.
        music_intent = await classify_music_request(
            request.text
        )

        if music_intent is None:
            return CapabilityResult(
                claimed=False,
                handled=False,
                domain=None,
                path="not_claimed",
            )

        # Explicit requests are currently the only semantic
        # music requests authorised to cause playback.
        if (
            music_intent.retrieval_type == "explicit"
            and music_intent.query
            and area is not None
        ):
            result = await play_explicit(
                music_intent.query,
                area,
            )

            return CapabilityResult(
                claimed=True,
                handled=result["handled"],
                domain="music",
                path="semantic_music_explicit",
                result=result,
                metadata={
                    "intent": music_intent.intent,
                    "retrieval_type":
                        music_intent.retrieval_type,
                    "query": music_intent.query,
                },
            )

        # Descriptive catalogue requests may retrieve real
        # MA candidates and play only from the grounded bounded session.
        if music_intent.retrieval_type in {
            "similar",
            "activity",
            "mood",
            "genre",
            "era",
            "era_genre",
        }:
            session = await retrieve_semantic_session(
                music_intent
            )

            candidate_count = (
                len(session.candidates)
                if session is not None
                else 0
            )

            # A descriptive request may only cause playback
            # when retrieval produced real MA candidates and
            # the request resolved to an allowed area.
            if (
                session is not None
                and candidate_count > 0
                and area is not None
            ):
                result = await play_descriptive(
                    session,
                    area,
                )

                return CapabilityResult(
                    claimed=True,
                    handled=result["handled"],
                    domain="music",
                    path="semantic_music_descriptive",
                    result=result,
                    metadata={
                        "intent": music_intent.intent,
                        "retrieval_type":
                            music_intent.retrieval_type,
                        "query": music_intent.query,
                        "genre": music_intent.genre,
                        "year_from": music_intent.year_from,
                        "year_to": music_intent.year_to,
                        "candidate_count":
                            candidate_count,
                        "context": {
                            "area": area,
                            "satellite":
                                request.satellite,
                            "listener":
                                request.listener,
                        },
                    },
                )

            return CapabilityResult(
                claimed=True,
                handled=False,
                domain="music",
                path="semantic_music_retrieved",
                metadata={
                    "intent": music_intent.intent,
                    "retrieval_type":
                        music_intent.retrieval_type,
                    "query": music_intent.query,
                    "genre": music_intent.genre,
                    "year_from": music_intent.year_from,
                    "year_to": music_intent.year_to,
                    "candidate_count": candidate_count,
                    "context": {
                        "area": area,
                        "satellite": request.satellite,
                        "listener": request.listener,
                    },
                },
            )

        # Music was recognised, but this retrieval strategy
        # is not yet supported.
        return CapabilityResult(
            claimed=True,
            handled=False,
            domain="music",
            path="semantic_music",
            metadata={
                "intent": music_intent.intent,
                "retrieval_type":
                    music_intent.retrieval_type,
                "query": music_intent.query,
                "confidence": music_intent.confidence,
                "context": {
                    "area": area,
                    "satellite": request.satellite,
                    "listener": request.listener,
                },
            },
        )


music_capability = MusicCapability()
