from app.capabilities.base import Capability
from app.capabilities.models import CapabilityResult
from app.capabilities.music import music_capability
from app.capabilities.replay import replay_capability
from app.voice.requests import VoiceRequest


CAPABILITIES: tuple[Capability, ...] = (
    replay_capability,
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

    for capability in CAPABILITIES:
        result = await capability.handle(request)

        if result.claimed:
            return result

    return None
