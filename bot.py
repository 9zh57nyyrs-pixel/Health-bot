import os
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import database
from gemini_client import GeminiClient

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.init_db()
    user_id = update.effective_user.id
    user = database.get_user(user_id)
    
    keyboard = [['📊 Мой профиль', '👨‍⚕️ Консультация'], ['📉 Мои анализы', '⚙️ Настройки']]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    msg = "Добро пожаловать в систему HealthHelper! "
    if not user:
        msg += "Давайте составим вашу медкарту. Сколько вам лет и какой у вас пол?"
    else:
        msg += f"Рад видеть вас снова. Как ваше самочувствие?"
        
    await update.message.reply_text(msg, reply_markup=markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    # Пытаемся "подслушать" данные и сохранить их в базу автоматом
    if "лет" in text.lower():
        import re
        age = re.search(r'\d+', text)
        if age:
            database.save_user(user_id, age=int(age.group()))
    
    if "муж" in text.lower() or "жен" in text.lower():
        gender = "мужской" if "муж" in text.lower() else "женский"
        database.save_user(user_id, gender=gender)

    # Отправляем запрос в Gemini
    response = await GeminiClient.ask(text, user_id)
    await update.message.reply_text(response)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo = await update.message.photo[-1].get_file()
    photo_bytes = await photo.download_as_bytearray()
    
    await update.message.reply_text("⏳ Анализирую ваши данные, подождите...")
    response = await GeminiClient.ask(None, user_id, bytes(photo_bytes))
    await update.message.reply_text(response)

def main():
    token = os.getenv("TELEGRAM_TOKEN")
    app = Application.builder().token(token).build()
    
    database.init_db()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    app.run_polling()

if __name__ == "__main__":
    main()
