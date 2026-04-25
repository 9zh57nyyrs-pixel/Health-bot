import os
import sqlite3
import logging
import sys
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# --- Настройки логов ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# --- Конфигурация ИИ ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_KEY)

# Путь к БД для хранения анкет (чтобы ИИ знал, с кем говорит)
DB_PATH = "/tmp/medical_bot.db"

# --- Глубокая инструкция (Системный промпт) ---
SYSTEM_PROMPT = (
    "Ты — продвинутый медицинский ИИ, интегрированный в Telegram. "
    "Твоя задача: вести живой, интеллектуальный диалог. "
    "1. Ты НЕ шаблонный бот. Ты анализируешь каждое слово пользователя. "
    "2. Используй данные из анкеты пользователя (возраст, вес, болезни) для уточнения диагноза. "
    "3. Если тебе присылают фото, ты проводишь глубокий визуальный анализ. "
    "4. Твой стиль: профессиональный, эмпатичный, подробный. "
    "5. Если данных мало — задавай уточняющие вопросы, как реальный врач на приеме."
)

# --- Функции контекста ---
def get_user_profile(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        if res:
            return f"Пациент: {res[1]}, {res[2]} лет, вес {res[3]}кг. Хронические заболевания: {res[5]}."
    except: pass
    return "Профиль пациента еще не заполнен."

# --- Главный мозг бота ---
async def ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text or update.message.caption or "Проанализируй это"
    
    # Инициализируем историю чата в памяти бота (чтобы он не забывал начало разговора)
    if 'chat_session' not in context.user_data:
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM_PROMPT
        )
        # Создаем сессию с историей
        context.user_data['chat_session'] = model.start_chat(history=[])
        # Добавляем данные профиля в начало разговора первым скрытым сообщением
        profile = get_user_profile(user_id)
        await context.user_data['chat_session'].send_message_async(f"СИСТЕМНАЯ СВОДКА О ПАЦИЕНТЕ: {profile}")

    # Обработка фото
    img_data = None
    if update.message.photo:
        await update.message.reply_chat_action("upload_photo")
        file = await update.message.photo[-1].get_file()
        img_bytes = await file.download_as_bytearray()
        img_data = {"mime_type": "image/jpeg", "data": bytes(img_bytes)}

    # Отправка запроса в ИИ
    await update.message.reply_chat_action("typing")
    try:
        if img_data:
            response = await context.user_data['chat_session'].send_message_async([user_text, img_data])
        else:
            response = await context.user_data['chat_session'].send_message_async(user_text)
        
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка ИИ: {e}")
        await update.message.reply_text("🧬 ИИ обрабатывает запрос слишком долго. Попробуйте еще раз.")

# --- Вспомогательные команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Сбрасываем историю при команде /start
    context.user_data.clear()
    await update.message.reply_text("Привет! Я твой персональный ИИ-врач. Я помню историю нашего общения. Опиши свою проблему или пришли фото.")

def main():
    # Создаем таблицу профилей, если её нет
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, gender TEXT, age TEXT, weight TEXT, height TEXT, ill TEXT)")
    conn.close()

    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    # Бот реагирует на ВСЁ: текст и фото, без жестких сценариев
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, ai_chat))
    
    print("--- ИНТЕГРИРОВАННЫЙ ИИ ЗАПУЩЕН ---", flush=True)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
