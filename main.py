import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from bot.config import Config
from bot.handlers import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    Config.validate()
    
    bot = Bot(token=Config.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    
    dp.include_router(router)
    
    logger.info("Бот запущен!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
