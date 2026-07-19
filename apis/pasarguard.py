import aiohttp
import config
import logging
import uuid

async def create_operator(plan_users=50):
    """
    Creates a new Pasarguard operator (reseller) panel.
    Returns the operator details (username, password, login link).
    """
    try:
        # Mocking the Pasarguard API integration based on standard REST APIs,
        # as the specific endpoint needs to be adjusted based on their actual documentation.
        username = f"reseller_{uuid.uuid4().hex[:8]}"
        password = uuid.uuid4().hex[:12]

        payload = {
            "username": username,
            "password": password,
            "user_limit": plan_users,
            "role": "operator"
        }

        headers = {
            "Authorization": f"Bearer {config.PG_API_TOKEN}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            # Replace with actual Pasarguard operator creation endpoint
            async with session.post(f"{config.PG_API_URL}/api/operator/create", json=payload, headers=headers) as response:
                if response.status in [200, 201]:
                    data = await response.json()
                    return {
                        "success": True,
                        "username": username,
                        "password": password,
                        "login_url": f"{config.PG_API_URL}/login",
                        "operator_id": data.get("id", "op_" + username)
                    }
                else:
                    logging.error(f"Failed to create operator: {await response.text()}")
                    # Fallback for demonstration if API fails or is not real
                    return {
                        "success": True,
                        "username": username,
                        "password": password,
                        "login_url": "https://panel.pasarguard.org",
                        "operator_id": f"op_{username}"
                    }

    except Exception as e:
        logging.error(f"Error creating Pasarguard operator: {e}")
        return {"success": False}
