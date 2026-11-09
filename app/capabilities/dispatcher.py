import os
import re

from app.capabilities.base import Capability
from app.capabilities.models import CapabilityResult
from app.capabilities.music import music_capability
from app.capabilities.media import bare_intent, media_coordinator
from app.capabilities.replay import replay_capability
from app.capabilities.nutrition import nutrition_capability
from app.capabilities.mealie import mealie_capability
from app.capabilities.video import video_capability
from app.nutrition.dialogue import is_followup
from app.video.intents import recognise
from app.voice.requests import VoiceRequest


CAPABILITIES: tuple[Capability, ...] = (
    replay_capability,
    nutrition_capability,
    mealie_capability,
    video_capability,
    music_capability,
)


async def dispatch_capabilities(
    request: VoiceRequest,
) -> CapabilityResult | None:
    """
    Offer a request to bounded Jarvis capabilities in order.

    The first capability that claims the request owns it,
    whether or not that capability is currently authorised
    or able to complete the requested action.

    None means no bounded capability claimed the request,
    allowing wider Jarvis routing to continue.
    """

    if request._video_deadline == "extended-v1":
        result = await media_coordinator.resume(request)
        if result is not None:
            return result
        intent = recognise(request.text)
        if intent is None or not intent.explicit or intent.operation != "play":
            raise ValueError("Cold-start request has no valid video continuation")
        result = await video_capability.handle(request)
        if not result.claimed:
            raise ValueError("Cold-start request is no longer owned by video")
        return result

    result = await CAPABILITIES[0].handle(request)  # replay
    if result.claimed:
        return result

    # Typed nutrition actions retain priority. Only exact media answers can
    # bypass a generic nutrition follow-up, and a shared cancel is disambiguated.
    if not (request.nutrition or request.nutrition_history or request.nutrition_confirmation):
        result = await media_coordinator.answer(request, nutrition_followup=is_followup)
        if result is not None:
            return result
    for capability in CAPABILITIES[1:-2]:
        result = await capability.handle(request)
        if result.claimed:
            return result

    intent = bare_intent(request.text)
    if intent is not None and os.environ.get("VIDEO_ENABLED", "false").lower() == "true":
        result = await media_coordinator.play(request, intent)
        if result is not None:
            return result
        result = await music_capability.handle(request, catalogue_checked=True)
        return result if result.claimed else None

    if re.match(r"^(?:(?:ask jarvis to|jarvis[:,]?|can you|could you)\s+)*(?:play|put)\s+",
                request.text.strip(), re.I):
        media_coordinator.forget(request)
    for capability in CAPABILITIES[-2:]:
        result = await capability.handle(request)
        if result.claimed:
            return result
    return None
