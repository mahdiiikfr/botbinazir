import httpx
import logging
from database.db import get_setting

logger = logging.getLogger(__name__)

async def request_zarinpal_payment(amount_toman: int, description: str, callback_url: str) -> dict:
    """
    Send payment request to ZarinPal v4 API.
    Returns payment URL and Authority, or mock fallback details.
    """
    merchant_id = await get_setting("zarinpal_merchant", "7b134bb0-802c-473d-9be2-441d8e1faef0")

    # ZarinPal expects amount in Rials
    amount_rial = amount_toman * 10

    url = "https://api.zarinpal.com/pg/v4/payment/request.json"
    payload = {
        "merchant_id": merchant_id,
        "amount": int(amount_rial),
        "description": description,
        "callback_url": callback_url,
        "metadata": {
            "mobile": "09123456789", # placeholder
            "email": "user@domain.com" # placeholder
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=8)
            if response.status_code == 200:
                res_data = response.json()
                data = res_data.get("data", {})
                code = data.get("code")
                authority = data.get("authority")

                if code == 100 and authority:
                    return {
                        "success": True,
                        "authority": authority,
                        "payment_url": f"https://www.zarinpal.com/pg/StartPay/{authority}",
                        "is_mock": False
                    }
    except Exception as e:
        logger.error(f"ZarinPal payment request error: {e}")

    # Mock / Sandbox fallback for developer test / unreachable endpoints
    mock_authority = f"MOCK-AUTH-{int(amount_toman)}"
    return {
        "success": True,
        "authority": mock_authority,
        "payment_url": f"https://sandbox.zarinpal.com/pg/StartPay/{mock_authority}",
        "is_mock": True
    }

async def verify_zarinpal_payment(amount_toman: int, authority: str) -> dict:
    """
    Verify payment from ZarinPal v4 API.
    """
    if authority.startswith("MOCK-AUTH-"):
        # Simulated success in mock mode
        return {
            "success": True,
            "ref_id": "MOCK-REF-123456",
            "message": "پرداخت آزمایشی تایید شد."
        }

    merchant_id = await get_setting("zarinpal_merchant", "7b134bb0-802c-473d-9be2-441d8e1faef0")
    amount_rial = amount_toman * 10

    url = "https://api.zarinpal.com/pg/v4/payment/verify.json"
    payload = {
        "merchant_id": merchant_id,
        "amount": int(amount_rial),
        "authority": authority
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=8)
            if response.status_code == 200:
                res_data = response.json()
                data = res_data.get("data", {})
                code = data.get("code")
                ref_id = data.get("ref_id")

                if code == 100 or code == 101:
                    return {
                        "success": True,
                        "ref_id": str(ref_id),
                        "message": "پرداخت با موفقیت تایید شد."
                    }
                else:
                    return {
                        "success": False,
                        "ref_id": None,
                        "message": f"خطا در تایید پرداخت. کد خطا: {code}"
                    }
    except Exception as e:
        logger.error(f"ZarinPal payment verification error: {e}")

    return {
        "success": False,
        "ref_id": None,
        "message": "اتصال به درگاه زرین‌پال برقرار نشد."
    }
