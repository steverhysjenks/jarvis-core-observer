import pytest

from app.observer.context import (
    build_observer_context,
    build_observer_snapshot,
)


pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_live_observer_context_contract():
    context = await build_observer_context()

    assert "generated_at" in context
    assert "local_time" in context
    assert "user" in context
    assert "environment" in context
    assert "schedule" in context
    assert "household" in context
    assert "recent_activity" in context
    assert "capabilities" in context

    assert (
        context["local_time"]["timezone"]
        == "Europe/London"
    )


@pytest.mark.asyncio
async def test_live_work_context_contract():
    context = await build_observer_context()

    work = context["schedule"]["work"]

    assert work["calendar_status"] in {
        "free",
        "busy",
        "tentative",
        "away",
        "unknown",
    }

    assert work["expectation"] in {
        "applicable",
        "not_applicable",
        "suspended_leave",
        "suspended_holiday",
    }

    assert isinstance(
        work["normal_working_day"],
        bool,
    )

    assert isinstance(
        work["ha_workday"],
        bool,
    )

    assert isinstance(
        work["on_leave"],
        bool,
    )


@pytest.mark.asyncio
async def test_live_observer_snapshot_contract():
    snapshot = await build_observer_snapshot()

    assert "attention" in snapshot

    attention = snapshot["attention"]

    assert isinstance(
        attention["candidate_count"],
        int,
    )

    assert isinstance(
        attention["candidates"],
        list,
    )

    assert (
        attention["candidate_count"]
        == len(attention["candidates"])
    )
