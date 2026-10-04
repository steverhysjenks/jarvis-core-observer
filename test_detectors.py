import asyncio
import json

from app.observer.context import (
    build_observer_context,
)
from app.observer.detectors import (
    run_detectors,
)


async def test():
    context = await build_observer_context()

    candidates = await run_detectors(
        context
    )

    print("OBSERVER DETECTORS")
    print("==================")

    print(
        json.dumps(
            candidates,
            indent=2,
        )
    )


asyncio.run(test())
