import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from app.adapters.homeassistant import ha_client

PERSON_ENTITY="person.steve"
BERMUDA_TRACKER="device_tracker.my_phone_bermuda_tracker"
BERMUDA_AREA="sensor.my_phone_area"
BERMUDA_FLOOR="sensor.my_phone_floor"
BERMUDA_DISTANCE="sensor.my_phone_distance"
LOCATION_STABILITY_SECONDS=20
LOCAL_TIMEZONE=ZoneInfo("Europe/London")

def usable_state(state):
    if not state: return None
    value=state.get("state")
    return None if value in (None,"unknown","unavailable","") else value

def as_float(value):
    try: return float(value)
    except (TypeError,ValueError): return None

def state_age_seconds(state):
    if not state or not state.get("last_changed"): return None
    try: changed=datetime.fromisoformat(state["last_changed"]).astimezone(LOCAL_TIMEZONE)
    except (TypeError,ValueError): return None
    return max(0.0,(datetime.now(LOCAL_TIMEZONE)-changed).total_seconds())

async def build_user_context() -> dict:
    person,tracker,area,floor,distance=await asyncio.gather(
        ha_client.get_state_optional(PERSON_ENTITY),ha_client.get_state_optional(BERMUDA_TRACKER),ha_client.get_state_optional(BERMUDA_AREA),ha_client.get_state_optional(BERMUDA_FLOOR),ha_client.get_state_optional(BERMUDA_DISTANCE))
    person_state=usable_state(person); area_value=usable_state(area); floor_value=usable_state(floor); distance_value=as_float(usable_state(distance)); age=state_age_seconds(area)
    return {
        "generated_at":datetime.now(LOCAL_TIMEZONE).isoformat(),
        "home":person_state=="home",
        "location":{"area":area_value,"floor":floor_value,"distance_m":distance_value,"source":"bermuda" if area_value else None,"stable":bool(area_value and age is not None and age>=LOCATION_STABILITY_SECONDS),"stable_for_seconds":round(age,1) if age is not None else None},
        "capabilities":{"presence":person is not None,"room_location":area_value is not None},
        "evidence":{"person_state":person_state,"bermuda_tracker_state":usable_state(tracker)},
    }
