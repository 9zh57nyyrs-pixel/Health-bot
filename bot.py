import os
import sqlite3
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройки
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DB_PATH = "/tmp/medical_bot.db"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Функции базы данных
def get_user_record(uid):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return res

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_text = update.message.text
    user_data = get_user_record(uid)

    # Формируем СТРОГУЮ инструкцию для ИИ
    if not user_data:
        # Если анкеты нет — режим сбора данных
        system_instruction = (
            "Ты — медицинский ассистент. У тебя НЕТ данных об этом пользователе. "
            "ТВОЯ ЗАДАЧА: Провести опрос. Не отправляй пользователя к ссылкам или в личный кабинет. "
            "Спрашивай по одному пункту за раз: сначала пол и возраст, потом рост и вес, потом жалобы. "
            "Если пользователь просто поздоровался или сказал 'готов', начни опрос с первого вопроса."
        )
    else:
        # Если анкета есть — режим консультации
        system_instruction = (
            f"Ты — медицинский ассистент. ДАННЫЕ ПАЦИЕНТА: {user_data}. "
            "Используй эти данные в ответах. Если пользователь хочет что-то изменить, обнови информацию."
        )

    prompt = f"{system_instruction}\n\nПользователь пишет: {user_text}"

    try:
        response = model.generate_content(prompt)
        await update.message.reply_text(response.text)
        
        # ЛОГИКА СОХРАНЕНИЯ (упрощенно)
        # Если ИИ в ответе подтвердил, что данные получены, можно добавить код записи в БД здесь
        # Но для начала достаточно, чтобы он просто начал спрашивать.
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

def main():
    # Создаем БД
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, info TEXT)")
    conn.close()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()
