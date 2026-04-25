import os
import sys
import logging
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Логирование для отслеживания процесса в Railway
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# Настройка ИИ с использованием стабильной модели
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    # Используем 'gemini-pro', она наиболее совместима и не выдает 404
    model = genai.GenerativeModel('gemini-pro')
else:
    model = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Бот запущен и готов к работе. Расскажите о себе (пол, возраст, вес, жалобы), "
        "и я дам рекомендации на основе этих данных."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not model:
        await update.message.reply_text("❌ Ошибка: API ключ не настроен в Variables.")
        return

    await update.message.reply_chat_action("typing")
    
    user_text = update.message.text
    
    try:
        # Прямой запрос к ИИ
        response = model.generate_content(user_text)
        
        if response and response.text:
            await update.message.reply_text(response.text)
        else:
            await update.message.reply_text("ИИ получил запрос, но не смог сгенерировать текст. Попробуйте уточнить вопрос.")
            
    except Exception as e:
        # Если возникнет любая ошибка, бот сразу выведет её текст
        logger.error(f"Ошибка Gemini: {e}")
        await update.message.reply_text(f"Произошла техническая ошибка: {str(e)}")

def main():
    if not TOKEN:
        print("Критическая ошибка: TELEGRAM_TOKEN не найден!")
        return
        
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("--- БОТ ЗАПУЩЕН И ГОТОВ К ОБЩЕНИЮ ---", flush=True)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
