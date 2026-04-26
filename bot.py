import os
import sys
import logging
import base64
import httpx
import psycopg2
import psycopg2.extras
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

GENDER, AGE, DISEASES, MEDS = range(4)
MAX_HISTORY = 10

SYSTEM_PROMPT = (
    "Ты — персональный медицинский ассистент. "
    "Отвечаешь на русском языке. "
    "Пиши коротко, чётко и по делу — без лишних вступлений и повторений. "
    "Учитывай данные пациента из контекста. "
    "Если вопрос не про здоровье — вежливо скажи об этом. "
    "В конце ответа кратко напоминай что ты не заменяешь врача."
)


# ══════════════════════════════════════════════════════════════════════════════
# Claude API
# ══════════════════════════════════════════════════════════════════════════════

async def ask_claude(messages: list, system: str = SYSTEM_PROMPT) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "system": system,
        "messages": messages,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


# ══════════════════════════════════════════════════════════════════════════════
# База данных
# ══════════════════════════════════════════════════════════════════════════════

def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL не задан!")
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY, gender TEXT, age INTEGER,
                    diseases TEXT, meds TEXT)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL,
                    role TEXT NOT NULL, message TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW())
            """)
    logger.info("БД инициализирована")


def get_patient_context(uid: int) -> str:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
                row = cur.fetchone()
        if row:
            return (f"Пол: {row['gender']}, возраст: {row['age']}, "
                    f"заболевания: {row['diseases']}, лекарства: {row['meds']}.")
    except Exception as e:
        logger.error(f"Ошибка чтения пациента {uid}: {e}")
    return "Анкета не заполнена."


def save_patient(uid: int, gender: str, age: int, diseases: str, meds: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (id, gender, age, diseases, meds)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE
                SET gender=%s, age=%s, diseases=%s, meds=%s
            """, (uid, gender, age, diseases, meds, gender, age, diseases, meds))


def load_history(uid: int) -> list:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT role, message FROM history
                    WHERE user_id=%s ORDER BY created_at DESC LIMIT %s
                """, (uid, MAX_HISTORY))
                rows = cur.fetchall()
        return list(reversed(rows))
    except Exception as e:
        logger.error(f"Ошибка истории {uid}: {e}")
        return []


def append_history(uid: int, role: str, message: str):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO history (user_id, role, message) VALUES (%s,%s,%s)",
                    (uid, role, message))
    except Exception as e:
        logger.error(f"Ошибка записи истории {uid}: {e}")


def clear_history(uid: int):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM history WHERE user_id=%s", (uid,))
    except Exception as e:
        logger.error(f"Ошибка очистки истории {uid}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Команды
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "друг"
    await update.message.reply_text(
        f"👋 Привет, {name}!\n\n"
        "Я — твой персональный медицинский ассистент.\n\n"
        "Что я умею:\n"
        "• Отвечать на медицинские вопросы\n"
        "• Анализировать фото результатов анализов\n"
        "• Учитывать твои личные данные и препараты\n"
        "• Помнить контекст нашего разговора\n\n"
        "Команды:\n"
        "/anketa — заполнить личную анкету\n"
        "/mydata — посмотреть свои данные\n"
        "/reset — очистить историю разговора\n"
        "/help — помощь\n\n"
        "⚠️ Я не заменяю врача. При серьёзных симптомах обратись к специалисту."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Как пользоваться:\n\n"
        "1. Заполни анкету /anketa\n"
        "2. Задавай медицинские вопросы текстом\n"
        "3. Отправь фото анализов — помогу разобраться\n"
        "4. /reset — начать разговор заново\n\n"
        "⚠️ Я ИИ-ассистент, не врач."
    )


async def cmd_mydata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ctx = get_patient_context(update.effective_user.id)
    await update.message.reply_text(f"📋 Твои данные:\n{ctx}")


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_history(update.effective_user.id)
    await update.message.reply_text("🗑 История очищена. Начинаем заново!")


# ══════════════════════════════════════════════════════════════════════════════
# Анкета
# ══════════════════════════════════════════════════════════════════════════════

async def anketa_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Мужской", "Женский"]]
    await update.message.reply_text(
        "📝 Заполним анкету!\n\nШаг 1/4 — Укажи пол:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return GENDER


async def anketa_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text not in ("Мужской", "Женский"):
        await update.message.reply_text("Выбери: Мужской или Женский")
        return GENDER
    context.user_data["gender"] = text
    await update.message.reply_text(
        "Шаг 2/4 — Введи возраст (например: 28):",
        reply_markup=ReplyKeyboardRemove()
    )
    return AGE


async def anketa_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or not (1 <= int(text) <= 120):
        await update.message.reply_text("Введи корректный возраст (1-120):")
        return AGE
    context.user_data["age"] = int(text)
    await update.message.reply_text(
        "Шаг 3/4 — Хронические заболевания через запятую.\n"
        "Если нет — напиши «Нет»:"
    )
    return DISEASES


async def anketa_diseases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["diseases"] = update.message.text.strip()
    await update.message.reply_text(
        "Шаг 4/4 — Какие лекарства принимаешь постоянно?\n"
        "Если нет — напиши «Нет»:"
    )
    return MEDS


async def anketa_meds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    meds = update.message.text.strip()
    d = context.user_data
    try:
        save_patient(uid, d["gender"], d["age"], d["diseases"], meds)
        await update.message.reply_text(
            "✅ Анкета сохранена!\n\n"
            f"• Пол: {d['gender']}\n"
            f"• Возраст: {d['age']}\n"
            f"• Заболевания: {d['diseases']}\n"
            f"• Лекарства: {meds}"
        )
    except Exception as e:
        logger.error(f"Ошибка сохранения анкеты {uid}: {e}")
        await update.message.reply_text("⚠️ Не удалось сохранить. Попробуй позже.")
    return ConversationHandler.END


async def anketa_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════════════════
# Основной обработчик сообщений
# ══════════════════════════════════════════════════════════════════════════════

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_text = update.message.text or update.message.caption or "Проанализируй изображение"
    await update.message.reply_chat_action(ChatAction.TYPING)

    patient_ctx = get_patient_context(uid)
    system = SYSTEM_PROMPT + f"\n\nДАННЫЕ ПАЦИЕНТА: {patient_ctx}"

    # Собираем историю для Claude
    history = load_history(uid)
    messages = []

    # История диалога (Claude требует строгое чередование user/assistant)
    for msg in history:
        messages.append({
            "role": msg["role"],
            "content": msg["message"]
        })

    # Текущий запрос
    if update.message.photo:
        try:
            file = await update.message.photo[-1].get_file()
            img_bytes = await file.download_as_bytearray()
            img_b64 = base64.standard_b64encode(bytes(img_bytes)).decode()
            messages.append({
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": img_b64
                    }},
                    {"type": "text", "text": user_text}
                ]
            })
        except Exception as e:
            logger.error(f"Ошибка фото {uid}: {e}")
            await update.message.reply_text("⚠️ Не удалось загрузить фото.")
            return
    else:
        messages.append({"role": "user", "content": user_text})

    try:
        answer = await ask_claude(messages, system=system)
        append_history(uid, "user", user_text)
        append_history(uid, "assistant", answer[:1000])
        for i in range(0, len(answer), 4000):
            await update.message.reply_text(answer[i:i+4000])
    except httpx.HTTPStatusError as e:
        body = e.response.text
        logger.error(f"Claude API HTTP error {e.response.status_code}: {body}")
        await update.message.reply_text(f"⚠️ Ошибка API {e.response.status_code}: {body[:300]}")
    except Exception as e:
        logger.error(f"Ошибка Claude API {uid}: {e}")
        await update.message.reply_text(f"⚠️ Ошибка: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# Запуск
# ══════════════════════════════════════════════════════════════════════════════

def main():
    if not TOKEN:
        logger.critical("TELEGRAM_TOKEN не задан!")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        logger.critical("ANTHROPIC_API_KEY не задан!")
        sys.exit(1)
    if not DATABASE_URL:
        logger.critical("DATABASE_URL не задан!")
        sys.exit(1)

    init_db()

    app = Application.builder().token(TOKEN).build()

    anketa_handler = ConversationHandler(
        entry_points=[CommandHandler("anketa", anketa_start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_age)],
            DISEASES: [MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_diseases)],
            MEDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_meds)],
        },
        fallbacks=[CommandHandler("cancel", anketa_cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("mydata", cmd_mydata))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(anketa_handler)
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_all))

    logger.info("Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
