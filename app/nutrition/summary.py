"""Read-only, bounded nutrition projections; no diary persistence or conversation state."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
import math
import os
from pathlib import Path
import secrets
import time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.adapters.sparky_mcp import NutritionUnavailable, sparky

TZ = ZoneInfo("Europe/London")
router = APIRouter(prefix="/nutrition", tags=["nutrition summaries"])
_cache = {}
_locks = {name: asyncio.Lock() for name in ("today", "history")}


def now():
    return datetime.now(TZ)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def authorize(authorization):
    """A dedicated secret file: never accept the broad conversational API key."""
    if os.environ.get("NUTRITION_ENABLED", "false").lower() != "true":
        raise HTTPException(503, "Nutrition summaries unavailable")
    try:
        token = Path(os.environ["NUTRITION_SUMMARY_TOKEN_FILE"]).read_text().strip()
    except (KeyError, OSError):
        raise HTTPException(503, "Nutrition summaries unavailable") from None
    if len(token) < 32:
        raise HTTPException(503, "Nutrition summaries unavailable")
    supplied = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if not secrets.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(401, "Summary read credential required", headers={"WWW-Authenticate": "Bearer"})


def rows_by_date(data, start, end):
    if not isinstance(data, list) or len(data) > (end - start).days + 1:
        raise NutritionUnavailable("Invalid aggregate response")
    rows = {}
    for row in data:
        if not isinstance(row, dict):
            raise NutritionUnavailable("Invalid aggregate row")
        day = row.get("entry_date")
        if not isinstance(day, str) or not start.isoformat() <= day <= end.isoformat():
            raise NutritionUnavailable("Invalid aggregate date")
        try:
            if datetime.strptime(day, "%Y-%m-%d").date().isoformat() != day:
                raise ValueError()
        except ValueError:
            raise NutritionUnavailable("Invalid aggregate date") from None
        if day in rows or row.get("energy_unit") != "kcal":
            raise NutritionUnavailable("Duplicate date or unsupported energy unit")
        rows[day] = row
    return rows


def base(stamp):
    return {"timezone": "Europe/London", "updated_at": stamp.isoformat(), "status": "valid"}


async def current(stamp):
    day = stamp.date()
    rows = rows_by_date(await sparky.call("sparky_get_nutrition_summary", {"date": day.isoformat()}), day, day)
    goal = await sparky.call("sparky_get_goal_snapshot", {"target_date": day.isoformat()})
    if not isinstance(goal, dict):
        raise NutritionUnavailable("Invalid goal response")
    row = rows.get(day.isoformat())
    warning = bool(row and row.get("nutrition_warning"))
    totals = {key: number(row.get(key)) if row and not warning else None
              for key in ("calories", "protein", "carbs", "fat")}
    target, consumed = number(goal.get("calories")), totals["calories"]
    return {**base(stamp), "date": day.isoformat(), "goal_kcal": target,
            "consumed_kcal": consumed,
            "remaining_kcal": target - consumed if target is not None and consumed is not None else None,
            "progress_percent": round(consumed / target * 100, 2) if target and consumed is not None else None,
            "protein_g": totals["protein"], "carbs_g": totals["carbs"], "fat_g": totals["fat"],
            "has_entries": row is not None, "status": "partial" if warning else "valid",
            "source": "SparkyFitness native aggregates and effective goal",
            "nutrient_provenance": "Native v1.8.0 aggregates cannot distinguish missing source nutrients from zero"}


async def history(stamp):
    end = stamp.date()
    start = end - timedelta(days=13)
    rows = rows_by_date(await sparky.call("sparky_get_nutrition_summary",
                                        {"start_date": start.isoformat(), "end_date": end.isoformat()}), start, end)
    days = []
    for offset in range(14):
        day = start + timedelta(days=offset)
        row = rows.get(day.isoformat())
        value = number(row.get("calories")) if row and not row.get("nutrition_warning") else None
        days.append({"date": day.isoformat(), "calories_kcal": value, "has_entries": row is not None,
                     "is_today": day == end,
                     "status": "unavailable" if row and value is None else "valid" if row else "no_entries"})
    completed = [d["calories_kcal"] for d in days if not d["is_today"] and d["has_entries"] and d["calories_kcal"] is not None]
    incomplete = any(d["status"] == "unavailable" for d in days)
    return {**base(stamp), "window_days": 14, "start_date": start.isoformat(), "end_date": end.isoformat(),
            "days": days, "logged_days": sum(d["has_entries"] for d in days),
            "completed_logged_days": len(completed), "average_includes_today": False,
            "average_logged_day_kcal": round(sum(completed) / len(completed), 2) if completed and not incomplete else None,
            "today_kcal": days[-1]["calories_kcal"], "status": "partial" if incomplete else "valid"}


async def response(kind, authorization):
    authorize(authorization)
    async with _locks[kind]:
        stamp = now()
        cached = _cache.get(kind)
        if cached and cached[0] == stamp.date() and time.monotonic() < cached[1]:
            payload, code = deepcopy(cached[2]), cached[3]
        else:
            try:
                async with asyncio.timeout(20):
                    payload = await (current(stamp) if kind == "today" else history(stamp))
                # Never publish yesterday's response after an upstream call crosses midnight.
                if now().date() != stamp.date():
                    raise NutritionUnavailable("Diary date changed during retrieval")
                code = 200
            except (NutritionUnavailable, TimeoutError):
                payload = {"timezone": "Europe/London", "date": now().date().isoformat(),
                           "status": "unavailable", "updated_at": None, "error": "Nutrition source unavailable"}
                if kind == "history":
                    payload.update(window_days=14, days=[{"date": (now().date() - timedelta(days=13-i)).isoformat(),
                        "calories_kcal": None, "has_entries": None, "is_today": i == 13, "status": "unavailable"}
                        for i in range(14)], logged_days=None, completed_logged_days=None, average_logged_day_kcal=None)
                else:
                    payload.update({key: None for key in ("goal_kcal", "consumed_kcal", "remaining_kcal", "progress_percent", "protein_g", "carbs_g", "fat_g")})
                code = 503
            _cache[kind] = (stamp.date(), time.monotonic() + (30 if code == 200 else 5), deepcopy(payload), code)
    return JSONResponse(payload, status_code=code, headers={"Cache-Control": "no-store"})


@router.get("/summary/today")
async def today_summary(authorization: str | None = Header(default=None)):
    return await response("today", authorization)


@router.get("/summary/history")
async def history_summary(authorization: str | None = Header(default=None)):
    return await response("history", authorization)
