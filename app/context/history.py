from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.adapters.homeassistant import ha_client
LOCAL_TIMEZONE=ZoneInfo("Europe/London"); PRIMARY_ENTRANCE_ENTITY="binary_sensor.front_door_opening"; PRIMARY_USER_ENTITY="person.steve"

def _local(value): return datetime.fromisoformat(value).astimezone(LOCAL_TIMEZONE)

async def build_history_context(hours: int=24)->dict:
    end=datetime.now(LOCAL_TIMEZONE); start=end-timedelta(hours=hours)
    door=await ha_client.get_history(PRIMARY_ENTRANCE_ENTITY,start,end); person=await ha_client.get_history(PRIMARY_USER_ENTITY,start,end); timeline=[]
    for record in door[1:]:
        if record.get("state") in ("on","off") and record.get("last_changed"):
            timeline.append({"event":"entrance_opened" if record["state"]=="on" else "entrance_closed","at":_local(record["last_changed"]).isoformat()})
    previous=person[0].get("state") if person else None
    for record in person[1:]:
        state=record.get("state"); changed=record.get("last_changed")
        if not changed or state==previous: continue
        if state=="home": event="user_arrived_home"
        elif state=="not_home": event="user_away"
        else: event="user_entered_zone"
        timeline.append({"event":event,"at":_local(changed).isoformat(),"from":previous,"to":state}); previous=state
    timeline.sort(key=lambda x:x["at"])
    return {"window_hours":hours,"timeline":timeline,"event_count":len(timeline)}
