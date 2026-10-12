import pytest

import app.observer.runner as runner


@pytest.mark.asyncio
async def test_cycle_order_is_resolve_detect_evaluate(
    monkeypatch,
):
    calls = []

    async def fake_context():
        calls.append("context")
        return {
            "generated_at":
                "2026-10-05T18:00:00+01:00",
        }

    def fake_resolve(context):
        calls.append("resolve")
        return [
            {
                "resolved": True,
            }
        ]

    async def fake_detect(context):
        calls.append("detect")
        return [
            {
                "type": "test_candidate",
            }
        ]

    async def fake_evaluate(
        context,
        candidates,
        mode,
    ):
        calls.append("evaluate")
        return [
            {
                "action_taken": False,
            }
        ]

    monkeypatch.setattr(
        runner,
        "build_observer_context",
        fake_context,
    )
    monkeypatch.setattr(
        runner,
        "resolve_open_situations",
        fake_resolve,
    )
    monkeypatch.setattr(
        runner,
        "run_detectors",
        fake_detect,
    )
    monkeypatch.setattr(
        runner,
        "evaluate_candidates",
        fake_evaluate,
    )

    result = await runner.run_observer_cycle()

    assert calls == [
        "context",
        "resolve",
        "detect",
        "evaluate",
    ]

    assert result["resolution_count"] == 1
    assert result["candidate_count"] == 1
    assert result["evaluation_count"] == 1


@pytest.mark.asyncio
async def test_cycle_failure_is_recorded_and_reraised(
    monkeypatch,
):
    async def broken_context():
        raise RuntimeError(
            "synthetic HA failure"
        )

    monkeypatch.setattr(
        runner,
        "build_observer_context",
        broken_context,
    )

    with pytest.raises(
        RuntimeError,
        match="synthetic HA failure",
    ):
        await runner.run_observer_cycle()

    assert (
        runner.observer_status["last_error"]
        == "RuntimeError: synthetic HA failure"
    )
