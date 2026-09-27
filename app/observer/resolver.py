import json
from app.storage.ledger import mark_resolved, open_entries

def resolve_routine_departure(entry: dict, context: dict) -> dict | None:
    user=context.get("user",{})
    if user.get("home") is not False: return None
    resolved=mark_resolved(entry["candidate_key"],"primary_user_no_longer_home")
    return {"candidate_key":entry["candidate_key"],"candidate_type":entry["candidate_type"],"resolved":True,"reason":"primary_user_no_longer_home","resolved_at":resolved.get("resolved_at") if resolved else None}

RESOLVERS={"routine_departure_deviation":resolve_routine_departure}

def resolve_open_situations(context: dict) -> list[dict]:
    resolutions=[]
    for entry in open_entries():
        resolver=RESOLVERS.get(entry.get("candidate_type"))
        if resolver is None: continue
        try: json.loads(entry["candidate_json"])
        except (TypeError,json.JSONDecodeError): continue
        resolution=resolver(entry,context)
        if resolution is not None: resolutions.append(resolution)
    return resolutions
