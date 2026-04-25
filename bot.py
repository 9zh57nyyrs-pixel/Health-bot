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
from telegram import Update, ReplyKeyboardMarkup, constants
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler,
)

# Настройка логирования для отслеживания вылетов в Railway
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AdvancedMedicalBot")

# Конфигурация из переменных окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
AI_KEY = os.getenv("GEMINI_API_KEY")
DB_PATH = "advanced_health.db"

# Состояния диалога
GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT_MODE = range(6)

# --- ИНТЕЛЛЕКТУАЛЬНОЕ ЯДРО (БЕЗ ЦЕНЗУРЫ) ---
if AI_KEY:
    genai.configure(api_key=AI_KEY)

# Отключаем фильтры, чтобы Gemini не блокировал медицинский контент
SAFETY = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
}

class ProfessionalDoctorAI:
    def __init__(self):
        self.model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            safety_settings=SAFETY,
            system_instruction=(
                "Ты — высококвалифицированный врач-терапевт с 20-летним стажем. "
                "Твоя цель: проводить глубокий анализ симптомов и анализов. "
                "Всегда учитывай параметры пациента (пол, возраст, вес, болезни). "
                "Твои ответы должны быть структурированными, профессиональными и содержать "
                "конкретные рекомендации по дальнейшим шагам или обследованиям."
            )
        )

    async def get_answer(self, profile, user_msg, photo=None):
        context = (
            f"КЛИНИЧЕСКАЯ КАРТИНА:\nПациент: {profile['gender']}, {profile['age']} лет.\n"
            f"Параметры: {profile['weight']}кг, {profile['height']}см.\n"
            f"Анамнез: {profile['diseases']}\n\n"
            f"ЖАЛОБА/ВОПРОС: {user_msg}"
        )
        try:
            content = [context, photo] if photo else context
            response = await asyncio.to_thread(self.model.generate_content, content)
            return response.text
        except Exception as e:
            logger.error(f"AI ERROR: {e}")
            return "🩺 Извините, произошел технический сбой в нейросети. Попробуйте еще раз."

doctor_ai = ProfessionalDoctorAI()

# --- СИСТЕМА ПАМЯТИ (SQLITE) ---
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
            (id INTEGER PRIMARY KEY, gender TEXT, age INTEGER, weight REAL, height REAL, diseases TEXT)''')

def get_user_data(uid):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if res:
            return {"gender": res[1], "age": res[2], "weight": res[3], "height": res[4], "diseases": res[5]}
        return None

# --- ЛОГИКА ВЗАИМОДЕЙСТВИЯ ---
def get_main_kb():
    return ReplyKeyboardMarkup([['🔬 Консультация', '📂 Моя медкарта'], ['🆘 Экстренная помощь']], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user_data(update.effective_user.id)
    if user:
        await update.message.reply_text(
            f"👋 Добро пожаловать, Доктор на связи.\nВаша карта загружена. Что вас беспокоит?", 
            reply_markup=get_main_kb()
        )
        return CHAT_MODE
    
    await update.message.reply_text(
        "Здравствуйте! Я ваш продвинутый медицинский ИИ-ассистент.\n"
        "Для точной диагностики мне нужно создать вашу цифровую карту. Укажите ваш пол:",
        reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True)
    )
    return GENDER

async def process_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    step = context.user_data.get('reg_step', GENDER)

    if step == GENDER:
        context.user_data['tmp_gender'] = text
        context.user_data['reg_step'] = AGE
        await update.message.reply_text("Укажите ваш полный возраст:")
        return AGE
    elif step == AGE:
        context.user_data['tmp_age'] = int(re.search(r'\d+', text).group())
        context.user_data['reg_step'] = WEIGHT
        await update.message.reply_text("Ваш вес в килограммах:")
        return WEIGHT
    elif step == WEIGHT:
        context.user_data['tmp_weight'] = float(re.search(r'\d+', text).group())
        context.user_data['reg_step'] = HEIGHT
        await update.message.reply_text("Ваш рост в сантиметрах:")
        return HEIGHT
    elif step == HEIGHT:
        context.user_data['tmp_height'] = float(re.search(r'\d+', text).group())
        context.user_data['reg_step'] = DISEASES
        await update.message.reply_text("Есть ли хронические заболевания? Если нет, напишите 'Нет'.")
        return DISEASES

async def finalize_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    diseases = update.message.text
    ud = context.user_data
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?)", 
                     (uid, ud['tmp_gender'], ud['tmp_age'], ud['tmp_weight'], ud['tmp_height'], diseases))
    
    await update.message.reply_text("✅ Цифровая медкарта успешно создана. Теперь я готов к работе!", reply_markup=get_main_kb())
    return CHAT_MODE

async def handle_medical_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user_data(update.effective_user.id)
    msg = update.message.text

    if not user: return await start(update, context)

    if msg == '📂 Моя медкарта':
        info = f"📊 *Ваш профиль:*\nПол: {user['gender']}\nВозраст: {user['age']}\nВес: {user['weight']} кг\nРост: {user['height']} см\nАнамнез: {user['diseases']}"
        await update.message.reply_text(info, parse_mode='Markdown')
        return CHAT_MODE

    if msg == '🆘 Экстренная помощь':
        await update.message.reply_text("🚨 Срочно вызывайте помощь: 103 или 112!")
        return CHAT_MODE

    await update.message.reply_chat_action(constants.ChatAction.TYPING)
    response = await doctor_ai.get_answer(user, msg)
    await update.message.reply_text(response, parse_mode='Markdown')
    return CHAT_MODE

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user_data(update.effective_user.id)
    if not user: return
    
    await update.message.reply_text("🩺 Анализирую изображение (анализы/документы)... Пожалуйста, подождите.")
    photo_file = await update.message.photo[-1].get_file()
    img = Image.open(io.BytesIO(await photo_file.download_as_bytearray()))
    
    response = await doctor_ai.get_answer(user, "Проанализируй приложенное медицинское фото.", img)
    await update.message.reply_text(response, parse_mode='Markdown')

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(filters.ALL, start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_registration)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_registration)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_registration)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_registration)],
            DISEASES: [MessageHandler(filters.TEXT & ~filters.COMMAND, finalize_registration)],
            CHAT_MODE: [
                MessageHandler(filters.PHOTO, handle_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_medical_chat)
            ],
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True
    )
    
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == '__main__':
    main()
