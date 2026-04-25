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

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT_MODE = range(6)

# --- Настройка ИИ с обходом фильтров безопасности ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = (
    "Ты — элитный врач-терапевт с огромным стажем. "
    "Давай подробные, научно обоснованные советы. "
    "Используй данные пациента для анализа. "
    "Обязательно делай пометку, что это не является окончательным диагнозом."
)

# Настройки для предотвращения ложных блокировок медицинского контента
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

def get_gemini_model():
    models_to_try = [
        'gemini-1.5-flash-latest', 
        'gemini-1.5-flash', 
        'gemini-1.5-pro-latest',
        'gemini-pro'
    ]
    for m_name in models_to_try:
        try:
            m = genai.GenerativeModel(
                model_name=m_name, 
                system_instruction=SYSTEM_INSTRUCTION,
                safety_settings=SAFETY_SETTINGS
            )
            # Проверка связи
            m.generate_content("test", generation_config={"max_output_tokens": 1})
            logger.info(f"Успешно подключена модель: {m_name}")
            return m
        except Exception as e:
            logger.warning(f"Ошибка при попытке {m_name}: {e}")
    return None

model = get_gemini_model()

# --- Работа с БД ---
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
def get_main_menu():
    return ReplyKeyboardMarkup([['Моя медкарта', 'Консультация'], ['SOS']], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if get_user(user_id):
        await update.message.reply_text("👋 С возвращением! Я готов к консультации.", reply_markup=get_main_menu())
        return CHAT_MODE
    
    await update.message.reply_text("Здравствуйте! Я врач-терапевт. Давайте создадим вашу медкарту. Ваш пол?",
                                   reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True))
    return GENDER

async def collect_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gender'] = update.message.text
    await update.message.reply_text("Введите ваш возраст:")
    return AGE

async def collect_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    age_match = re.search(r'\d+', update.message.text)
    if not age_match:
        await update.message.reply_text("Пожалуйста, введите возраст цифрами.")
        return AGE
    context.user_data['age'] = int(age_match.group())
    await update.message.reply_text("Введите ваш вес (кг):")
    return WEIGHT

async def collect_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    w_match = re.search(r'\d+', update.message.text)
    if not w_match:
        await update.message.reply_text("Введите вес цифрами.")
        return WEIGHT
    context.user_data['weight'] = float(w_match.group())
    await update.message.reply_text("Введите ваш рост (см):")
    return HEIGHT

async def collect_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    h_match = re.search(r'\d+', update.message.text)
    if not h_match:
        await update.message.reply_text("Введите рост цифрами.")
        return HEIGHT
    context.user_data['height'] = float(h_match.group())
    await update.message.reply_text("Укажите ваши хронические заболевания (или напишите 'Нет'):")
    return DISEASES

async def collect_diseases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['diseases'] = update.message.text
    save_user(update.effective_user.id, context.user_data)
    await update.message.reply_text("✅ Карта создана. Теперь вы можете задавать вопросы или прислать фото анализов.", reply_markup=get_main_menu())
    return CHAT_MODE

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if text == "Моя медкарта":
        u = get_user(user_id)
        msg = f"📋 *Ваша медкарта:*\nВозраст: {u[2]}\nВес: {u[3]} кг\nРост: {u[4]} см\nБолезни: {u[5]}"
        await update.message.reply_text(msg, parse_mode='Markdown')
        return
    
    if text == "SOS":
        await update.message.reply_text("🚨 Срочно обратитесь в службу спасения: 103 или 112!")
        return

    # Обращение к ИИ
    global model
    if not model: model = get_gemini_model()
    
    try:
        u = get_user(user_id)
        prompt = (f"ПАЦИЕНТ: {u[1]}, {u[2]} лет, вес {u[3]}кг, рост {u[4]}см. "
                  f"Хроническое: {u[5]}. ВОПРОС: {text}")
        
        response = model.generate_content(prompt)
        await update.message.reply_text(response.text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        if "429" in str(e):
            await update.message.reply_text("⏳ Слишком много запросов. Подождите минуту.")
        else:
            await update.message.reply_text("🩺 Врач сейчас на обходе. Пожалуйста, повторите вопрос позже.")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⌛ Анализирую ваше изображение, секунду...")
    try:
        photo = await update.message.photo[-1].get_file()
        b_img = await photo.download_as_bytearray()
        img = Image.open(io.BytesIO(b_img))
        
        u = get_user(update.effective_user.id)
        res = model.generate_content([
            f"Проанализируй эти анализы для пациента ({u[2]} лет). Выдели отклонения.", 
            img
        ])
        await update.message.reply_text(res.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Photo error: {e}")
        await update.message.reply_text("Не удалось распознать фото. Попробуйте сделать снимок четче.")

def main():
    if not TELEGRAM_TOKEN: return
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(filters.ALL & ~filters.COMMAND, start)],
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
