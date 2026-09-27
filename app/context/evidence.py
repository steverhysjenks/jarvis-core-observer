from datetime import datetime
from zoneinfo import ZoneInfo
from app.adapters.homeassistant import ha_client

LOCAL_TIMEZONE = ZoneInfo("Europe/London")
PRIMARY_ENTRANCE_ENTITY = "binary_sensor.front_door_opening"

async def entity_transition_occurred(entity_id: str, to_state: str, start: datetime, end: datetime) -> dict:
    actual_now = datetime.now(LOCAL_TIMEZONE)
    start = start.astimezone(LOCAL_TIMEZONE)
    end = end.astimezone(LOCAL_TIMEZONE)
    if start > actual_now:
        return {"entity_id": entity_id, "target_state": to_state, "status": "future_window", "evidence_available": False, "occurred": None, "count": None, "first_occurred": None, "last_occurred": None, "window": {"start": start.isoformat(), "end": end.isoformat()}}
    effective_end = min(end, actual_now)
    history = await ha_client.get_history(entity_id, start, effective_end)
    transitions = []
    for record in history[1:]:
        if record.get("state") != to_state or not record.get("last_changed"):
            continue
        transitions.append(datetime.fromisoformat(record["last_changed"]).astimezone(LOCAL_TIMEZONE))
    return {"entity_id": entity_id, "target_state": to_state, "status": "observed", "evidence_available": True, "occurred": bool(transitions), "count": len(transitions), "first_occurred": transitions[0].isoformat() if transitions else None, "last_occurred": transitions[-1].isoformat() if transitions else None, "window": {"start": start.isoformat(), "end": effective_end.isoformat()}}

async def entrance_activity(start: datetime, end: datetime) -> dict:
    result = await entity_transition_occurred(PRIMARY_ENTRANCE_ENTITY, "on", start, end)
    return {"semantic_event": "entrance_opened", "status": result["status"], "evidence_available": result["evidence_available"], "occurred": result["occurred"], "count": result["count"], "first_occurred": result["first_occurred"], "last_occurred": result["last_occurred"], "window": result["window"]}
