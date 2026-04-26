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



# 1. ФУНКЦИЯ АВТОПОДБОРА МОДЕЛИ (решает проблему 404 навсегда)

def setup_ai():

    try:

        genai.configure(api_key=GEMINI_KEY)

        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]

        # Пробуем найти лучшую из доступных

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



# 2. РАБОТА С ДАННЫМИ

def get_context(uid):

    try:

        conn = sqlite3.connect(DB_PATH)

        res = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

        conn.close()

        if res:

            return f"Данные пациента: {res[1]}, возраст {res[2]}, болезни: {res[3]}, лекарства: {res[4]}."

    except: pass

    return "Данные анкеты отсутствуют. Напомни пользователю заполнить её."



async def save_anketa(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # Формат: /anketa Муж 30 Гастрит Омез

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



# 3. ОБРАБОТКА ТЕКСТА И ФОТО

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not ai_model:

        await update.message.reply_text("ИИ не инициализирован.")

        return



    content = [

        "Ты — персональный медицинский ассистент. Используй данные пациента ниже для анализа.\n",

        f"КОНТЕКСТ: {get_context(update.effective_user.id)}\n",

        f"ЗАПРОС: {update.message.text or update.message.caption or 'Проанализируй это'}"

    ]



    # Если прислали фото (анализы или симптомы)

    if update.message.photo:

        await update.message.reply_chat_action(ChatAction.TYPING)

        file = await update.message.photo[-1].get_file()

        img_bytes = await file.download_as_bytearray()

        content.append({"mime_type": "image/jpeg", "data": bytes(img_bytes)})



    await update.message.reply_chat_action(ChatAction.TYPING)

    try:

        response = ai_model.generate_content(content)

        # Отправка длинных сообщений

        text = response.text

        for i in range(0, len(text), 4000):

            await update.message.reply_text(text[i:i+4000])

    except Exception as e:

        await update.message.reply_text(f"⚠️ Ошибка: {str(e)}")



def main():

    conn = sqlite3.connect(DB_PATH)

    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, g TEXT, a TEXT, h TEXT, m TEXT, al TEXT)")

    conn.close()



    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("anketa", save_anketa))

    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_all))

    app.run_polling()



if __name__ == '__main__':

    main() 
