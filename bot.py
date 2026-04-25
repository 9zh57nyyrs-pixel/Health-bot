import os
import re
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (Application, CommandHandler, MessageHandler, 
                          filters, ContextTypes, ConversationHandler)
import database
from gemini_client import GeminiClient

# Состояния анкеты
GENDER, AGE, WEIGHT, HEIGHT, CHAT = range(5)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MedicalBot:
    def __init__(self):
        self.ai = GeminiClient()
        database.init_db()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = database.get_user(update.effective_user.id)
        if not user or not user.get('age'):
            await update.message.reply_text(
                "👨‍⚕️ Здравствуйте! Я ваш ИИ-терапевт. Давайте заполним медкарту.\nВаш пол?",
                reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True)
            )
            return GENDER
        await update.message.reply_text("С возвращением! Что вас беспокоит?", reply_markup=self.main_menu())
        return CHAT

    def main_menu(self):
        return ReplyKeyboardMarkup([['📊 Анализы', '📉 Вес'], ['👨‍⚕️ Консультация']], resize_keyboard=True)

    async def save_gender(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        database.save_user(update.effective_user.id, gender=update.message.text)
        await update.message.reply_text("Сколько вам полных лет?")
        return AGE

    async def save_age(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        age = re.search(r'\d+', update.message.text)
        if not age:
            await update.message.reply_text("Введите возраст цифрами.")
            return AGE
        database.save_user(update.effective_user.id, age=int(age.group()))
        await update.message.reply_text("Ваш вес в кг?")
        return WEIGHT

    async def save_weight(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        weight = re.search(r'\d+', update.message.text)
        database.save_user(update.effective_user.id, weight=float(weight.group()))
        await update.message.reply_text("Ваш рост в см?")
        return HEIGHT

    async def save_height(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        database.save_user(update.effective_user.id, height=float(re.search(r'\d+', update.message.text).group()))
        await update.message.reply_text("Карта заполнена. Я готов к консультации!", reply_markup=self.main_menu())
        return CHAT

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_profile = database.get_user(user_id)
        
        if update.message.photo:
            await update.message.reply_text("🔍 Анализирую фото анализов...")
            photo = await update.message.photo[-1].get_file()
            photo_bytes = await photo.download_as_bytearray()
            resp = await self.ai.generate_response("Разбери анализ на фото", user_profile, bytes(photo_bytes))
        else:
            resp = await self.ai.generate_response(update.message.text, user_profile)
        
        await update.message.reply_text(resp)
        return CHAT

def main():
    bot = MedicalBot()
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', bot.start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.save_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.save_age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.save_weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.save_height)],
            CHAT: [MessageHandler(filters.TEXT | filters.PHOTO, bot.handle_message)],
        },
        fallbacks=[CommandHandler('start', bot.start)]
    )
    
    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
