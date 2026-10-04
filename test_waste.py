import asyncio
import json

from app.context.waste import (
    build_waste_context,
)


async def main():
    context = await build_waste_context()

    print(
        json.dumps(
            context,
            indent=2,
        )
    )


asyncio.run(main())
