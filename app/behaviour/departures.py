from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.context.history import build_history_context
LOCAL_TIMEZONE=ZoneInfo("Europe/London"); DOOR_CORRELATION_MINUTES=10

async def get_departure_observations(days: int=28)->list[dict]:
    history=await build_history_context(hours=days*24); events=history["timeline"]; observations=[]; used_exits=set()
    for i,event in enumerate(events):
        if event["event"]!="entrance_closed": continue
        closed=datetime.fromisoformat(event["at"])
        for j,later in enumerate(events[i+1:],start=i+1):
            when=datetime.fromisoformat(later["at"]); delta=(when-closed).total_seconds()/60
            if delta>DOOR_CORRELATION_MINUTES: break
            if j in used_exits: continue
            if later["event"] in ("user_away","user_entered_zone") and later.get("from")=="home":
                observations.append({"at":closed.isoformat(),"date":closed.date().isoformat(),"weekday":closed.strftime("%A"),"time":closed.strftime("%H:%M"),"corroboration":"entrance_cycle_plus_person_exit"}); used_exits.add(j); break
    return observations
