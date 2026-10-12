import pytest

from app.context.availability import (
    build_availability_context,
)
from app.context.calendar import (
    build_calendar_context,
)
from app.context.history import (
    build_history_context,
)
from app.context.home import (
    build_home_context,
)
from app.context.places import (
    discover_places,
)
from app.context.user import (
    build_user_context,
)


pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_home_context_live():
    result = await build_home_context()

    assert isinstance(result, dict)
    assert "home" in result


@pytest.mark.asyncio
async def test_user_context_live():
    result = await build_user_context()

    assert isinstance(
        result["home"],
        bool,
    )

    assert "location" in result
    assert "source" in result["location"]


@pytest.mark.asyncio
async def test_places_live():
    result = await discover_places(
        force_refresh=True
    )

    assert "places" in result
    assert isinstance(
        result["places"],
        list,
    )

    ids = {
        place["id"]
        for place in result["places"]
    }

    assert "home" in ids


@pytest.mark.asyncio
async def test_calendar_live():
    result = await build_calendar_context(
        days=7
    )

    assert "events" in result
    assert "temporal" in result

    assert isinstance(
        result["events"],
        list,
    )


@pytest.mark.asyncio
async def test_history_live():
    result = await build_history_context(
        hours=2
    )

    assert "timeline" in result
    assert "summary" in result

    assert isinstance(
        result["timeline"],
        list,
    )

    assert (
        result["summary"]["total_events"]
        == len(result["timeline"])
    )


@pytest.mark.asyncio
async def test_availability_live():
    result = (
        await build_availability_context()
    )

    assert "work" in result
    assert "capabilities" in result

    assert result["work"][
        "calendar_status"
    ] in {
        "free",
        "busy",
        "tentative",
        "away",
        "unknown",
    }
