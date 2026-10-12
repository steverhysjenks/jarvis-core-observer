import pytest

import app.observer.action_executor as executor


@pytest.mark.asyncio
async def test_executor_rejects_unapproved_action(
    monkeypatch,
):
    called = False

    async def fake_announce(*args, **kwargs):
        nonlocal called
        called = True
        return {"announced": True}

    monkeypatch.setattr(
        executor,
        "announce_to_user",
        fake_announce,
    )

    result = await executor.execute_action(
        {
            "allowed": False,
        },
        candidate_key="test:key",
    )

    assert result["executed"] is False
    assert result["reason"] == "action_not_allowed"
    assert called is False


@pytest.mark.asyncio
async def test_executor_rejects_unknown_interaction():
    result = await executor.execute_action(
        {
            "allowed": True,
            "interaction": "turn_off_house",
        },
        candidate_key="test:key",
    )

    assert result["executed"] is False

    assert (
        result["reason"]
        == "unsupported_interaction"
    )


@pytest.mark.asyncio
async def test_failed_voice_delivery_does_not_mark_announced(
    monkeypatch,
):
    marked = False

    async def fake_announce(*args, **kwargs):
        return {
            "announced": False,
            "reason": "test_voice_failure",
        }

    def fake_mark(key):
        nonlocal marked
        marked = True
        return {}

    monkeypatch.setattr(
        executor,
        "announce_to_user",
        fake_announce,
    )

    monkeypatch.setattr(
        executor,
        "mark_announced",
        fake_mark,
    )

    result = await executor.execute_action(
        {
            "allowed": True,
            "interaction": "announce",
            "message": "Test",
            "preannounce": True,
        },
        candidate_key="test:key",
    )

    assert result["executed"] is False
    assert marked is False


@pytest.mark.asyncio
async def test_success_marks_ledger_before_history(
    monkeypatch,
):
    calls = []

    async def fake_announce(*args, **kwargs):
        calls.append("announce")

        return {
            "announced": True,
            "location": {
                "area": "Office area",
            },
            "target": {
                "entity_id": "test.satellite",
            },
        }

    def fake_mark(key):
        calls.append("ledger")

        return {
            "announced_at":
                "2026-10-05T18:00:00+01:00",
            "announcement_count": 1,
        }

    def fake_delivery(**kwargs):
        calls.append("history")

        return {
            "id": 1,
        }

    monkeypatch.setattr(
        executor,
        "announce_to_user",
        fake_announce,
    )

    monkeypatch.setattr(
        executor,
        "mark_announced",
        fake_mark,
    )

    monkeypatch.setattr(
        executor,
        "record_delivery",
        fake_delivery,
    )

    result = await executor.execute_action(
        {
            "allowed": True,
            "interaction": "announce",
            "message": "Test",
            "preannounce": True,
        },
        candidate_key="test:key",
        candidate_type="test",
    )

    assert result["executed"] is True

    assert calls == [
        "announce",
        "ledger",
        "history",
    ]


@pytest.mark.asyncio
async def test_history_failure_cannot_undo_delivery(
    monkeypatch,
):
    async def fake_announce(*args, **kwargs):
        return {
            "announced": True,
            "location": {
                "area": "Office area",
            },
            "target": {
                "entity_id": "test.satellite",
            },
        }

    def fake_mark(key):
        return {
            "announced_at":
                "2026-10-05T18:00:00+01:00",
            "announcement_count": 1,
        }

    def broken_history(**kwargs):
        raise RuntimeError(
            "simulated history failure"
        )

    monkeypatch.setattr(
        executor,
        "announce_to_user",
        fake_announce,
    )

    monkeypatch.setattr(
        executor,
        "mark_announced",
        fake_mark,
    )

    monkeypatch.setattr(
        executor,
        "record_delivery",
        broken_history,
    )

    result = await executor.execute_action(
        {
            "allowed": True,
            "interaction": "announce",
            "message": "Test",
        },
        candidate_key="test:key",
    )

    assert result["executed"] is True
    assert result["ledger"]["announcement_count"] == 1
    assert result["delivery"] is None

    assert "RuntimeError" in (
        result["delivery_history_error"]
    )
