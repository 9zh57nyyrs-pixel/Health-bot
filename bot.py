import os, logging, sqlite3, asyncio
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

# Путь для базы данных (используем /tmp для стабильности на Railway)
DB_PATH = "/tmp/medical_v6.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, profile TEXT)')

def get_user_profile(uid):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT profile FROM users WHERE id=?", (uid,)).fetchone()
        return res[0] if res else None

# Главное меню
MAIN_KBD = ReplyKeyboardMarkup([
    ['🩺 Задать вопрос', '📋 Моя карта'],
    ['🆘 SOS (103/112)', '⚙️ Сбросить данные']
], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    uid = update.effective_user.id
    profile = get_user_profile(uid)
    
    if profile:
        await update.message.reply_text("✅ Вы в главном меню ассистента.", reply_markup=MAIN_KBD)
    else:
        await update.message.reply_text(
            "Здравствуйте! Чтобы я мог давать точные советы, введите через запятую: "
            "Пол, Возраст, Вес, Хронические заболевания.\n\n"
            "Пример: Мужчина, 40 лет, 90 кг, гипертония."
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    profile = get_user_profile(uid)

    # 1. Регистрация, если профиля нет
    if not profile:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO users (id, profile) VALUES (?, ?)", (uid, text))
        await update.message.reply_text("✅ Данные сохранены! Пользуйтесь меню:", reply_markup=MAIN_KBD)
        return

    # 2. Обработка кнопок меню
    if text == '📋 Моя карта':
        await update.message.reply_text(f"📊 Ваши данные:\n{profile}", reply_markup=MAIN_KBD)
        return
    
    if text == '🆘 SOS (103/112)':
        await update.message.reply_text("🚨 Срочно звоните 103 или 112!", reply_markup=MAIN_KBD)
        return

    if text == '⚙️ Сбросить данные':
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM users WHERE id=?", (uid,))
        await update.message.reply_text("🗑 Данные удалены. Нажмите /start для новой записи.")
        return

    # 3. Консультация через ИИ
    await update.message.reply_chat_action(constants.ChatAction.TYPING)
    try:
        prompt = f"Контекст: {profile}. Вопрос пациента: {text}. Ответь как врач."
        response = await asyncio.to_thread(model.generate_content, prompt)
        await update.message.reply_text(response.text, parse_mode='Markdown', reply_markup=MAIN_KBD)
    except Exception as e:
        logger.error(f"AI Error: {e}")
        await update.message.reply_text("❌ Ошибка связи. Попробуйте через минуту (возможно, лимит запросов).")

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()
