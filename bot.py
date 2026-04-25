import os
import sqlite3
import logging
import sys
from datetime import datetime
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, CallbackContext

# ПРИНУДИТЕЛЬНЫЙ ВЫВОД В ЛОГИ RAILWAY
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# ПУТЬ К БАЗЕ ДАННЫХ (используем /tmp для Railway, чтобы не было ошибок записи)
DB_PATH = "/tmp/medical_bot.db"

# СОСТОЯНИЯ
SURVEY_GENDER, SURVEY_AGE, SURVEY_WEIGHT, SURVEY_HEIGHT, SURVEY_ILLNESSES, MAIN_MENU, CONSULTATION, ANALYSES = range(8)

# ЧТЕНИЕ ПЕРЕМЕННЫХ
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    print("CRITICAL ERROR: Tokens not found in environment variables!")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
        (user_id INTEGER PRIMARY KEY, gender TEXT, age INTEGER, weight INTEGER, height INTEGER, illnesses TEXT)''')
    conn.commit()
    conn.close()

async def start(update: Update, context: CallbackContext):
    logger.info(f"User {update.effective_user.id} started the bot")
    await update.message.reply_text("Здравствуйте! Я ваш медицинский ИИ-ассистент. Давайте заполним вашу карту. Ваш пол (М/Ж)?")
    return SURVEY_GENDER

# ... (остальную логику опроса я сокращу для краткости, используйте структуру из первого сообщения) ...
# ВАЖНО: В конце файла убедитесь, что блок запуска выглядит так:

def main():
    init_db()
    print("Бот успешно инициализирован и запускается...", flush=True)
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавьте сюда ваши handler'ы (conv_handler и т.д.)
    # ...
    
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"Критическая ошибка при запуске: {e}", flush=True)
        logger.error(e)
