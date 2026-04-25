import os
import sqlite3
import logging
import asyncio
from datetime import datetime
from typing import List, Optional

import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackContext,
    filters,
)

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Константы состояний
SURVEY_GENDER, SURVEY_AGE, SURVEY_WEIGHT, SURVEY_HEIGHT, SURVEY_ILLNESSES, MAIN_MENU = range(6)
CONSULTATION, ANALYSES = range(6, 8)

# Конфигурация API
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PORT = int(os.environ.get("PORT", 8080))
DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN")

genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = (
    "Вы — высококвалифицированный врач-терапевт. Ваша задача — проводить предварительные консультации. "
    "Всегда напоминайте, что ваши советы не являются окончательным диагнозом и нужно очно обратиться к врачу. "
    "Используйте данные медкарты пользователя (пол, возраст, вес, рост, болезни) для контекста. "
    "Отвечайте профессионально, эмпатично и четко."
)

# Работа с БД
def init_db():
    conn = sqlite3.connect("medical_bot.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
        (user_id INTEGER PRIMARY KEY, gender TEXT, age INTEGER, weight INTEGER, height INTEGER, illnesses TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, role TEXT, content TEXT, timestamp DATETIME)''')
    conn.commit()
    conn.close()

def save_user(user_id, data):
    conn = sqlite3.connect("medical_bot.db")
    cursor = conn.cursor()
    cursor.execute('''INSERT OR REPLACE INTO users (user_id, gender, age, weight, height, illnesses) 
        VALUES (?, ?, ?, ?, ?, ?)''', (user_id, data['gender'], data['age'], data['weight'], data['height'], data['illnesses']))
    conn.commit()
    conn.close()

def get_user_profile(user_id):
    conn = sqlite3.connect("medical_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def save_message(user_id, role, content):
    conn = sqlite3.connect("medical_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                   (user_id, role, content, datetime.now()))
    conn.commit()
    conn.close()

# Gemini AI Logic
async def call_gemini(prompt, history=[], photo_data=None):
    models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
    
    for model_name in models:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=SYSTEM_INSTRUCTION if "1.5" in model_name else None
            )
            
            content = []
            if photo_data:
                content.append({"mime_type": "image/jpeg", "data": photo_data})
            content.append(prompt)
            
            # Если gemini-pro (старая), системная инструкция идет первым сообщением
            chat = model.start_chat(history=history)
            response = await chat.send_message_async(content)
            return response.text
        except Exception as e:
            logger.error(f"Error with {model_name}: {e}")
            continue
    return "Извините, сейчас я не могу ответить. Попробуйте позже."

# Обработчики команд
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    
    if profile:
        return await show_main_menu(update, context)
    
    await update.message.reply_text("Здравствуйте! Я ваш медицинский ассистент. Давайте заполним медкарту. Ваш пол (М/Ж)?")
    return SURVEY_GENDER

async def survey_gender(update: Update, context: CallbackContext):
    context.user_data['gender'] = update.message.text
    await update.message.reply_text("Ваш возраст?")
    return SURVEY_AGE

async def survey_age(update: Update, context: CallbackContext):
    context.user_data['age'] = update.message.text
    await update.message.reply_text("Ваш вес (кг)?")
    return SURVEY_WEIGHT

async def survey_height(update: Update, context: CallbackContext):
    context.user_data['weight'] = update.message.text
    await update.message.reply_text("Ваш рост (см)?")
    return SURVEY_HEIGHT

async def survey_illnesses(update: Update, context: CallbackContext):
    context.user_data['height'] = update.message.text
    await update.message.reply_text("Есть ли у вас хронические заболевания или аллергии? (Если нет, напишите 'нет')")
    return SURVEY_ILLNESSES

async def complete_survey(update: Update, context: CallbackContext):
    context.user_data['illnesses'] = update.message.text
    save_user(update.effective_user.id, context.user_data)
    await update.message.reply_text("Профиль сохранен!")
    return await show_main_menu(update, context)

async def show_main_menu(update: Update, context: CallbackContext):
    keyboard = [
        [KeyboardButton("💊 Консультация"), KeyboardButton("📋 Медкарта")],
        [KeyboardButton("🔬 Анализы (фото)"), KeyboardButton("🆘 SOS")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Главное меню:", reply_markup=reply_markup)
    return MAIN_MENU

async def handle_menu(update: Update, context: CallbackContext):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "💊 Консультация":
        await update.message.reply_text("Опишите ваши симптомы или задайте вопрос:", reply_markup=ReplyKeyboardRemove())
        return CONSULTATION
    
    elif text == "📋 Медкарта":
        p = get_user_profile(user_id)
        msg = f"👤 Пол: {p[1]}\n🎂 Возраст: {p[2]}\n⚖️ Вес: {p[3]} кг\n📏 Рост: {p[4]} см\n⚠️ Болезни: {p[5]}"
        await update.message.reply_text(msg)
        return MAIN_MENU

    elif text == "🔬 Анализы (фото)":
        await update.message.reply_text("Пожалуйста, отправьте фото результатов анализов или документов:", reply_markup=ReplyKeyboardRemove())
        return ANALYSES

    elif text == "🆘 SOS":
        await update.message.reply_text("При жизнеугрожающих состояниях немедленно звоните 103 или 112!")
        return MAIN_MENU

async def process_consultation(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_input = update.message.text
    
    profile = get_user_profile(user_id)
    context_prompt = f"Пациент: {profile[1]}, {profile[2]} лет, {profile[3]}кг/{profile[4]}см. Хроническое: {profile[5]}. Запрос: {user_input}"
    
    save_message(user_id, "user", user_input)
    
    loading_msg = await update.message.reply_text("Анализирую данные...")
    response = await call_gemini(context_prompt)
    
    save_message(user_id, "assistant", response)
    await loading_msg.delete()
    await update.message.reply_text(response)
    return await show_main_menu(update, context)

async def process_photo(update: Update, context: CallbackContext):
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте именно фото.")
        return ANALYSES

    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    
    loading_msg = await update.message.reply_text("Изучаю документ...")
    prompt = "Проанализируй этот медицинский документ/анализ. Объясни значения и укажи на отклонения от нормы."
    
    response = await call_gemini(prompt, photo_data=bytes(photo_bytes))
    await loading_msg.delete()
    await update.message.reply_text(response)
    return await show_main_menu(update, context)

async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
    return await show_main_menu(update, context)

def main():
    init_db()
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SURVEY_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, survey_gender)],
            SURVEY_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, survey_age)],
            SURVEY_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, survey_weight)],
            SURVEY_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, survey_height)],
            SURVEY_ILLNESSES: [MessageHandler(filters.TEXT & ~filters.COMMAND, complete_survey)],
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu)],
            CONSULTATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_consultation)],
            ANALYSES: [MessageHandler(filters.PHOTO, process_photo)],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)],
    )

    application.add_handler(conv_handler)

    if DOMAIN:
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"https://{DOMAIN}/{TELEGRAM_TOKEN}"
        )
    else:
        application.run_polling()

if __name__ == '__main__':
    main()
