import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import database
from gemini_client import GeminiClient

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.init_db()
    reply_keyboard = [['📊 Мое здоровье', '📝 Заполнить анкету'], ['📅 План чекапа', '📉 График веса']]
    await update.message.reply_text(
        "Здравствуйте! Я ваш персональный терапевт. Нам нужно настроить ваш профиль для точных рекомендаций.",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=False, resize_keyboard=True)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    # Простая логика сохранения данных из текста (парсинг возраста/пола)
    if "мне" in text.lower() and "лет" in text.lower():
        # Пример: "Мне 39 лет, я мужчина" -> извлекаем 39 и муж
        import re
        age = re.search(r'\d+', text)
        if age:
            database.save_user(user_id, age=int(age.group()))
            await update.message.reply_text("✅ Возраст сохранен в вашу карту.")
    
    response = await GeminiClient.ask(text, user_id)
    await update.message.reply_text(response)

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message)) # Добавьте обработку фото
    app.run_polling()

if __name__ == "__main__":
    main()
