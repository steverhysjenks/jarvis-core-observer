VOICE_TARGETS = {
    "Office area": "assist_satellite.office_voice_assistant_assist_satellite",
    "Kitchen": "assist_satellite.kitchen_voice_assistant_assist_satellite",
    "Master Bedroom": "assist_satellite.my_bedroom_voice_assistant_assist_satellite",
}

def resolve_voice_target(area: str | None) -> dict:
    entity_id=VOICE_TARGETS.get(area)
    if not entity_id: return {"available":False,"area":area,"entity_id":None,"reason":"no_voice_target_for_area"}
    return {"available":True,"area":area,"entity_id":entity_id,"reason":"exact_area_match"}
