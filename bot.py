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

# --- ГЛУБОКОЕ ЛОГИРОВАНИЕ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("HealthMaster")

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DB_PATH = "health_v3_core.db"

GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT_MODE = range(6)

# --- ИНИЦИАЛИЗАЦИЯ ИИ (СНЯТИЕ БЛОКИРОВОК) ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Отключаем все фильтры, чтобы Gemini не блокировал медицинские советы
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

class MedicalAI:
    def __init__(self):
        self.model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            safety_settings=SAFETY_SETTINGS,
            system_instruction=(
                "Ты — элитный врач-терапевт. Твоя задача: анализировать состояние пациента, "
                "учитывая его пол, возраст, вес и историю болезней. Давай развернутые рекомендации. "
                "Если присылают фото анализов — расшифровывай их максимально подробно."
            )
        )

    async def generate_response(self, profile, message, image=None):
        try:
            # Формируем глубокий контекст для ИИ
            full_prompt = (
                f"ПАЦИЕНТ: {profile['gender']}, {profile['age']} лет, {profile['weight']}кг, {profile['height']}см.\n"
                f"АНАМНЕЗ: {profile['diseases']}\n\n"
                f"ВОПРОС: {message}"
            )
            content = [full_prompt, image] if image else full_prompt
            response = await asyncio.to_thread(self.model.generate_content, content)
            return response.text
        except Exception as e:
            logger.error(f"AI ERROR: {e}")
            return "⚠️ Произошла ошибка при анализе данных. Попробуйте переформулировать запрос."

ai_engine = MedicalAI()

# --- ЯДРО БАЗЫ ДАННЫХ ---
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
            (id INTEGER PRIMARY KEY, gender TEXT, age INTEGER, weight REAL, height REAL, diseases TEXT)''')
        conn.commit()

def get_user(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

# --- ЛОГИКА БОТА ---
def main_menu():
    return ReplyKeyboardMarkup([['🧬 Консультация', '📋 Моя медкарта'], ['🆘 SOS']], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user:
        await update.message.reply_text("👋 Доктор готов к работе. Что вас беспокоит?", reply_markup=main_menu())
        return CHAT_MODE
    
    await update.message.reply_text(
        "Здравствуйте! Я — ваш продвинутый медицинский ИИ-ассистент.\n"
        "Чтобы мои советы были точными, давайте заполним вашу карту. Ваш пол?",
        reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True)
    )
    return GENDER

async def collect_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    state = context.user_data.get('step', GENDER)

    if state == GENDER:
        context.user_data['gender'] = text
        await update.message.reply_text("Укажите ваш возраст:")
        context.user_data['step'] = AGE
        return AGE
    elif state == AGE:
        context.user_data['age'] = int(re.search(r'\d+', text).group())
        await update.message.reply_text("Ваш текущий вес (кг):")
        context.user_data['step'] = WEIGHT
        return WEIGHT
    elif state == WEIGHT:
        context.user_data['weight'] = float(re.search(r'\d+', text).group())
        await update.message.reply_text("Ваш рост (см):")
        context.user_data['step'] = HEIGHT
        return HEIGHT
    elif state == HEIGHT:
        context.user_data['height'] = float(re.search(r'\d+', text).group())
        await update.message.reply_text("Есть ли хронические заболевания? (или 'Нет')")
        context.user_data['step'] = DISEASES
        return DISEASES

async def save_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    d = update.message.text
    ud = context.user_data
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?)", 
                     (user_id, ud['gender'], ud['age'], ud['weight'], ud['height'], d))
    
    await update.message.reply_text("✅ Карта сохранена! Теперь вы в надежных руках.", reply_markup=main_menu())
    return CHAT_MODE

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    text = update.message.text

    if not user: return await start(update, context)

    if text == '📋 Моя медкарта':
        await update.message.reply_text(f"📊 Ваш профиль: {user[1]}, {user[2]}л, {user[3]}кг, {user[4]}см. Болезни: {user[5]}")
        return CHAT_MODE
    
    if text == '🆘 SOS':
        await update.message.reply_text("🚨 Срочно вызывайте скорую: 103 или 112!")
        return CHAT_MODE

    await update.message.reply_chat_action(constants.ChatAction.TYPING)
    
    profile = {"gender": user[1], "age": user[2], "weight": user[3], "height": user[4], "diseases": user[5]}
    response = await ai_engine.generate_response(profile, text)
    
    await update.message.reply_text(response, parse_mode='Markdown')
    return CHAT_MODE

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user: return
    
    await update.message.reply_text("🧪 Анализирую изображение... Секунду.")
    photo = await update.message.photo[-1].get_file()
    img = Image.open(io.BytesIO(await photo.download_as_bytearray()))
    
    profile = {"gender": user[1], "age": user[2], "weight": user[3], "height": user[4], "diseases": user[5]}
    response = await ai_engine.generate_response(profile, "Проанализируй этот медицинский документ.", img)
    await update.message.reply_text(response, parse_mode='Markdown')

def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(filters.ALL, start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_data)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_data)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_data)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_data)],
            DISEASES: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_profile)],
            CHAT_MODE: [
                MessageHandler(filters.PHOTO, handle_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, chat)
            ],
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True
    )
    
    app.add_handler(conv)
    app.run_polling()

if __name__ == '__main__':
    main()
