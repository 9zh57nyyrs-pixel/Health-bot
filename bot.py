import os
import sys
import logging
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# Глобальная переменная для модели
active_model = None

def init_ai():
    global active_model
    try:
        genai.configure(api_key=GEMINI_KEY)
        # ПОИСК ДОСТУПНОЙ МОДЕЛИ
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if available_models:
            # Берем первую доступную (например, gemini-1.5-flash-latest или gemini-pro)
            model_name = available_models[0]
            active_model = genai.GenerativeModel(model_name)
            print(f"--- ИСПОЛЬЗУЕТСЯ МОДЕЛЬ: {model_name} ---", flush=True)
        else:
            print("--- НЕТ ДОСТУПНЫХ МОДЕЛЕЙ ДЛЯ ВАШЕГО КЛЮЧА ---", flush=True)
    except Exception as e:
        print(f"--- ОШИБКА ПРИ ПОИСКЕ МОДЕЛЕЙ: {e} ---", flush=True)

# Инициализируем при запуске
init_ai()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот запущен. Напиши любой вопрос.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global active_model
    if not active_model:
        # Попробуем инициализировать еще раз, если при старте не вышло
        init_ai()
        if not active_model:
            await update.message.reply_text("❌ Ошибка: Не удалось найти доступную модель ИИ. Проверьте ключ API.")
            return

    await update.message.reply_chat_action("typing")
    try:
        response = active_model.generate_content(update.message.text)
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Ошибка Gemini: {e}")
        await update.message.reply_text(f"⚠️ Ошибка связи с ИИ: {str(e)}")

def main():
    if not TOKEN:
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("--- БОТ ВКЛЮЧЕН ---", flush=True)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
