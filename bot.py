import os
import sqlite3
import logging
import sys
import asyncio
from datetime import datetime

import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# 1. Настройка логов для Railway
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# 2. Переменные и БД (используем /tmp для записи)
DB_PATH = "/tmp/medical_bot.db"
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_KEY)

# Состояния
GENDER, AGE, WEIGHT, HEIGHT, ILLNESSES, MENU, CONSULT, PHOTO = range(8)

# 3. Функции БД
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
        (id INTEGER PRIMARY KEY, gender TEXT, age TEXT, weight TEXT, height TEXT, ill TEXT)''')
    conn.commit()
    conn.close()

# 4. Логика ИИ
async def ask_gemini(prompt, photo=None):
    models = ["gemini-1.5-flash", "gemini-1.5-pro"]
    for m_name in models:
        try:
            model = genai.GenerativeModel(m_name)
            content = [prompt]
            if photo:
                content.append({"mime_type": "image/jpeg", "data": photo})
            response = await model.generate_content_async(content)
            return response.text
        except: continue
    return "⚠️ Ошибка связи с ИИ."

# 5. Хендлеры
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Добро пожаловать! Начнем с медкарты. Ваш пол?")
    return GENDER

async def get_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['g'] = update.message.text
    await update.message.reply_text("Ваш возраст?")
    return AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a'] = update.message.text
    await update.message.reply_text("Ваш вес?")
    return WEIGHT

async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['w'] = update.message.text
    await update.message.reply_text("Ваш рост?")
    return HEIGHT

async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['h'] = update.message.text
    await update.message.reply_text("Хронические заболевания?")
    return ILLNESSES

async def get_ill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?)", 
                 (update.effective_user.id, ud['g'], ud['a'], ud['w'], ud['h'], update.message.text))
    conn.commit()
    conn.close()
    return await show_menu(update)

async def show_menu(update: Update):
    kb = [["💊 Консультация", "📋 Медкарта"], ["🔬 Анализы", "🆘 SOS"]]
    await update.message.reply_text("Меню:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return MENU

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "💊 Консультация":
        await update.message.reply_text("Опишите проблему:", reply_markup=ReplyKeyboardRemove())
        return CONSULT
    if text == "📋 Медкарта":
        conn = sqlite3.connect(DB_PATH); r = conn.execute("SELECT * FROM users WHERE id=?", (update.effective_user.id,)).fetchone(); conn.close()
        await update.message.reply_text(f"Данные: {r[1]}, {r[2]} лет, {r[3]}кг, {r[4]}см. Болезни: {r[5]}")
        return MENU
    if text == "🔬 Анализы":
        await update.message.reply_text("Пришлите фото:", reply_markup=ReplyKeyboardRemove())
        return PHOTO
    if text == "🆘 SOS":
        await update.message.reply_text("Вызывайте 103/112!")
        return MENU

async def do_consult(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = await ask_gemini(f"Как врач, ответь на вопрос: {update.message.text}")
    await update.message.reply_text(ans)
    return await show_menu(update)

async def do_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.photo[-1].get_file()
    img_bytes = await file.download_as_bytearray()
    ans = await ask_gemini("Проанализируй анализ на фото:", photo=bytes(img_bytes))
    await update.message.reply_text(ans)
    return await show_menu(update)

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            ILLNESSES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ill)],
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu)],
            CONSULT: [MessageHandler(filters.TEXT & ~filters.COMMAND, do_consult)],
            PHOTO: [MessageHandler(filters.PHOTO, do_photo)],
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    app.add_handler(conv)
    print("--- БОТ ЗАПУЩЕН ---", flush=True)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
