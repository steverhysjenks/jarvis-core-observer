from app.context.user import build_user_context
from app.storage.ledger import recent_observations
from app.voice.routing import resolve_voice_target


async def get_shadow_announcements(
    limit: int = 50,
) -> dict:
    """
    Return recent messages that Jarvis judged worthy of an
    interruption.

    This is a read-only shadow-mode view. It never performs
    an announcement or any other external action.
    """

    observations = recent_observations(
        limit=limit,
    )

    candidates = [
        observation
        for observation in observations
        if (
            observation.get("judgement")
            == "interrupt"
            and observation.get("message")
        )
    ]

    user = await build_user_context()

    location = user.get(
        "location",
        {},
    )

    area = location.get("area")

    voice_target = resolve_voice_target(
        area
    )

    announcements = []

    for observation in candidates:
        announcements.append(
            {
                "observation_id":
                    observation.get("id"),
                "candidate_key":
                    observation.get(
                        "candidate_key"
                    ),
                "candidate_type":
                    observation.get(
                        "candidate_type"
                    ),
                "observed_at":
                    observation.get(
                        "observed_at"
                    ),
                "judgement":
                    observation.get(
                        "judgement"
                    ),
                "confidence":
                    observation.get(
                        "confidence"
                    ),
                "reason":
                    observation.get(
                        "reason"
                    ),
                "message":
                    observation.get(
                        "message"
                    ),
                "model":
                    observation.get(
                        "model"
                    ),
                "would_target": {
                    "area":
                        area,
                    "voice":
                        voice_target,
                },
                "action_taken": False,
            }
        )

    return {
        "mode": "shadow",
        "count": len(
            announcements
        ),
        "current_user_location": {
            "home":
                user.get("home"),
            "area":
                area,
            "floor":
                location.get("floor"),
            "source":
                location.get("source"),
        },
        "voice_target":
            voice_target,
        "announcements":
            announcements,
    }
