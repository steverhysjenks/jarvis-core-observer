import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from app.adapters.homeassistant import ha_client

LOCAL_TIMEZONE = ZoneInfo("Europe/London")
WASTE_CALENDARS = ("calendar.bins", "calendar.bins_2")
PUT_OUT_FROM = time(hour=19, minute=0)

def _event_date(event: dict):
    raw = event.get("start", {}).get("date") if isinstance(event.get("start"), dict) else event.get("start")
    if not raw: return None
    try: return datetime.fromisoformat(raw).date()
    except ValueError: return None

async def build_waste_context(days: int = 7, now: datetime | None = None) -> dict:
    now = (now or datetime.now(LOCAL_TIMEZONE)).astimezone(LOCAL_TIMEZONE)
    end = now + timedelta(days=days)
    results = await asyncio.gather(*(ha_client.get_calendar_events(e, now, end) for e in WASTE_CALENDARS))
    grouped = {}
    for entity_id, events in zip(WASTE_CALENDARS, results):
        for event in events:
            d = _event_date(event)
            if d is None: continue
            item = grouped.setdefault(d, {"types": [], "sources": []})
            summary = event.get("summary")
            if summary and summary not in item["types"]: item["types"].append(summary)
            if entity_id not in item["sources"]: item["sources"].append(entity_id)
    future = sorted(d for d in grouped if d >= now.date())
    if not future:
        return {"next_collection": None, "preparation_window": None}
    collection_date = future[0]
    collection = grouped[collection_date]
    prep_start = datetime.combine(collection_date - timedelta(days=1), PUT_OUT_FROM, tzinfo=LOCAL_TIMEZONE)
    prep_end = datetime.combine(collection_date, time.min, tzinfo=LOCAL_TIMEZONE)
    return {"next_collection": {"date": collection_date.isoformat(), "types": collection["types"], "sources": collection["sources"]}, "preparation_window": {"starts": prep_start.isoformat(), "ends": prep_end.isoformat(), "active": prep_start <= now < prep_end, "put_out_from": PUT_OUT_FROM.strftime("%H:%M")}}
