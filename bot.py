import os, logging, sqlite3, asyncio
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования для Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка ИИ
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

# Используем папку /tmp, так как Railway часто запрещает запись в корень
DB_PATH = "/tmp/health_v5.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, profile TEXT)')

def get_user_profile(uid):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT profile FROM users WHERE id=?", (uid,)).fetchone()
        return res[0] if res else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    uid = update.effective_user.id
    profile = get_user_profile(uid)
    
    if profile:
        await update.message.reply_text(f"✅ Карта активна: {profile}\n\nЧто вас беспокоит?")
    else:
        await update.message.reply_text(
            "Добро пожаловать! Напишите ваш пол, возраст, вес и болезни одним сообщением через запятую.\n"
            "Пример: Мужчина, 30 лет, 80 кг, нет болезней."
        )

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    profile = get_user_profile(uid)

    # Если профиля нет — сохраняем первое сообщение как профиль
    if not profile:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO users (id, profile) VALUES (?, ?)", (uid, text))
        await update.message.reply_text("✅ Данные сохранены! Теперь задавайте любые медицинские вопросы.")
        return

    # Если профиль есть — работаем как консультант
    await update.message.reply_chat_action(constants.ChatAction.TYPING)
    try:
        # Формируем запрос к ИИ
        prompt = f"Пациент: {profile}. Вопрос: {text}. Ответь как квалифицированный врач."
        
        # Если прислали фото анализов
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            img_data = await photo_file.download_as_bytearray()
            # Для простоты в этой версии обрабатываем только текст, 
            # чтобы избежать падений из-за памяти на Railway
            prompt += " (К сообщению было приложено фото)"

        response = await asyncio.to_thread(model.generate_content, prompt)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("🩺 Ошибка связи с ИИ. Попробуйте написать вопрос короче.")

def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("Нет токена!")
        return
        
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_all))
    
    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()
