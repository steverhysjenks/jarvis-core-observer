from datetime import datetime
from zoneinfo import ZoneInfo
LOCAL_TIMEZONE = ZoneInfo("Europe/London")

def _minutes(time_string: str) -> int:
    hour, minute = map(int, time_string.split(":")); return hour * 60 + minute

def enrich_candidate(observer: dict, candidate: dict) -> dict:
    enriched = {**candidate, "facts": {}}
    facts = enriched["facts"]; user = observer.get("user", {}); schedule = observer.get("schedule", {})
    facts["user_currently_home"] = user.get("home") is True
    facts["user_area"] = user.get("area")
    if candidate.get("type") == "routine_departure_deviation":
        routine = candidate.get("routine", {}); current = candidate.get("current", {})
        facts["minutes_from_typical"] = current.get("minutes_from_expected")
        source_range = routine.get("source_range", {}); current_time = current.get("time"); latest = source_range.get("latest"); earliest = source_range.get("earliest")
        if current_time and earliest and latest:
            current_dt = datetime.fromisoformat(current_time).astimezone(LOCAL_TIMEZONE); current_minutes = current_dt.hour * 60 + current_dt.minute
            earliest_minutes = _minutes(earliest); latest_minutes = _minutes(latest)
            facts["outside_historical_range"] = not (earliest_minutes <= current_minutes <= latest_minutes)
            facts["minutes_beyond_historical_latest"] = max(0, current_minutes - latest_minutes)
        facts["routine_confidence"] = routine.get("confidence"); facts["routine_recurrence"] = routine.get("recurrence")
    event = schedule.get("next_timed_event"); facts["calendar_event_soon"] = False; facts["calendar_starts_in_minutes"] = None
    if event:
        starts_in = event.get("starts_in_minutes")
        if isinstance(starts_in, (int,float)) and 0 <= starts_in <= 30:
            facts["calendar_event_soon"] = True; facts["calendar_starts_in_minutes"] = starts_in; facts["calendar_event_summary"] = event.get("summary"); facts["calendar_event_location"] = event.get("location")
    return enriched

def candidate_is_valid(candidate: dict) -> bool:
    facts = candidate.get("facts", {})
    if candidate.get("type") == "routine_departure_deviation" and not facts.get("user_currently_home", False): return False
    return True

def candidate_has_required_facts(candidate: dict) -> bool:
    facts = candidate.get("facts", {})
    if candidate.get("type") == "routine_departure_deviation":
        required = ("user_currently_home","minutes_from_typical","outside_historical_range","minutes_beyond_historical_latest","routine_confidence","routine_recurrence")
        return all(facts.get(k) is not None for k in required)
    return True
