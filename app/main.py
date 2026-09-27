import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException, Query
from app.adapters.homeassistant import HomeAssistantError
from app.context.calendar import build_calendar_context
from app.context.history import build_history_context
from app.context.home import build_home_context
from app.context.user import build_user_context
from app.observer.context import build_observer_snapshot
from app.observer.runner import get_observer_status, observer_loop
LOCAL_TIMEZONE=ZoneInfo("Europe/London")

@asynccontextmanager
async def lifespan(app: FastAPI):
    task=asyncio.create_task(observer_loop(),name="jarvis-observer")
    try: yield
    finally:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass

app=FastAPI(title="Jarvis Core",description="Context and proactive intelligence layer for Jarvis",version="0.7.0",lifespan=lifespan)
@app.get("/")
async def root(): return {"service":"Jarvis Core","status":"online","version":"0.7.0","docs":"/docs"}
@app.get("/health")
async def health(): return {"status":"healthy","service":"jarvis-core","version":"0.7.0","timestamp":datetime.now(LOCAL_TIMEZONE).isoformat(),"timezone":"Europe/London"}
@app.get("/context/home")
async def home_context():
    try: return await build_home_context()
    except HomeAssistantError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
@app.get("/context/user")
async def user_context():
    try: return await build_user_context()
    except HomeAssistantError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
@app.get("/context/calendar")
async def calendar_context(days:int=Query(default=7,ge=1,le=30)):
    try: return await build_calendar_context(days=days)
    except HomeAssistantError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
@app.get("/context/history")
async def history_context(hours:int=Query(default=24,ge=1,le=168)):
    try: return await build_history_context(hours=hours)
    except HomeAssistantError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
@app.get("/context/observer")
async def observer_context():
    try: return await build_observer_snapshot()
    except HomeAssistantError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
@app.get("/observer/status")
async def observer_status(): return get_observer_status()
