import os
import sqlite3
import logging
import sys
import asyncio
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# --- Настройка ИИ ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_KEY)

# Инструкция, которая делает бота "умным"
SYSTEM_PROMPT = (
    "Ты — продвинутый медицинский ИИ-эксперт. Твоя база знаний актуальна на 2024 год. "
    "Твои правила: 1. Анализируй жалобы в контексте возраста и веса пользователя. "
    "2. Если прислано фото анализов, делай подробный разбор показателей. "
    "3. Отвечай развернуто, структурировано, на русском языке. "
    "4. В конце каждого важного совета добавляй: 'Это мнение ИИ, проконсультируйтесь с врачом'."
)

# --- База данных для контекста ---
DB_PATH = "/tmp/medical_bot.db"

def get_user_context(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if res:
        return f"Данные пациента: Пол {res[1]}, Возраст {res[2]}, Вес {res[3]}, Рост {res[4]}, Хронические болезни: {res[5]}."
    return "Данные пациента не заполнены."

# --- Продвинутая функция общения с ИИ ---
async def talk_to_ai(user_id, user_message, chat_history, photo_bytes=None):
    # Подключаем модель Pro для высокого качества ответов
    model = genai.GenerativeModel(
        model_name="gemini-1.5-pro",
        system_instruction=SYSTEM_PROMPT
    )
    
    # Собираем контекст: данные пользователя + история чата + текущий вопрос
    context = get_user_context(user_id)
    full_prompt = f"{context}\n\nИстория последних сообщений:\n{chat_history}\n\nВопрос пациента: {user_message}"
    
    content = [full_prompt]
    if photo_bytes:
        content.append({"mime_type": "image/jpeg", "data": photo_bytes})
    
    response = await model.generate_content_async(content)
    return response.text

# --- Обработка сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    
    # Работаем с историей (храним в памяти context.user_data)
    if 'history' not in context.user_data:
        context.user_data['history'] = ""
    
    await update.message.reply_chat_action("typing")
    
    # Отправляем ИИ
    response = await talk_to_ai(user_id, user_text, context.user_data['history'])
    
    # Обновляем историю для следующего раза
    context.user_data['history'] += f"\nПациент: {user_text}\nИИ: {response[:100]}..."
    if len(context.user_data['history']) > 1000: # Чистим старую историю
        context.user_data['history'] = context.user_data['history'][-1000:]
        
    await update.message.reply_text(response, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Здесь можно оставить опрос (как в прошлом коде) или сразу перейти к чату
    await update.message.reply_text("Я готов к работе. Пришлите описание симптомов или фото анализов.")

def main():
    # Создаем базу если нет
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, gender TEXT, age TEXT, weight TEXT, height TEXT, ill TEXT)")
    conn.close()

    app = Application.builder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    
    app.add_handler(CommandHandler("start", start))
    # Бот будет реагировать на любой текст и любые фото
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("--- ПРОДВИНУТЫЙ ИИ-БОТ ЗАПУЩЕН ---", flush=True)
    app.run_polling()

if __name__ == '__main__':
    main()
