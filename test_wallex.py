import asyncio
from apis.wallex import get_usd_rate

async def main():
    rate = await get_usd_rate()
    print("Rate:", rate)

asyncio.run(main())
