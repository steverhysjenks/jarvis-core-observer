import re

from app.capabilities.models import CapabilityResult
from app.voice.replay import repeat_last_announcement
from app.voice.requests import VoiceRequest


REPLAY_PATTERNS = (
    re.compile(
        r"^(?:please\s+)?repeat\s+that(?:\s+please)?[.!?]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:please\s+)?say\s+that\s+again(?:\s+please)?[.!?]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:please\s+)?repeat\s+(?:your\s+)?last\s+"
        r"(?:message|announcement)(?:\s+please)?[.!?]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^what\s+did\s+you\s+just\s+say[.!?]*$",
        re.IGNORECASE,
    ),
)


class ReplayCapability:
    """
    Bounded capability for explicitly replaying Jarvis's
    most recent proactive announcement.
    """

    async def handle(
        self,
        request: VoiceRequest,
    ) -> CapabilityResult:
        text = request.text.strip()

        claimed = any(
            pattern.fullmatch(text)
            for pattern in REPLAY_PATTERNS
        )

        if not claimed:
            return CapabilityResult(
                claimed=False,
                handled=False,
                domain="replay",
                path="not_replay",
            )

        result = await repeat_last_announcement(
            source_satellite=request.satellite,
        )

        return CapabilityResult(
            claimed=True,
            handled=result.get("replayed") is True,
            domain="replay",
            path=(
                "repeat_last"
                if result.get("replayed") is True
                else "repeat_last_unavailable"
            ),
            result=result,
            metadata={
                "source_area": request.area,
                "source_satellite": request.satellite,
            },
        )


replay_capability = ReplayCapability()
