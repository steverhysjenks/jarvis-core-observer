def detect_upcoming_departure(context: dict, warning_minutes: int = 30):
    # Bootstrap calendar-based detector retained from the milestone.
    # Keep this conservative; richer scheduled-departure semantics belong in a later milestone.
    user=context.get("user",{}); event=context.get("schedule",{}).get("next_timed_event")
    if not user.get("home") or not event: return None
    starts=event.get("starts_in_minutes")
    if not isinstance(starts,(int,float)) or starts<0 or starts>warning_minutes: return None
    return {"type":"upcoming_departure","priority":"candidate","reason":"calendar_event_approaching_user_home","event":event}
