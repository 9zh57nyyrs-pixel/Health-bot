import os
import sys
import logging
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Логирование в реальном времени
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Ключи
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# Настройка ИИ вынесена в функцию
def configure_ai():
    if not GEMINI_KEY:
        return None
    genai.configure(api_key=GEMINI_KEY)
    return genai.GenerativeModel('gemini-1.5-flash')

model = configure_ai()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот онлайн. Напиши мне вопрос для ИИ.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not model:
        await update.message.reply_text("Ошибка: API ключ Gemini не найден в настройках Railway!")
        return

    user_text = update.message.text
    print(f"Запрос к ИI: {user_text}", flush=True)
    
    await update.message.reply_chat_action("typing")
    
    try:
        # Используем асинхронный вызов, чтобы бот не зависал
        response = await model.generate_content_async(user_text)
        await update.message.reply_text(response.text)
    except Exception as e:
        error_msg = f"Ошибка связи с ИИ: {str(e)}"
        logger.error(error_msg)
        await update.message.reply_text("ИИ временно недоступен. Проверь логи Railway.")

def main():
    if not TOKEN:
        print("КРИТИЧЕСКАЯ ОШИБКА: Нет TELEGRAM_TOKEN!", flush=True)
        return
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("--- БОТ ЗАПУЩЕН ---", flush=True)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
