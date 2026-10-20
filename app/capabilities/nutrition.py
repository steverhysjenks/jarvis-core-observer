import os

from app.adapters.sparky_mcp import NutritionUnavailable
from app.capabilities.models import CapabilityResult
from app.nutrition import service


class NutritionCapability:
    async def handle(self, request):
        if os.getenv("NUTRITION_ENABLED", "false").lower() != "true":
            return CapabilityResult(False, False, None, "not_claimed")
        claimed = bool(request.nutrition or request.nutrition_history or request.nutrition_confirmation or service.INTENT.search(request.text.strip()))
        if request.text.strip().lower() in ("yes", "confirm nutrition"):
            # A pending nutrition confirmation must exist, or leave music/routing alone.
            with service.connection() as db:
                claimed = db.execute("SELECT 1 FROM receipts WHERE context=? AND state='pending' AND expires>?", (service.context_key(request), service.time.time())).fetchone() is not None
        if not claimed:
            return CapabilityResult(False, False, None, "not_claimed")
        try:
            result = await service.handle(request)
        except NutritionUnavailable:
            result = {"status": "unavailable", "message": "Nutrition is unavailable. Nothing will be automatically retried."}
        return CapabilityResult(True, True, "nutrition", "native_mcp", result)


nutrition_capability = NutritionCapability()
