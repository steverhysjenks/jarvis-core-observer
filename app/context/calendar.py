import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.adapters.homeassistant import ha_client
LOCAL_TIMEZONE=ZoneInfo("Europe/London")

def _normalise(entity,event,now):
    start=event.get("start"); end=event.get("end"); all_day=isinstance(start,str) and len(start)==10
    item={"calendar":entity,"calendar_name":entity.split(".",1)[-1],"summary":event.get("summary"),"start":start,"end":end,"all_day":all_day,"location":event.get("location"),"uid":event.get("uid")}
    if not all_day and start:
        s=datetime.fromisoformat(start).astimezone(LOCAL_TIMEZONE); item["starts_in_minutes"]=round((s-now).total_seconds()/60)
    return item

async def build_calendar_context(days: int=7)->dict:
    now=datetime.now(LOCAL_TIMEZONE); end=now+timedelta(days=days); calendars=await ha_client.get_entities_by_domain("calendar")
    ids=[c["entity_id"] for c in calendars]; results=await asyncio.gather(*(ha_client.get_calendar_events(i,now,end) for i in ids)); events=[]
    for entity,items in zip(ids,results): events.extend(_normalise(entity,e,now) for e in items)
    timed=[e for e in events if not e["all_day"] and e.get("start")]; timed.sort(key=lambda e:e["start"])
    all_day=[e for e in events if e["all_day"]]
    happening=[]
    for e in timed:
        s=datetime.fromisoformat(e["start"]).astimezone(LOCAL_TIMEZONE); en=datetime.fromisoformat(e["end"]).astimezone(LOCAL_TIMEZONE) if e.get("end") else s
        if s<=now<=en: happening.append(e)
    upcoming=[e for e in timed if datetime.fromisoformat(e["start"]).astimezone(LOCAL_TIMEZONE)>now]
    return {"happening_now":happening,"next_timed_event":upcoming[0] if upcoming else None,"upcoming_timed":upcoming,"all_day_context":all_day}
