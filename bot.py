import asyncio
import logging
import os
import re
import sqlite3
import sys
from contextlib import contextmanager

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

(STATE_MENU, STATE_ASK_GENDER, STATE_ASK_AGE, STATE_ASK_WEIGHT,
 STATE_ASK_HEIGHT, STATE_ASK_CONDITIONS, STATE_CHAT, STATE_PHOTO) = range(8)

MENU_KB   = ReplyKeyboardMarkup([["💊 Консультация", "📋 Медкарта"], ["🔬 Анализы (фото)", "🆘 SOS"]], resize_keyboard=True)
GENDER_KB = ReplyKeyboardMarkup([["👨 Мужской", "👩 Женский"]], resize_keyboard=True, one_time_keyboard=True)
SKIP_KB   = ReplyKeyboardMarkup([["⏭ Пропустить"]], resize_keyboard=True, one_time_keyboard=True)
BACK_KB   = ReplyKeyboardMarkup([["🔙 Меню"]], resize_keyboard=True)

DB = "bot.db"

def init_db():
    with sqlite3.connect(DB) as c:
        c.execute("CREATE TABLE IF NOT EXISTS users (uid INTEGER PRIMARY KEY, gender TEXT, age INTEGER, weight INTEGER, height INTEGER, conditions TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS msgs (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, role TEXT, content TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP)")
    logger.info("DB ready")

def get_p(uid):
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
        return dict(r) if r else {}

def set_p(uid, **kw):
    with sqlite3.connect(DB) as c:
        c.execute("INSERT OR IGNORE INTO users (uid) VALUES (?)", (uid,))
        if kw:
            sets = ", ".join(f"{k}=?" for k in kw)
            c.execute(f"UPDATE users SET {sets} WHERE uid=?", list(kw.values()) + [uid])

def add_msg(uid, role, text):
    with sqlite3.connect(DB) as c:
        c.execute("INSERT OR IGNORE INTO users (uid) VALUES (?)", (uid,))
        c.execute("INSERT INTO msgs (uid,role,content) VALUES (?,?,?)", (uid, role, text[:4000]))

def get_hist(uid, n=8):
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT role,content FROM (SELECT role,content,ts FROM msgs WHERE uid=? ORDER BY ts DESC LIMIT ?) ORDER BY ts", (uid, n)).fetchall()
        return [(r["role"], r["content"]) for r in rows]

SYSTEM = "Ты — элитный врач-терапевт с 30-летним опытом. Медицинский ассистент в Telegram. Учитывай данные профиля пациента. Давай подробные ответы с Markdown-форматированием. Объясняй термины простыми словами. Указывай когда нужна срочная помощь."
SAFETY = {HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH, HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH, HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE, HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH}
MODELS = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
gmodel = None

def setup_gemini(key):
    global gmodel
    genai.configure(api_key=key)
    gmodel = genai.GenerativeModel(MODELS[0], system_instruction=SYSTEM, safety_settings=SAFETY, generation_config=genai.types.GenerationConfig(temperature=0.7, max_output_tokens=2048))
    logger.info(f"Gemini ready: {MODELS[0]}")

def _ask(msg, hist, pctx):
    gh = [{"role": "model" if r == "assistant" else "user", "parts": [c]} for r, c in hist[:-1]]
    text = f"[Пациент: {pctx}]\n\n{msg}"
    for i, name in enumerate(MODELS):
        try:
            m = gmodel if i == 0 else genai.GenerativeModel(name, system_instruction=SYSTEM, safety_settings=SAFETY)
            return m.start_chat(history=gh).send_message(text).text
        except Exception as e:
            logger.error(f"{name}: {e}")
    return "⚠️ ИИ временно недоступен. Попробуйте позже."

def _img(byt, pctx, cap):
    prompt = f"[Пациент: {pctx}]\nРасшифруй медицинский документ: тип, показатели, нормы, отклонения, рекомендации.{chr(10)+cap if cap else ''}"
    mime = "image/png" if byt[:4] == b'\x89PNG' else "image/jpeg"
    for i, name in enumerate(MODELS):
        try:
            m = gmodel if i == 0 else genai.GenerativeModel(name, system_instruction=SYSTEM, safety_settings=SAFETY)
            return m.generate_content([prompt, {"mime_type": mime, "data": byt}]).text
        except Exception as e:
            logger.error(f"img {name}: {e}")
    return "⚠️ Не удалось проанализировать изображение."

async def ask_ai(msg, hist, pctx): return await asyncio.to_thread(_ask, msg, hist, pctx)
async def img_ai(b, pctx, cap=""): return await asyncio.to_thread(_img, b, pctx, cap)

def num(t):
    m = re.search(r"\b(\d{1,3})\b", t)
    return int(m.group(1)) if m else None

def pctx(p):
    pts = []
    if p.get("gender"):     pts.append("Пол: " + ("мужской" if p["gender"] == "male" else "женский"))
    if p.get("age"):        pts.append(f"Возраст: {p['age']} лет")
    if p.get("weight"):     pts.append(f"Вес: {p['weight']} кг")
    if p.get("height"):     pts.append(f"Рост: {p['height']} см")
    if p.get("conditions"): pts.append(f"Заболевания: {p['conditions']}")
    return "; ".join(pts) or "Данные не указаны"

def fmt(p):
    if not p or not p.get("age"): return "📋 *Медкарта пуста.* Используйте /start"
    lines = ["📋 *Ваша медицинская карта*\n"]
    if p.get("gender"):     lines.append("• *Пол:* " + ("Мужской" if p["gender"] == "male" else "Женский"))
    if p.get("age"):        lines.append(f"• *Возраст:* {p['age']} лет")
    if p.get("weight"):     lines.append(f"• *Вес:* {p['weight']} кг")
    if p.get("height"):     lines.append(f"• *Рост:* {p['height']} см")
    if p.get("conditions"): lines.append(f"• *Заболевания:* {p['conditions']}")
    return "\n".join(lines)

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid, name = u.effective_user.id, u.effective_user.first_name
    p = get_p(uid)
    if not p or not p.get("age"):
        await u.message.reply_text(f"👋 Здравствуйте, *{name}*!\n\nЯ — медицинский ассистент на базе ИИ.\nЗаполним медкарту.\n\n*Шаг 1/5:* Укажите пол:", parse_mode=ParseMode.MARKDOWN, reply_markup=GENDER_KB)
        return STATE_ASK_GENDER
    await u.message.reply_text(f"👋 С возвращением, *{name}*!", parse_mode=ParseMode.MARKDOWN, reply_markup=MENU_KB)
    return STATE_MENU

async def h_gender(u: Update, c: ContextTypes.DEFAULT_TYPE):
    t = u.message.text.lower(); uid = u.effective_user.id
    if "муж" in t: g = "male"
    elif "жен" in t: g = "female"
    else:
        await u.message.reply_text("Выберите пол кнопками:", reply_markup=GENDER_KB)
        return STATE_ASK_GENDER
    set_p(uid, gender=g)
    await u.message.reply_text("✅ *Шаг 2/5:* Сколько лет? _(например: 34)_", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
    return STATE_ASK_AGE

async def h_age(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id; v = num(u.message.text)
    if not v or not (1 <= v <= 120):
        await u.message.reply_text("⚠️ Напишите возраст числом, например *34*:", parse_mode=ParseMode.MARKDOWN)
        return STATE_ASK_AGE
    set_p(uid, age=v)
    await u.message.reply_text(f"✅ {v} лет.\n\n*Шаг 3/5:* Вес в кг?", parse_mode=ParseMode.MARKDOWN, reply_markup=SKIP_KB)
    return STATE_ASK_WEIGHT

async def h_weight(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id; t = u.message.text
    if "пропуст" in t.lower() or "⏭" in t: v = None
    else:
        v = num(t)
        if not v or not (20 <= v <= 300):
            await u.message.reply_text("⚠️ Напишите вес числом или «Пропустить»:", reply_markup=SKIP_KB)
            return STATE_ASK_WEIGHT
    if v: set_p(uid, weight=v)
    await u.message.reply_text(f"✅ {'Принято.' if v else 'Пропущено.'}\n\n*Шаг 4/5:* Рост в см?", parse_mode=ParseMode.MARKDOWN, reply_markup=SKIP_KB)
    return STATE_ASK_HEIGHT

async def h_height(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id; t = u.message.text
    if "пропуст" in t.lower() or "⏭" in t: v = None
    else:
        v = num(t)
        if not v or not (50 <= v <= 250):
            await u.message.reply_text("⚠️ Напишите рост числом или «Пропустить»:", reply_markup=SKIP_KB)
            return STATE_ASK_HEIGHT
    if v: set_p(uid, height=v)
    await u.message.reply_text(f"✅ {'Принято.' if v else 'Пропущено.'}\n\n*Шаг 5/5:* Хронические заболевания, аллергии?", parse_mode=ParseMode.MARKDOWN, reply_markup=SKIP_KB)
    return STATE_ASK_CONDITIONS

async def h_conditions(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id; t = u.message.text.strip()
    if "пропуст" not in t.lower() and "⏭" not in t: set_p(uid, conditions=t)
    await u.message.reply_text("🎉 *Медкарта заполнена!*\n\nЗадайте медицинский вопрос.\n\n⚠️ _Ответы информационны и не заменяют врача._", parse_mode=ParseMode.MARKDOWN, reply_markup=MENU_KB)
    return STATE_MENU

async def h_menu(u: Update, c: ContextTypes.DEFAULT_TYPE):
    t = u.message.text; uid = u.effective_user.id
    tl = t.lower()
    if "медкарт" in tl:
        await u.message.reply_text(fmt(get_p(uid)), parse_mode=ParseMode.MARKDOWN, reply_markup=MENU_KB)
        return STATE_MENU
    if "анализ" in tl:
        await u.message.reply_text("🔬 Пришлите фото медицинского документа:", reply_markup=BACK_KB)
        return STATE_PHOTO
    if "sos" in tl:
        await u.message.reply_text("🆘 *ЭКСТРЕННАЯ ПОМОЩЬ*\n\n📞 Скорая: *103*\n📞 Единый: *112*\n\nОпишите ситуацию:", parse_mode=ParseMode.MARKDOWN, reply_markup=MENU_KB)
        return STATE_CHAT
    if "консультац" in tl:
        await u.message.reply_text("💊 Задайте ваш вопрос:", reply_markup=MENU_KB)
        return STATE_CHAT
    if "меню" in tl or "🔙" in t:
        await u.message.reply_text("Главное меню:", reply_markup=MENU_KB)
        return STATE_MENU
    return await h_chat(u, c)

async def h_chat(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id; text = u.message.text.strip()
    p = get_p(uid)
    if not p or not p.get("age"):
        await u.message.reply_text("⚠️ Сначала заполните медкарту. Укажите пол:", reply_markup=GENDER_KB)
        return STATE_ASK_GENDER
    await u.message.chat.send_action(ChatAction.TYPING)
    add_msg(uid, "user", text)
    try:
        reply = await ask_ai(text, get_hist(uid), pctx(p))
    except Exception as e:
        logger.error(f"chat error: {e}", exc_info=True)
        reply = "⚠️ Ошибка ИИ. Попробуйте ещё раз."
    add_msg(uid, "assistant", reply)
    await u.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN, reply_markup=MENU_KB)
    return STATE_MENU

async def h_photo(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id
    if u.message.text:
        t = u.message.text
        if "меню" in t.lower() or "🔙" in t:
            await u.message.reply_text("Главное меню:", reply_markup=MENU_KB)
            return STATE_MENU
        await u.message.reply_text("Пришлите фото или нажмите «🔙 Меню».")
        return STATE_PHOTO
    ph = u.message.photo; doc = u.message.document
    if not ph and not doc:
        await u.message.reply_text("Пожалуйста, пришлите фото.")
        return STATE_PHOTO
    await u.message.reply_text("🔍 Анализирую...")
    await u.message.chat.send_action(ChatAction.TYPING)
    try:
        f = await (u.message.photo[-1] if ph else doc).get_file()
        byt = bytes(await f.download_as_bytearray())
        p = get_p(uid); cap = u.message.caption or ""
        reply = await img_ai(byt, pctx(p), cap)
        add_msg(uid, "user", f"[Фото]{' ' + cap if cap else ''}")
        add_msg(uid, "assistant", reply)
        await u.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN, reply_markup=MENU_KB)
    except Exception as e:
        logger.error(f"photo error: {e}", exc_info=True)
        await u.message.reply_text("⚠️ Не удалось обработать фото.", reply_markup=MENU_KB)
    return STATE_MENU

async def cancel(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("Отменено.", reply_markup=MENU_KB)
    return STATE_MENU

async def reset(u: Update, c: ContextTypes.DEFAULT_TYPE):
    set_p(u.effective_user.id, gender=None, age=None, weight=None, height=None, conditions=None)
    await u.message.reply_text("🔄 Профиль сброшен. Укажите пол:", reply_markup=GENDER_KB)
    return STATE_ASK_GENDER

async def on_error(update: object, c: ContextTypes.DEFAULT_TYPE):
    logger.error("Global error:", exc_info=c.error)
    if isinstance(update, Update) and update.effective_message:
        try: await update.effective_message.reply_text("⚠️ Ошибка. Попробуйте /start")
        except Exception: pass

def main():
    token      = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not token:
        logger.critical("TELEGRAM_BOT_TOKEN не задан!")
        sys.exit(1)
    if not gemini_key:
        logger.critical("GEMINI_API_KEY не задан!")
        sys.exit(1)

    init_db()
    setup_gemini(gemini_key)

    app = Application.builder().token(token).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATE_ASK_GENDER:     [MessageHandler(filters.TEXT & ~filters.COMMAND, h_gender)],
            STATE_ASK_AGE:        [MessageHandler(filters.TEXT & ~filters.COMMAND, h_age)],
            STATE_ASK_WEIGHT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, h_weight)],
            STATE_ASK_HEIGHT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, h_height)],
            STATE_ASK_CONDITIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, h_conditions)],
            STATE_MENU:  [MessageHandler(filters.TEXT & ~filters.COMMAND, h_menu),
                          MessageHandler(filters.PHOTO | filters.Document.IMAGE, h_photo)],
            STATE_CHAT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, h_chat),
                          MessageHandler(filters.PHOTO | filters.Document.IMAGE, h_photo)],
            STATE_PHOTO: [MessageHandler(filters.PHOTO | filters.Document.IMAGE, h_photo),
                          MessageHandler(filters.TEXT & ~filters.COMMAND, h_photo)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("reset", reset))
    app.add_error_handler(on_error)

    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    port   = int(os.environ.get("PORT", 8080))

    if domain:
        url_path = "webhook"
        logger.info(f"Webhook mode: https://{domain}/{url_path} port={port}")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=url_path,
            webhook_url=f"https://{domain}/{url_path}",
            drop_pending_updates=True,
        )
    else:
        logger.info("Polling mode")
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
