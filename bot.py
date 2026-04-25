import os, logging, sqlite3, asyncio
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Логи для отладки в Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка ИИ
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

DB_PATH = "/tmp/health.db" # Используем временную папку Railway для записи

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, info TEXT)')

def get_user(uid):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT info FROM users WHERE id=?", (uid,)).fetchone()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    uid = update.effective_user.id
    if get_user(uid):
        await update.message.reply_text("✅ Карта активна. Какой у вас медицинский вопрос?")
        return
    
    # Если пользователя нет, начинаем сбор данных (упрощенно, чтобы не зациклило)
    context.user_data['step'] = 'collect'
    await update.message.reply_text("Добро пожаловать! Напишите ваш пол, возраст и вес одним сообщением:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    
    # Логика регистрации
    if context.user_data.get('step') == 'collect':
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO users (id, info) VALUES (?, ?)", (uid, text))
        context.user_data['step'] = None
        await update.message.reply_text("✅ Данные сохранены! Теперь задавайте вопросы.")
        return

    # Логика консультации
    user_info = get_user(uid)
    if not user_info:
        await start(update, context)
        return

    await update.message.reply_chat_action(constants.ChatAction.TYPING)
    try:
        full_prompt = f"Пациент: {user_info[0]}. Вопрос: {text}. Ответь как врач."
        response = await asyncio.to_thread(model.generate_content, full_prompt)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"AI Error: {e}")
        await update.message.reply_text("🩺 Ошибка связи с ИИ. Попробуйте кратко повторить вопрос.")

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()
