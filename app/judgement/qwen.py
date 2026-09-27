import json
import httpx
from app.config import settings
from app.observer.enrichment import enrich_candidate, candidate_has_required_facts, candidate_is_valid

SYSTEM_PROMPT = """You are the judgement component of a proactive home AI observer.
A deterministic system has already observed the environment, detected something potentially noteworthy, and calculated factual evidence.
Your task is only to judge whether the user should be interrupted.
Decisions: ignore, monitor, interrupt.
Be conservative about interruption, but do not avoid interruption when supplied evidence indicates timely action may help.
Treat supplied facts as authoritative. Do not recalculate times or contradict supplied facts. Do not invent intentions, routines, people, events, destinations, causes, household rules or capabilities.
Return JSON only: {\"decision\":\"ignore|monitor|interrupt\",\"confidence\":0.0,\"reason\":\"short explanation\",\"message\":null}
If interrupt, message must be short and suitable for a home voice assistant. Otherwise message must be null."""

def build_judgement_context(observer: dict) -> dict:
    return {k: observer.get(k) for k in ("local_time","user","environment","schedule","recent_activity")}

async def judge_candidate(observer: dict, candidate: dict) -> dict:
    enriched = enrich_candidate(observer, candidate)
    if not candidate_has_required_facts(enriched):
        return {"candidate": enriched, "judgement": {"decision":"ignore","confidence":1.0,"reason":"Candidate missing required deterministic facts.","message":None}, "model":"deterministic-policy"}
    if not candidate_is_valid(enriched):
        return {"candidate": enriched, "judgement": {"decision":"ignore","confidence":1.0,"reason":"Candidate invalidated by current deterministic state.","message":None}, "model":"deterministic-policy"}
    request = {"model": settings.judgement_model, "stream": False, "format":"json", "messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":json.dumps({"context":build_judgement_context(observer),"candidate":enriched}, separators=(",",":"))}], "options":{"temperature":0.1}}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{settings.ollama_url}/api/chat", json=request); response.raise_for_status(); result=response.json()
    judgement=json.loads(result["message"]["content"])
    return {"candidate": enriched, "judgement": judgement, "model": settings.judgement_model}
