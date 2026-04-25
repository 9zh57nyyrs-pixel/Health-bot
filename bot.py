import os
import sqlite3
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# Настройки
TOKEN = os.environ.get("TELEGRAM_TOKEN")
API_KEY = os.environ.get("GEMINI_API_KEY")
# База данных теперь хранится в надежном месте Railway (или в /tmp для тестов)
DB_PATH = "users_data.db" 

# Инициализация ИИ (с автоподбором модели)
genai.configure(api_key=API_KEY)
def get_model():
    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    name = 'models/gemini-1.5-flash' if 'models/gemini-1.5-flash' in models else models[0]
    return genai.GenerativeModel(name)

model = get_model()

# --- ЛОГИКА ИЗОЛЯЦИИ ДАННЫХ ---

def init_db():
    conn = sqlite3.connect(DB_PATH)
    # Создаем таблицу, где первичный ключ - это ID пользователя в Телеграм
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                    (user_id INTEGER PRIMARY KEY, info TEXT)''')
    conn.close()

def get_user_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT info FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return res[0] if res else None

def save_user_info(user_id, text):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO users (user_id, info) VALUES (?, ?)", (user_id, text))
    conn.commit()
    conn.close()

# --- ОБРАБОТКА СООБЩЕНИЙ ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id  # Уникальный ID каждого человека
    user_text = update.message.text
    
    # Достаем данные ТОЛЬКО этого пользователя
    current_profile = get_user_info(user_id)
    
    # Инструкция для ИИ
    if not current_profile:
        system_instruction = (
            "Ты — медицинский ассистент. Это НОВЫЙ пользователь. "
            "Начни опрос вежливо: спроси пол, возраст и рост. "
            "ЗАПРЕЩЕНО говорить про личные кабинеты. Ты сам проводишь опрос прямо здесь."
        )
    else:
        system_instruction = (
            f"Ты — медицинский ассистент. ДАННЫЕ ЭТОГО ПАЦИЕНТА: {current_profile}. "
            "Отвечай на вопросы, используя этот контекст. Если он сообщает новые данные о здоровье — запомни их."
        )

    await update.message.reply_chat_action(ChatAction.TYPING)
    
    try:
        response = model.generate_content(f"{system_instruction}\n\nСообщение пользователя: {user_text}")
        response_text = response.text
        
        # Если ИИ в ответе зафиксировал данные (например, после опроса), 
        # мы можем обновлять профиль. Для простоты пока просто даем ИИ вести диалог.
        # В идеале: если в ответе есть ключевые слова, сохраняем info.
        
        await update.message.reply_text(response_text)
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {str(e)}")

def main():
    init_db()
    if not TOKEN: return
    
    # Railway запускает один экземпляр, который обслуживает ВСЕХ
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Бот запущен и разделяет пользователей...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
