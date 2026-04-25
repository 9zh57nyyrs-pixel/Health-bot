import os
import sqlite3
import logging
import re
import google.generativeai as genai
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, ConversationHandler
)

# 1. НАСТРОЙКА ЛОГИРОВАНИЯ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. ИНИЦИАЛИЗАЦИЯ БД
DB_PATH = 'health_data.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, age INTEGER, gender TEXT, 
                       weight REAL, height REAL, chronic TEXT)''')
    conn.commit()
    conn.close()

def db_update(user_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    for key, value in kwargs.items():
        cursor.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def db_get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# 3. ЛОГИКА GEMINI (С ЗАЩИТОЙ ОТ 404)
def get_ai_advice(user_id, user_text, photo_data=None):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    
    user = db_get_user(user_id)
    context = f"Пациент: {user['gender'] if user else 'неизвестно'}, {user['age'] if user else '?'} лет."
    
    # Пытаемся использовать разные версии модели, если одна недоступна
    models_to_try = ['gemini-1.5-flash', 'gemini-1.5-pro']
    
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=f"Ты профессиональный врач. Учитывай данные: {context}. Не ставь диагнозы, давай рекомендации."
            )
            
            if photo_data:
                response = model.generate_content([{"mime_type": "image/jpeg", "data": photo_data}, user_text])
            else:
                response = model.generate_content(user_text)
            return response.text
        except Exception as e:
            logger.error(f"Ошибка с моделью {model_name}: {e}")
            continue
            
    return "⚠️ Сервис временно недоступен. Проверьте API ключ или регион сервера (США/Европа)."

# 4. МАШИНА СОСТОЯНИЙ БОТА
GENDER, AGE, WEIGHT, CHAT = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    user = db_get_user(update.effective_user.id)
    
    if not user or not user.get('age'):
        await update.message.reply_text(
            "👨‍⚕️ Добро пожаловать! Я ваш ИИ-помощник по здоровью.\n"
            "Для начала заполним профиль. Ваш пол?",
            reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True)
        )
        return GENDER
    
    await update.message.reply_text(
        "Рад вас видеть снова! Чем могу помочь сегодня?",
        reply_markup=ReplyKeyboardMarkup([['👨‍⚕️ Консультация', '📊 Мои данные']], resize_keyboard=True)
    )
    return CHAT

async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_update(update.effective_user.id, gender=update.message.text)
    await update.message.reply_text("Укажите ваш возраст (полных лет):")
    return AGE

async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = re.search(r'\d+', update.message.text)
    if not val:
        await update.message.reply_text("Пожалуйста, введите возраст цифрами.")
        return AGE
    db_update(update.effective_user.id, age=int(val.group()))
    await update.message.reply_text("Ваш текущий вес (кг)?")
    return WEIGHT

async def set_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = re.search(r'\d+', update.message.text)
    db_update(update.effective_user.id, weight=float(val.group()))
    await update.message.reply_text("Профиль настроен! Опишите жалобы или пришлите фото анализов.")
    return CHAT

async def handle_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if update.message.photo:
        await update.message.reply_text("📥 Анализирую ваше изображение...")
        file = await update.message.photo[-1].get_file()
        photo_bytes = await file.download_as_bytearray()
        response = get_ai_advice(user_id, "Расшифруй это медицинское изображение", bytes(photo_bytes))
    else:
        response = get_ai_advice(user_id, update.message.text)
    
    await update.message.reply_text(response)
    return CHAT

# 5. ЗАПУСК
if __name__ == '__main__':
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("ОШИБКА: Нет токена Telegram!")
        exit()

    app = Application.builder().token(token).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_weight)],
            CHAT: [MessageHandler(filters.TEXT | filters.PHOTO, handle_main)],
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    app.add_handler(conv_handler)
    print("Бот запущен...")
    app.run_polling()
