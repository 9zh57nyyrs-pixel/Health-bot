import os
import sys
import sqlite3
import logging
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Логирование
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DB_PATH = "/tmp/medical_bot.db"

# Настройка ИИ (автоматический выбор модели)
def get_ai_model():
    try:
        genai.configure(api_key=GEMINI_KEY)
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Выбираем 1.5 Flash если есть, иначе первую доступную
        name = 'models/gemini-1.5-flash' if 'models/gemini-1.5-flash' in models else models[0]
        return genai.GenerativeModel(name)
    except:
        return None

model = get_ai_model()

# --- Работа с данными пользователя ---
def get_user_data(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        if res:
            return f"Пациент: пол {res[1]}, возраст {res[2]}, вес {res[3]}, рост {res[4]}. Болезни: {res[5]}."
    except: pass
    return "Данные о пользователе еще не внесены."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я готов. Твои данные из анкеты будут учитываться при каждом ответе.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    
    # Извлекаем данные из базы
    context_info = get_user_data(user_id)
    
    # Формируем «прокачанный» запрос для ИИ
    full_prompt = (
        f"Ты — персональный медицинский консультант. Твои знания основаны на данных этого пользователя.\n"
        f"ДАННЫЕ ПОЛЬЗОВАТЕЛЯ: {context_info}\n\n"
        f"ВОПРОС ПОЛЬЗОВАТЕЛЯ: {user_text}\n\n"
        f"Дай персонализированную рекомендацию. Если данных не хватает, скажи каких именно."
    )

    await update.message.reply_chat_action("typing")
    try:
        response = model.generate_content(full_prompt)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка связи с ИИ: {e}")

def main():
    # Создаем таблицу если её нет
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, gender TEXT, age TEXT, weight TEXT, height TEXT, ill TEXT)")
    conn.close()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
