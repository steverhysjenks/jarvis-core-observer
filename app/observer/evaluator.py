from app.context.user import build_user_context
from app.judgement.qwen import judge_candidate
from app.observer.action_executor import execute_action
from app.observer.action_policy import evaluate_action_policy
from app.storage.ledger import candidate_key, record_candidate

async def evaluate_candidate(observer: dict, candidate: dict, mode: str="shadow") -> dict:
    result=await judge_candidate(observer,candidate)
    ledger=record_candidate(result["candidate"],mode=mode,judgement=result["judgement"],model=result["model"])
    key=ledger.get("candidate_key") or candidate_key(result["candidate"])
    user=await build_user_context()
    policy=evaluate_action_policy(result,user,mode,candidate_key=key)
    action={"executed":False,"reason":"policy_not_allowed"}
    if policy.get("allowed") is True: action=await execute_action(policy,key)
    return {**result,"ledger":ledger,"mode":mode,"policy":policy,"action":action,"action_taken":action.get("executed") is True}

async def evaluate_candidates(observer: dict,candidates: list[dict],mode: str="shadow") -> list[dict]:
    results=[]
    for candidate in candidates: results.append(await evaluate_candidate(observer,candidate,mode=mode))
    return results
