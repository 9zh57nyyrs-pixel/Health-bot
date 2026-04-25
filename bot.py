import os
import sys
import logging
import asyncio
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Принудительный вывод логов
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Читаем ключи
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# Настройка Gemini
try:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("--- СВЯЗЬ С GOOGLE AI УСТАНОВЛЕНА ---", flush=True)
except Exception as e:
    print(f"--- ОШИБКА НАСТРОЙКИ AI: {e} ---", flush=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    print(f"Получено сообщение: {user_text}", flush=True)
    
    try:
        # Прямой запрос к ИИ без лишних наворотов
        response = model.generate_content(user_text)
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Ошибка при ответе ИИ: {e}")
        await update.message.reply_text(f"Ошибка связи с ИИ: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот запущен. Напиши мне что угодно.")

def main():
    if not TOKEN:
        print("ОШИБКА: Нет токена Телеграм!", flush=True)
        return
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("--- БОТ ПОДКЛЮЧАЕТСЯ К ТЕЛЕГРАМ ---", flush=True)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
