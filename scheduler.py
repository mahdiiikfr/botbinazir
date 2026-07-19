import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import db
from apis import openstack_api
import logging

async def hourly_billing(bot):
    logging.info("Running hourly billing cycle...")
    servers = await db.get_servers()

    for s in servers:
        user = await db.get_user(s['user_id'])
        if not user:
            continue

        balance = user[2]
        hourly_cost = s['hourly_cost']

        if balance >= hourly_cost:
            # Deduct balance
            await db.update_balance(s['user_id'], -hourly_cost)
        else:
            # Insufficient balance, delete server
            logging.info(f"Deleting server {s['os_server_id']} for user {s['user_id']} due to insufficient balance.")
            success = await openstack_api.delete_server(s['os_server_id'])

            if success:
                await db.update_server_status(s['os_server_id'], 'deleted')
                try:
                    await bot.send_message(
                        s['user_id'],
                        f"⚠️ موجودی کیف پول شما برای تمدید سرور {s['name']} کافی نبود.\nسرور شما حذف شد."
                    )
                except Exception as e:
                    logging.error(f"Failed to notify user {s['user_id']}: {e}")

def setup_scheduler(bot):
    scheduler = AsyncIOScheduler()
    # Run every hour
    scheduler.add_job(hourly_billing, 'interval', hours=1, args=[bot])
    scheduler.start()
    return scheduler
