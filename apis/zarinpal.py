import aiohttp
import config
import logging

ZP_API_REQUEST = "https://api.zarinpal.com/pg/v4/payment/request.json"
ZP_API_VERIFY = "https://api.zarinpal.com/pg/v4/payment/verify.json"
ZP_API_STARTPAY = "https://www.zarinpal.com/pg/StartPay/"

async def request_payment(amount_toman, description, callback_url):
    try:
        # Zarinpal works with Rial (in old API) or Toman (in v4 if specified, but usually Rial).
        # We assume amount is passed in Rial or Toman based on ZarinPal config. Let's assume Rial for safety.
        amount_rial = amount_toman * 10

        payload = {
            "merchant_id": config.ZP_MERCHANT,
            "amount": amount_rial,
            "description": description,
            "callback_url": callback_url
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(ZP_API_REQUEST, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("data", {}).get("code") == 100:
                        authority = data["data"]["authority"]
                        return {
                            "success": True,
                            "payment_url": f"{ZP_API_STARTPAY}{authority}",
                            "authority": authority
                        }

                logging.error(f"ZarinPal request failed: {await response.text()}")
                return {"success": False}
    except Exception as e:
        logging.error(f"Error in ZarinPal request: {e}")
        return {"success": False}

async def verify_payment(amount_toman, authority):
    try:
        amount_rial = amount_toman * 10
        payload = {
            "merchant_id": config.ZP_MERCHANT,
            "amount": amount_rial,
            "authority": authority
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(ZP_API_VERIFY, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("data", {}).get("code") in [100, 101]:
                        return {"success": True, "ref_id": data["data"]["ref_id"]}

                logging.error(f"ZarinPal verify failed: {await response.text()}")
                return {"success": False}
    except Exception as e:
        logging.error(f"Error in ZarinPal verify: {e}")
        return {"success": False}
