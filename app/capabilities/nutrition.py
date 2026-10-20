import os
import re
import logging

from app.adapters.sparky_mcp import NutritionUnavailable, request_tools
from app.capabilities.models import CapabilityResult
from app.nutrition import service
from app.nutrition.presentation import present


class NutritionCapability:
    async def handle(self, request):
        if os.getenv("NUTRITION_ENABLED", "false").lower() != "true":
            return CapabilityResult(False, False, None, "not_claimed")
        from app.nutrition.dialogue import is_followup
        text=request.text.strip().lower().rstrip('.?!')
        claimed = bool(request.nutrition or request.nutrition_history or request.nutrition_confirmation or service.INTENT.search(request.text.strip()) or is_followup(request))
        claimed = claimed or bool(re.search(r'\b(?:daily|configured|my)\b.*\bcalori(?:e|es)\b.*\b(?:target|goal)\b|\b(?:add|log|drank|drunk|had)\b.*\bwater\b',text))
        if text in ("yes", "confirm", "yes please", "confirm nutrition"):
            # A pending nutrition confirmation must exist, or leave music/routing alone.
            with service.connection() as db:
                claimed = db.execute("SELECT 1 FROM receipts WHERE context=? AND state='pending' AND expires>?", (service.context_key(request), service.time.time())).fetchone() is not None
        if not claimed:
            return CapabilityResult(False, False, None, "not_claimed")
        calls=[]
        token=request_tools.set(calls)
        try:
            result = await service.handle(request)
        except NutritionUnavailable:
            result = {"status": "unavailable", "message": "Nutrition is unavailable. Nothing will be automatically retried."}
        finally:
            request_tools.reset(token)
        logging.getLogger('uvicorn.error').info('nutrition request_id=%s status=%s mcp_calls=%s', request.request_id, result['status'],len(calls))
        return CapabilityResult(True, True, "nutrition", "native_mcp", result, {
            'speech':present(result), 'operation_status':result['status'],
            'conversation_id':request.conversation_id,
            'continue_conversation':result['status'] in ('clarification_required','confirmation_required'),
            'request_id':request.request_id,
            'mcp_calls':len(calls),
        })


nutrition_capability = NutritionCapability()
