import os
import sys
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Логирование прямо в консоль Railway
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)

TOKEN = os.environ.get("TELEGRAM_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот успешно запущен на Railway и работает!")

async def main():
    if not TOKEN:
        print("ОШИБКА: TELEGRAM_TOKEN не найден!", flush=True)
        return

    print("--- ЗАПУСК БОТА ---", flush=True)
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    # drop_pending_updates очистит старые сообщения, чтобы бот не завис
    await application.initialize()
    await application.updater.start_polling(drop_pending_updates=True)
    await application.start()
    print("--- БОТ В СЕТИ ---", flush=True)
    
    # Держим процесс запущенным
    while True:
        await asyncio.sleep(1)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА: {e}", flush=True)
