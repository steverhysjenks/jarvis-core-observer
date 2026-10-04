import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.adapters.homeassistant import HomeAssistantError
from app.context.calendar import build_calendar_context
from app.context.history import build_history_context
from app.context.home import build_home_context
from app.context.user import build_user_context
from app.observer.announcements import get_shadow_announcements
from app.observer.context import build_observer_snapshot
from app.observer.runner import (
    get_observer_status,
    observer_loop,
)
from app.voice.orchestrator import handle_voice_request
from app.voice.requests import VoiceRequest
from app.voice.replay import repeat_last_announcement
from app.storage.deliveries import recent_deliveries
from app.web.notifications import notification_history_html


LOCAL_TIMEZONE = ZoneInfo("Europe/London")

JARVIS_CORE_API_KEY = os.environ.get(
    "JARVIS_CORE_API_KEY",
    "",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    observer_task = asyncio.create_task(
        observer_loop(),
        name="jarvis-observer",
    )

    try:
        yield

    finally:
        observer_task.cancel()

        try:
            await observer_task

        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Jarvis Core",
    description="Context and proactive intelligence layer for Jarvis",
    version="1.1.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {
        "service": "Jarvis Core",
        "status": "online",
        "version": "1.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "jarvis-core",
        "version": "1.1.0",
        "timestamp": datetime.now(LOCAL_TIMEZONE).isoformat(),
        "timezone": "Europe/London",
    }


@app.get("/context/home")
async def home_context():
    try:
        return await build_home_context()
    except HomeAssistantError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@app.get("/context/user")
async def user_context():
    try:
        return await build_user_context()
    except HomeAssistantError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@app.get("/context/calendar")
async def calendar_context(
    days: int = Query(
        default=7,
        ge=1,
        le=30,
        description="Number of days of calendar context to retrieve",
    ),
):
    try:
        return await build_calendar_context(days=days)
    except HomeAssistantError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@app.get("/context/history")
async def history_context(
    hours: int = Query(
        default=24,
        ge=1,
        le=168,
        description="Number of hours of semantic history to retrieve",
    ),
):
    try:
        return await build_history_context(hours=hours)
    except HomeAssistantError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@app.get("/context/observer")
async def observer_context():
    try:
        return await build_observer_snapshot()
    except HomeAssistantError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@app.get("/observer/status")
async def observer_status():
    return get_observer_status()


@app.get("/observer/announcements")
async def observer_announcements(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description=(
            "Number of recent Observer decisions "
            "to inspect"
        ),
    ),
):
    try:
        return await get_shadow_announcements(
            limit=limit
        )
    except HomeAssistantError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@app.get("/api/notifications")
async def notification_history_api(
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description=(
            "Number of recent delivered "
            "notifications to return"
        ),
    ),
):
    return {
        "notifications":
            recent_deliveries(
                limit=limit
            ),
        "limit": limit,
    }


@app.get(
    "/notifications",
    response_class=HTMLResponse,
)
async def notification_history_page(
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
    ),
):
    return notification_history_html(
        limit=limit
    )


@app.post("/voice/repeat-last")
async def repeat_last_voice_message(
    authorization: str | None = Header(
        default=None
    ),
):
    expected = f"Bearer {JARVIS_CORE_API_KEY}"

    if (
        not JARVIS_CORE_API_KEY
        or authorization is None
        or not secrets.compare_digest(
            authorization,
            expected,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )

    return await repeat_last_announcement()


@app.post("/request")
async def request_handler(
    request: VoiceRequest,
    authorization: str | None = Header(default=None),
):
    """
    Process an inbound Jarvis request.

    Deterministic capabilities are attempted first.
    Requests not claimed by them fall through to the
    semantic routing path.
    """

    expected = f"Bearer {JARVIS_CORE_API_KEY}"

    if (
        not JARVIS_CORE_API_KEY
        or authorization is None
        or not secrets.compare_digest(
            authorization,
            expected,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )

    try:
        return await handle_voice_request(request)

    except HomeAssistantError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
