import os
import logging
import re
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, ConversationHandler
)
import database
from gemini_client import GeminiClient

# Состояния диалога
GENDER, AGE, WEIGHT, HEIGHT, DISEASES, CHAT = range(6)

logging.basicConfig(level=logging.INFO)

def main_menu():
    return ReplyKeyboardMarkup([
        ['👨‍⚕️ Консультация', '📈 Мои данные'],
        ['📸 Загрузить анализы', '📋 План чекапа'],
        ['🆘 SOS: Симптомы', '⚙️ Настройки']
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.init_db()
    user = database.get_profile(update.effective_user.id)
    
    if not user or not user.get('age'):
        await update.message.reply_text(
            "👨‍⚕️ Приветствую! Я ваш персональный врач.\n"
            "Давайте создадим вашу карту здоровья. Укажите ваш пол:",
            reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True)
        )
        return GENDER
    
    await update.message.reply_text("Рад вас видеть! Каков ваш запрос сегодня?", reply_markup=main_menu())
    return CHAT

async def get_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.update_profile(update.effective_user.id, gender=update.message.text)
    await update.message.reply_text("Отлично. Сколько вам полных лет?")
    return AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    age = re.findall(r'\d+', update.message.text)
    if not age:
        await update.message.reply_text("Пожалуйста, введите число.")
        return AGE
    database.update_profile(update.effective_user.id, age=int(age[0]))
    await update.message.reply_text("Ваш текущий вес (в кг)?")
    return WEIGHT

async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    weight = re.findall(r'\d+', update.message.text)
    if not weight:
        await update.message.reply_text("Введите число.")
        return WEIGHT
    database.update_profile(update.effective_user.id, weight=float(weight[0]))
    await update.message.reply_text("Ваш рост (в см)?")
    return HEIGHT

async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    height = re.findall(r'\d+', update.message.text)
    if not height:
        await update.message.reply_text("Введите число.")
        return HEIGHT
    database.update_profile(update.effective_user.id, height=float(height[0]))
    await update.message.reply_text("Есть ли у вас хронические заболевания? (Если нет, напишите 'Нет')")
    return DISEASES

async def get_diseases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.update_profile(update.effective_user.id, chronic_diseases=update.message.text)
    await update.message.reply_text(
        "Карта заполнена! Теперь вы можете задавать вопросы или присылать фото анализов.",
        reply_markup=main_menu()
    )
    return CHAT

async def handle_medical_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if update.message.photo:
        await update.message.reply_text("📥 Получил фото. Начинаю анализ медицинских показателей...")
        photo = await update.message.photo[-1].get_file()
        photo_bytes = await photo.download_as_bytearray()
        response = await GeminiClient.get_medical_advice(user_id, "Разбери анализы", True, bytes(photo_bytes))
    else:
        response = await GeminiClient.get_medical_advice(user_id, update.message.text)
    
    await update.message.reply_text(response, reply_markup=main_menu())
    return CHAT

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            DISEASES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_diseases)],
            CHAT: [MessageHandler(filters.TEXT | filters.PHOTO, handle_medical_chat)],
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    app.add_handler(conv_handler)
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
