import json
from app.storage.ledger import recent_entries,recent_observations
print("=== SITUATIONS ===")
print(json.dumps(recent_entries(),indent=2))
print("\n=== OBSERVATIONS ===")
print(json.dumps(recent_observations(),indent=2))
