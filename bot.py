import os
import logging
import sqlite3
import re
import io
from datetime import datetime
from PIL import Image

import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# --- Инициализация путей и логов ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "medical_bot.db")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Переменные окружения (задаются в панели Railway)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Состояния диалога
GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT_MODE = range(6)

# --- Настройка ИИ ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.error("КРИТИЧЕСКАЯ ОШИБКА: GEMINI_API_KEY не установлен!")

SYSTEM_INSTRUCTION = (
    "Ты — элитный врач-терапевт. Твои ответы должны быть глубокими и профессиональными. "
    "Всегда учитывай данные профиля пациента. В конце каждого ответа добавляй: "
    "'Требуется очная консультация специалиста.'"
)

def get_gemini_model():
    """Fallback-система для предотвращения ошибки 404"""
    models = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
    for m_name in models:
        try:
            model = genai.GenerativeModel(model_name=m_name, system_instruction=SYSTEM_INSTRUCTION)
            # Проверочный микро-запрос
            model.generate_content("Hi", generation_config={"max_output_tokens": 1})
            logger.info(f"Используется модель: {m_name}")
            return model
        except Exception as e:
            logger.warning(f"Модель {m_name} недоступна: {e}")
    return None

model = get_gemini_model()

# --- Работа с БД ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
        (user_id INTEGER PRIMARY KEY, gender TEXT, age INTEGER, weight REAL, height REAL, diseases TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS history 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, role TEXT, content TEXT)''')
    conn.commit()
    conn.close()

def save_user(user_id, data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?)''',
                   (user_id, data['gender'], data['age'], data['weight'], data['height'], data['diseases']))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res

# --- Логика бота ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if get_user(user_id):
        await update.message.reply_text("✅ Система готова. Чем я могу помочь?", 
                                       reply_markup=ReplyKeyboardMarkup([['Моя медкарта', 'Консультация'], ['SOS']], resize_keyboard=True))
        return CHAT_MODE
    
    await update.message.reply_text("Здравствуйте! Я ваш ИИ-врач. Для начала заполним карту. Ваш пол?",
                                   reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True))
    return GENDER

async def collect_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gender'] = update.message.text
    await update.message.reply_text("Ваш возраст?")
    return AGE

async def collect_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    age = re.search(r'\d+', update.message.text)
    if not age: return AGE
    context.user_data['age'] = int(age.group())
    await update.message.reply_text("Ваш вес (кг)?")
    return WEIGHT

async def collect_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    w = re.search(r'\d+', update.message.text)
    if not w: return WEIGHT
    context.user_data['weight'] = float(w.group())
    await update.message.reply_text("Ваш рост (см)?")
    return HEIGHT

async def collect_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    h = re.search(r'\d+', update.message.text)
    if not h: return HEIGHT
    context.user_data['height'] = float(h.group())
    await update.message.reply_text("Хронические заболевания? (или 'Нет')")
    return DISEASES

async def collect_diseases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['diseases'] = update.message.text
    save_user(update.effective_user.id, context.user_data)
    await update.message.reply_text("Профиль сохранен. Задавайте вопросы.", 
                                   reply_markup=ReplyKeyboardMarkup([['Моя медкарта', 'Консультация'], ['SOS']], resize_keyboard=True))
    return CHAT_MODE

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if text == "Моя медкарта":
        u = get_user(user_id)
        await update.message.reply_text(f"📋 Карта:\nВозраст: {u[2]}\nВес: {u[3]}кг\nБолезни: {u[5]}")
        return
    
    if text == "SOS":
        await update.message.reply_text("🚨 Срочно звоните 103 или 112!")
        return

    try:
        u = get_user(user_id)
        prompt = f"Контекст пациента: пол {u[1]}, {u[2]} лет, вес {u[3]}кг. Запрос: {text}"
        response = model.generate_content(prompt)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        await update.message.reply_text("Ошибка ИИ. Попробуйте еще раз.")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = await update.message.photo[-1].get_file()
    bytes_img = await photo.download_as_bytearray()
    img = Image.open(io.BytesIO(bytes_img))
    
    await update.message.reply_text("🔍 Анализирую фото...")
    try:
        response = model.generate_content(["Опиши показатели анализов на фото и сравни их с нормой", img])
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Photo error: {e}")
        await update.message.reply_text("Не удалось прочитать фото.")

# --- Запуск ---
def main():
    if not TELEGRAM_TOKEN:
        print("Error: No TELEGRAM_TOKEN")
        return

    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(filters.ALL, start)],
        states={
            GENDER: [MessageHandler(filters.TEXT, collect_gender)],
            AGE: [MessageHandler(filters.TEXT, collect_age)],
            WEIGHT: [MessageHandler(filters.TEXT, collect_weight)],
            HEIGHT: [MessageHandler(filters.TEXT, collect_height)],
            DISEASES: [MessageHandler(filters.TEXT, collect_diseases)],
            CHAT_MODE: [
                MessageHandler(filters.PHOTO, photo_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler)
            ],
        },
        fallbacks=[CommandHandler('start', start)],
    )

    app.add_handler(conv)
    logger.info("Бот запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
