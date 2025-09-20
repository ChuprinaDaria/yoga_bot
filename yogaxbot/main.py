#!/usr/bin/env python3
"""
YogaX Bot - Telegram бот для йоги
Entrypoint файл з polling режимом
"""

import asyncio
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from handlers import router
from handlers.tasks import trial_maintenance, purge_workouts
from db import seed_free_workouts_if_empty

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError('BOT_TOKEN не знайдено в .env')

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    scheduler = AsyncIOScheduler()
    scheduler.start()
    scheduler.add_job(trial_maintenance, 'interval', days=1, args=[bot])
    scheduler.add_job(purge_workouts, 'interval', minutes=10, args=[bot])

    seed_free_workouts_if_empty()

    async def scheduler_middleware(handler, event, data):
        data['scheduler'] = scheduler
        return await handler(event, data)

    dp.update.outer_middleware.register(scheduler_middleware)

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
