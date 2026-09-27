import asyncio
from app.adapters.homeassistant import ha_client

ENTITIES = {
    "person": "person.steve",
    "tracker": "device_tracker.my_phone_bermuda_tracker",
    "area": "sensor.my_phone_area",
    "floor": "sensor.my_phone_floor",
    "distance": "sensor.my_phone_distance",
}

async def build_user_context() -> dict:
    person, tracker, area, floor, distance = await asyncio.gather(*(ha_client.get_state_optional(e) for e in ENTITIES.values()))
    person_state = person.get("state") if person else None
    return {
        "home": person_state == "home",
        "person_state": person_state,
        "area": area.get("state") if area else None,
        "floor": floor.get("state") if floor else None,
        "distance": distance.get("state") if distance else None,
        "location_source": "bermuda" if area else None,
    }
