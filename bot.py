import os, sqlite3, asyncio, logging
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
# Настройка ИИ
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

DB_PATH = "/tmp/health_final.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, profile TEXT)')

def get_user(uid):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT profile FROM users WHERE id=?", (uid,)).fetchone()

# Удобное меню
KBD = ReplyKeyboardMarkup([['📋 Моя карта', '🩺 Вопрос']], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    uid = update.effective_user.id
    if get_user(uid):
        await update.message.reply_text("✅ Бот готов. Нажмите кнопку или задайте вопрос.", reply_markup=KBD)
    else:
        await update.message.reply_text("Введите: Пол, Возраст, Вес, Болезни (через запятую).")

async def main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    profile = get_user(uid)

    if not profile:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO users VALUES (?, ?)", (uid, text))
        await update.message.reply_text("✅ Сохранено! Спрашивайте.", reply_markup=KBD)
        return

    if text == '📋 Моя карта':
        await update.message.reply_text(f"📊 Ваш профиль: {profile[0]}")
        return

    # Запрос к ИИ
    await update.message.reply_chat_action(constants.ChatAction.TYPING)
    try:
        # Укорачиваем промпт для экономии ресурсов
        resp = await asyncio.to_thread(model.generate_content, f"User:{profile[0]}. Question:{text}")
        await update.message.reply_text(resp.text, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text("⏳ Лимит запросов. Подождите 5 минут.")

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_handler))
    app.run_polling()

if __name__ == '__main__':
    main()
