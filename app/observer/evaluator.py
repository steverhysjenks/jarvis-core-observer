from app.context.user import (
    build_user_context,
)
from app.judgement.qwen import (
    judge_candidate,
)
from app.observer.action_executor import (
    execute_action,
)
from app.observer.action_policy import (
    evaluate_action_policy,
)
from app.storage.ledger import (
    record_candidate,
)


async def evaluate_candidate(
    observer: dict,
    candidate: dict,
    mode: str = "shadow",
) -> dict:
    """
    Evaluate one attention candidate, persist the
    judgement, apply deterministic action policy and,
    only when explicitly permitted, execute the action.

    Shadow mode can observe, judge and persist but can
    never cross the external-action boundary.
    """

    result = await judge_candidate(
        observer,
        candidate,
    )

    judgement = result["judgement"]
    enriched_candidate = result["candidate"]

    ledger = record_candidate(
        enriched_candidate,
        mode=mode,
        judgement=judgement,
        model=result["model"],
    )

    candidate_key = ledger[
        "candidate_key"
    ]

    # Use fresh semantic user context for the action
    # boundary rather than relying on the older observer
    # snapshot.
    user = await build_user_context()

    policy = evaluate_action_policy(
        result,
        user,
        mode=mode,
        candidate_key=candidate_key,
    )

    action = {
        "executed": False,
        "reason": policy.get(
            "reason",
            "action_not_allowed",
        ),
    }

    if policy.get("allowed") is True:
        action = await execute_action(
            policy,
            candidate_key,
            candidate_type=(
                enriched_candidate.get(
                    "type"
                )
            ),
        )

    return {
        **result,
        "ledger": ledger,
        "mode": mode,
        "policy": policy,
        "action": action,
        "action_taken":
            action.get("executed")
            is True,
    }


async def evaluate_candidates(
    observer: dict,
    candidates: list[dict],
    mode: str = "shadow",
) -> list[dict]:
    """
    Evaluate attention candidates sequentially.

    Sequential evaluation is deliberate so that local
    model load and proactive actions remain predictable.
    """

    results = []

    for candidate in candidates:
        result = await evaluate_candidate(
            observer,
            candidate,
            mode=mode,
        )

        results.append(result)

    return results
