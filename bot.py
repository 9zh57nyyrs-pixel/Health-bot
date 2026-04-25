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
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler,
)

# --- ГЛУБОКОЕ ЛОГИРОВАНИЕ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- ГЛОБАЛЬНЫЕ НАСТРОЙКИ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DB_PATH = os.path.join(os.getcwd(), "medical_system_v2.db")

GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT_MODE = range(6)

# --- ПРОДВИНУТАЯ КОНФИГУРАЦИЯ ИИ ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Снимаем все ограничения, чтобы врач мог отвечать на любые вопросы
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

class MedicalAI:
    def __init__(self):
        self.model = None
        self.reinit_model()

    def reinit_model(self):
        # Перебор моделей от мощных к быстрым
        for m_name in ['gemini-1.5-pro-latest', 'gemini-1.5-flash-latest', 'gemini-pro']:
            try:
                self.model = genai.GenerativeModel(
                    model_name=m_name,
                    safety_settings=SAFETY_SETTINGS,
                    system_instruction=(
                        "Ты — высококвалифицированный врач-терапевт с 20-летним стажем. "
                        "Твоя задача: анализировать данные пациента (пол, возраст, вес) и давать "
                        "структурированные медицинские рекомендации. Будь профессионален, "
                        "используй медицинские термины, но объясняй их понятно."
                    )
                )
                logger.info(f"Инициализирована модель: {m_name}")
                break
            except Exception as e:
                logger.error(f"Ошибка инициализации {m_name}: {e}")

    async def ask(self, prompt, image=None):
        try:
            content = [prompt, image] if image else prompt
            response = await asyncio.to_thread(self.model.generate_content, content)
            return response.text
        except Exception as e:
            logger.error(f"Критическая ошибка Gemini: {e}")
            self.reinit_model() # Пробуем восстановить модель
            return "⚠️ Произошел технический сбой в нейросети. Пожалуйста, повторите запрос через 10 секунд."

ai_doctor = MedicalAI()

# --- ЯДРО БАЗЫ ДАННЫХ ---
class Database:
    def __init__(self, path):
        self.path = path
        self._create_table()

    def _create_table(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS patients 
                (id INTEGER PRIMARY KEY, gender TEXT, age INTEGER, 
                 weight REAL, height REAL, history TEXT, created_at TEXT)''')
            conn.commit()

    def save_patient(self, user_id, data):
        with sqlite3.connect(self.path) as conn:
            conn.execute('''INSERT OR REPLACE INTO patients VALUES (?, ?, ?, ?, ?, ?, ?)''',
                         (user_id, data['gender'], data['age'], data['weight'], 
                          data['height'], data['diseases'], datetime.now().isoformat()))
            conn.commit()

    def get_patient(self, user_id):
        with sqlite3.connect(self.path) as conn:
            return conn.execute("SELECT * FROM patients WHERE id=?", (user_id,)).fetchone()

db = Database(DB_PATH)

# --- ИНТЕРФЕЙС И ЛОГИКА ---
def get_main_kb():
    return ReplyKeyboardMarkup([['🧬 Новая консультация', '📋 Моя карта'], ['🆘 SOS']], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_patient(update.effective_user.id)
    if user:
        await update.message.reply_text(
            f"С возвращением! Я ознакомился с вашей картой. Что вас беспокоит сегодня?",
            reply_markup=get_main_kb()
        )
        return CHAT_MODE
    
    await update.message.reply_text(
        "Здравствуйте. Я ваш персональный медицинский эксперт. Для точности рекомендаций "
        "мне необходимо завести вашу медицинскую карту. Укажите ваш пол:",
        reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True)
    )
    return GENDER

async def collect_step(update: Update, context: ContextTypes.DEFAULT_TYPE, next_state, msg, key):
    raw_text = update.message.text
    context.user_data[key] = raw_text
    await update.message.reply_text(msg)
    return next_state

# Промежуточные шаги с валидацией
async def c_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nums = re.findall(r'\d+', update.message.text)
    if not nums: 
        await update.message.reply_text("Пожалуйста, введите возраст цифрами.")
        return AGE
    context.user_data['age'] = int(nums[0])
    await update.message.reply_text("Ваш текущий вес в килограммах?")
    return WEIGHT

async def c_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nums = re.findall(r'\d+', update.message.text)
    if not nums: return WEIGHT
    context.user_data['weight'] = float(nums[0])
    await update.message.reply_text("Ваш рост в сантиметрах?")
    return HEIGHT

async def c_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nums = re.findall(r'\d+', update.message.text)
    if not nums: return HEIGHT
    context.user_data['height'] = float(nums[0])
    await update.message.reply_text("Перечислите хронические заболевания или напишите 'Нет':")
    return DISEASES

async def c_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['diseases'] = update.message.text
    db.save_patient(update.effective_user.id, context.user_data)
    await update.message.reply_text(
        "✅ Медицинская карта сформирована. Теперь я учитываю ваши особенности при каждом ответе.",
        reply_markup=get_main_kb()
    )
    return CHAT_MODE

async def doctor_consult(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = db.get_patient(update.effective_user.id)
    
    if not user: return await start(update, context)

    if text == '📋 Моя карта':
        await update.message.reply_text(f"📊 Данные: {user[1]}, {user[2]} лет, {user[3]}кг, {user[4]}см. Анамнез: {user[5]}")
        return CHAT_MODE
    
    if text == '🆘 SOS':
        await update.message.reply_text("🚨 Срочно свяжитесь со службой спасения: 103 или 112!")
        return CHAT_MODE

    await update.message.reply_chat_action("typing")
    
    prompt = (
        f"КОНТЕКСТ ПАЦИЕНТА: Пол {user[1]}, Возраст {user[2]}, Вес {user[3]}кг, Рост {user[4]}см, "
        f"Хронические болезни: {user[5]}. ЗАПРОС: {text}"
    )
    
    answer = await ai_doctor.ask(prompt)
    await update.message.reply_text(answer, parse_mode='Markdown')
    return CHAT_MODE

async def photo_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_patient(update.effective_user.id)
    await update.message.reply_text("🔄 Обработка медицинского изображения... Пожалуйста, подождите.")
    
    file = await update.message.photo[-1].get_file()
    img_byte = await file.download_as_bytearray()
    img = Image.open(io.BytesIO(img_byte))
    
    prompt = f"Пациент ({user[2]} лет). Проведи визуальный анализ медицинского документа или симптома на фото."
    answer = await ai_doctor.ask(prompt, img)
    await update.message.reply_text(answer, parse_mode='Markdown')

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), MessageHandler(filters.ALL, start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: collect_step(u, c, AGE, "Сколько вам полных лет?", "gender"))],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, c_age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, c_weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, c_height)],
            DISEASES: [MessageHandler(filters.TEXT & ~filters.COMMAND, c_final)],
            CHAT_MODE: [
                MessageHandler(filters.PHOTO, photo_analysis),
                MessageHandler(filters.TEXT & ~filters.COMMAND, doctor_consult)
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    logger.info("Бот запущен и готов к работе.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
