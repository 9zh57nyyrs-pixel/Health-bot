import os
import logging
import sqlite3
import re
import io
import asyncio
from datetime import datetime
from PIL import Image

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler,
)

# --- ПРОФЕССИОНАЛЬНОЕ ЛОГИРОВАНИЕ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MedicalBotCore")

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DB_PATH = "medical_system_v3.db"

# Состояния диалога
GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT_MODE = range(6)

# --- ИНИЦИАЛИЗАЦИЯ ИИ С НУЛЕВЫМИ ФИЛЬТРАМИ ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Настройка для медицинского контекста (отключаем блокировки)
SAFETY = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

class MedicalEngine:
    def __init__(self):
        self.model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            safety_settings=SAFETY,
            system_instruction=(
                "Ты — продвинутый цифровой врач-терапевт. Твоя цель — помогать пациентам, "
                "основываясь на их данных (возраст, вес, болезни). Давай глубокую диагностику, "
                "но всегда напоминай о важности очного визита."
            )
        )

    async def generate_response(self, user_profile, user_message, image=None):
        prompt = (
            f"ПРОФИЛЬ ПАЦИЕНТА: {user_profile['gender']}, {user_profile['age']} лет, "
            f"вес {user_profile['weight']}кг, рост {user_profile['height']}см. "
            f"Анамнез: {user_profile['diseases']}.\n"
            f"ЗАПРОС: {user_message}"
        )
        try:
            content = [prompt, image] if image else prompt
            response = await asyncio.to_thread(self.model.generate_content, content)
            return response.text
        except Exception as e:
            logger.error(f"Gemini API Error: {e}")
            return "🩺 Мои системы временно перегружены. Попробуйте переформулировать вопрос."

engine = MedicalEngine()

# --- СЛОЙ БАЗЫ ДАННЫХ ---
def db_manage(query, params=(), fetch=False):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            if fetch: return cur.fetchone()
            conn.commit()
    except Exception as e:
        logger.error(f"Database Error: {e}")
        return None

def init_system():
    db_manage('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, gender TEXT, age INTEGER, weight REAL, height REAL, diseases TEXT)''')

# --- ЛОГИКА ИНТЕРФЕЙСА ---
def main_kb():
    return ReplyKeyboardMarkup([['🧬 Консультация', '📋 Моя карта'], ['🆘 SOS']], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db_manage("SELECT * FROM users WHERE id=?", (user_id,), fetch=True)
    
    if user:
        await update.message.reply_text("👋 Система готова. Доктор на связи.", reply_markup=main_kb())
        return CHAT_MODE
    
    await update.message.reply_text(
        "Добро пожаловать в интеллектуальную медицинскую систему.\n"
        "Для начала работы необходимо создать вашу цифровую карту. Ваш пол?",
        reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True)
    )
    return GENDER

async def collect_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gender'] = update.message.text
    await update.message.reply_text("Укажите ваш возраст:")
    return AGE

async def collect_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    age = re.findall(r'\d+', update.message.text)
    if not age: return AGE
    context.user_data['age'] = int(age[0])
    await update.message.reply_text("Ваш вес (кг):")
    return WEIGHT

async def collect_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    w = re.findall(r'\d+', update.message.text)
    if not w: return WEIGHT
    context.user_data['weight'] = float(w[0])
    await update.message.reply_text("Ваш рост (см):")
    return HEIGHT

async def collect_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    h = re.findall(r'\d+', update.message.text)
    if not h: return HEIGHT
    context.user_data['height'] = float(h[0])
    await update.message.reply_text("Есть ли у вас хронические заболевания? Если нет, напишите 'Нет'.")
    return DISEASES

async def finalize_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    d = update.message.text
    ud = context.user_data
    
    db_manage("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?)", 
              (user_id, ud['gender'], ud['age'], ud['weight'], ud['height'], d))
    
    await update.message.reply_text("✅ Цифровая медкарта успешно сохранена.", reply_markup=main_kb())
    return CHAT_MODE

async def handle_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    # Защита от потери данных
    u_data = db_manage("SELECT * FROM users WHERE id=?", (user_id,), fetch=True)
    if not u_data: return await start(update, context)
    
    profile = {"gender": u_data[1], "age": u_data[2], "weight": u_data[3], "height": u_data[4], "diseases": u_data[5]}

    if text == '📋 Моя карта':
        await update.message.reply_text(f"📊 Текущие данные: {profile['gender']}, {profile['age']} лет, {profile['weight']}кг. Анамнез: {profile['diseases']}")
    elif text == '🆘 SOS':
        await update.message.reply_text("🚨 Экстренная помощь: 103 / 112")
    else:
        await update.message.reply_chat_action("typing")
        response = await engine.generate_response(profile, text)
        await update.message.reply_text(response, parse_mode='Markdown')
    return CHAT_MODE

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u_data = db_manage("SELECT * FROM users WHERE id=?", (user_id,), fetch=True)
    profile = {"gender": u_data[1], "age": u_data[2], "weight": u_data[3], "height": u_data[4], "diseases": u_data[5]}

    await update.message.reply_text("🔬 Провожу визуальный анализ...")
    photo = await update.message.photo[-1].get_file()
    img = Image.open(io.BytesIO(await photo.download_as_bytearray()))
    
    response = await engine.generate_response(profile, "Проанализируй это медицинское изображение", img)
    await update.message.reply_text(response, parse_mode='Markdown')

def main():
    init_system()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(filters.ALL, start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_height)],
            DISEASES: [MessageHandler(filters.TEXT & ~filters.COMMAND, finalize_card)],
            CHAT_MODE: [
                MessageHandler(filters.PHOTO, handle_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main)
            ],
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    app.add_handler(conv)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
