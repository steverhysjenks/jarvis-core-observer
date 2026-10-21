"""Offline summary boundary tests; all source data is synthetic."""
from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

from app.main import app
from app.nutrition import summary
from app.adapters.sparky_mcp import NutritionUnavailable

TOKEN = "synthetic-summary-token-for-offline-tests-only"
DAY = "2026-10-21"


@pytest.fixture(autouse=True)
def setup_summary(monkeypatch, tmp_path):
    token = tmp_path / "summary.token"
    token.write_text(TOKEN)
    monkeypatch.setenv("NUTRITION_ENABLED", "true")
    monkeypatch.setenv("NUTRITION_SUMMARY_TOKEN_FILE", str(token))
    monkeypatch.setattr(summary, "now", lambda: datetime(2026, 10, 21, 10, tzinfo=summary.TZ))
    summary._cache.clear()
    async def native(name, args, **kwargs):
        assert not kwargs.get("write")
        if name == "sparky_get_goal_snapshot":
            return {"calories": 2000}
        assert name == "sparky_get_nutrition_summary"
        return [{"entry_date": DAY, "calories": 500, "protein": 20, "carbs": 60, "fat": 15, "energy_unit": "kcal"}]
    monkeypatch.setattr(summary.sparky, "call", native)


async def get(path="today", token=TOKEN, method="GET"):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://isolated.test") as client:
        return await client.request(method, "/nutrition/summary/" + path, headers={"Authorization": "Bearer " + token})


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["", "wrong", "isolated-test-placeholder"])
async def test_summary_rejects_missing_wrong_and_broad_token(token, monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("Unauthorised request reached MCP")
    monkeypatch.setattr(summary.sparky, "call", forbidden)
    for path in ("today", "history"):
        assert (await get(path, token)).status_code == 401


@pytest.mark.asyncio
async def test_summary_credential_cannot_write_or_use_conversation():
    assert (await get(method="POST")).status_code == 405
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://isolated.test") as client:
        r = await client.post("/request", headers={"Authorization": "Bearer " + TOKEN}, json={"text": "Log water"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_current_native_values_and_cache_headers():
    r = await get()
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    data = r.json()
    assert data["date"] == DAY and data["status"] == "valid"
    assert [data[k] for k in ("goal_kcal", "consumed_kcal", "remaining_kcal", "progress_percent", "protein_g", "carbs_g", "fat_g")] == [2000, 500, 1500, 25, 20, 60, 15]
    assert data["updated_at"].endswith("+01:00")
    assert TOKEN not in r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("goal", [None, 0, False, "2000"])
async def test_absent_zero_invalid_goals_never_invent_target(goal, monkeypatch):
    original = summary.sparky.call
    async def native(name, args):
        return {"calories": goal} if name == "sparky_get_goal_snapshot" else await original(name, args)
    monkeypatch.setattr(summary.sparky, "call", native)
    data = (await get()).json()
    assert data["goal_kcal"] == (0 if goal == 0 and not isinstance(goal, bool) else None)
    assert data["progress_percent"] is None


@pytest.mark.asyncio
async def test_empty_diary_is_unknown_not_zero(monkeypatch):
    async def native(name, args):
        return {"calories": 2000} if name == "sparky_get_goal_snapshot" else []
    monkeypatch.setattr(summary.sparky, "call", native)
    daily = (await get()).json()
    assert daily["goal_kcal"] == 2000 and daily["has_entries"] is False
    assert daily["consumed_kcal"] is None and daily["remaining_kcal"] is None
    history = (await get("history")).json()
    assert len(history["days"]) == 14 and history["logged_days"] == 0
    assert history["average_logged_day_kcal"] is None
    assert all(d["calories_kcal"] is None and d["status"] == "no_entries" for d in history["days"])


@pytest.mark.asyncio
async def test_history_one_bounded_aggregate_call_and_completed_average(monkeypatch):
    calls = []
    async def native(name, args):
        calls.append((name, args))
        return [{"entry_date": day, "calories": kcal, "energy_unit": "kcal"}
                for day, kcal in [("2026-10-08", 0), ("2026-10-20", 2000), (DAY, 500)]]
    monkeypatch.setattr(summary.sparky, "call", native)
    data = (await get("history")).json()
    assert data["average_logged_day_kcal"] == 1000
    assert data["logged_days"] == 3 and data["completed_logged_days"] == 2
    assert data["today_kcal"] == 500 and data["average_includes_today"] is False
    assert len(data["days"]) == 14 and sum(d["is_today"] for d in data["days"]) == 1
    assert data["days"][1]["calories_kcal"] is None
    await get("history")
    assert calls == [("sparky_get_nutrition_summary", {"start_date": "2026-10-08", "end_date": DAY})]
    assert len(json.dumps(data)) < 4096


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [{}, [{"entry_date": DAY, "energy_unit": "kJ"}],
    [{"entry_date": "2026-10-22", "energy_unit": "kcal"}],
    [{"entry_date": DAY, "energy_unit": "kcal"}] * 2])
async def test_malformed_source_fails_closed(rows, monkeypatch):
    async def native(*args):
        return rows
    monkeypatch.setattr(summary.sparky, "call", native)
    r = await get()
    assert r.status_code == 503 and r.json()["consumed_kcal"] is None


@pytest.mark.asyncio
async def test_missing_nutrients_and_legacy_warning_not_silently_zero(monkeypatch):
    async def native(name, args):
        if name == "sparky_get_goal_snapshot":
            return {"calories": 2000}
        return [{"entry_date": DAY, "calories": 500, "energy_unit": "kcal"}]
    monkeypatch.setattr(summary.sparky, "call", native)
    assert (await get()).json()["protein_g"] is None
    summary._cache.clear()
    async def warned(name, args):
        data = await native(name, args)
        if isinstance(data, list):
            data[0]["nutrition_warning"] = "synthetic legacy ambiguity"
        return data
    monkeypatch.setattr(summary.sparky, "call", warned)
    assert (await get()).json()["status"] == "partial"
    h = (await get("history")).json()
    assert h["days"][-1]["has_entries"] is True and h["days"][-1]["status"] == "unavailable"
    assert h["days"][-1]["calories_kcal"] is None


@pytest.mark.asyncio
async def test_source_outage_never_returns_old_as_fresh(monkeypatch):
    await get()
    await get("history")
    monkeypatch.setattr(summary.time, "monotonic", lambda: float("inf"))
    async def unavailable(*args):
        raise NutritionUnavailable("do not disclose internal details")
    monkeypatch.setattr(summary.sparky, "call", unavailable)
    for path in ("today", "history"):
        r = await get(path)
        assert r.status_code == 503 and r.json()["status"] == "unavailable"
        assert r.json()["updated_at"] is None and "internal details" not in r.text
        if path == "history":
            assert len(r.json()["days"]) == 14
            assert all(d["has_entries"] is None for d in r.json()["days"])


@pytest.mark.asyncio
async def test_midnight_invalidates_cache(monkeypatch):
    calls = []
    async def native(name, args):
        calls.append(args)
        return {} if name == "sparky_get_goal_snapshot" else []
    monkeypatch.setattr(summary.sparky, "call", native)
    await get()
    await get()
    assert len(calls) == 2
    monkeypatch.setattr(summary, "now", lambda: datetime(2026, 10, 22, 0, tzinfo=summary.TZ))
    assert (await get()).json()["date"] == "2026-10-22"
    assert len(calls) == 4


@pytest.mark.parametrize("utc,local,offset", [
    ("2026-03-29T00:30:00+00:00", "2026-03-29", 0),
    ("2026-03-29T01:30:00+00:00", "2026-03-29", 1),
    ("2026-10-25T00:30:00+00:00", "2026-10-25", 1),
    ("2026-10-25T01:30:00+00:00", "2026-10-25", 0),
    ("2026-10-21T23:30:00+00:00", "2026-10-22", 1)])
def test_london_calendar_and_dst_boundaries(utc, local, offset):
    stamp = datetime.fromisoformat(utc).astimezone(summary.TZ)
    assert stamp.date().isoformat() == local and stamp.utcoffset() == timedelta(hours=offset)
