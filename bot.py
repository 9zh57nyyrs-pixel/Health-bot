import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import database
from gemini_client import GeminiClient

# Константы состояний
ANKETA_STEP = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.init_db()
    user_id = update.effective_user.id
    profile, _ = database.get_full_context(user_id)
    
    keyboard = [['📝 Моя медкарта', '📊 Анализы'], ['📅 План чекапа', '🆘 Помощь']]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    if not profile:
        await update.message.reply_text(
            "👨‍⚕️ Добро пожаловать! Я ваш ИИ-терапевт.\n"
            "Для начала работы мне нужно заполнить вашу медицинскую карту.\n"
            "Пожалуйста, напишите ваш возраст, пол и текущий вес (например: 35 лет, мужской, 80 кг).",
            reply_markup=markup
        )
    else:
        await update.message.reply_text("С возвращением! Я готов к работе. Что вас беспокоит?", reply_markup=markup)

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    # Логика автоматического сохранения данных
    if text and any(word in text.lower() for word in ['лет', 'муж', 'жен', 'кг']):
        # Тут можно добавить сложный Regex парсинг как в коде Claude
        await update.message.reply_text("📥 Данные приняты в обработку...")
    
    # Если фото - обрабатываем как анализы
    if update.message.photo:
        photo = await update.message.photo[-1].get_file()
        photo_bytes = await photo.download_as_bytearray()
        res = await GeminiClient.get_response(user_id, photo_bytes=bytes(photo_bytes))
    else:
        res = await GeminiClient.get_response(user_id, text_input=text)
        
    await update.message.reply_text(res)

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_all))
    
    print("Сервер запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
