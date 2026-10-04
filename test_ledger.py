import json

from app.storage.ledger import (
    DATABASE_PATH,
    recent_entries,
    record_candidate,
)


candidate = {
    "type": "possible_bins_not_put_out",
    "priority": "candidate",
    "reason": (
        "waste_collection_tomorrow_"
        "no_entrance_activity"
    ),
    "collection_date": "2026-10-01",
    "collection_types": [
        "Black Bin & Food Waste",
        "Recycling",
    ],
}


print("Database:")
print(DATABASE_PATH)

print()
print("First observation:")
print(
    json.dumps(
        record_candidate(candidate),
        indent=2,
    )
)

print()
print("Second observation:")
print(
    json.dumps(
        record_candidate(candidate),
        indent=2,
    )
)

print()
print("Ledger:")
print(
    json.dumps(
        recent_entries(),
        indent=2,
    )
)
