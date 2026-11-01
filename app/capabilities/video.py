"""Video requests remain owned even while the feature is disabled."""
from app.capabilities.models import CapabilityResult
from app.video.intents import recognise


class VideoCapability:
    async def handle(self, request):
        intent = recognise(request.text)
        if intent is None:
            return CapabilityResult(False, False, None, "not_claimed")
        return CapabilityResult(True, False, "video", "bounded_video", {"status": "disabled"}, {
            "operation_status": "disabled", "speech": "Video playback is currently disabled.",
            "operation": intent.operation, "title": intent.title, "year": intent.year,
            "room": intent.room, "continue_conversation": False,
        })


video_capability = VideoCapability()
