import logging
import os
import re
import sqlite3
from datetime import datetime
from PIL import Image
import io

import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)

# --- НАСТРОЙКИ И ЛОГИРОВАНИЕ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Состояния ConversationHandler
GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT_MODE = range(6)

# --- ИНИЦИАЛИЗАЦИЯ ИИ ---
genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = """
Ты — элитный врач-терапевт с 20-летним стажем. Твоя задача — проводить глубокие медицинские консультации.
Правила:
1. Тон: профессиональный, эмпатичный, спокойный.
2. Всегда делай дисклеймер: "Данная консультация носит информационный характер. Для постановки диагноза обратитесь к врачу очно".
3. Используй данные профиля пользователя (возраст, вес и т.д.) для персонализации советов.
4. Если прислано фото анализов, проанализируй показатели и укажи на отклонения от референсных значений.
5. Задавай уточняющие вопросы, если симптомы описаны нечетко.
"""

def get_gemini_model():
    """Динамический подбор модели для избежания ошибки 404."""
    models_to_try = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=SYSTEM_INSTRUCTION
            )
            # Пробный запрос для проверки доступности
            model.generate_content("test", generation_config={"max_output_tokens": 1})
            logger.info(f"Успешно подключена модель: {model_name}")
            return model
        except Exception as e:
            logger.warning(f"Модель {model_name} недоступна: {e}")
    raise RuntimeError("Ни одна из моделей Gemini не доступна.")

model = get_gemini_model()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('medical_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            gender TEXT,
            age INTEGER,
            weight REAL,
            height REAL,
            diseases TEXT,
            created_at TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def update_user_profile(user_id, **kwargs):
    conn = sqlite3.connect('medical_bot.db')
    cursor = conn.cursor()
    columns = ', '.join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [user_id]
    
    # Пытаемся обновить, если нет — вставляем
    cursor.execute(f"UPDATE users SET {columns} WHERE user_id = ?", values)
    if cursor.rowcount == 0:
        cols = ', '.join(kwargs.keys())
        placeholders = ', '.join(['?' * len(kwargs)])
        cursor.execute(f"INSERT INTO users (user_id, {cols}, created_at) VALUES (?, {placeholders}, ?)",
                       [user_id] + list(kwargs.values()) + [datetime.now()])
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect('medical_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def save_history(user_id, role, content):
    conn = sqlite3.connect('medical_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                   (user_id, role, content, datetime.now()))
    conn.commit()
    conn.close()

def get_history(user_id, limit=10):
    conn = sqlite3.connect('medical_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM history WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", 
                   (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r, "parts": [c]} for r, c in reversed(rows)]

# --- ЛОГИКА БОТА ---

def get_main_menu():
    keyboard = [
        ["Консультация", "Моя медкарта"],
        ["Анализы", "SOS"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_user_data(user.id)
    
    if not db_user:
        await update.message.reply_text(
            f"Здравствуйте, {user.first_name}! Я ваш персональный медицинский ИИ-ассистент.\n"
            "Чтобы я мог давать точные советы, мне нужно составить вашу медкарту. "
            "Укажите ваш пол:",
            reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True)
        )
        return GENDER
    else:
        await update.message.reply_text(
            "С возвращением! Я готов к работе. Выберите действие в меню.",
            reply_markup=get_main_menu()
        )
        return CHAT_MODE

# --- ЦЕПОЧКА ОПРОСА ---

async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gender'] = update.message.text
    await update.message.reply_text("Введите ваш возраст (полных лет):")
    return AGE

async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = re.search(r'\d+', update.message.text)
    if not val:
        await update.message.reply_text("Пожалуйста, введите возраст числом.")
        return AGE
    context.user_data['age'] = int(val.group())
    await update.message.reply_text("Введите ваш вес в кг (например, 75):")
    return WEIGHT

async def set_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = re.search(r'\d+', update.message.text)
    if not val:
        await update.message.reply_text("Пожалуйста, введите вес числом.")
        return WEIGHT
    context.user_data['weight'] = float(val.group())
    await update.message.reply_text("Введите ваш рост в см:")
    return HEIGHT

async def set_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = re.search(r'\d+', update.message.text)
    if not val:
        await update.message.reply_text("Пожалуйста, введите рост числом.")
        return HEIGHT
    context.user_data['height'] = float(val.group())
    await update.message.reply_text("Есть ли у вас хронические заболевания? (Если нет, напишите 'Нет'):")
    return DISEASES

async def set_diseases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    diseases = update.message.text
    user_id = update.effective_user.id
    
    update_user_profile(
        user_id, 
        gender=context.user_data['gender'],
        age=context.user_data['age'],
        weight=context.user_data['weight'],
        height=context.user_data['height'],
        diseases=diseases
    )
    
    await update.message.reply_text(
        "Профиль успешно создан! Теперь вы можете задать любой медицинский вопрос или прислать фото анализов.",
        reply_markup=get_main_menu()
    )
    return CHAT_MODE

# --- РЕЖИМ ЧАТА И ОБРАБОТКА МЕДИА ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    # Обработка кнопок меню
    if text == "Моя медкарта":
        data = get_user_data(user_id)
        msg = (f"📋 *Ваша медкарта:*\n\nПол: {data[1]}\nВозраст: {data[2]}\n"
               f"Вес: {data[3]} кг\nРост: {data[4]} см\nХроническое: {data[5]}")
        await update.message.reply_text(msg, parse_mode='Markdown')
        return
    
    if text == "SOS":
        await update.message.reply_text("‼️ Если у вас экстренная ситуация — немедленно вызовите скорую помощь по номеру 103 или 112!")
        return

    # Проактивная проверка: если каким-то образом профиль пуст
    if not get_user_data(user_id):
        await update.message.reply_text("Для начала работы необходимо заполнить профиль.")
        return await start(update, context)

    # Работа с Gemini
    try:
        history = get_history(user_id)
        user_info = get_user_data(user_id)
        context_prompt = f"[Пациент: {user_info[1]}, {user_info[2]} лет, вес {user_info[3]}кг, рост {user_info[4]}см, хронические болезни: {user_info[5]}]\nЗапрос: {text}"
        
        chat = model.start_chat(history=history)
        response = chat.send_message(context_prompt)
        
        save_history(user_id, "user", text)
        save_history(user_id, "model", response.text)
        
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка Gemini: {e}")
        await update.message.reply_text("Произошла ошибка при обработке запроса. Попробуйте позже.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo_file = await update.message.photo[-1].get_file()
    img_byte_array = await photo_file.download_as_bytearray()
    
    img = Image.open(io.BytesIO(img_byte_array))
    
    await update.message.reply_text("⏳ Анализирую фото ваших анализов, подождите...")
    
    try:
        user_info = get_user_data(user_id)
        prompt = [
            f"Проанализируй медицинские анализы на фото для пациента: {user_info[2]} лет, {user_info[1]}. Укажи на отклонения.",
            img
        ]
        response = model.generate_content(prompt)
        
        save_history(user_id, "user", "[Прислал фото анализов]")
        save_history(user_id, "model", response.text)
        
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка при анализе фото: {e}")
        await update.message.reply_text("Не удалось распознать текст на фото. Убедитесь, что снимок четкий.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено.", reply_markup=get_main_menu())
    return CHAT_MODE

# --- ЗАПУСК ---

def main():
    init_db()
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(filters.TEXT & ~filters.COMMAND, start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_height)],
            DISEASES: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_diseases)],
            CHAT_MODE: [
                MessageHandler(filters.PHOTO, handle_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )

    application.add_handler(conv_handler)
    
    logger.info("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
