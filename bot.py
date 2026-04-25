import os
import sys
import sqlite3
import logging
import google.generativeai as genai
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логов
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DB_PATH = "/tmp/medical_bot.db"

# Инициализация ИИ
def get_ai_model():
    try:
        genai.configure(api_key=GEMINI_KEY)
        # Автоподбор доступной модели
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        name = 'models/gemini-1.5-flash' if 'models/gemini-1.5-flash' in available else available[0]
        return genai.GenerativeModel(name)
    except Exception as e:
        print(f"Ошибка ИИ при старте: {e}")
        return None

model = get_ai_model()

def get_user_data(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        if res:
            return f"Пациент: пол {res[1]}, возраст {res[2]}, вес {res[3]}, рост {res[4]}. Болезни: {res[5]}."
    except: pass
    return "Данные анкеты не найдены."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот запущен. Я учитываю данные из твоей анкеты.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not model:
        await update.message.reply_text("❌ Ошибка: ИИ не настроен.")
        return

    user_id = update.effective_user.id
    user_text = update.message.text
    context_info = get_user_data(user_id)
    
    prompt = (
        f"Ты — медицинский эксперт. Используй данные ниже для ответа.\n"
        f"ДАННЫЕ ПАЦИЕНТА: {context_info}\n"
        f"ВОПРОС: {user_text}\n"
        f"Отвечай структурированно."
    )

    await update.message.reply_chat_action(ChatAction.TYPING)
    
    try:
        response = model.generate_content(prompt)
        text = response.text
        
        try:
            # Пытаемся отправить красиво с Markdown
            await update.message.reply_text(text, parse_mode='Markdown')
        except Exception:
            # Если Telegram ругается на символы (твоя ошибка 404/parse), шлем обычным текстом
            await update.message.reply_text(text)
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"⚠️ Ошибка ИИ: {str(e)}")

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, gender TEXT, age TEXT, weight TEXT, height TEXT, ill TEXT)")
    conn.close()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("--- БОТ ВКЛЮЧЕН ---", flush=True)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
