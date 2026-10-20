"""Deterministic clarification, source checks and durable write receipts."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.adapters.sparky_mcp import NutritionUnavailable, sparky

TZ = ZoneInfo("Europe/London")
STATE_PATH = Path("/var/lib/jarvis-core/nutrition-receipts.sqlite")
CORE = ("calories", "protein", "carbs", "fat")
UNSUPPORTED = ("sodium", "potassium", "fiber", "sugar", "vitamin_a", "vitamin_c", "calcium", "iron", "cholesterol", "saturated_fat", "polyunsaturated_fat", "monounsaturated_fat", "trans_fat")
INTENT = re.compile(r"^(?:nutrition\b|i(?:'ve| have)? (?:eaten|had|ate)\b|log\b|how (?:many calories|much protein)\b|what did i eat\b|(?:remove|delete|change)\b.*\b(?:logged|toast|chocolate|breakfast|lunch|dinner|snack)\b|(?:search|find)\b.*\b(?:food|nutrition)\b)", re.I)


def clarify(message):
    return {"status": "clarification_required", "message": message}


def context_key(request):
    return hashlib.sha256(json.dumps([request.area, request.listener, request.satellite]).encode()).hexdigest()


def connection():
    STATE_PATH.touch(mode=0o600, exist_ok=True)
    db = sqlite3.connect(STATE_PATH, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, context TEXT NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL, result TEXT, expires REAL NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS receipt_context ON receipts(context, expires)")
    db.execute("DELETE FROM receipts WHERE expires < ? AND state='pending'", (time.time(),))
    db.commit()
    return db


def scrub(value):
    """Native zero-valued micronutrients are not proof of source completeness."""
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: None if k in UNSUPPORTED else scrub(v) for k, v in value.items()}
    return value


async def provenance(food):
    """Verify macros before writes; do not treat missing OFF/Mealie data as zero."""
    kind = food.get("provider_type")
    if kind == "openfoodfacts":
        code = str(food.get("barcode") or food.get("provider_external_id") or "")
        if not re.fullmatch(r"\d{8,14}", code):
            return False
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False) as client:
                response = await client.get("https://world.openfoodfacts.org/api/v2/product/" + code + ".json", params={"fields": "code,nutriments,serving_quantity"}, headers={"User-Agent": "JarvisNutrition/1.0"})
                response.raise_for_status()
                product = response.json()["product"]
            declared = product.get("nutriments", {})
            for field in ("proteins", "carbohydrates", "fat"):
                if declared.get(field + "_100g") is None and not (product.get("serving_quantity") and declared.get(field + "_serving") is not None):
                    return False
            return any(declared.get(k) is not None for k in ("energy-kcal_100g", "energy-kj_100g", "energy_100g", "energy-kcal_serving"))
        except (httpx.HTTPError, ValueError, KeyError):
            return False
    if kind == "mealie":
        slug = str(food.get("provider_external_id", ""))
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", slug):
            return False
        try:
            token = Path(os.environ["NUTRITION_MEALIE_TOKEN_FILE"]).read_text().strip()
            async with httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False) as client:
                response = await client.get("http://192.168.0.26:9925/api/recipes/" + slug, headers={"Authorization": "Bearer " + token})
                response.raise_for_status()
                nutrition = response.json().get("nutrition") or {}
            return all(nutrition.get(key) not in (None, "") for key in ("calories", "proteinContent", "carbohydrateContent", "fatContent"))
        except (OSError, KeyError, httpx.HTTPError, ValueError):
            return False
    # Existing custom foods are the user's declarations, not generated estimates.
    return bool(food.get("is_custom")) and not kind


def choose_variant(food, variant_id, unit):
    variants = [food.get("default_variant")] + (food.get("variants") or [])
    unique = {v["id"]: v for v in variants if isinstance(v, dict) and v.get("id")}
    if variant_id:
        return unique.get(variant_id)
    matches = [v for v in unique.values() if str(v.get("serving_unit", "")).rstrip("s") == unit.rstrip("s")]
    return matches[0] if len(matches) == 1 else None


async def prepare(selection):
    action = selection.action
    if action in ("update_entry", "delete_entry"):
        if not selection.entry_id or not selection.entry_date:
            return clarify("Which diary entry and date do you mean? I will show the match before changing it.")
        diary = await sparky.call("sparky_get_food_diary", {"date": selection.entry_date.isoformat(), "limit": 50})
        entries = diary.get("food_entries", [])
        entry = next((e for e in entries if e.get("id") == str(selection.entry_id)), None)
        if entry is None:
            return clarify("I cannot identify that food entry on this date. Please select the entry from the diary.")
        payload = {"action": action, "entry_id": str(selection.entry_id)}
        if action == "update_entry":
            if selection.quantity is None or selection.unit is None:
                return clarify("What should the corrected amount and unit be?")
            # Keep the same historical reference unit; ambiguous conversion must be clarified.
            if str(entry.get("unit", "")).rstrip("s") != selection.unit.rstrip("s"):
                return clarify("Please correct it using the entry's original unit, so its nutrition reference is preserved.")
            payload.update(quantity=selection.quantity, unit=selection.unit)
        return {"payload": payload, "description": f"{action} for {entry.get('food_name', entry.get('name', 'selected food'))}, currently {entry.get('quantity')} {entry.get('unit')}, on {selection.entry_date} at {entry.get('entry_time')}; entry {entry['id']}"}
    if not selection.food_id or selection.quantity is None or not selection.unit or not selection.consumed_at or not selection.meal:
        return clarify("Which product, how much, which meal, and when did you eat it? Please select the food and give its actual consumption time.")
    if selection.meal == "dinner":
        return clarify("By dinner, do you mean lunch or your evening meal?")
    if selection.consumed_at.utcoffset() is None:
        return clarify("Please include the consumption date and timezone; I won't assume the recording time.")
    consumed = selection.consumed_at.astimezone(TZ)
    if consumed > datetime.now(TZ) + timedelta(minutes=5):
        return clarify("That consumption time is in the future. When did you actually eat it?")
    food = await sparky.call("sparky_get_food_details", {"food_id": str(selection.food_id)})
    if not isinstance(food, dict) or food.get("id") != str(selection.food_id):
        return clarify("Please select an identifiable food from SparkyFitness.")
    if not await provenance(food):
        return clarify("This food's declared calorie and macro data is incomplete or unverified. Please verify its source nutrition before logging it.")
    amount, unit = selection.quantity, selection.unit
    if unit == "packet":
        if selection.pack_weight_g is None:
            return clarify("What is the weight of one packet? I won't guess a pack size.")
        amount, unit = amount * selection.pack_weight_g, "g"
    variant = choose_variant(food, str(selection.variant_id) if selection.variant_id else None, unit)
    if not variant or (str(variant.get("serving_unit", "")).rstrip("s") != unit.rstrip("s") and not (unit == 'serving' and selection.variant_id)):
        return clarify("Which serving variant matches that unit? I won't convert slices, grams or servings without a defined reference.")
    if any(variant.get(k) is None for k in CORE):
        return clarify("The selected serving has incomplete calorie or macro data.")
    meal = {"evening meal": "dinner", "snack": "snacks"}.get(selection.meal, selection.meal)
    payload = {"action": "log_food", "food_id": food["id"], "variant_id": variant["id"], "quantity": amount, "unit": unit, "meal_type": meal, "entry_date": consumed.date().isoformat(), "entry_time": consumed.strftime("%H:%M")}
    return {"payload": payload, "description": f"Log {amount:g} {unit} of {food['name']} for {selection.meal} at {consumed.isoformat()}"}


async def confirm(request, identifier):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM receipts WHERE id=? AND context=?", (identifier, context_key(request))).fetchone()
        if row is None:
            return clarify("No matching nutrition confirmation is pending for this device.")
        if row["state"] == "done":
            return {"status": "already_completed", "receipt_id": identifier}
        if row["state"] != "pending":
            return {"status": "reconciliation_required", "message": "The previous write may have succeeded. Check the Sparky diary before retrying.", "receipt_id": identifier}
        if row["expires"] < time.time():
            return clarify("That confirmation expired. Please check the details again.")
        db.execute("UPDATE receipts SET state='in_flight' WHERE id=?", (identifier,))
        payload = json.loads(row["payload"])
    # Receipt is committed BEFORE sending. Never retry uncertain remote writes.
    try:
        value = await sparky.call("sparky_manage_food", payload, write=True)
        message = value.get("message", "") if isinstance(value, dict) else ""
        if not message.startswith("✅"):
            raise NutritionUnavailable("Unrecognised write acknowledgement")
        entry_id = re.search(r"Entry ID: ([0-9a-f-]{36})", message)
        if payload['action'] == 'log_food' and entry_id is None:
            raise NutritionUnavailable('Missing logged entry identifier')
        result = {"status": "completed", "receipt_id": identifier, "entry_id": entry_id.group(1) if entry_id else payload.get("entry_id")}
        with connection() as db:
            db.execute("UPDATE receipts SET state='done', result=? WHERE id=?", (json.dumps(result), identifier))
        from app.nutrition.dialogue import store
        store(context_key(request), {})
        return result
    except NutritionUnavailable:
        with connection() as db:
            db.execute("UPDATE receipts SET state='uncertain' WHERE id=?", (identifier,))
        return {"status": "reconciliation_required", "receipt_id": identifier, "message": "I cannot confirm the write result. Check the Sparky diary before retrying; I will not send it again."}


async def handle(request):
    text = request.text.strip().lower().rstrip(".?!")
    text = re.sub(r'^nutrition[: ]+\s*', '', text)
    selection = request.nutrition
    if request.nutrition_confirmation:
        return await confirm(request, request.nutrition_confirmation)
    if text in ("yes", "confirm nutrition"):
        with connection() as db:
            rows = db.execute("SELECT id FROM receipts WHERE context=? AND state='pending' AND expires>?", (context_key(request), time.time())).fetchall()
        if len(rows) != 1:
            return clarify("Please identify which nutrition action you are confirming.")
        return await confirm(request, rows[0]["id"])
    today = datetime.now(TZ).date()
    if selection is None and ("calories" in text or "protein" in text):
        data = await sparky.call("sparky_get_nutrition_summary", {"date": today.isoformat()})
        if not isinstance(data, list):
            raise NutritionUnavailable('Unexpected nutrition summary')
        rows = data
        if len(rows) > 1:
            raise NutritionUnavailable("Unexpected multi-day nutrition summary")
        row = rows[0] if rows else {key: 0 for key in CORE}
        if row.get('energy_unit', 'kcal') != 'kcal':
            raise NutritionUnavailable('Native energy unit is not kcal')
        totals = {key: row.get(key) for key in CORE}
        goal = await sparky.call("sparky_get_goal_snapshot", {"target_date": today.isoformat()})
        remaining = None
        if not row.get('nutrition_warning') and isinstance(goal.get("calories"), (int, float)) and isinstance(totals["calories"], (int, float)):
            remaining = goal["calories"] - totals["calories"]
        return {"status": "read", "date": today.isoformat(), "totals": totals, "energy_unit": "kcal", "nutrition_warning": row.get('nutrition_warning'), "remaining_calories": remaining, "source": "SparkyFitness native summary and effective goal", "unsupported_nutrients": {k: None for k in UNSUPPORTED}}
    if selection is None and text.startswith("what did i eat"):
        day = today - timedelta(days=1) if "yesterday" in text else today
        result = await sparky.call("sparky_get_food_diary", {"date": day.isoformat(), "limit": 50})
        if "evening" in text:
            entries = result.get("food_entries", [])
            result["food_entries"] = [r for r in entries if r.get("entry_time") and r["entry_time"] >= "17:00"]
            result["unclassified_time_count"] = sum(not r.get("entry_time") for r in entries)
            result["evening_definition"] = "17:00 onwards Europe/London; missing times are not assigned"
        return {"status": "read", "diary": scrub(result), "source": "SparkyFitness"}
    if selection is None and text.startswith(("search ", "find ")):
        query = re.sub(r"^(?:search|find)(?: for)?(?: food| nutrition)?\s+", "", text)
        result = await sparky.call("sparky_search_foods", {"query": query, "limit": 10})
        return {"status": "read", "foods": scrub(result), "source": "SparkyFitness saved foods"}
    if selection is None:
        from app.nutrition.dialogue import resolve
        resolved = await resolve(request)
        if isinstance(resolved, dict):
            return resolved
        selection = resolved
    prepared = await prepare(selection)
    if "payload" not in prepared:
        return prepared
    payload = prepared["payload"]
    fingerprint = hashlib.sha256(json.dumps([context_key(request), payload], sort_keys=True).encode()).hexdigest()
    identity = hashlib.sha256((request.request_id or fingerprint).encode()).hexdigest()
    with connection() as db:
        uncertain = db.execute("SELECT id FROM receipts WHERE context=? AND state IN ('in_flight','uncertain')", (context_key(request),)).fetchone()
        if uncertain:
            return {"status":"reconciliation_required", "receipt_id":uncertain['id'], "message":"An earlier write has an uncertain outcome. Verify the native diary and have the receipt reconciled before another write."}
        existing = db.execute("SELECT * FROM receipts WHERE id=?", (identity,)).fetchone()
        if existing:
            if existing["fingerprint"] != fingerprint or existing["context"] != context_key(request):
                return clarify("That request ID was already used for different details. Please start a new request.")
            if existing["state"] == "done":
                return {"status": "already_completed", "receipt_id": identity}
            if existing["state"] != "pending":
                return {"status": "reconciliation_required", "receipt_id": identity}
        else:
            db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?,?)", (identity, context_key(request), fingerprint, json.dumps(payload), "pending", None, time.time()+600))
    return {"status": "confirmation_required", "message": prepared["description"] + ". Confirm?", "confirmation_id": identity}
