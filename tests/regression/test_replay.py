from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import app.voice.replay as replay


TZ = ZoneInfo("Europe/London")


def recent_delivery():
    return {
        "id": 42,
        "candidate_key": "routine:test",
        "candidate_type":
            "routine_departure_deviation",
        "message":
            "You normally leave around now.",
        "delivered_at":
            datetime.now(TZ).isoformat(),
    }


@pytest.mark.asyncio
async def test_no_previous_announcement_fails_cleanly(
    monkeypatch,
):
    monkeypatch.setattr(
        replay,
        "latest_proactive_delivery",
        lambda: None,
    )

    result = (
        await replay.repeat_last_announcement()
    )

    assert result["replayed"] is False

    assert (
        result["reason"]
        == "no_recent_announcement"
    )


@pytest.mark.asyncio
async def test_expired_replay_rejected(
    monkeypatch,
):
    old = recent_delivery()

    old["delivered_at"] = (
        datetime.now(TZ)
        - timedelta(hours=2)
    ).isoformat()

    monkeypatch.setattr(
        replay,
        "latest_proactive_delivery",
        lambda: old,
    )

    result = (
        await replay.repeat_last_announcement()
    )

    assert result["replayed"] is False

    assert (
        result["reason"]
        == "no_recent_announcement"
    )


@pytest.mark.asyncio
async def test_replay_prefers_interaction_satellite(
    monkeypatch,
):
    original = recent_delivery()
    recorded = {}

    monkeypatch.setattr(
        replay,
        "latest_proactive_delivery",
        lambda: original,
    )

    async def fake_satellite(
        message,
        satellite,
        preannounce=True,
    ):
        return {
            "announced": True,
            "location": {
                "area": "Kitchen",
            },
            "target": {
                "entity_id": satellite,
            },
        }

    async def forbidden_user(*args, **kwargs):
        raise AssertionError(
            "Semantic fallback should not run"
        )

    def fake_record(**kwargs):
        recorded.update(kwargs)
        return {"id": 99}

    monkeypatch.setattr(
        replay,
        "announce_to_satellite",
        fake_satellite,
    )

    monkeypatch.setattr(
        replay,
        "announce_to_user",
        forbidden_user,
    )

    monkeypatch.setattr(
        replay,
        "record_delivery",
        fake_record,
    )

    result = (
        await replay.repeat_last_announcement(
            source_satellite=
                "assist_satellite."
                "kitchen_voice_assistant_"
                "assist_satellite"
        )
    )

    assert result["replayed"] is True

    assert (
        result["delivery_route"]
        == "interaction_endpoint"
    )

    assert (
        recorded["delivery_type"]
        == "user_requested_replay"
    )

    assert (
        recorded["candidate_key"]
        == original["candidate_key"]
    )


@pytest.mark.asyncio
async def test_invalid_source_falls_back_to_user_location(
    monkeypatch,
):
    original = recent_delivery()

    monkeypatch.setattr(
        replay,
        "latest_proactive_delivery",
        lambda: original,
    )

    async def invalid_satellite(*args, **kwargs):
        return {
            "announced": False,
            "reason":
                "invalid_source_satellite",
        }

    async def semantic_user(*args, **kwargs):
        return {
            "announced": True,
            "location": {
                "area": "Office area",
            },
            "target": {
                "entity_id": "office.test",
            },
        }

    monkeypatch.setattr(
        replay,
        "announce_to_satellite",
        invalid_satellite,
    )

    monkeypatch.setattr(
        replay,
        "announce_to_user",
        semantic_user,
    )

    monkeypatch.setattr(
        replay,
        "record_delivery",
        lambda **kwargs: {"id": 100},
    )

    result = (
        await replay.repeat_last_announcement(
            source_satellite="invalid.test"
        )
    )

    assert result["replayed"] is True

    assert (
        result["delivery_route"]
        == "semantic_user_location"
    )
