import pytest

import app.observer.evaluator as evaluator


@pytest.mark.asyncio
async def test_evaluator_order_and_fresh_user_context(
    monkeypatch,
):
    calls = []

    async def fake_judge(observer, candidate):
        calls.append("judge")
        return {
            "judgement": {
                "decision": "interrupt",
                "confidence": 0.9,
                "reason": "test",
                "message": "Test message",
            },
            "candidate": {
                **candidate,
                "enriched": True,
            },
            "model": "mock-model",
        }

    def fake_record(
        candidate,
        mode,
        judgement,
        model,
    ):
        calls.append("ledger")
        assert candidate["enriched"] is True
        return {
            "candidate_key": "test:key",
            "ledger_status": "new",
            "mode": mode,
        }

    async def fake_user():
        calls.append("fresh_user")
        return {
            "home": True,
            "location": {
                "source": "bermuda",
                "stable": True,
                "area": "Office area",
            },
        }

    def fake_policy(
        result,
        user,
        mode,
        candidate_key,
    ):
        calls.append("policy")
        assert candidate_key == "test:key"
        assert user["location"]["area"] == "Office area"
        return {
            "allowed": True,
            "interaction": "announce",
            "message": "Test message",
        }

    async def fake_execute(
        policy,
        candidate_key,
        candidate_type=None,
    ):
        calls.append("execute")
        return {
            "executed": True,
            "reason": "announcement_delivered",
        }

    monkeypatch.setattr(
        evaluator,
        "judge_candidate",
        fake_judge,
    )
    monkeypatch.setattr(
        evaluator,
        "record_candidate",
        fake_record,
    )
    monkeypatch.setattr(
        evaluator,
        "build_user_context",
        fake_user,
    )
    monkeypatch.setattr(
        evaluator,
        "evaluate_action_policy",
        fake_policy,
    )
    monkeypatch.setattr(
        evaluator,
        "execute_action",
        fake_execute,
    )

    result = await evaluator.evaluate_candidate(
        {
            "user": {
                "location": {
                    "area": "Kitchen",
                }
            }
        },
        {
            "type": "test_candidate",
        },
        mode="live",
    )

    assert calls == [
        "judge",
        "ledger",
        "fresh_user",
        "policy",
        "execute",
    ]

    assert result["action_taken"] is True


@pytest.mark.asyncio
async def test_shadow_denial_never_reaches_executor(
    monkeypatch,
):
    executed = False

    async def fake_judge(observer, candidate):
        return {
            "judgement": {
                "decision": "interrupt",
                "confidence": 0.9,
                "reason": "test",
                "message": "Test",
            },
            "candidate": candidate,
            "model": "mock",
        }

    monkeypatch.setattr(
        evaluator,
        "judge_candidate",
        fake_judge,
    )

    monkeypatch.setattr(
        evaluator,
        "record_candidate",
        lambda *args, **kwargs: {
            "candidate_key": "test:key",
        },
    )

    async def fake_user():
        return {
            "home": True,
            "location": {},
        }

    monkeypatch.setattr(
        evaluator,
        "build_user_context",
        fake_user,
    )

    monkeypatch.setattr(
        evaluator,
        "evaluate_action_policy",
        lambda *args, **kwargs: {
            "allowed": False,
            "reason": "observer_not_live",
        },
    )

    async def forbidden_execute(*args, **kwargs):
        nonlocal executed
        executed = True
        return {}

    monkeypatch.setattr(
        evaluator,
        "execute_action",
        forbidden_execute,
    )

    result = await evaluator.evaluate_candidate(
        {},
        {
            "type": "test_candidate",
        },
        mode="shadow",
    )

    assert executed is False
    assert result["action_taken"] is False
    assert (
        result["action"]["reason"]
        == "observer_not_live"
    )


@pytest.mark.asyncio
async def test_candidates_evaluated_sequentially(
    monkeypatch,
):
    order = []

    async def fake_evaluate(
        observer,
        candidate,
        mode,
    ):
        order.append(candidate["id"])
        return {
            "id": candidate["id"],
        }

    monkeypatch.setattr(
        evaluator,
        "evaluate_candidate",
        fake_evaluate,
    )

    result = await evaluator.evaluate_candidates(
        {},
        [
            {"id": 1},
            {"id": 2},
            {"id": 3},
        ],
    )

    assert order == [1, 2, 3]
    assert [x["id"] for x in result] == [1, 2, 3]
