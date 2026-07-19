import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import config
import db
import scheduler
from handlers import user, admin

logging.basicConfig(level=logging.INFO)

async def main():
    await db.init_db()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(user.router)
    dp.include_router(admin.router)

    sched = scheduler.setup_scheduler(bot)

    # Start web server for zarinpal verification
    import web_app
    from aiohttp import web

    app = web_app.init_web()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

    try:
        logging.info("Starting bot...")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
