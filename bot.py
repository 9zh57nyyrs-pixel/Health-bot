import os
import logging
import sqlite3
import re
import io
import asyncio
from PIL import Image
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from telegram import Update, ReplyKeyboardMarkup, constants
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler,
)

# Детальные логи для Railway
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
AI_KEY = os.getenv("GEMINI_API_KEY")
DB_NAME = "medical_expert_v3.db"

# Этапы опроса
GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT_MODE = range(6)

# --- ИИ КОНФИГУРАЦИЯ ---
if AI_KEY:
    genai.configure(api_key=AI_KEY)

SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

model = genai.GenerativeModel(
    model_name='gemini-1.5-flash',
    safety_settings=SAFETY_SETTINGS,
    system_instruction="Ты — опытный врач-терапевт. Анализируй жалобы и фото анализов пользователя, учитывая его медкарту."
)

# --- БАЗА ДАННЫХ (БЕЗВЫЛЕТНАЯ) ---
def db_query(sql, params=(), fetch=False):
    """Универсальная функция для работы с БД без утечек соединений"""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            if fetch:
                return cursor.fetchone()
            conn.commit()
    except Exception as e:
        logger.error(f"Database error: {e}")
    return None

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users 
                (id INTEGER PRIMARY KEY, gender TEXT, age INTEGER, weight REAL, height REAL, diseases TEXT)''')

# --- ГЛАВНАЯ ЛОГИКА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db_query("SELECT * FROM users WHERE id=?", (user_id,), fetch=True)

    if user:
        await update.message.reply_text(
            f"🩺 Рад видеть вас снова. Карта загружена ({user[1]}, {user[2]} лет).\nЧем я могу помочь?",
            reply_markup=ReplyKeyboardMarkup([['📋 Моя карта', '🧬 Консультация']], resize_keyboard=True)
        )
        return CHAT_MODE

    await update.message.reply_text(
        "Здравствуйте! Я ваш медицинский ассистент. Давайте заполним карту. Ваш пол?",
        reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True)
    )
    return GENDER

async def get_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gender'] = update.message.text
    await update.message.reply_text("Ваш возраст?")
    return AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = int(re.search(r'\d+', update.message.text).group())
        context.user_data['age'] = val
        await update.message.reply_text("Ваш вес (кг)?")
        return WEIGHT
    except:
        await update.message.reply_text("Пожалуйста, введите возраст цифрами.")
        return AGE

async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['weight'] = update.message.text
    await update.message.reply_text("Ваш рост (см)?")
    return HEIGHT

async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['height'] = update.message.text
    await update.message.reply_text("Хронические болезни (или 'нет')?")
    return DISEASES

async def get_diseases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    d = context.user_data
    dis = update.message.text
    
    db_query("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?)", 
             (uid, d['gender'], d['age'], d['weight'], d['height'], dis))
    
    await update.message.reply_text("✅ Карта сохранена. Теперь вы можете задавать любые вопросы или присылать фото анализов.",
                                   reply_markup=ReplyKeyboardMarkup([['📋 Моя карта', '🧬 Консультация']], resize_keyboard=True))
    return CHAT_MODE

async def medical_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message.text
    user = db_query("SELECT * FROM users WHERE id=?", (uid,), fetch=True)

    if not user:
        return await start(update, context)

    if msg == '📋 Моя карта':
        await update.message.reply_text(f"📊 Карта: {user[1]}, {user[2]} лет, {user[3]}кг, {user[4]}см.\nБолезни: {user[5]}")
        return CHAT_MODE

    await update.message.reply_chat_action(constants.ChatAction.TYPING)
    
    profile = f"Пациент: {user[1]}, {user[2]} лет, вес {user[3]}, рост {user[4]}, анамнез: {user[5]}."
    
    try:
        # Если есть фото
        photo = None
        if update.message.photo:
            file = await update.message.photo[-1].get_file()
            photo = Image.open(io.BytesIO(await file.download_as_bytearray()))
            prompt = [profile, "Проанализируй фото анализов и ответь на вопрос пользователя: " + (msg or "что на фото?"), photo]
        else:
            prompt = f"{profile}\nВопрос: {msg}"

        response = await asyncio.to_thread(model.generate_content, prompt)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"AI Error: {e}")
        await update.message.reply_text("⚠️ Ошибка обработки. Попробуйте переформулировать вопрос.")
    
    return CHAT_MODE

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(filters.ALL, start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            DISEASES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_diseases)],
            CHAT_MODE: [
                MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, medical_handler)
            ],
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True
    )
    
    app.add_handler(conv_handler)
    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()
