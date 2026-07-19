import logging
from database.db import (
    get_all_vps_servers,
    get_user,
    update_user_balance,
    create_transaction,
    delete_vps_server
)
from services.openstack_service import delete_server, FLAVOR_PRICES_USD, DEFAULT_HOURLY_USD
from services.exchange_service import get_current_dollar_rate
from database.db import get_setting
from bot_instance import bot

logger = logging.getLogger(__name__)

async def run_hourly_billing():
    """
    Background job that runs every hour.
    Deducts hourly server costs from users' wallets and deletes servers if wallet drops to <= 0.
    """
    logger.info("Starting hourly billing cycle...")

    # 1. Fetch current exchange rate and profit margin
    dollar_rate = await get_current_dollar_rate()
    profit_margin = float(await get_setting("profit_margin", "50"))
    profit_factor = 1.0 + (profit_margin / 100.0)

    # 2. Get all active servers
    servers = await get_all_vps_servers()
    if not servers:
        logger.info("No active VPS servers found for billing.")
        return

    for server in servers:
        user_id = server["user_id"]
        server_id = server["id"]
        os_id = server["openstack_server_id"]
        server_name = server["server_name"]
        flavor_name = server["flavor_id"]  # note: we store flavor name or flavor id. Let's make sure we map it correctly.

        # 3. Get user details
        user = await get_user(user_id)
        if not user:
            logger.warning(f"User {user_id} for server {server_name} not found in database. Skipping.")
            continue

        wallet_balance = user["wallet_balance"]

        # 4. Calculate hourly price dynamically based on current dollar rate
        # Find flavor name from FLAVOR_PRICES_USD or default
        # (We will store flavor_name in db for easy lookup or we can try matching flavor_id)
        raw_usd = FLAVOR_PRICES_USD.get(flavor_name, DEFAULT_HOURLY_USD)

        hourly_cost_toman = int(raw_usd * dollar_rate * profit_factor)
        if hourly_cost_toman < 1:
            hourly_cost_toman = 1 # ensure at least 1 toman

        logger.info(f"Billing user {user_id} for server {server_name}: cost {hourly_cost_toman} Tomans (Wallet: {wallet_balance})")

        # 5. Deduct from wallet
        new_balance = wallet_balance - hourly_cost_toman
        await update_user_balance(user_id, -hourly_cost_toman)

        # 6. Record transaction
        await create_transaction(
            user_id=user_id,
            amount=hourly_cost_toman,
            type_='VPS_HOURLY',
            payment_method='SYSTEM',
            status='APPROVED',
            ref_id=f"VPS-{server_id}-BILLING"
        )

        # 7. Check if user is out of credit
        if new_balance <= 0:
            logger.warning(f"User {user_id} wallet is <= 0 ({new_balance}). Initiating VPS deletion...")

            # Delete server from OpenStack
            deleted = await delete_server(os_id)
            if deleted:
                logger.info(f"Server {os_id} deleted successfully from OpenStack.")
            else:
                logger.error(f"Failed to delete server {os_id} from OpenStack.")

            # Delete server from local DB
            await delete_vps_server(server_id)

            # Send notification to user
            try:
                msg = (
                    f"⚠️ **اطلاعیه مهم حذف سرور**\n\n"
                    f"کاربر گرامی، موجودی کیف پول شما به اتمام رسید.\n"
                    f"سرور مجازی شما با نام **{server_name}** به دلیل عدم داشتن اعتبار کافی به طور کامل حذف گردید.\n\n"
                    f"لطفاً جهت جلوگیری از قطع خدمات دیگر، کیف پول خود را شارژ نمایید."
                )
                await bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Could not notify user {user_id} about deletion: {e}")

    logger.info("Hourly billing cycle complete.")
