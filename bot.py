import os
import sys
import logging
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка вывода логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Получение ключей
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# Настройка ИИ (асинхронная модель)
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот на связи. Отправьте ваш вопрос или фото.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Берем текст из сообщения или подписи к фото
    prompt = update.message.text or update.message.caption or "Проанализируй это изображение"
    
    # Визуальный индикатор "печатает"
    await update.message.reply_chat_action("typing")
    
    content = [prompt]
    
    # Если есть фото, качаем и добавляем в запрос
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        img_bytes = await file.download_as_bytearray()
        content.append({"mime_type": "image/jpeg", "data": bytes(img_bytes)})

    try:
        # Критически важно: асинхронный вызов generate_content_async
        response = await model.generate_content_async(content)
        
        if response.text:
            await update.message.reply_text(response.text, parse_mode='Markdown')
        else:
            await update.message.reply_text("ИИ вернул пустой ответ.")
            
    except Exception as e:
        logger.error(f"Ошибка Gemini: {e}")
        await update.message.reply_text(f"❌ Ошибка ИИ: {str(e)}")

def main():
    if not TOKEN or not GEMINI_KEY:
        print("ОШИБКА: Проверьте TELEGRAM_TOKEN и GEMINI_API_KEY в Railway!", flush=True)
        return

    # Создание приложения
    application = Application.builder().token(TOKEN).build()

    # Хендлеры
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    print("--- ЗАПУСК БОТА ---", flush=True)
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
