import os
import sys
import logging
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# 1. Логи — теперь ты увидишь каждую ошибку в консоли Railway
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# 2. Настройка ИИ
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_KEY)

# Инструкция, которая делает его умным (можешь менять под себя)
SYSTEM_PROMPT = "Ты — продвинутый медицинский ИИ. Отвечай развернуто, профессионально и только на русском языке. Ты помнишь всё, что тебе писали раньше в этом чате."

# 3. Главная функция связи
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Создаем сессию чата с памятью, если ее нет
    if 'chat' not in context.user_data:
        model = genai.GenerativeModel(model_name="gemini-1.5-flash", system_instruction=SYSTEM_PROMPT)
        context.user_data['chat'] = model.start_chat(history=[])

    user_text = update.message.text or update.message.caption or "Посмотри на фото"
    
    # Собираем контент (текст + фото если есть)
    content = [user_text]
    if update.message.photo:
        await update.message.reply_chat_action("upload_photo")
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        content.append({"mime_type": "image/jpeg", "data": bytes(photo_bytes)})
    else:
        await update.message.reply_chat_action("typing")

    # Отправка в Gemini
    try:
        response = await context.user_data['chat'].send_message_async(content)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"ОШИБКА ИИ: {e}")
        await update.message.reply_text("Произошла ошибка в ИИ. Попробуй еще раз.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear() # Полная очистка памяти при рестарте
    await update.message.reply_text("Связь с ИИ установлена. Я тебя слушаю.")

def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("НЕТ ТОКЕНА ТЕЛЕГРАМ!")
        return

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))
    
    print("--- БОТ ЗАПУЩЕН ---", flush=True)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
