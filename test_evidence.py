import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.context.evidence import entrance_activity


LOCAL_TIMEZONE = ZoneInfo("Europe/London")


async def main():
    result = await entrance_activity(
        start=datetime(
            2026, 9, 26, 19, 0,
            tzinfo=LOCAL_TIMEZONE,
        ),
        end=datetime(
            2026, 9, 27, 0, 0,
            tzinfo=LOCAL_TIMEZONE,
        ),
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


asyncio.run(main())
