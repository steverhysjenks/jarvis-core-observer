import asyncio, logging
from datetime import datetime
from zoneinfo import ZoneInfo
from app.observer.context import build_observer_context
from app.observer.detectors import run_detectors
from app.observer.evaluator import evaluate_candidates
LOGGER=logging.getLogger("jarvis.observer"); LOCAL_TIMEZONE=ZoneInfo("Europe/London"); OBSERVER_INTERVAL_SECONDS=60; OBSERVER_MODE="shadow"
observer_status={"running":False,"mode":OBSERVER_MODE,"interval_seconds":OBSERVER_INTERVAL_SECONDS,"cycles_completed":0,"last_cycle_started":None,"last_cycle_completed":None,"last_error":None,"last_candidate_count":None,"last_evaluation_count":None}
def get_observer_status(): return {**observer_status}
async def run_observer_cycle():
    started=datetime.now(LOCAL_TIMEZONE); observer_status["last_cycle_started"]=started.isoformat()
    try:
        context=await build_observer_context(); candidates=await run_detectors(context); evaluations=await evaluate_candidates(context,candidates,mode=OBSERVER_MODE); completed=datetime.now(LOCAL_TIMEZONE)
        observer_status["cycles_completed"]+=1; observer_status["last_cycle_completed"]=completed.isoformat(); observer_status["last_candidate_count"]=len(candidates); observer_status["last_evaluation_count"]=len(evaluations); observer_status["last_error"]=None
        LOGGER.info("Observer cycle complete: candidates=%s evaluations=%s",len(candidates),len(evaluations)); return {"generated_at":context["generated_at"],"candidate_count":len(candidates),"evaluation_count":len(evaluations),"evaluations":evaluations}
    except Exception as exc:
        observer_status["last_error"]=f"{type(exc).__name__}: {exc}"; raise
async def observer_loop():
    observer_status["running"]=True; LOGGER.info("Observer starting in %s mode with %ss interval",OBSERVER_MODE,OBSERVER_INTERVAL_SECONDS)
    try:
        while True:
            try: await run_observer_cycle()
            except asyncio.CancelledError: raise
            except Exception: LOGGER.exception("Observer cycle failed")
            await asyncio.sleep(OBSERVER_INTERVAL_SECONDS)
    finally:
        observer_status["running"]=False; LOGGER.info("Observer stopped")
