import httpx
import logging
from database.db import get_setting

logger = logging.getLogger(__name__)

async def fetch_tether_price_wallex() -> int:
    """Fetch Tether price in Tomans from Wallex API"""
    url = "https://api.wallex.ir/v1/markets"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # Structure: data["result"]["symbols"]["USDT-TMN"]["stats"]["bidPrice"]
            # Some APIs use stats -> lastPrice or bidPrice
            symbols = data.get("result", {}).get("symbols", {})
            usdt_tmn = symbols.get("USDT-TMN") or symbols.get("USDTTMN")
            if usdt_tmn:
                stats = usdt_tmn.get("stats", {})
                price = stats.get("bidPrice") or stats.get("lastPrice") or stats.get("askPrice")
                if price:
                    return int(float(price))
    raise Exception("Wallex API returned invalid status or structure")

async def fetch_tether_price_nobitex() -> int:
    """Fetch Tether price in Tomans from Nobitex API"""
    url = "https://api.nobitex.ir/v2/orderbook/USDTIRT"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # Nobitex returns price in Rials, need to convert to Tomans
            # bids format: bids = [ [price, quantity], ... ]
            bids = data.get("bids", [])
            if bids and len(bids[0]) > 0:
                price_rial = float(bids[0][0])
                price_toman = int(price_rial / 10)
                return price_toman
    raise Exception("Nobitex API returned invalid status or structure")

async def get_current_dollar_rate() -> int:
    """
    Get current dollar rate in Tomans.
    Tries Wallex, then Nobitex, and falls back to manual admin setting if both fail or if dollar_rate_auto is disabled.
    """
    use_auto = await get_setting("dollar_rate_auto", "1")
    manual_rate = int(await get_setting("dollar_rate_manual", "70000"))

    if use_auto == "1":
        # Try Wallex
        try:
            rate = await fetch_tether_price_wallex()
            if rate > 10000: # Sanity check
                logger.info(f"Fetched dollar rate from Wallex: {rate} Tomans")
                return rate
        except Exception as e:
            logger.warning(f"Could not fetch dollar rate from Wallex: {e}")

        # Try Nobitex
        try:
            rate = await fetch_tether_price_nobitex()
            if rate > 10000: # Sanity check
                logger.info(f"Fetched dollar rate from Nobitex: {rate} Tomans")
                return rate
        except Exception as e:
            logger.warning(f"Could not fetch dollar rate from Nobitex: {e}")

    # Fallback to manual rate
    logger.info(f"Using manual/fallback dollar rate: {manual_rate} Tomans")
    return manual_rate
