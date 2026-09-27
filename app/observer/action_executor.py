from app.storage.ledger import mark_announced
from app.voice.announcements import announce_to_user

async def execute_action(policy: dict, candidate_key: str) -> dict:
    if policy.get("allowed") is not True: return {"executed":False,"reason":"policy_not_allowed"}
    if policy.get("interaction") != "announce": return {"executed":False,"reason":"unsupported_interaction"}
    result=await announce_to_user(policy["message"],preannounce=policy.get("preannounce",True))
    if result.get("announced") is True:
        mark_announced(candidate_key)
        return {"executed":True,"reason":"announcement_delivered","delivery":result}
    return {"executed":False,"reason":result.get("reason","announcement_failed"),"delivery":result}
