import os
import sys
import sqlite3
import logging
import google.generativeai as genai
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Логирование
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DB_PATH = "/tmp/medical_bot.db"

# 1. Поиск работающей модели (чтобы не было 404)
def get_ai_model():
    try:
        genai.configure(api_key=GEMINI_KEY)
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        name = 'models/gemini-1.5-flash' if 'models/gemini-1.5-flash' in models else models[0]
        return genai.GenerativeModel(name)
    except Exception as e:
        print(f"Ошибка ИИ: {e}")
        return None

model = get_ai_model()

# 2. Получение данных из анкеты
def get_user_data(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        if res:
            # Превращаем данные в понятный для ИИ текст
            return f"Пациент: пол {res[1]}, возраст {res[2]}, вес {res[3]}кг, рост {res[4]}см. Хронические болезни: {res[5]}."
    except Exception as e:
        logger.error(f"Ошибка БД: {e}")
    return "Данные анкеты отсутствуют. Попроси пользователя их предоставить."

# 3. Отправка длинных сообщений (чтобы не было "Message is too long")
async def send_response(update, text):
    if len(text) <= 4000:
        try:
            await update.message.reply_text(text, parse_mode='Markdown')
        except:
            await update.message.reply_text(text)
    else:
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Связь установлена. Я вижу твою анкету и готов давать рекомендации.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not model:
        await update.message.reply_text("❌ Ошибка ИИ.")
        return

    user_id = update.effective_user.id
    user_info = get_user_data(user_id)
    
    # ФОРМИРУЕМ ПРОВЕРЕННЫЙ ПРОМПТ
    prompt = (
        f"ИНСТРУКЦИЯ: Ты — профессиональный медицинский ассистент. "
        f"Твои ответы должны основываться НА ДАННЫХ ПАЦИЕНТА ниже.\n\n"
        f"ДАННЫЕ ИЗ АНКЕТЫ: {user_info}\n\n"
        f"ВОПРОС ПОЛЬЗОВАТЕЛЯ: {update.message.text}\n\n"
        f"ОТВЕТ: Дай конкретные рекомендации. Не пиши общих фраз о том, что ты ничего не знаешь."
    )

    await update.message.reply_chat_action(ChatAction.TYPING)
    try:
        response = model.generate_content(prompt)
        await send_response(update, response.text)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {str(e)}")

def main():
    # Создаем таблицу, если её нет
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, gender TEXT, age TEXT, weight TEXT, height TEXT, ill TEXT)")
    conn.close()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
