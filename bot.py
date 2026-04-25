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

# Переменные
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DB_PATH = "/tmp/medical_bot.db"

# 1. ФУНКЦИЯ АВТОПОДБОРА МОДЕЛИ
def setup_ai():
    try:
        genai.configure(api_key=GEMINI_KEY)
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priority = ['models/gemini-1.5-flash', 'models/gemini-1.5-flash-latest', 'models/gemini-pro']
        for p in priority:
            if p in models:
                logger.info(f"Выбрана модель: {p}")
                return genai.GenerativeModel(p)
        return genai.GenerativeModel(models[0]) if models else None
    except Exception as e:
        logger.error(f"Ошибка ИИ: {e}")
        return None

ai_model = setup_ai()

# 2. РАБОТА С ДАННЫМИ (БЕЗОПАСНАЯ)
def get_context(uid):
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        if res:
            return f"Данные пациента: пол {res[1]}, возраст {res[2]}, болезни: {res[3]}, лекарства: {res[4]}."
    except: pass
    return "ДАННЫЕ АНКЕТЫ ОТСУТСТВУЮТ."

async def save_anketa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Команда /anketa остается для ручного ввода: /anketa Муж 30 Гастрит Омез
    u = update.effective_user.id
    d = context.args
    if len(d) < 4:
        await update.message.reply_text("Используй: /anketa Пол Возраст Болезни Лекарства")
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?)", (u, d[0], d[1], d[2], d[3], "Нет"))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Анкета сохранена!")

# 3. ОБРАБОТКА ТЕКСТА И ФОТО + АВТО-ОПРОС
async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ai_model:
        await update.message.reply_text("ИИ не инициализирован.")
        return

    uid = update.effective_user.id
    user_context = get_context(uid)
    
    # Промпт, который заставляет ИИ проводить опрос
    if "Данные анкеты отсутствуют" in user_context:
        instruction = (
            "Ты — медицинский ассистент. Данных о пациенте нет. "
            "ТВОЯ ЗАДАЧА: Проведи опрос прямо сейчас. Спроси пол и возраст. "
            "Не пиши общих фраз, не предлагай искать анкету. Просто задай вопрос."
        )
    else:
        instruction = f"Ты — мед-ассистент. Контекст пациента: {user_context}"

    content = [
        f"УСТАНОВКА: {instruction}\n",
        f"СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ: {update.message.text or update.message.caption or 'Проанализируй'}"
    ]
    
    # ЖЕСТКАЯ ИНСТРУКЦИЯ ДЛЯ ИИ
    if user_context == "ДАННЫЕ АНКЕТЫ ОТСУТСТВУЮТ.":
        instruction = (
            "Ты — персональный медицинский ассистент. У тебя НЕТ данных о пациенте.\n"
            "ТВОЯ ЗАДАЧА: Проведи опрос прямо в чате. Спрашивай по одному пункту: "
            "1. Пол и возраст. 2. Рост и вес. 3. Хронические заболевания. 4. Лекарства.\n"
            "ЗАПРЕЩЕНО говорить про личные кабинеты или ссылки. Ты сам — анкета."
        )
    else:
        instruction = f"Ты — медицинский ассистент. Используй эти данные: {user_context}"

    content = [
        f"СИСТЕМНАЯ РОЛЬ: {instruction}\n",
        f"ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {update.message.text or update.message.caption or 'Проанализируй'}"
    ]

    # Добавляем фото, если есть
    if update.message.photo:
        await update.message.reply_chat_action(ChatAction.TYPING)
        file = await update.message.photo[-1].get_file()
        img_bytes = await file.download_as_bytearray()
        content.append({"mime_type": "image/jpeg", "data": bytes(img_bytes)})

    await update.message.reply_chat_action(ChatAction.TYPING)
    try:
        response = ai_model.generate_content(content)
        text = response.text
        # Нарезка длинных сообщений
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000])
    except Exception as e:
        logger.error(f"Ошибка в handle_all: {e}")
        # Если ошибка связана с длинным сообщением или Markdown, шлем чистый текст
        try:
            await update.message.reply_text(f"⚠️ Произошла ошибка ИИ. Попробуйте переформулировать запрос.")
        except:
            pass

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, g TEXT, a TEXT, h TEXT, m TEXT, al TEXT)")
    conn.close()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("anketa", save_anketa))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_all))
    
    # Важно: убираем drop_pending_updates, чтобы не терять сообщения
    app.run_polling()

if __name__ == '__main__':
    main()
