from app.capabilities.dispatcher import dispatch_capabilities
from app.context.areas import canonical_area
from app.voice.requests import VoiceRequest


async def handle_voice_request(
    request: VoiceRequest,
) -> dict:
    """
    Top-level Jarvis request orchestration.

    Order:
    1. bounded capabilities
    2. wider semantic routing
    """

    capability_result = await dispatch_capabilities(
        request
    )

    if capability_result is not None:
        return capability_result.as_dict()

    # No bounded capability claimed the request.
    # Continue to the existing wider semantic routing path.
    area = canonical_area(request.area)

    return {
        "handled": False,
        "domain": None,
        "path": "semantic",
        "text": request.text,
        "context": {
            "area": area,
            "satellite": request.satellite,
            "listener": request.listener,
        },
    }
