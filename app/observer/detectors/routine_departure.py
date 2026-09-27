from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.behaviour.routines import get_departure_routine_model
LOCAL_TIMEZONE=ZoneInfo("Europe/London"); ROUTINE_LOOKBACK_DAYS=28; EARLY_WARNING_MINUTES=10; LATE_WARNING_MINUTES=20

def routine_time_today(now,time_string):
    h,m=map(int,time_string.split(":")); return now.replace(hour=h,minute=m,second=0,microsecond=0)

async def detect_routine_departure_deviation(context: dict, now: datetime|None=None)->list[dict]:
    now=(now or datetime.now(LOCAL_TIMEZONE)).astimezone(LOCAL_TIMEZONE); user=context.get("user",{})
    if not user.get("home"): return []
    model=await get_departure_routine_model(days=ROUTINE_LOOKBACK_DAYS); today=now.strftime("%A"); candidates=[]
    for routine in model["actionable_routines"]:
        if routine["weekday"]!=today: continue
        expected=routine_time_today(now,routine["typical_time"]); window_start=expected-timedelta(minutes=EARLY_WARNING_MINUTES); window_end=expected+timedelta(minutes=LATE_WARNING_MINUTES)
        if now<window_start or now>window_end: continue
        delta=round((now-expected).total_seconds()/60,1)
        candidates.append({"type":"routine_departure_deviation","priority":"candidate","reason":"user_home_during_expected_departure_window","routine":{"weekday":routine["weekday"],"typical_time":routine["typical_time"],"confidence":routine["confidence"],"recurrence":routine["recurrence"],"observed_days":routine["observed_days"],"opportunities":routine["opportunities"],"source_range":routine["source_cluster"]["range"],"deviation_minutes":routine["source_cluster"]["deviation_minutes"]},"current":{"time":now.isoformat(),"minutes_from_expected":delta,"user_home":True,"user_area":user.get("area")}})
    return candidates
