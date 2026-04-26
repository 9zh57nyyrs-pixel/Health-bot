import os
import sys
import logging
import psycopg2
import psycopg2.extras
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

# ─── Логирование ───────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ─── Переменные окружения ───────────────────────────────────────────────────────
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

# ─── Шаги анкеты ───────────────────────────────────────────────────────────────
GENDER, AGE, DISEASES, MEDS = range(4)
MAX_HISTORY = 10


def setup_ai():
    try:
        genai.configure(api_key=GEMINI_KEY)
        models = [
            m.name for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        ]
        priority = [
            "models/gemini-1.5-flash",
            "models/gemini-1.5-flash-latest",
            "models/gemini-pro",
        ]
        for p in priority:
            if p in models:
                logger.info(f"Выбрана модель: {p}")
                return genai.GenerativeModel(p)
        if models:
            logger.info(f"Используем первую доступную модель: {models[0]}")
            return genai.GenerativeModel(models[0])
        logger.error("Нет доступных моделей Gemini")
        return None
    except Exception as e:
        logger.error(f"Ошибка инициализации ИИ: {e}")
        return None


ai_model = setup_ai()


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("Переменная DATABASE_URL не задана!")
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id      BIGINT PRIMARY KEY,
                        gender  TEXT,
                        age     INTEGER,
                        diseases TEXT,
                        meds    TEXT
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS history (
                        id      SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        role    TEXT NOT NULL,
                        message TEXT NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        raise


def get_patient_context(uid: int) -> str:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
                row = cur.fetchone()
        if row:
            return (
                f"Пол: {row['gender']}, возраст: {row['age']}, "
                f"хронические заболевания: {row['diseases']}, "
                f"принимаемые лекарства: {row['meds']}."
            )
    except Exception as e:
        logger.error(f"Ошибка чтения данных пациента (uid={uid}): {e}")
    return "Данные анкеты отсутствуют. Напомни пользователю заполнить её командой /anketa."


def save_patient(uid: int, gender: str, age: int, diseases: str, meds: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (id, gender, age, diseases, meds)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET gender=%s, age=%s, diseases=%s, meds=%s
            """, (uid, gender, age, diseases, meds,
                  gender, age, diseases, meds))


def load_history(uid: int) -> list[dict]:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT role, message FROM history
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (uid, MAX_HISTORY))
                rows = cur.fetchall()
        return list(reversed(rows))
    except Exception as e:
        logger.error(f"Ошибка загрузки истории (uid={uid}): {e}")
        return []


def append_history(uid: int, role: str, message: str):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO history (user_id, role, message) VALUES (%s, %s, %s)",
                    (uid, role, message)
                )
    except Exception as e:
        logger.error(f"Ошибка записи истории (uid={uid}): {e}")


def clear_history(uid: int):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM history WHERE user_id = %s", (uid,))
    except Exception as e:
        logger.error(f"Ошибка очистки истории (uid={uid}): {e}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "друг"
    await update.message.reply_text(
        f"👋 Привет, {name}!\n\n"
        "Я — твой персональный медицинский ассистент на базе ИИ.\n\n"
        "Что я умею:\n"
        "• От
