import os
import sys
import sqlite3
import logging
import google.generativeai as genai
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- НАСТРОЙКИ ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DB_PATH = "/tmp/medical_bot.db"

# Инициализация ИИ
genai.configure(api_key=GEMINI_KEY)
# Используем flash для скорости или pro для точности
model = genai.GenerativeModel('gemini-1.5-flash') 

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                    (id INTEGER PRIMARY KEY, gender TEXT, age TEXT, 
                     history TEXT, meds TEXT, allergies TEXT)''')
    conn.close()

def save_user(uid, gender, age, history, meds, allergies):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?)", 
                 (uid, gender, age, history, meds, allergies))
    conn.commit()
    conn.close()

def get_user(uid):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    if res:
        return f"Пациент: {res[1]}, {res[2]} лет. Анамнез: {res[3]}. Лекарства: {res[4]}. Аллергии: {res[5]}."
    return None

# --- ЛОГИКА БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Здравствуйте! Я ваш медицинский ассистент.\n\n"
        "Чтобы я мог давать точные рекомендации, заполните анкету командой:\n"
        "/anketa [Пол] [Возраст] [Болезни] [Лекарства] [Аллергии]\n\n"
        "Пример:\n/anketa Муж 35 Гастрит Омез Нет"
    )

async def set_anketa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Упрощенный парсинг для примера
        args = context.args
        if len(args) < 5:
            await update.message.reply_text("Ошибка! Введите: /anketa Пол Возраст Болезни Лекарства Аллергии")
            return
        
        save_user(update.effective_user.id, args[0], args[1], args[2], args[3], args[4])
        await update.message.reply_text("✅ Данные сохранены! Теперь можете задавать вопросы.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка сохранения: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    user_query = update.message.text

    # Формируем инструкцию для ИИ
    system_prompt = (
        "Ты — высококвалифицированный медицинский ассистент. Твоя задача — помогать пользователю анализировать симптомы "
        "и давать рекомендации по следующим шагам (к какому врачу пойти, какие уточняющие вопросы себе задать).\n"
        "ВАЖНО: Всегда добавляй дисклеймер, что ты не заменяешь врача.\n\n"
    )
    
    if user_data:
        full_prompt = f"{system_prompt} КОНТЕКСТ ПАЦИЕНТА: {user_data}\n\n ВОПРОС: {user_query}"
    else:
        full_prompt = f"{system_prompt} (Данных о пациенте нет, попроси его заполнить анкету если это важно).\n\n ВОПРОС: {user_query}"

    await update.message.reply_chat_action(ChatAction.TYPING)
    
    try:
        response = model.generate_content(full_prompt)
        # Если ответ слишком длинный, режем его (защита от ошибки Message too long)
        text = response.text
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000])
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка ИИ: {e}")

# --- ЗАПУСК ---
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("anketa", set_anketa))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()
