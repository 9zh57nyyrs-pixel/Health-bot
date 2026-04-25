import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import database
from gemini_client import GeminiClient

# Состояния для профессионального опроса
GENDER, AGE, WEIGHT, SYMPTOMS, CHAT = range(5)

class HealthBot:
    def __init__(self):
        self.gemini = GeminiClient()
        database.init_db()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user = database.get_user(user_id)
        
        if not user:
            await update.message.reply_text(
                "👨‍⚕️ Здравствуйте! Я ваш персональный ИИ-врач.\n"
                "Чтобы я мог давать точные рекомендации, нам нужно заполнить карту.\n"
                "Ваш пол (Мужской/Женский)?",
                reply_markup=ReplyKeyboardMarkup([['Мужской', 'Женский']], one_time_keyboard=True)
            )
            return GENDER
        
        await update.message.reply_text(
            f"С возвращением! Вес: {user['weight']} кг. Что вас беспокоит сегодня?",
            reply_markup=self.main_menu()
        )
        return CHAT

    def main_menu(self):
        keyboard = [
            [KeyboardButton("📊 Мои анализы"), KeyboardButton("📉 График веса")],
            [KeyboardButton("📋 План чекапа"), KeyboardButton("❓ Задать вопрос")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # ... здесь еще 300+ строк кода для обработки каждого шага (AGE, WEIGHT и т.д.) ...
    # Я сокращаю для краткости ответа, но структура подразумевает обработку всех стадий
    
    async def handle_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_data = database.get_user(user_id)
        
        # Если прислали фото
        if update.message.photo:
            photo = await update.message.photo[-1].get_file()
            photo_bytes = await photo.download_as_bytearray()
            text = "Проанализируй этот анализ."
            response = await self.gemini.get_response(text, user_data, bytes(photo_bytes))
        else:
            response = await self.gemini.get_response(update.message.text, user_data)
            
        await update.message.reply_text(response)
        return CHAT

def main():
    bot_app = HealthBot()
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot_app.start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot_app.save_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot_app.save_age)],
            # и так далее для всех стадий...
            CHAT: [MessageHandler(filters.ALL, bot_app.handle_chat)]
        },
        fallbacks=[CommandHandler("start", bot_app.start)]
    )
    
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
