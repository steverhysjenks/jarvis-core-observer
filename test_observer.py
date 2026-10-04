import asyncio
import json

from app.observer.context import (
    build_observer_snapshot,
)


async def test():
    snapshot = await build_observer_snapshot()

    print(
        json.dumps(
            snapshot,
            indent=2,
        )
    )


asyncio.run(test())
