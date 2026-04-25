import os
import logging
import sqlite3
import re
import io
from PIL import Image
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler,
)

# Настройки путей - используем корень проекта для простоты
DB_PATH = "medical_bot.db"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT_MODE = range(6)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

SAFETY = {cat: HarmBlockThreshold.BLOCK_NONE for cat in HarmCategory}

def get_model():
    for name in ['gemini-1.5-flash-latest', 'gemini-1.5-flash']:
        try:
            return genai.GenerativeModel(model_name=name, safety_settings=SAFETY,
                system_instruction="Ты врач-терапевт. Давай краткие советы.")
        except: continue
    return None

model = get_model()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute('''CREATE TABLE IF NOT EXISTS users 
        (user_id INTEGER PRIMARY KEY, gender TEXT, age INTEGER, weight REAL, height REAL, diseases TEXT)''')
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_PATH)
    user = conn.cursor().execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()

    if user:
        await update.message.reply_text("👋 Доктор на связи!", reply_markup=ReplyKeyboardMarkup([['Моя медкарта', 'Консультация'], ['SOS']], resize_keyboard=True))
        return CHAT_MODE
    
    await update.message.reply_text("Ваш пол?", reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True))
    return GENDER

async def collect_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gender'] = update.message.text
    await update.message.reply_text("Ваш возраст?")
    return AGE

async def collect_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['age'] = int(re.search(r'\d+', update.message.text).group())
    await update.message.reply_text("Ваш вес (кг)?")
    return WEIGHT

async def collect_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['weight'] = float(re.search(r'\d+', update.message.text).group())
    await update.message.reply_text("Ваш рост (см)?")
    return HEIGHT

async def collect_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['height'] = float(re.search(r'\d+', update.message.text).group())
    await update.message.reply_text("Болезни?")
    return DISEASES

async def collect_diseases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    d = update.message.text
    u = context.user_data
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?)", (user_id, u['gender'], u['age'], u['weight'], u['height'], d))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Сохранено!", reply_markup=ReplyKeyboardMarkup([['Моя медкарта', 'Консультация'], ['SOS']], resize_keyboard=True))
    return CHAT_MODE

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    conn = sqlite3.connect(DB_PATH)
    u = conn.cursor().execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()

    if text == "Моя медкарта":
        await update.message.reply_text(f"📋 Карта: {u[1]}, {u[2]}л, {u[3]}кг")
        return
    
    try:
        res = model.generate_content(f"Пациент {u[2]}л, {u[3]}кг. Вопрос: {text}")
        await update.message.reply_text(res.text, parse_mode='Markdown')
    except:
        await update.message.reply_text("Ошибка ИИ. Попробуйте еще раз.")

def main():
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
            CHAT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler)],
        },
        fallbacks=[CommandHandler('start', start)]
    )
    app.add_handler(conv)
    app.run_polling()

if __name__ == '__main__':
    main()
