import json
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config import settings
from app.observer.enrichment import enrich_candidate, candidate_has_required_facts, candidate_is_valid

class Judgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["ignore", "monitor", "interrupt"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)
    message: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_message_contract(self):
        if self.decision == "interrupt":
            if self.message is None or not self.message.strip():
                raise ValueError("interrupt requires a non-empty message")
            self.message = self.message.strip()
        elif self.message is not None:
            raise ValueError("ignore/monitor require message=null")
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("reason must not be blank")
        return self

SYSTEM_PROMPT = """
You are the judgement component of a proactive home AI observer.

A deterministic system has already:
- observed the environment;
- detected something potentially noteworthy;
- calculated factual evidence about the situation.

Your task is only to judge whether the user should be interrupted.

Decisions:
- ignore: no further attention is useful;
- monitor: noteworthy, but interruption is not yet justified;
- interrupt: there is sufficient reason to proactively tell the user.

Be conservative about interruption, but do not avoid interruption when
the supplied evidence indicates the user may benefit from timely action.

Treat supplied facts as authoritative.
Do not recalculate times or contradict supplied facts.
Do not invent intentions, routines, people, events, destinations,
causes, household rules, or capabilities.

The only proactive capability available to you is:
- speak one short informational announcement to the user in their current room.

If you choose interrupt:
- provide only the words that should be spoken;
- keep the message short and natural;
- state the useful information directly;
- make the announcement informational rather than conversational;
- do not ask the user a question or require acknowledgement;
- do not speculate about why the situation occurred;
- do not imply the user forgot, intended, failed, or made a mistake unless that fact was explicitly supplied;
- do not ask whether the user wants you to perform another action;
- do not offer to send messages, change devices, contact people, modify calendars, control the home, or perform any other action;
- do not claim that any action has already been performed.

Return JSON only:
{
  "decision": "ignore|monitor|interrupt",
  "confidence": 0.0,
  "reason": "short explanation",
  "message": null
}

confidence must be between 0.0 and 1.0.
If decision is "interrupt", message must be a short natural spoken message suitable for a home voice assistant.
For ignore or monitor, message must be null.
""".strip()

def build_judgement_context(observer: dict) -> dict:
    return {k: observer.get(k) for k in ("local_time", "user", "environment", "schedule", "recent_activity")}

def safe_failure_judgement(reason: str) -> dict:
    return {"decision": "ignore", "confidence": 1.0, "reason": reason, "message": None}

async def judge_candidate(observer: dict, candidate: dict) -> dict:
    enriched = enrich_candidate(observer, candidate)
    if not candidate_has_required_facts(enriched):
        return {"candidate": enriched, "judgement": safe_failure_judgement("Candidate missing required deterministic facts."), "model": "deterministic-policy"}
    if not candidate_is_valid(enriched):
        return {"candidate": enriched, "judgement": safe_failure_judgement("Candidate invalidated by current deterministic state."), "model": "deterministic-policy"}
    payload = {"context": build_judgement_context(observer), "candidate": enriched}
    request = {"model": settings.judgement_model, "stream": False, "format": "json", "messages": [{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":json.dumps(payload,separators=(",",":"))}], "options":{"temperature":0.1}}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{settings.ollama_url}/api/chat", json=request)
            response.raise_for_status(); result = response.json()
        raw = json.loads(result["message"]["content"])
        judgement = Judgement.model_validate(raw)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValidationError) as exc:
        return {"candidate": enriched, "judgement": safe_failure_judgement("Judgement model output failed validation."), "model": settings.judgement_model, "judgement_error": type(exc).__name__}
    return {"candidate": enriched, "judgement": judgement.model_dump(), "model": settings.judgement_model}
