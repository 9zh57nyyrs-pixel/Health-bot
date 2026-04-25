import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import database
from gemini_client import GeminiClient # Изменили импорт
import matplotlib.pyplot as plt
import io

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Я ваш ИИ-врач на базе Gemini.\n\n"
        "📸 Пришлите фото анализов — я их расшифрую.\n"
        "📈 Команда /graph — график вашего веса.\n"
        "💬 Просто пишите симптомы — я помогу разобраться."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Вижу фото, анализирую данные... Пожалуйста, подождите.")
    
    # Скачиваем фото из Телеграма
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    
    # Отправляем в Gemini
    response = await GeminiClient.ask(None, update.effective_user.id, bytes(photo_bytes))
    await update.message.reply_text(response)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    # Быстрая проверка на опасные симптомы
    danger = ["боль в груди", "тяжело дышать", "очень высокое давление"]
    if any(word in user_text.lower() for word in danger):
        await update.message.reply_text("⚠️ СРОЧНО: Ваши симптомы выглядят опасными. Пожалуйста, вызовите скорую помощь (103/112)!")
    
    response = await GeminiClient.ask(user_text, update.effective_user.id)
    await update.message.reply_text(response)

async def send_graph(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = database.get_weight_history(update.effective_user.id)
    if not data:
        await update.message.reply_text("Данных о весе пока нет. Напишите, например: 'Мой вес сегодня 75 кг'")
        return
    
    plt.figure(figsize=(8, 4))
    plt.plot([x['date'] for x in data], [x['weight'] for x in data], color='green', marker='o')
    plt.title("Ваш прогресс")
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    await update.message.reply_photo(photo=buf)

def main():
    token = os.getenv("TELEGRAM_TOKEN")
    app = Application.builder().token(token).build()
    
    database.init_db()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("graph", send_graph))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()

if __name__ == "__main__":
    main()
