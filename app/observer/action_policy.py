from datetime import datetime
from zoneinfo import ZoneInfo
from app.config import settings
from app.storage.ledger import get_entry, latest_announcement
from app.voice.routing import resolve_voice_target

LOCAL_TIMEZONE=ZoneInfo("Europe/London")
GLOBAL_ANNOUNCEMENT_COOLDOWN_SECONDS=settings.global_announcement_cooldown_seconds

def evaluate_action_policy(evaluation: dict, user: dict, mode: str, candidate_key: str | None=None) -> dict:
    judgement=evaluation.get("judgement",{}); decision=judgement.get("decision"); message=judgement.get("message")
    location=user.get("location",{}); area=location.get("area")
    if mode != "live": return {"allowed":False,"reason":"observer_not_live"}
    if decision != "interrupt": return {"allowed":False,"reason":"judgement_not_interrupt"}
    if not isinstance(message,str) or not message.strip(): return {"allowed":False,"reason":"announcement_message_missing"}
    if candidate_key:
        entry=get_entry(candidate_key)
        if entry is not None:
            if entry.get("status")=="resolved": return {"allowed":False,"reason":"situation_resolved"}
            if entry.get("announced_at"): return {"allowed":False,"reason":"situation_already_announced","announced_at":entry.get("announced_at"),"announcement_count":entry.get("announcement_count",0)}
    latest=latest_announcement()
    if latest is not None and latest.get("announced_at") and latest.get("candidate_key") != candidate_key:
        try:
            elapsed=(datetime.now(LOCAL_TIMEZONE)-datetime.fromisoformat(latest["announced_at"])).total_seconds()
            if elapsed < GLOBAL_ANNOUNCEMENT_COOLDOWN_SECONDS:
                return {"allowed":False,"reason":"global_announcement_cooldown","seconds_since_last_announcement":round(elapsed,1),"cooldown_seconds":GLOBAL_ANNOUNCEMENT_COOLDOWN_SECONDS}
        except (TypeError,ValueError): pass
    if user.get("home") is not True: return {"allowed":False,"reason":"primary_user_not_home"}
    if location.get("source") != "bermuda": return {"allowed":False,"reason":"room_location_unavailable"}
    if location.get("stable") is not True: return {"allowed":False,"reason":"user_location_not_stable","area":area,"stable_for_seconds":location.get("stable_for_seconds")}
    target=resolve_voice_target(area)
    if not target["available"]: return {"allowed":False,"reason":target["reason"],"area":area,"target":target}
    return {"allowed":True,"reason":"voice_action_eligible","interaction":"announce","audience":"primary_user","message":message.strip(),"preannounce":True,"area":area,"target":target}
