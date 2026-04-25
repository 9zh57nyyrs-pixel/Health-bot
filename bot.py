"""
Medical Consultation Telegram Bot
Powered by Gemini 1.5 Flash | python-telegram-bot v20+
"""

import asyncio
import logging
import os
import re
import sys
from io import BytesIO

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from database import (
    init_db,
    get_user_profile,
    update_user_profile,
    save_message,
    get_history,
    clear_history,
)
from gemini_client import GeminiClient

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ─── Conversation States ──────────────────────────────────────────────────────

(
    STATE_MENU,
    STATE_ASK_GENDER,
    STATE_ASK_AGE,
    STATE_ASK_WEIGHT,
    STATE_ASK_HEIGHT,
    STATE_ASK_CONDITIONS,
    STATE_CHAT,
    STATE_WAITING_PHOTO,
) = range(8)

# ─── Keyboard Layouts ─────────────────────────────────────────────────────────

MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["💊 Консультация", "📋 Моя медкарта"],
        ["🔬 Анализы (фото)", "🆘 SOS"],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

GENDER_KEYBOARD = ReplyKeyboardMarkup(
    [["👨 Мужской", "👩 Женский"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

SKIP_KEYBOARD = ReplyKeyboardMarkup(
    [["⏭ Пропустить"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def extract_number(text: str) -> int | None:
    """Extract first integer from free-form text using regex."""
    match = re.search(r"\b(\d{1,3})\b", text)
    if match:
        return int(match.group(1))
    return None


def format_profile(profile: dict) -> str:
    """Format user profile for display."""
    lines = ["📋 *Ваша медицинская карта*\n"]
    fields = {
        "gender": ("Пол", lambda v: "Мужской" if v == "male" else "Женский"),
        "age": ("Возраст", lambda v: f"{v} лет"),
        "weight": ("Вес", lambda v: f"{v} кг"),
        "height": ("Рост", lambda v: f"{v} см"),
        "conditions": ("Хронические заболевания", lambda v: v or "Не указаны"),
    }
    any_data = False
    for key, (label, formatter) in fields.items():
        val = profile.get(key)
        if val is not None and val != "":
            lines.append(f"• *{label}:* {formatter(val)}")
            any_data = True
    if not any_data:
        lines.append("_Профиль не заполнен. Используйте /start для опроса._")
    return "\n".join(lines)


def build_context_summary(profile: dict) -> str:
    """Build a short patient context string for Gemini."""
    parts = []
    if profile.get("gender"):
        parts.append("Пол: " + ("мужской" if profile["gender"] == "male" else "женский"))
    if profile.get("age"):
        parts.append(f"Возраст: {profile['age']} лет")
    if profile.get("weight"):
        parts.append(f"Вес: {profile['weight']} кг")
    if profile.get("height"):
        parts.append(f"Рост: {profile['height']} см")
    if profile.get("conditions"):
        parts.append(f"Хронические заболевания: {profile['conditions']}")
    if not parts:
        return "Данные пациента не предоставлены."
    return "Данные пациента: " + "; ".join(parts) + "."


# ─── Handler: /start ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    uid = user.id
    logger.info(f"/start от пользователя {uid} (@{user.username})")

    profile = get_user_profile(uid)
    is_new = not profile or not profile.get("age")

    if is_new:
        await update.message.reply_text(
            f"👋 Здравствуйте, *{user.first_name}*!\n\n"
            "Я — ваш персональный медицинский ассистент на базе ИИ.\n"
            "Чтобы давать точные рекомендации, мне нужно узнать о вас немного больше.\n\n"
            "📝 Давайте заполним вашу медкарту. Это займёт ~1 минуту.\n\n"
            "*Шаг 1/5:* Укажите ваш пол:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=GENDER_KEYBOARD,
        )
        return STATE_ASK_GENDER
    else:
        await update.message.reply_text(
            f"👋 С возвращением, *{user.first_name}*!\n\n"
            "Ваш профиль загружен. Чем могу помочь?\n"
            "Задайте вопрос или выберите действие в меню ниже.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return STATE_MENU


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reset profile and start over."""
    uid = update.effective_user.id
    update_user_profile(uid, gender=None, age=None, weight=None, height=None, conditions=None)
    clear_history(uid)
    logger.info(f"Пользователь {uid} сбросил профиль.")
    await update.message.reply_text(
        "🔄 Профиль сброшен. Начинаем заново!\n\nУкажите ваш пол:",
        reply_markup=GENDER_KEYBOARD,
    )
    return STATE_ASK_GENDER


# ─── Onboarding Handlers ──────────────────────────────────────────────────────

async def handle_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.lower()
    uid = update.effective_user.id

    if "муж" in text:
        gender = "male"
    elif "жен" in text:
        gender = "female"
    else:
        await update.message.reply_text(
            "Пожалуйста, выберите пол с помощью кнопок ниже:",
            reply_markup=GENDER_KEYBOARD,
        )
        return STATE_ASK_GENDER

    update_user_profile(uid, gender=gender)
    logger.info(f"Пользователь {uid}: пол = {gender}")

    await update.message.reply_text(
        "✅ Отлично!\n\n*Шаг 2/5:* Сколько вам лет?\n_(можно написать, например: «мне 34 года»)_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )
    return STATE_ASK_AGE


async def handle_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    uid = update.effective_user.id
    age = extract_number(text)

    if age is None or not (1 <= age <= 120):
        await update.message.reply_text(
            "⚠️ Не смог распознать возраст. Пожалуйста, напишите число, например: *34*",
            parse_mode=ParseMode.MARKDOWN,
        )
        return STATE_ASK_AGE

    update_user_profile(uid, age=age)
    logger.info(f"Пользователь {uid}: возраст = {age}")

    await update.message.reply_text(
        f"✅ Принято: {age} лет.\n\n*Шаг 3/5:* Ваш вес?\n_(в килограммах, например: «70» или «вешу 85 кг»)_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=SKIP_KEYBOARD,
    )
    return STATE_ASK_WEIGHT


async def handle_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    uid = update.effective_user.id

    if "пропуст" in text.lower() or text.strip() == "⏭ Пропустить":
        weight = None
    else:
        weight = extract_number(text)
        if weight is None or not (20 <= weight <= 300):
            await update.message.reply_text(
                "⚠️ Не смог распознать вес. Напишите число (например: *75*) или нажмите «Пропустить».",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=SKIP_KEYBOARD,
            )
            return STATE_ASK_WEIGHT

    if weight:
        update_user_profile(uid, weight=weight)
    logger.info(f"Пользователь {uid}: вес = {weight}")

    await update.message.reply_text(
        f"✅ {'Принято: ' + str(weight) + ' кг.' if weight else 'Пропущено.'}\n\n"
        "*Шаг 4/5:* Ваш рост?\n_(в сантиметрах, например: «172»)_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=SKIP_KEYBOARD,
    )
    return STATE_ASK_HEIGHT


async def handle_height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    uid = update.effective_user.id

    if "пропуст" in text.lower() or text.strip() == "⏭ Пропустить":
        height = None
    else:
        height = extract_number(text)
        if height is None or not (50 <= height <= 250):
            await update.message.reply_text(
                "⚠️ Не смог распознать рост. Напишите число (например: *172*) или нажмите «Пропустить».",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=SKIP_KEYBOARD,
            )
            return STATE_ASK_HEIGHT

    if height:
        update_user_profile(uid, height=height)
    logger.info(f"Пользователь {uid}: рост = {height}")

    await update.message.reply_text(
        f"✅ {'Принято: ' + str(height) + ' см.' if height else 'Пропущено.'}\n\n"
        "*Шаг 5/5 (последний):* Есть ли у вас хронические заболевания, аллергии или важные особенности здоровья?\n\n"
        "_Например: «диабет 2 типа, аллергия на пенициллин» или нажмите «Пропустить»_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=SKIP_KEYBOARD,
    )
    return STATE_ASK_CONDITIONS


async def handle_conditions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    uid = update.effective_user.id

    if "пропуст" in text.lower() or text == "⏭ Пропустить":
        conditions = None
    else:
        conditions = text

    if conditions:
        update_user_profile(uid, conditions=conditions)
    logger.info(f"Пользователь {uid}: заболевания = {conditions}")

    await update.message.reply_text(
        "🎉 *Отлично! Ваша медкарта заполнена.*\n\n"
        "Теперь я буду учитывать ваши данные при каждой консультации.\n"
        "Задайте любой медицинский вопрос или выберите действие в меню ниже.\n\n"
        "⚠️ _Напоминание: я — ИИ-ассистент. Мои ответы не заменяют визит к врачу._",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=MAIN_MENU_KEYBOARD,
    )
    return STATE_MENU


# ─── Main Menu Handler ────────────────────────────────────────────────────────

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    uid = update.effective_user.id

    if "медкарт" in text.lower():
        profile = get_user_profile(uid)
        await update.message.reply_text(
            format_profile(profile or {}),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return STATE_MENU

    elif "анализ" in text.lower():
        await update.message.reply_text(
            "🔬 *Режим анализа медицинских документов*\n\n"
            "Пришлите фото анализов, снимка или медицинского документа — "
            "я постараюсь его расшифровать и объяснить результаты.\n\n"
            "_Поддерживаются фото лабораторных анализов, ЭКГ, рентгенов и т.д._",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardMarkup(
                [["🔙 Главное меню"]],
                resize_keyboard=True,
            ),
        )
        return STATE_WAITING_PHOTO

    elif "sos" in text.lower():
        await update.message.reply_text(
            "🆘 *ЭКСТРЕННАЯ ПОМОЩЬ*\n\n"
            "📞 *Скорая помощь:* 103 (Россия)\n"
            "📞 *Единый экстренный:* 112\n"
            "📞 *Телефон доверия:* 8-800-2000-122\n\n"
            "━━━━━━━━━━━━━━━\n"
            "Если вы или кто-то рядом в опасности — *немедленно звоните 112*.\n\n"
            "Опишите вашу ситуацию, и я дам первичные рекомендации до приезда врача:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return STATE_CHAT

    elif "консультац" in text.lower():
        await update.message.reply_text(
            "💊 *Режим консультации*\n\n"
            "Опишите ваши симптомы или задайте медицинский вопрос.\n"
            "Я учту ваши данные из медкарты.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return STATE_CHAT

    elif "меню" in text.lower() or text == "🔙 Главное меню":
        await update.message.reply_text(
            "Главное меню:",
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return STATE_MENU

    else:
        # Any other text → treat as a consultation question
        return await handle_chat(update, context)


# ─── Chat Handler (AI Consultation) ──────────────────────────────────────────

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    user_text = update.message.text.strip()

    # Проверка: если профиль не заполнен — проактивно предлагаем
    profile = get_user_profile(uid)
    if not profile or not profile.get("age"):
        await update.message.reply_text(
            "⚠️ Я вижу, что вы ещё не заполнили медкарту.\n"
            "Для более точных рекомендаций давайте сначала пройдём короткий опрос.\n\n"
            "Укажите ваш пол:",
            reply_markup=GENDER_KEYBOARD,
        )
        return STATE_ASK_GENDER

    await update.message.chat.send_action(ChatAction.TYPING)

    # Сохраняем сообщение пользователя
    save_message(uid, "user", user_text)

    # Получаем историю
    history = get_history(uid, limit=10)
    patient_context = build_context_summary(profile)

    gemini: GeminiClient = context.bot_data["gemini"]

    try:
        response_text = await gemini.chat(
            user_message=user_text,
            history=history,
            patient_context=patient_context,
        )
    except Exception as e:
        logger.error(f"Ошибка Gemini для пользователя {uid}: {e}", exc_info=True)
        response_text = (
            "⚠️ Произошла ошибка при обращении к ИИ-сервису. "
            "Попробуйте повторить через несколько секунд или перезапустите бота командой /start."
        )

    # Сохраняем ответ
    save_message(uid, "assistant", response_text)

    await update.message.reply_text(
        response_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=MAIN_MENU_KEYBOARD,
    )
    return STATE_MENU


# ─── Photo Handler (Multimodal Analysis) ─────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id

    if update.message.text and ("меню" in update.message.text.lower() or "🔙" in update.message.text):
        await update.message.reply_text("Возвращаемся в главное меню.", reply_markup=MAIN_MENU_KEYBOARD)
        return STATE_MENU

    photo = update.message.photo
    document = update.message.document

    if not photo and not document:
        await update.message.reply_text(
            "Пожалуйста, пришлите *фото* медицинского документа или анализа.\n"
            "Или нажмите «🔙 Главное меню».",
            parse_mode=ParseMode.MARKDOWN,
        )
        return STATE_WAITING_PHOTO

    await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
    await update.message.reply_text("🔍 Анализирую изображение, подождите...")

    try:
        # Получаем файл
        if photo:
            file_obj = await update.message.photo[-1].get_file()
        else:
            file_obj = await document.get_file()

        file_bytes = await file_obj.download_as_bytearray()
        image_data = bytes(file_bytes)

        # Получаем профиль
        profile = get_user_profile(uid) or {}
        patient_context = build_context_summary(profile)
        caption = update.message.caption or ""

        gemini: GeminiClient = context.bot_data["gemini"]

        await update.message.chat.send_action(ChatAction.TYPING)

        response_text = await gemini.analyze_image(
            image_bytes=image_data,
            patient_context=patient_context,
            caption=caption,
        )

        save_message(uid, "user", f"[Фото анализа отправлено]{'. Комментарий: ' + caption if caption else ''}")
        save_message(uid, "assistant", response_text)

        await update.message.reply_text(
            response_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return STATE_MENU

    except Exception as e:
        logger.error(f"Ошибка анализа фото для пользователя {uid}: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Не удалось обработать изображение. Попробуйте прислать другое фото или повторите позже.",
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return STATE_MENU


# ─── Fallback & Error Handlers ────────────────────────────────────────────────

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Действие отменено. Вы в главном меню.",
        reply_markup=MAIN_MENU_KEYBOARD,
    )
    return STATE_MENU


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    history = get_history(uid, limit=5)
    if not history:
        await update.message.reply_text("История консультаций пуста.")
        return
    lines = ["📜 *Последние 5 сообщений:*\n"]
    for role, content, ts in history:
        icon = "👤" if role == "user" else "🤖"
        lines.append(f"{icon} _{ts}_\n{content[:200]}{'...' if len(content) > 200 else ''}\n")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Глобальная ошибка бота:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Произошла внутренняя ошибка. Попробуйте /start для перезапуска."
            )
        except Exception:
            pass


# ─── Application Bootstrap ────────────────────────────────────────────────────

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if not token:
        logger.critical("TELEGRAM_BOT_TOKEN не задан в переменных окружения!")
        sys.exit(1)
    if not gemini_key:
        logger.critical("GEMINI_API_KEY не задан в переменных окружения!")
        sys.exit(1)

    # Инициализация БД
    init_db()
    logger.info("База данных инициализирована.")

    # Инициализация Gemini
    gemini_client = GeminiClient(api_key=gemini_key)
    logger.info(f"Gemini клиент создан. Модель: {gemini_client.model_name}")

    # Создание приложения
    app = Application.builder().token(token).build()
    app.bot_data["gemini"] = gemini_client

    # ── Conversation Handler ──────────────────────────────────────────────────
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
        ],
        states={
            STATE_ASK_GENDER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gender),
            ],
            STATE_ASK_AGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age),
            ],
            STATE_ASK_WEIGHT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_weight),
            ],
            STATE_ASK_HEIGHT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_height),
            ],
            STATE_ASK_CONDITIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conditions),
            ],
            STATE_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo),
            ],
            STATE_CHAT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo),
            ],
            STATE_WAITING_PHOTO: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_photo),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True,
        name="medical_consultation",
        persistent=False,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_error_handler(error_handler)

    logger.info("🤖 Бот запускается...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
