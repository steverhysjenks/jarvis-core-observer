import json

from app.observer.enrichment import (
    enrich_candidate,
    candidate_is_valid,
)


observer = {
    "user": {
        "home": True,
        "area": "Office area",
    },
    "schedule": {
        "next_timed_event": {
            "summary": "School pickup",
            "location": "School",
            "starts_in_minutes": 10,
        }
    },
}

candidate = {
    "type": "routine_departure_deviation",
    "routine": {
        "confidence": "strong",
        "recurrence": 1.0,
        "source_range": {
            "earliest": "15:02",
            "latest": "15:17",
        },
    },
    "current": {
        "time":
            "2026-09-30T15:30:00+01:00",
        "minutes_from_expected": 16.0,
    },
}

enriched = enrich_candidate(
    observer,
    candidate,
)

print("HOME + LATE")
print("===========")
print(
    json.dumps(
        enriched["facts"],
        indent=2,
    )
)
print(
    "Valid:",
    candidate_is_valid(enriched),
)

observer["user"]["home"] = False

enriched = enrich_candidate(
    observer,
    candidate,
)

print()
print("ALREADY AWAY")
print("============")
print(
    json.dumps(
        enriched["facts"],
        indent=2,
    )
)
print(
    "Valid:",
    candidate_is_valid(enriched),
)
