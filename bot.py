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

# --- НАСТРОЙКИ ЛОГИРОВАНИЯ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ И БД ---
DB_PATH = "/tmp/medical_bot.db"  # Путь для Railway
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_KEY)

# СОСТОЯНИЯ ДИАЛОГА
GENDER, AGE, WEIGHT, HEIGHT, ILLNESSES, MENU, CONSULT, PHOTO = range(8)

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
        (id INTEGER PRIMARY KEY, gender TEXT, age TEXT, weight TEXT, height TEXT, ill TEXT)''')
    conn.commit()
    conn.close()

# --- ЛОГИКА ВЗАИМОДЕЙСТВИЯ С GEMINI ---
async def ask_gemini(prompt, photo=None):
    # Системная инструкция для "умных" ответов
    system_instruction = (
        "Ты — профессиональный медицинский ИИ-ассистент. Твои ответы должны быть: "
        "1. Структурированными и подробными. 2. На русском языке. "
        "3. С обязательным дисклеймером: 'Данная информация носит ознакомительный характер, "
        "необходима консультация специалиста'. 4. Если прислано фото анализов, опиши "
        "показатели и их соответствие нормам."
    )
    
    models = ["gemini-1.5-flash", "gemini-1.5-pro"]
    for m_name in models:
        try:
            model = genai.GenerativeModel(
                model_name=m_name,
                system_instruction=system_instruction
            )
            content = [prompt]
            if photo:
                content.append({"mime_type": "image/jpeg", "data": photo})
            
            response = await model.generate_content_async(content)
            return response.text
        except Exception as e:
            logger.error(f"Ошибка модели {m_name}: {e}")
            continue
    return "⚠️ Ошибка связи с ИИ-мозгом. Попробуйте позже."

# --- ОБРАБОТЧИКИ КОМАНД ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Здравствуйте! Я ваш медицинский помощник. Чтобы я мог давать точные советы, "
        "давайте заполним вашу анкету.\n\nВведите ваш пол (М/Ж):",
        reply_markup=ReplyKeyboardRemove()
    )
    return GENDER

async def get_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['g'] = update.message.text
    await update.message.reply_text("Ваш возраст?")
    return AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a'] = update.message.text
    await update.message.reply_text("Ваш вес (кг)?")
    return WEIGHT

async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['w'] = update.message.text
    await update.message.reply_text("Ваш рост (см)?")
    return HEIGHT

async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['h'] = update.message.text
    await update.message.reply_text("Есть ли у вас хронические заболевания? (Если нет, напишите 'Нет')")
    return ILLNESSES

async def get_ill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    user_id = update.effective_user.id
    ill = update.message.text
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?)", 
                 (user_id, ud['g'], ud['a'], ud['w'], ud['h'], ill))
    conn.commit()
    conn.close()
    
    await update.message.reply_text("✅ Медкарта сохранена!")
    return await show_menu(update)

async def show_menu(update: Update):
    kb = [
        [KeyboardButton("💊 Консультация"), KeyboardButton("📋 Медкарта")],
        [KeyboardButton("🔬 Анализы"), KeyboardButton("🆘 SOS")]
    ]
    await update.message.reply_text(
        "Выберите действие в меню:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )
    return MENU

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "💊 Консультация":
        await update.message.reply_text("Опишите ваши симптомы или задайте вопрос:")
        return CONSULT
    elif text == "📋 Медкарта":
        conn = sqlite3.connect(DB_PATH)
        r = conn.execute("SELECT * FROM users WHERE id=?", (update.effective_user.id,)).fetchone()
        conn.close()
        if r:
            msg = (f"👤 Ваша карта:\nПол: {r[1]}\nВозраст: {r[2]}\nВес: {r[3]}кг\n"
                   f"Рост: {r[4]}см\nБолезни: {r[5]}")
        else:
            msg = "Карта не найдена. Нажмите /start"
        await update.message.reply_text(msg)
        return MENU
    elif text == "🔬 Анализы":
        await update.message.reply_text("Пришлите четкое фото ваших анализов:")
        return PHOTO
    elif text == "🆘 SOS":
        await update.message.reply_text("⚠️ Срочно звоните по номеру 103 или 112!")
        return MENU
    return MENU

async def do_consult(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Достаем данные пользователя для контекста
    conn = sqlite3.connect(DB_PATH)
    r = conn.execute("SELECT * FROM users WHERE id=?", (update.effective_user.id,)).fetchone()
    conn.close()
    
    user_info = f"Пациент: {r[1]}, {r[2]} лет, вес {r[3]}кг. Болезни: {r[5]}." if r else ""
    prompt = f"Контекст: {user_info}\nВопрос пользователя: {update.message.text}"
    
    await update.message.reply_chat_action("typing")
    ans = await ask_gemini(prompt)
    await update.message.reply_text(ans)
    return await show_menu(update)

async def do_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Анализирую фото, это займет несколько секунд...")
    file = await update.message.photo[-1].get_file()
    img_bytes = await file.download_as_bytearray()
    
    ans = await ask_gemini("Проанализируй эти медицинские анализы:", photo=bytes(img_bytes))
    await update.message.reply_text(ans)
    return await show_menu(update)

# --- ЗАПУСК ---
def main():
    init_db()
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN не найден!")
        return

    application = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
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
        fallbacks=[CommandHandler("start", start)],
    )
    
    application.add_handler(conv_handler)
    
    print("--- БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ ---", flush=True)
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
