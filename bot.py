import asyncio, logging, os, re, sqlite3, sys
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

S_MENU,S_GENDER,S_AGE,S_WEIGHT,S_HEIGHT,S_COND,S_CHAT,S_PHOTO = range(8)

MENU_KB   = ReplyKeyboardMarkup([["💊 Консультация","📋 Медкарта"],["🔬 Анализы (фото)","🆘 SOS"]], resize_keyboard=True)
GENDER_KB = ReplyKeyboardMarkup([["👨 Мужской","👩 Женский"]], resize_keyboard=True, one_time_keyboard=True)
SKIP_KB   = ReplyKeyboardMarkup([["⏭ Пропустить"]], resize_keyboard=True, one_time_keyboard=True)
BACK_KB   = ReplyKeyboardMarkup([["🔙 Меню"]], resize_keyboard=True)

DB = "bot.db"
def init_db():
    with sqlite3.connect(DB) as c:
        c.execute("CREATE TABLE IF NOT EXISTS u (uid INTEGER PRIMARY KEY, gender TEXT, age INTEGER, weight INTEGER, height INTEGER, cond TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS m (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, role TEXT, txt TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP)")
    log.info("DB OK")

def gp(uid):
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM u WHERE uid=?", (uid,)).fetchone()
        return dict(r) if r else {}

def sp(uid, **kw):
    with sqlite3.connect(DB) as c:
        c.execute("INSERT OR IGNORE INTO u (uid) VALUES (?)", (uid,))
        if kw:
            c.execute("UPDATE u SET " + ", ".join(f"{k}=?" for k in kw) + " WHERE uid=?", list(kw.values())+[uid])

def am(uid, role, txt):
    with sqlite3.connect(DB) as c:
        c.execute("INSERT OR IGNORE INTO u (uid) VALUES (?)", (uid,))
        c.execute("INSERT INTO m (uid,role,txt) VALUES (?,?,?)", (uid, role, txt[:3000]))

def gh(uid, n=8):
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT role,txt FROM (SELECT role,txt,ts FROM m WHERE uid=? ORDER BY ts DESC LIMIT ?) ORDER BY ts", (uid,n)).fetchall()
        return [(r["role"],r["txt"]) for r in rows]

SYS = "Ты элитный врач-терапевт с 30-летним опытом. Медицинский ассистент в Telegram. Учитывай профиль пациента. Отвечай подробно с Markdown. Объясняй термины просто. Указывай когда нужна срочная помощь."
SAF = {HarmCategory.HARM_CATEGORY_HARASSMENT:HarmBlockThreshold.BLOCK_ONLY_HIGH,HarmCategory.HARM_CATEGORY_HATE_SPEECH:HarmBlockThreshold.BLOCK_ONLY_HIGH,HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT:HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT:HarmBlockThreshold.BLOCK_ONLY_HIGH}
MDL = ["gemini-1.5-flash","gemini-1.5-pro","gemini-pro"]
gm = None

def setup(key):
    global gm
    genai.configure(api_key=key)
    gm = genai.GenerativeModel(MDL[0], system_instruction=SYS, safety_settings=SAF, generation_config=genai.types.GenerationConfig(temperature=0.7, max_output_tokens=2048))
    log.info(f"Gemini: {MDL[0]}")

def _ask(msg, hist, ctx):
    gh2 = [{"role":"model" if r=="assistant" else "user","parts":[c]} for r,c in hist[:-1]]
    txt = f"[Пациент: {ctx}]\n\n{msg}"
    for i,n in enumerate(MDL):
        try:
            m = gm if i==0 else genai.GenerativeModel(n, system_instruction=SYS, safety_settings=SAF)
            return m.start_chat(history=gh2).send_message(txt).text
        except Exception as e:
            log.error(f"{n}: {e}")
    return "⚠️ ИИ недоступен. Попробуйте позже."

def _img(b, ctx, cap):
    p = f"[Пациент: {ctx}]\nРасшифруй меддокумент: тип, показатели, нормы, отклонения, рекомендации." + (f"\n{cap}" if cap else "")
    mime = "image/png" if b[:4]==b'\x89PNG' else "image/jpeg"
    for i,n in enumerate(MDL):
        try:
            m = gm if i==0 else genai.GenerativeModel(n, system_instruction=SYS, safety_settings=SAF)
            return m.generate_content([p,{"mime_type":mime,"data":b}]).text
        except Exception as e:
            log.error(f"img {n}: {e}")
    return "⚠️ Не удалось обработать фото."

async def ai(msg,hist,ctx): return await asyncio.to_thread(_ask,msg,hist,ctx)
async def ai_img(b,ctx,cap=""): return await asyncio.to_thread(_img,b,ctx,cap)

def num(t):
    m=re.search(r"\b(\d{1,3})\b",t)
    return int(m.group(1)) if m else None

def mkctx(p):
    r=[]
    if p.get("gender"): r.append("Пол: "+("мужской" if p["gender"]=="male" else "женский"))
    if p.get("age"):    r.append(f"Возраст: {p['age']} лет")
    if p.get("weight"): r.append(f"Вес: {p['weight']} кг")
    if p.get("height"): r.append(f"Рост: {p['height']} см")
    if p.get("cond"):   r.append(f"Заболевания: {p['cond']}")
    return "; ".join(r) or "Нет данных"

def mkcard(p):
    if not p or not p.get("age"): return "📋 *Медкарта пуста.* Используйте /start"
    r=["📋 *Ваша медицинская карта*\n"]
    if p.get("gender"): r.append("• *Пол:* "+("Мужской" if p["gender"]=="male" else "Женский"))
    if p.get("age"):    r.append(f"• *Возраст:* {p['age']} лет")
    if p.get("weight"): r.append(f"• *Вес:* {p['weight']} кг")
    if p.get("height"): r.append(f"• *Рост:* {p['height']} см")
    if p.get("cond"):   r.append(f"• *Заболевания:* {p['cond']}")
    return "\n".join(r)

async def cmd_start(u,c):
    uid,name=u.effective_user.id,u.effective_user.first_name
    p=gp(uid)
    if not p or not p.get("age"):
        await u.message.reply_text(f"👋 Здравствуйте, *{name}*!\n\nЯ медицинский ассистент на базе ИИ.\nЗаполним медкарту.\n\n*Шаг 1/5:* Укажите пол:",parse_mode=ParseMode.MARKDOWN,reply_markup=GENDER_KB)
        return S_GENDER
    await u.message.reply_text(f"👋 С возвращением, *{name}*!",parse_mode=ParseMode.MARKDOWN,reply_markup=MENU_KB)
    return S_MENU

async def h_gender(u,c):
    t=u.message.text.lower();uid=u.effective_user.id
    if "муж" in t: g="male"
    elif "жен" in t: g="female"
    else:
        await u.message.reply_text("Выберите пол кнопками:",reply_markup=GENDER_KB)
        return S_GENDER
    sp(uid,gender=g)
    await u.message.reply_text("✅ *Шаг 2/5:* Сколько лет? _(например: 34)_",parse_mode=ParseMode.MARKDOWN,reply_markup=ReplyKeyboardRemove())
    return S_AGE

async def h_age(u,c):
    uid=u.effective_user.id;v=num(u.message.text)
    if not v or not (1<=v<=120):
        await u.message.reply_text("⚠️ Напишите возраст числом, например *34*:",parse_mode=ParseMode.MARKDOWN)
        return S_AGE
    sp(uid,age=v)
    await u.message.reply_text(f"✅ {v} лет.\n\n*Шаг 3/5:* Вес в кг?",parse_mode=ParseMode.MARKDOWN,reply_markup=SKIP_KB)
    return S_WEIGHT

async def h_weight(u,c):
    uid=u.effective_user.id;t=u.message.text
    v=None if ("пропуст" in t.lower() or "⏭" in t) else num(t)
    if v is not None and not (20<=v<=300):
        await u.message.reply_text("⚠️ Напишите вес числом или «Пропустить»:",reply_markup=SKIP_KB)
        return S_WEIGHT
    if v: sp(uid,weight=v)
    await u.message.reply_text(f"✅ {'Принято.' if v else 'Пропущено.'}\n\n*Шаг 4/5:* Рост в см?",parse_mode=ParseMode.MARKDOWN,reply_markup=SKIP_KB)
    return S_HEIGHT

async def h_height(u,c):
    uid=u.effective_user.id;t=u.message.text
    v=None if ("пропуст" in t.lower() or "⏭" in t) else num(t)
    if v is not None and not (50<=v<=250):
        await u.message.reply_text("⚠️ Напишите рост числом или «Пропустить»:",reply_markup=SKIP_KB)
        return S_HEIGHT
    if v: sp(uid,height=v)
    await u.message.reply_text(f"✅ {'Принято.' if v else 'Пропущено.'}\n\n*Шаг 5/5:* Хронические заболевания, аллергии?",parse_mode=ParseMode.MARKDOWN,reply_markup=SKIP_KB)
    return S_COND

async def h_cond(u,c):
    uid=u.effective_user.id;t=u.message.text.strip()
    if "пропуст" not in t.lower() and "⏭" not in t: sp(uid,cond=t)
    await u.message.reply_text("🎉 *Медкарта заполнена!*\n\nЗадайте медицинский вопрос.\n\n⚠️ _Ответы не заменяют врача._",parse_mode=ParseMode.MARKDOWN,reply_markup=MENU_KB)
    return S_MENU

async def h_menu(u,c):
    t=u.message.text;uid=u.effective_user.id;tl=t.lower()
    if "медкарт" in tl:
        await u.message.reply_text(mkcard(gp(uid)),parse_mode=ParseMode.MARKDOWN,reply_markup=MENU_KB)
        return S_MENU
    if "анализ" in tl:
        await u.message.reply_text("🔬 Пришлите фото медицинского документа:",reply_markup=BACK_KB)
        return S_PHOTO
    if "sos" in tl:
        await u.message.reply_text("🆘 *ЭКСТРЕННАЯ ПОМОЩЬ*\n\n📞 Скорая: *103*\n📞 Единый: *112*\n\nОпишите ситуацию:",parse_mode=ParseMode.MARKDOWN,reply_markup=MENU_KB)
        return S_CHAT
    if "консультац" in tl:
        await u.message.reply_text("💊 Задайте ваш вопрос:",reply_markup=MENU_KB)
        return S_CHAT
    if "меню" in tl or "🔙" in t:
        await u.message.reply_text("Главное меню:",reply_markup=MENU_KB)
        return S_MENU
    return await h_chat(u,c)

async def h_chat(u,c):
    uid=u.effective_user.id;txt=u.message.text.strip();p=gp(uid)
    if not p or not p.get("age"):
        await u.message.reply_text("⚠️ Сначала заполните медкарту:",reply_markup=GENDER_KB)
        return S_GENDER
    await u.message.chat.send_action(ChatAction.TYPING)
    am(uid,"user",txt)
    try: reply=await ai(txt,gh(uid),mkctx(p))
    except Exception as e:
        log.error(f"chat:{e}",exc_info=True);reply="⚠️ Ошибка ИИ. Попробуйте ещё раз."
    am(uid,"assistant",reply)
    await u.message.reply_text(reply,parse_mode=ParseMode.MARKDOWN,reply_markup=MENU_KB)
    return S_MENU

async def h_photo(u,c):
    uid=u.effective_user.id
    if u.message.text:
        if "меню" in u.message.text.lower() or "🔙" in u.message.text:
            await u.message.reply_text("Главное меню:",reply_markup=MENU_KB);return S_MENU
        await u.message.reply_text("Пришлите фото или нажмите «🔙 Меню».")
        return S_PHOTO
    ph=u.message.photo;doc=u.message.document
    if not ph and not doc:
        await u.message.reply_text("Пожалуйста, пришлите фото.");return S_PHOTO
    await u.message.reply_text("🔍 Анализирую...")
    await u.message.chat.send_action(ChatAction.TYPING)
    try:
        f=await (u.message.photo[-1] if ph else doc).get_file()
        b=bytes(await f.download_as_bytearray());p=gp(uid);cap=u.message.caption or ""
        reply=await ai_img(b,mkctx(p),cap)
        am(uid,"user",f"[Фото]{chr(32)+cap if cap else ""}")
        am(uid,"assistant",reply)
        await u.message.reply_text(reply,parse_mode=ParseMode.MARKDOWN,reply_markup=MENU_KB)
    except Exception as e:
        log.error(f"photo:{e}",exc_info=True)
        await u.message.reply_text("⚠️ Не удалось обработать фото.",reply_markup=MENU_KB)
    return S_MENU

async def h_cancel(u,c):
    await u.message.reply_text("Отменено.",reply_markup=MENU_KB);return S_MENU

async def h_reset(u,c):
    sp(u.effective_user.id,gender=None,age=None,weight=None,height=None,cond=None)
    await u.message.reply_text("🔄 Профиль сброшен:",reply_markup=GENDER_KB);return S_GENDER

async def h_err(update,c):
    log.error("ERR:",exc_info=c.error)
    if isinstance(update,Update) and update.effective_message:
        try: await update.effective_message.reply_text("⚠️ Ошибка. /start")
        except: pass

def main():
    token=os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN","")
    key=os.environ.get("GEMINI_API_KEY","")
    if not token: log.critical("НЕТ ТОКЕНА!"); sys.exit(1)
    if not key:   log.critical("НЕТ GEMINI KEY!"); sys.exit(1)
    init_db(); setup(key)
    app=Application.builder().token(token).build()
    conv=ConversationHandler(
        entry_points=[CommandHandler("start",cmd_start)],
        states={
            S_GENDER:[MessageHandler(filters.TEXT&~filters.COMMAND,h_gender)],
            S_AGE:   [MessageHandler(filters.TEXT&~filters.COMMAND,h_age)],
            S_WEIGHT:[MessageHandler(filters.TEXT&~filters.COMMAND,h_weight)],
            S_HEIGHT:[MessageHandler(filters.TEXT&~filters.COMMAND,h_height)],
            S_COND:  [MessageHandler(filters.TEXT&~filters.COMMAND,h_cond)],
            S_MENU:  [MessageHandler(filters.TEXT&~filters.COMMAND,h_menu),MessageHandler(filters.PHOTO|filters.Document.IMAGE,h_photo)],
            S_CHAT:  [MessageHandler(filters.TEXT&~filters.COMMAND,h_chat),MessageHandler(filters.PHOTO|filters.Document.IMAGE,h_photo)],
            S_PHOTO: [MessageHandler(filters.PHOTO|filters.Document.IMAGE,h_photo),MessageHandler(filters.TEXT&~filters.COMMAND,h_photo)],
        },
        fallbacks=[CommandHandler("cancel",h_cancel),CommandHandler("start",cmd_start)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("reset",h_reset))
    app.add_error_handler(h_err)
    domain=os.environ.get("RAILWAY_PUBLIC_DOMAIN","")
    port=int(os.environ.get("PORT",8080))
    if domain:
        log.info(f"Webhook: https://{domain}/wh port={port}")
        app.run_webhook(listen="0.0.0.0",port=port,url_path="wh",webhook_url=f"https://{domain}/wh",drop_pending_updates=True)
    else:
        log.info("Polling")
        app.run_polling(allowed_updates=Update.ALL_TYPES,drop_pending_updates=True)

if __name__=="__main__":
    main()
