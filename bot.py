import os
import logging
import psycopg2
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

# --- ГЛУБОКИЙ МОНИТОРИНГ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MedicalEliteBot")

# --- КОНФИГУРАЦИЯ СИСТЕМЫ ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
AI_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL") # Railway подставит это сам

GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT_MODE = range(6)

# --- ПРОДВИНУТЫЙ ИИ (ВРАЧ-ТЕРАПЕВТ) ---
if AI_KEY:
    genai.configure(api_key=AI_KEY)

# Полное отключение фильтров для медицинских целей
AI_SAFETY = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

class EliteDoctorAI:
    def __init__(self):
        self.model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            safety_settings=AI_SAFETY,
            system_instruction=(
                "Ты — элитный цифровой врач-терапевт. Твоя база знаний включает все современные протоколы лечения. "
                "Ты анализируешь пол, возраст, вес и анамнез пациента. Твои ответы должны быть глубокими, "
                "профессиональными и помогать человеку понять его состояние. Если прислали фото анализов — делай полный разбор."
            )
        )

    async def consult(self, profile, query, image=None):
        ctx = f"ПАЦИЕНТ: {profile['g']}, {profile['a']} лет, {profile['w']}кг, {profile['h']}см. БОЛЕЗНИ: {profile['d']}\nЗАПРОС: {query}"
        try:
            res = await asyncio.to_thread(self.model.generate_content, [ctx, image] if image else ctx)
            return res.text
        except Exception as e:
            logger.error(f"AI Crash: {e}")
            return "🩺 Мои нейронные связи временно перегружены. Пожалуйста, повторите вопрос короче."

doctor = EliteDoctorAI()

# --- СЛОЙ ВЕЧНОЙ ПАМЯТИ (POSTGRESQL) ---
def get_db_conn():
    # Если PostgreSQL нет, используем SQLite как запасной вариант
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    import sqlite3
    return sqlite3.connect("local_backup.db")

def init_db():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
        (id BIGINT PRIMARY KEY, gender TEXT, age INT, weight REAL, height REAL, diseases TEXT)''')
    conn.commit()
    cur.close()
    conn.close()

# --- ЛОГИКА ВЗАИМОДЕЙСТВИЯ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user:
        await update.message.reply_text(
            "👋 Рад вас видеть. Я изучил вашу медкарту. Какой медицинский вопрос вас беспокоит?",
            reply_markup=ReplyKeyboardMarkup([['📋 Моя карта', '🧬 Консультация'], ['🆘 SOS']], resize_keyboard=True)
        )
        return CHAT_MODE
    
    await update.message.reply_text(
        "Здравствуйте. Я ваш персональный медицинский эксперт.\nЧтобы рекомендации были точными, мне нужно создать ваш профиль. Ваш пол?",
        reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True)
    )
    return GENDER

async def collect_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    # Простая машина состояний через context.user_data
    if 'reg_data' not in context.user_data: context.user_data['reg_data'] = {}
    rd = context.user_data['reg_data']

    if 'gender' not in rd:
        rd['gender'] = txt
        await update.message.reply_text("Ваш возраст?")
        return AGE
    elif 'age' not in rd:
        rd['age'] = int(re.search(r'\d+', txt).group())
        await update.message.reply_text("Ваш вес (кг)?")
        return WEIGHT
    elif 'weight' not in rd:
        rd['weight'] = float(re.search(r'\d+', txt).group())
        await update.message.reply_text("Ваш рост (см)?")
        return HEIGHT
    elif 'height' not in rd:
        rd['height'] = float(re.search(r'\d+', txt).group())
        await update.message.reply_text("Перечислите хронические заболевания (или напишите 'Нет'):")
        return DISEASES

async def save_and_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    dis = update.message.text
    rd = context.user_data['reg_data']
    
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO users VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET diseases=%s",
                (uid, rd['gender'], rd['age'], rd['weight'], rd['height'], dis, dis))
    conn.commit()
    cur.close()
    conn.close()
    
    await update.message.reply_text("✅ Медкарта сохранена навсегда. Я готов к консультации.", 
                                   reply_markup=ReplyKeyboardMarkup([['📋 Моя карта', '🧬 Консультация'], ['🆘 SOS']], resize_keyboard=True))
    return CHAT_MODE

async def global_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message.text
    
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
    u = cur.fetchone()
    cur.close()
    conn.close()

    if not u: return await start(update, context)
    profile = {'g': u[1], 'a': u[2], 'w': u[3], 'h': u[4], 'd': u[5]}

    if msg == '📋 Моя карта':
        await update.message.reply_text(f"📊 Данные: {u[1]}, {u[2]}л, {u[3]}кг, {u[4]}см.\nБолезни: {u[5]}")
    elif msg == '🆘 SOS':
        await update.message.reply_text("🚨 Срочно звоните 103 или 112!")
    else:
        await update.message.reply_chat_action(constants.ChatAction.TYPING)
        ans = await doctor.consult(profile, msg)
        await update.message.reply_text(ans, parse_mode='Markdown')
    return CHAT_MODE

async def photo_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
    u = cur.fetchone()
    cur.close()
    conn.close()

    await update.message.reply_text("🔬 Врач изучает анализы...")
    photo = await update.message.photo[-1].get_file()
    img = Image.open(io.BytesIO(await photo.download_as_bytearray()))
    
    profile = {'g': u[1], 'a': u[2], 'w': u[3], 'h': u[4], 'd': u[5]}
    ans = await doctor.consult(profile, "Разбери анализы на фото.", img)
    await update.message.reply_text(ans, parse_mode='Markdown')

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(filters.ALL, start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_process)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_process)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_process)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_process)],
            DISEASES: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_and_finish)],
            CHAT_MODE: [
                MessageHandler(filters.PHOTO, photo_analysis),
                MessageHandler(filters.TEXT & ~filters.COMMAND, global_chat)
            ],
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    app.add_handler(conv)
    app.run_polling()

if __name__ == '__main__':
    main()
