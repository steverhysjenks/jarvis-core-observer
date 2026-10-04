from typing import Protocol

from app.capabilities.models import CapabilityResult
from app.voice.requests import VoiceRequest


class Capability(Protocol):
    """Contract implemented by bounded Jarvis capabilities."""

    async def handle(
        self,
        request: VoiceRequest,
    ) -> CapabilityResult:
        ...
