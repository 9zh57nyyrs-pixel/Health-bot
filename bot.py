import os
import sys
import logging
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Логи в консоль Railway
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# Настройка ИИ с учетом твоей ошибки 404
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    # Используем проверенное имя модели
    model = genai.GenerativeModel('gemini-1.5-flash') 
else:
    model = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот на связи! Попробуй отправить вопрос сейчас.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not model:
        await update.message.reply_text("❌ Ошибка: Ключ GEMINI_API_KEY не найден.")
        return

    await update.message.reply_chat_action("typing")
    
    try:
        # Прямой вызов без лишних оберток
        response = model.generate_content(update.message.text)
        
        if response and response.text:
            await update.message.reply_text(response.text)
        else:
            await update.message.reply_text("ИИ не смог сформулировать ответ.")
            
    except Exception as e:
        # Если снова будет 404, мы увидим подробности
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    if not TOKEN:
        print("НЕТ ТОКЕНА ТЕЛЕГРАМ")
        return
        
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("--- ЗАПУСК ПОЛЛИНГА ---", flush=True)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
