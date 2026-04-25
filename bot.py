import os
import sqlite3
import logging
import sys
import asyncio
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# --- Настройки ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

DB_PATH = "/tmp/medical_bot.db"
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_KEY)

# Состояния
GENDER, AGE, WEIGHT, HEIGHT, ILLNESSES, CHAT = range(6)

# --- Системная инструкция (делает ИИ умным) ---
SYSTEM_PROMPT = (
    "Ты — продвинутый медицинский ИИ-эксперт. Твои ответы должны быть глубокими, "
    "профессиональными и на русском языке. Всегда учитывай данные пациента (пол, возраст, вес), "
    "которые передаются тебе в контексте. Если прислано фото, делай подробный медицинский разбор. "
    "В конце пиши: 'Данная информация носит справочный характер. Требуется консультация врача'."
)

# --- База данных ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
        (id INTEGER PRIMARY KEY, gender TEXT, age TEXT, weight TEXT, height TEXT, ill TEXT)''')
    conn.commit()
    conn.close()

def get_user_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if res:
        return f"Пациент: {res[1]}, возраст {res[2]}, вес {res[3]}кг, рост {res[4]}см. Хронические болезни: {res[5]}."
    return "Данные анкеты отсутствуют."

# --- Логика ИИ ---
async def ask_gemini(user_id, message_text, photo_bytes=None):
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash", # Бесплатная и быстрая
        system_instruction=SYSTEM_PROMPT
    )
    
    user_context = get_user_info(user_id)
    full_query = f"КОНТЕКСТ: {user_context}\n\nВОПРОС: {message_text}"
    
    content = [full_query]
    if photo_bytes:
        content.append({"mime_type": "image/jpeg", "data": photo_bytes})
    
    try:
        response = await model.generate_content_async(content)
        return response.text
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        return "⚠️ Произошла ошибка при обращении к ИИ."

# --- Обработчики анкеты ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здравствуйте! Я ваш медицинский ИИ. Начнем с анкеты. Ваш пол (М/Ж)?")
    return GENDER

async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['g'] = update.message.text
    await update.message.reply_text("Ваш возраст?")
    return AGE

async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a'] = update.message.text
    await update.message.reply_text("Ваш вес?")
    return WEIGHT

async def set_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['w'] = update.message.text
    await update.message.reply_text("Ваш рост?")
    return HEIGHT

async def set_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['h'] = update.message.text
    await update.message.reply_text("Хронические болезни (или 'Нет')?")
    return ILLNESSES

async def save_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?)", 
                 (update.effective_user.id, ud['g'], ud['a'], ud['w'], ud['h'], update.message.text))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Анкета сохранена! Теперь вы можете просто писать мне вопросы или присылать фото анализов.")
    return CHAT

# --- Основной Чат ---
async def main_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    photo_bytes = None
    text = update.message.text or update.message.caption or "Проанализируй это фото"
    
    if update.message.photo:
        await update.message.reply_text("🔬 Изучаю изображение...")
        file = await update.message.photo[-1].get_file()
        photo_bytes = bytes(await file.download_as_bytearray())
    else:
        await update.message.reply_chat_action("typing")

    response = await ask_gemini(user_id, text, photo_bytes)
    await update.message.reply_text(response, parse_mode='Markdown')
    return CHAT

# --- Запуск ---
def main():
    init_db()
    if not TOKEN: return

    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_height)],
            ILLNESSES: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_profile)],
            CHAT: [MessageHandler(filters.TEXT | filters.PHOTO, main_chat)],
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    app.add_handler(conv)
    print("--- БОТ ВКЛЮЧЕН ---", flush=True)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
