import os
import logging
import sqlite3
import re
import io
from datetime import datetime
from PIL import Image

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler,
)

# --- Настройки ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "medical_bot.db")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT_MODE = range(6)

# --- ИИ Конфигурация ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

def get_gemini_model():
    # Пробуем 1.5 Flash (самая новая), потом Pro
    for m_name in ['gemini-1.5-flash-latest', 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']:
        try:
            m = genai.GenerativeModel(
                model_name=m_name,
                system_instruction="Ты элитный врач-терапевт. Давай четкие медицинские рекомендации на основе данных пациента.",
                safety_settings=SAFETY_SETTINGS
            )
            m.generate_content("Hi", generation_config={"max_output_tokens": 1})
            return m
        except: continue
    return None

model = get_gemini_model()

# --- База данных ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
        (user_id INTEGER PRIMARY KEY, gender TEXT, age INTEGER, weight REAL, height REAL, diseases TEXT)''')
    conn.commit()
    conn.close()

def save_user(user_id, data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?)',
                   (user_id, data['gender'], data.get('age', 0), data.get('weight', 0), data.get('height', 0), data.get('diseases', 'Нет')))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res

# --- Логика ---
def main_menu():
    return ReplyKeyboardMarkup([['Моя медкарта', 'Консультация'], ['SOS']], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    if user_data:
        await update.message.reply_text("👋 Доктор на связи. Какой у вас вопрос?", reply_markup=main_menu())
        return CHAT_MODE
    
    await update.message.reply_text("Здравствуйте! Я ваш медицинский ассистент. Давайте заполним карту. Ваш пол?",
                                   reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True))
    return GENDER

async def collect_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gender'] = update.message.text
    await update.message.reply_text("Ваш возраст?")
    return AGE

async def collect_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = re.search(r'\d+', update.message.text)
    if not val: return AGE
    context.user_data['age'] = int(val.group())
    await update.message.reply_text("Ваш вес (кг)?")
    return WEIGHT

async def collect_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = re.search(r'\d+', update.message.text)
    if not val: return WEIGHT
    context.user_data['weight'] = float(val.group())
    await update.message.reply_text("Ваш рост (см)?")
    return HEIGHT

async def collect_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = re.search(r'\d+', update.message.text)
    if not val: return HEIGHT
    context.user_data['height'] = float(val.group())
    await update.message.reply_text("Хронические заболевания? (или 'Нет')")
    return DISEASES

async def collect_diseases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['diseases'] = update.message.text
    save_user(update.effective_user.id, context.user_data)
    await update.message.reply_text("✅ Карта сохранена. Опишите ваши симптомы или пришлете фото анализов.", reply_markup=main_menu())
    return CHAT_MODE

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    u = get_user(user_id)
    if not u: # Если БД стерлась, возвращаем на опрос
        return await start(update, context)

    if text == "Моя медкарта":
        await update.message.reply_text(f"📋 Карта: {u[1]}, {u[2]} лет, {u[3]}кг, {u[4]}см. Болезни: {u[5]}")
        return
    if text == "SOS":
        await update.message.reply_text("🚨 Срочно звоните 103/112!")
        return

    global model
    if not model: model = get_gemini_model()
    
    try:
        prompt = f"Пациент: {u[1]}, {u[2]}л, {u[3]}кг. Жалоба: {text}"
        response = model.generate_content(prompt)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("⚠️ Ошибка связи с ИИ. Попробуйте кратко описать симптом.")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u: return await start(update, context)

    try:
        await update.message.reply_text("🔍 Анализирую фото...")
        photo = await update.message.photo[-1].get_file()
        b_img = await photo.download_as_bytearray()
        img = Image.open(io.BytesIO(b_img))
        
        res = model.generate_content([f"Пациент {u[2]} лет. Проанализируй анализы на фото.", img])
        await update.message.reply_text(res.text, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text("Не удалось распознать фото.")

def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(filters.ALL, start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_height)],
            DISEASES: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_diseases)],
            CHAT_MODE: [
                MessageHandler(filters.PHOTO, photo_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler)
            ],
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True
    )
    
    app.add_handler(conv)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
