from datetime import datetime
from zoneinfo import ZoneInfo
from app.context.evidence import entrance_activity
LOCAL_TIMEZONE=ZoneInfo("Europe/London")

async def detect_waste_preparation(context: dict)->list[dict]:
    waste=context.get("household",{}).get("waste")
    if not waste: return []
    collection=waste.get("next_collection"); window=waste.get("preparation_window")
    if not collection or not window or not window.get("active"): return []
    now=datetime.fromisoformat(context["generated_at"]).astimezone(LOCAL_TIMEZONE); start=datetime.fromisoformat(window["starts"]).astimezone(LOCAL_TIMEZONE)
    evidence=await entrance_activity(start=start,end=now)
    if not evidence["evidence_available"] or evidence["occurred"]: return []
    return [{"type":"possible_bins_not_put_out","priority":"candidate","reason":"waste_collection_tomorrow_no_entrance_activity","collection_date":collection["date"],"collection_types":collection["types"],"preparation_window":window,"evidence":{"entrance_activity":evidence}}]
