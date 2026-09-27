import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from app.context.home import build_home_context
from app.context.user import build_user_context
from app.context.calendar import build_calendar_context
from app.context.history import build_history_context
from app.context.waste import build_waste_context
from app.observer.detectors import run_detectors
LOCAL_TIMEZONE=ZoneInfo("Europe/London")

async def build_observer_context()->dict:
    now=datetime.now(LOCAL_TIMEZONE)
    home,user,calendar,history,waste=await asyncio.gather(build_home_context(),build_user_context(),build_calendar_context(days=7),build_history_context(hours=2),build_waste_context(days=7,now=now))
    return {"generated_at":now.isoformat(),"local_time":{"timezone":"Europe/London","date":now.date().isoformat(),"time":now.time().replace(microsecond=0).isoformat(),"utc_offset":now.strftime("%z"),"dst":bool(now.dst())},"user":user,"environment":home,"schedule":{"happening_now":calendar.get("happening_now",[]),"next_timed_event":calendar.get("next_timed_event"),"today_all_day":calendar.get("all_day_context",[])},"household":{"waste":waste},"recent_activity":history,"capabilities":{"presence":True,"room_location":user.get("area") is not None,"calendar":True,"waste_schedule":waste.get("next_collection") is not None,"semantic_history":True,"entrance_history":True,"user_presence_history":True,"room_history":False}}

async def build_observer_snapshot()->dict:
    context=await build_observer_context(); candidates=await run_detectors(context); return {**context,"attention":{"candidate_count":len(candidates),"candidates":candidates}}
