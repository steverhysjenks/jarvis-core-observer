import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.adapters.homeassistant import ha_client


LOCAL_TIMEZONE = ZoneInfo("Europe/London")
FRONT_DOOR = "binary_sensor.front_door_opening"


async def main():
    # Use yesterday evening simply to inspect the shape of
    # real HA Recorder data over a bounded evening window.
    start = datetime(
        2026, 9, 26, 19, 0,
        tzinfo=LOCAL_TIMEZONE,
    )

    end = datetime(
        2026, 9, 27, 0, 0,
        tzinfo=LOCAL_TIMEZONE,
    )

    history = await ha_client.get_history(
        FRONT_DOOR,
        start,
        end,
    )

    print(
        json.dumps(
            history,
            indent=2,
        )
    )


asyncio.run(main())
