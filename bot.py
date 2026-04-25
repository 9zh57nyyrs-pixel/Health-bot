"""
Medical Consultation Telegram Bot
Powered by Gemini | python-telegram-bot v20+
"""

import asyncio
import logging
import os
import re
import sqlite3
import sys
from contextlib import contextmanager

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── States ────────────────────────────────────────────────────────────────────
(STATE_MENU, STATE_ASK_GENDER, STATE_ASK_AGE, STATE_ASK_WEIGHT,
 STATE_ASK_HEIGHT, STATE_ASK_CONDITIONS, STATE_CHAT, STATE_WAITING_PHOTO) = range(8)

# ── Keyboards ─────────────────────────────────────────────────────────────────
MAIN_MENU_KB = ReplyKeyboardMarkup(
    [["💊 Консультация", "📋 Моя медкарта"], ["🔬 Анализы (фото)", "🆘 SOS"]],
    resize_keyboard=True,
)
GENDER_KB = ReplyKeyboardMarkup([["👨 Мужской", "👩 Женский"]], resize_keyboard=True, one_time_keyboard=True)
SKIP_KB   = ReplyKeyboardMarkup([["⏭ Пропустить"]], resize_keyboard=True, one_time_keyboard=True)

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = os.environ.get("DATABASE_PATH", "medical_bot.db")

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error: {e}")
        raise
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, gender TEXT, age INTEGER,
                weight INTEGER, height INTEGER, conditions TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                role TEXT, content TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        """)
    logger.info("DB initialized.")

def get_profile(uid):
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        return dict(row) if row else {}

def set_profile(uid, **kwargs):
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
        if kwargs:
            sets = ", ".join(f"{k}=?" for k in kwargs)
            conn.execute(f"UPDATE users SET {sets} WHERE user_id=?", list(kwargs.values()) + [uid])

def add_msg(uid, role, text):
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
        conn.execute("INSERT INTO messages (user_id,role,content) VALUES (?,?,?)", (uid, role, text))

def get_history(uid, limit=8):
    with db() as conn:
        rows = conn.execute("""
            SELECT role, content FROM (
                SELECT role, content, created_at FROM messages
                WHERE user_id=? ORDER BY created_at DESC LIMIT ?) ORDER BY created_at ASC
        """, (uid, limit)).fetchall()
        return [(r["role"], r["content"]) for r in rows]

# ── Gemini ────────────────────────────────────────────────────────────────────
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

SYSTEM_PROMPT = """Ты — элитный врач-терапевт с 30-летним опытом. Персональный медицинский ассистент в Telegram.
ПРАВИЛА: учитывай профиль пациента; давай развёрнутые ответы; объясняй термины; перечисляй возможные причины симптомов; указывай когда нужна срочная помощь; при анализе фото расшифровывай показатели и нормы; форматируй с Markdown."""

SAFETY = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
}
MODELS = ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-1.5-pro", "gemini-pro"]
_model = None

def init_gemini(api_key):
    global _model
    genai.configure(api_key=api_key)
    try:
        available = {m.name for m in genai.list_models()}
        logger.info(f"Available models: {available}")
    except Exception as e:
        logger.warning(f"Cannot list models: {e}")
        available = set()
    chosen = next((n for n in MODELS if f"models/{n}" in available or n in available), MODELS[0])
    logger.info(f"Using model: {chosen}")
    _model = genai.GenerativeModel(
        model_name=chosen, system_instruction=SYSTEM_PROMPT, safety_settings=SAFETY,
        generation_config=genai.types.GenerationConfig(temperature=0.7, max_output_tokens=2048))
    return chosen

def _sync_ask(user_msg, history, ctx_str):
    global _model
    gh = [{"role": "model" if r == "assistant" else "user", "parts": [c]} for r, c in history[:-1]]
    enriched = f"[Данные пациента: {ctx_str}]\n\nВопрос: {user_msg}"
    for i, name in enumerate(MODELS):
        try:
            m = _model if i == 0 else genai.GenerativeModel(name, system_instruction=SYSTEM_PROMPT, safety_settings=SAFETY)
            resp = m.start_chat(history=gh).send_message(enriched)
            if i > 0:
                _model = m
            return resp.text
        except Exception as e:
            logger.error(f"Model {name} failed: {e}")
    return "⚠️ ИИ временно недоступен. Попробуйте через минуту."

def _sync_img(image_bytes, ctx_str, caption):
    prompt = f"[Данные пациента: {ctx_str}]\nРасшифруй медицинский документ: определи тип, расшифруй показатели, укажи нормы, отметь отклонения, дай рекомендации.{chr(10) + 'Комментарий: ' + caption if caption else ''}"
    mime = "image/png" if image_bytes[:4] == b'\x89PNG' else "image/jpeg"
    for name in MODELS:
        try:
            return _model.generate_content([prompt, {"mime_type": mime, "data": image_bytes}]).text
        except Exception as e:
            logger.error(f"Image {name} failed: {e}")
    return "⚠️ Не удалось проанализировать изображение."

async def ask_gemini(msg, history, ctx): return await asyncio.to_thread(_sync_ask, msg, history, ctx)
async def analyze_img(b, ctx, cap=""): return await asyncio.to_thread(_sync_img, b, ctx, cap)

# ── Helpers ───────────────────────────────────────────────────────────────────
def extract_num(text):
    m = re.search(r"\b(\d{1,3})\b", text)
    return int(m.group(1)) if m else None

def patient_ctx(p):
    parts = []
    if p.get("gender"):     parts.append("Пол: " + ("мужской" if p["gender"] == "male" else "женский"))
    if p.get("age"):        parts.append(f"Возраст: {p['age']} лет")
    if p.get("weight"):     parts.append(f"Вес: {p['weight']} кг")
    if p.get("height"):     parts.append(f"Рост: {p['height']} см")
    if p.get("conditions"): parts.append(f"Заболевания: {p['conditions']}")
    return "; ".join(parts) if parts else "Данные не указаны"

def fmt_profile(p):
    if not p or not p.get("age"): return "📋 *Медкарта пуста.* Используйте /start"
    lines = ["📋 *Ваша медицинская карта*\n"]
    if p.get("gender"):     lines.append("• *Пол:* " + ("Мужской" if p["gender"] == "male" else "Женский"))
    if p.get("age"):        lines.append(f"• *Возраст:* {p['age']} лет")
    if p.get("weight"):     lines.append(f"• *Вес:* {p['weight']} кг")
    if p.get("height"):     lines.append(f"• *Рост:* {p['height']} см")
    if p.get("conditions"): lines.append(f"• *Заболевания:* {p['conditions']}")
    return "\n".join(lines)

# ── Handlers ──────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    name = update.effective_user.first_name
    p = get_profile(uid)
    if not p or not p.get("age"):
        await update.message.reply_text(
            f"👋 Здравствуйте, *{name}*!\n\nЯ — медицинский ассистент на базе ИИ.\nДавайте заполним медкарту. *Шаг 1/5:* Укажите пол:",
            parse_mode=ParseMode.MARKDOWN, reply_markup=GENDER_KB)
        return STATE_ASK_GENDER
    await update.message.reply_text(f"👋 С возвращением, *{name}*!", parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_MENU_KB)
    return STATE_MENU

async def handle_gender(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    t = update.message.text.lower(); uid = update.effective_user.id
    if "муж" in t: g = "male"
    elif "жен" in t: g = "female"
    else:
        await update.message.reply_text("Выберите пол кнопками:", reply_markup=GENDER_KB)
        return STATE_ASK_GENDER
    set_profile(uid, gender=g)
    await update.message.reply_text("✅ *Шаг 2/5:* Сколько лет? _(например: 34)_", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
    return STATE_ASK_AGE

async def handle_age(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id; age = extract_num(update.message.text)
    if not age or not (1 <= age <= 120):
        await update.message.reply_text("⚠️ Напишите возраст числом, например *34*:", parse_mode=ParseMode.MARKDOWN)
        return STATE_ASK_AGE
    set_profile(uid, age=age)
    await update.message.reply_text(f"✅ {age} лет.\n\n*Шаг 3/5:* Вес в кг? _(например: 75)_", parse_mode=ParseMode.MARKDOWN, reply_markup=SKIP_KB)
    return STATE_ASK_WEIGHT

async def handle_weight(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id; t = update.message.text
    if "пропуст" in t.lower() or "⏭" in t: w = None
    else:
        w = extract_num(t)
        if not w or not (20 <= w <= 300):
            await update.message.reply_text("⚠️ Напишите вес числом или «Пропустить»:", reply_markup=SKIP_KB)
            return STATE_ASK_WEIGHT
    if w: set_profile(uid, weight=w)
    await update.message.reply_text(f"✅ {'Принято.' if w else 'Пропущено.'}\n\n*Шаг 4/5:* Рост в см? _(например: 172)_", parse_mode=ParseMode.MARKDOWN, reply_markup=SKIP_KB)
    return STATE_ASK_HEIGHT

async def handle_height(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id; t = update.message.text
    if "пропуст" in t.lower() or "⏭" in t: h = None
    else:
        h = extract_num(t)
        if not h or not (50 <= h <= 250):
            await update.message.reply_text("⚠️ Напишите рост числом или «Пропустить»:", reply_markup=SKIP_KB)
            return STATE_ASK_HEIGHT
    if h: set_profile(uid, height=h)
    await update.message.reply_text(f"✅ {'Принято.' if h else 'Пропущено.'}\n\n*Шаг 5/5:* Хронические заболевания, аллергии?\n_Например: диабет 2 типа_", parse_mode=ParseMode.MARKDOWN, reply_markup=SKIP_KB)
    return STATE_ASK_CONDITIONS

async def handle_conditions(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id; t = update.message.text.strip()
    if "пропуст" not in t.lower() and "⏭" not in t: set_profile(uid, conditions=t)
    await update.message.reply_text(
        "🎉 *Медкарта заполнена!*\n\nЗадайте любой медицинский вопрос.\n\n⚠️ _Ответы информационны и не заменяют врача._",
        parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_MENU_KB)
    return STATE_MENU

async def handle_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    t = update.message.text; uid = update.effective_user.id
    if "медкарт" in t.lower():
        await update.message.reply_text(fmt_profile(get_profile(uid)), parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_MENU_KB)
        return STATE_MENU
    if "анализ" in t.lower():
        await update.message.reply_text("🔬 Пришлите фото медицинского документа:", reply_markup=ReplyKeyboardMarkup([["🔙 Меню"]], resize_keyboard=True))
        return STATE_WAITING_PHOTO
    if "sos" in t.lower():
        await update.message.reply_text("🆘 *ЭКСТРЕННАЯ ПОМОЩЬ*\n\n📞 Скорая: *103*\n📞 Единый: *112*\n\nОпишите ситуацию:", parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_MENU_KB)
        return STATE_CHAT
    if "консультац" in t.lower():
        await update.message.reply_text("💊 Задайте ваш вопрос:", reply_markup=MAIN_MENU_KB)
        return STATE_CHAT
    if "меню" in t.lower() or "🔙" in t:
        await update.message.reply_text("Главное меню:", reply_markup=MAIN_MENU_KB)
        return STATE_MENU
    return await handle_chat(update, ctx)

async def handle_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id; text = update.message.text.strip()
    p = get_profile(uid)
    if not p or not p.get("age"):
        await update.message.reply_text("⚠️ Сначала заполните медкарту. Укажите пол:", reply_markup=GENDER_KB)
        return STATE_ASK_GENDER
    await update.message.chat.send_action(ChatAction.TYPING)
    add_msg(uid, "user", text)
    try:
        reply = await ask_gemini(text, get_history(uid), patient_ctx(p))
    except Exception as e:
        logger.error(f"Gemini error: {e}", exc_info=True)
        reply = "⚠️ Ошибка ИИ. Попробуйте ещё раз."
    add_msg(uid, "assistant", reply)
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_MENU_KB)
    return STATE_MENU

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if update.message.text:
        t = update.message.text
        if "меню" in t.lower() or "🔙" in t:
            await update.message.reply_text("Главное меню:", reply_markup=MAIN_MENU_KB)
            return STATE_MENU
        await update.message.reply_text("Пришлите фото анализа или нажмите «🔙 Меню».")
        return STATE_WAITING_PHOTO
    photo = update.message.photo; doc = update.message.document
    if not photo and not doc:
        await update.message.reply_text("Пожалуйста, пришлите *фото*.", parse_mode=ParseMode.MARKDOWN)
        return STATE_WAITING_PHOTO
    await update.message.reply_text("🔍 Анализирую...")
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        f = await (update.message.photo[-1] if photo else doc).get_file()
        img = bytes(await f.download_as_bytearray())
        p = get_profile(uid); cap = update.message.caption or ""
        reply = await analyze_img(img, patient_ctx(p), cap)
        add_msg(uid, "user", f"[Фото]{' ' + cap if cap else ''}")
        add_msg(uid, "assistant", reply)
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_MENU_KB)
    except Exception as e:
        logger.error(f"Photo error: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Не удалось обработать фото.", reply_markup=MAIN_MENU_KB)
    return STATE_MENU

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отменено.", reply_markup=MAIN_MENU_KB)
    return STATE_MENU

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    set_profile(update.effective_user.id, gender=None, age=None, weight=None, height=None, conditions=None)
    await update.message.reply_text("🔄 Профиль сброшен. Укажите пол:", reply_markup=GENDER_KB)
    return STATE_ASK_GENDER

async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Глобальная ошибка:", exc_info=ctx.error)
    if isinstance(update, Update) and update.effective_message:
        try: await update.effective_message.reply_text("⚠️ Ошибка. Попробуйте /start")
        except Exception: pass

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN") or ""
    gemini_key = os.environ.get("GEMINI_API_KEY") or ""
    if not token:
        logger.critical("❌ TELEGRAM_BOT_TOKEN не задан!")
        sys.exit(1)
    if not gemini_key:
        logger.critical("❌ GEMINI_API_KEY не задан!")
        sys.exit(1)

    logger.info("Инициализация DB...")
    init_db()
    logger.info("Инициализация Gemini...")
    model_name = init_gemini(gemini_key)
    logger.info(f"Модель: {model_name}")

    app = Application.builder().token(token).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            STATE_ASK_GENDER:     [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gender)],
            STATE_ASK_AGE:        [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age)],
            STATE_ASK_WEIGHT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_weight)],
            STATE_ASK_HEIGHT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_height)],
            STATE_ASK_CONDITIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conditions)],
            STATE_MENU:  [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu),
                          MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo)],
            STATE_CHAT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat),
                          MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo)],
            STATE_WAITING_PHOTO: [MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo),
                                   MessageHandler(filters.TEXT & ~filters.COMMAND, handle_photo)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel), CommandHandler("start", cmd_start)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_error_handler(error_handler)
    logger.info("✅ Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
