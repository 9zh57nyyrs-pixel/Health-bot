import os
import sqlite3
import logging
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# Настройка логов, чтобы ты видел ошибки в панели Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
API_KEY = os.environ.get("GEMINI_API_KEY")
# ВАЖНО: Только папка /tmp/ разрешена для записи в Railway!
DB_PATH = "/tmp/users_medical_data.db" 

# Инициализация ИИ
def setup_ai():
    try:
        genai.configure(api_key=API_KEY)
        # Опрашиваем доступные модели, чтобы не было ошибки 404
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        name = 'models/gemini-1.5-flash' if 'models/gemini-1.5-flash' in models else models[0]
        logger.info(f"Используем модель: {name}")
        return genai.GenerativeModel(name)
    except Exception as e:
        logger.error(f"Критическая ошибка ИИ: {e}")
        return None

model = setup_ai()

# --- БАЗА ДАННЫХ ---
def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, info TEXT)")
        conn.close()
        logger.info("База данных готова.")
    except Exception as e:
        logger.error(f"Ошибка БД: {e}")

def get_user_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT info FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return res[0] if res else None

# --- ОБРАБОТКА ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_text = update.message.text
    
    # Изоляция: достаем данные ТОЛЬКО этого пользователя
    profile = get_user_info(user_id)
    
    if not profile:
        instruction = (
            "Ты — медицинский ассистент. Это новый пользователь. "
            "САМОЕ ВАЖНОЕ: Не говори про внешние анкеты. Ты сам проводишь опрос. "
            "Спроси у него по очереди: пол, возраст, рост, вес и жалобы."
        )
    else:
        instruction = f"Ты — мед-ассистент. Данные этого пациента: {profile}. Отвечай, учитывая их."

    await update.message.reply_chat_action(ChatAction.TYPING)
    
    try:
        response = model.generate_content(f"{instruction}\n\nЮзер: {user_text}")
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        await update.message.reply_text("⚠️ ИИ временно недоступен, попробуйте через минуту.")

def main():
    if not TOKEN or not API_KEY:
        logger.error("Проверь переменные окружения в Railway!")
        return

    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен...")
    # Убираем drop_pending_updates, чтобы бот не «проглатывал» сообщения при старте
    app.run_polling()

if __name__ == '__main__':
    main()
