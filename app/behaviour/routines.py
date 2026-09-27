from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.behaviour.departures import get_departure_observations
LOCAL_TIMEZONE=ZoneInfo("Europe/London"); CACHE_TTL=timedelta(hours=6); _cache={"at":None,"days":None,"model":None}

def _mins(t): h,m=map(int,t.split(":")); return h*60+m
def _hhmm(m): return f"{(m//60)%24:02d}:{m%60:02d}"

async def get_departure_routine_model(days: int=28)->dict:
    now=datetime.now(LOCAL_TIMEZONE)
    if _cache["model"] is not None and _cache["days"]==days and now-_cache["at"]<CACHE_TTL: return _cache["model"]
    obs=await get_departure_observations(days); by_day=defaultdict(list)
    for o in obs: by_day[o["weekday"]].append(o)
    start=(now-timedelta(days=days)).date(); opportunities=defaultdict(int)
    for n in range(days): opportunities[(start+timedelta(days=n)).strftime("%A")]+=1
    routines=[]
    for weekday,items in by_day.items():
        # One representative departure per date/time neighbourhood is sufficient for this milestone snapshot.
        unique={i["date"]:i for i in items}; values=sorted(_mins(i["time"]) for i in unique.values())
        if not values: continue
        typical=round(sum(values)/len(values)); observed=len(unique); opp=opportunities[weekday]; recurrence=observed/opp if opp else 0
        confidence="strong" if recurrence>=.90 else "moderate" if recurrence>=.75 else "weak"
        routine={"weekday":weekday,"typical_time":_hhmm(typical),"confidence":confidence,"recurrence":round(recurrence,3),"observed_days":observed,"opportunities":opp,"source_cluster":{"range":{"earliest":_hhmm(min(values)),"latest":_hhmm(max(values))},"deviation_minutes":max(abs(v-typical) for v in values)}}
        routines.append(routine)
    actionable=[r for r in routines if r["observed_days"]>=3 and r["recurrence"]>=.75]
    model={"days":days,"routines":routines,"actionable_routines":actionable}; _cache.update({"at":now,"days":days,"model":model}); return model
