from app.judgement.qwen import judge_candidate
from app.storage.ledger import record_candidate

async def evaluate_candidate(observer: dict, candidate: dict, mode: str = "shadow") -> dict:
    result = await judge_candidate(observer, candidate)
    ledger = record_candidate(result["candidate"], mode=mode, judgement=result["judgement"], model=result["model"])
    return {**result, "ledger": ledger, "mode": mode, "action_taken": False}

async def evaluate_candidates(observer: dict, candidates: list[dict], mode: str = "shadow") -> list[dict]:
    results=[]
    for candidate in candidates:
        results.append(await evaluate_candidate(observer,candidate,mode=mode))
    return results
