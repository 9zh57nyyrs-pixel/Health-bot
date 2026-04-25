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

# --- ЛОГИРОВАНИЕ ДЛЯ ПРОВЕРКИ ОШИБОК ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("HealthBot")

TOKEN = os.getenv("TELEGRAM_TOKEN")
AI_KEY = os.getenv("GEMINI_API_KEY")
DB_NAME = "health_data.db"

GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT_MODE = range(6)

# --- НАСТРОЙКА ИИ (БЕЗ ФИЛЬТРОВ) ---
if AI_KEY:
    genai.configure(api_key=AI_KEY)

AI_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
}

model = genai.GenerativeModel('gemini-1.5-flash', safety_settings=AI_SETTINGS)

# --- РАБОТА С БАЗОЙ (SQLITE - НЕ ТРЕБУЕТ НАСТРОЙКИ) ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, gender TEXT, age INT, weight REAL, height REAL, diseases TEXT)')
    conn.commit()
    conn.close()

def get_user(uid):
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()

# --- ЛОГИКА БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user:
        await update.message.reply_text("👋 Я готов. Карта загружена. Какой у вас вопрос?", 
            reply_markup=ReplyKeyboardMarkup([['🧬 Консультация', '📋 Карта']], resize_keyboard=True))
        return CHAT_MODE
    
    await update.message.reply_text("Привет! Я врач-ИИ. Давайте заполним карту. Ваш пол?",
        reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True))
    return GENDER

async def collect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    if 'data' not in context.user_data: context.user_data['data'] = {}
    d = context.user_data['data']

    if 'gender' not in d:
        d['gender'] = txt
        await update.message.reply_text("Возраст?")
        return AGE
    elif 'age' not in d:
        d['age'] = int(re.search(r'\d+', txt).group())
        await update.message.reply_text("Вес (кг)?")
        return WEIGHT
    elif 'weight' not in d:
        d['weight'] = float(re.search(r'\d+', txt).group())
        await update.message.reply_text("Рост (см)?")
        return HEIGHT
    elif 'height' not in d:
        d['height'] = float(re.search(r'\d+', txt).group())
        await update.message.reply_text("Хронические болезни?")
        return DISEASES

async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    dis = update.message.text
    d = context.user_data['data']
    
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?)", 
                     (uid, d['gender'], d['age'], d['weight'], d['height'], dis))
    
    await update.message.reply_text("✅ Сохранено. Спрашивайте!", 
        reply_markup=ReplyKeyboardMarkup([['🧬 Консультация', '📋 Карта']], resize_keyboard=True))
    return CHAT_MODE

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    msg = update.message.text
    if msg == '📋 Карта':
        return await update.message.reply_text(f"Профиль: {u[1]}, {u[2]}л, {u[3]}кг")
    
    await update.message.reply_chat_action(constants.ChatAction.TYPING)
    prompt = f"Пациент: {u[1]}, {u[2]} лет, болезни: {u[5]}. Вопрос: {msg}"
    res = await asyncio.to_thread(model.generate_content, prompt)
    await update.message.reply_text(res.text, parse_mode='Markdown')
    return CHAT_MODE

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(filters.ALL, start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect)],
            DISEASES: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish)],
            CHAT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat)],
        },
        fallbacks=[CommandHandler('start', start)]
    )
    app.add_handler(conv)
    app.run_polling()

if __name__ == '__main__':
    main()
