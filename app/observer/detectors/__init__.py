from app.observer.detectors.departure import detect_upcoming_departure
from app.observer.detectors.routine_departure import detect_routine_departure_deviation
from app.observer.detectors.waste import detect_waste_preparation

async def run_detectors(context: dict)->list[dict]:
    candidates=[]
    result=detect_upcoming_departure(context)
    if result: candidates.extend(result if isinstance(result,list) else [result])
    candidates.extend(await detect_routine_departure_deviation(context) or [])
    candidates.extend(await detect_waste_preparation(context) or [])
    return candidates
