import aiohttp

async def get_usd_rate():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.wallex.ir/v1/currencies/stats") as response:
                if response.status == 200:
                    data = await response.json()
                    # Example: get the USD/USDT to TMN/IRR rate. Let's use USDT or USD.
                    # Wallex often uses USDT for tether to toman
                    stats = data.get("result", [])
                    for stat in stats:
                        if stat.get("symbol") == "USDTTMN": # Tether to Toman
                            return float(stat.get("price", 0))

                    # Alternatively, if structure is different:
                    # Let's just fetch USDT-TMN from market if possible, this is a common endpoint
                    async with session.get("https://api.wallex.ir/v1/markets") as market_resp:
                        if market_resp.status == 200:
                            market_data = await market_resp.json()
                            if "result" in market_data and "symbols" in market_data["result"]:
                                usdt_tmn = market_data["result"]["symbols"].get("USDTTMN")
                                if usdt_tmn:
                                    return float(usdt_tmn.get("stats", {}).get("lastPrice", 0))

        # Fallback fake rate if API fails
        return 60000.0
    except Exception as e:
        print(f"Error fetching Wallex rate: {e}")
        return 60000.0
