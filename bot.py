import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from gemini_client import GeminiClient

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот перезагружен и готов к работе. Пришлите текст или фото анализов.")

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Если это фото
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        response = await GeminiClient.ask(None, user_id, bytes(photo_bytes))
    # Если это текст
    else:
        response = await GeminiClient.ask(update.message.text, user_id)
    
    await update.message.reply_text(response)

def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("Ошибка: TELEGRAM_TOKEN не найден!")
        return

    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_all))
    
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
