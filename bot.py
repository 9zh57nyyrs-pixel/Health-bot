import os
import sys
import logging
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Вывод логов максимально подробно
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# Настройка модели
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Связь с Telegram есть! Проверяю связь с ИИ...")
    
    try:
        # Пробный запрос к ИИ прямо при старте
        test_res = await model.generate_content_async("Привет, ты работаешь?")
        await update.message.reply_text(f"🤖 ИИ ответил: {test_res.text}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка ИИ: {str(e)}")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = await model.generate_content_async(update.message.text)
        await update.message.reply_text(res.text)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    print("--- ЗАПУСК ---", flush=True)
    app.run_polling()

if __name__ == '__main__':
    main()
