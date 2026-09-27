from app.adapters.homeassistant import ha_client
from app.context.user import build_user_context
from app.voice.routing import resolve_voice_target

async def announce_to_user(message: str, preannounce: bool=True) -> dict:
    user=await build_user_context(); location=user.get("location",{})
    if user.get("home") is not True: return {"announced":False,"reason":"primary_user_not_home"}
    if location.get("stable") is not True: return {"announced":False,"reason":"user_location_not_stable","area":location.get("area")}
    target=resolve_voice_target(location.get("area"))
    if not target["available"]: return {"announced":False,"reason":target["reason"],"target":target}
    await ha_client.call_service("assist_satellite","announce",{"entity_id":target["entity_id"],"message":message,"preannounce":preannounce})
    return {"announced":True,"reason":"announcement_delivered","area":location.get("area"),"target":target}
