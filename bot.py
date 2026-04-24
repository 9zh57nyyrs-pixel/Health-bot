import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from config import TELEGRAM_TOKEN
from database import (
    init_db,
    save_user,
    save_health_record,
    get_health_records,
    save_conversation,
    get_conversation_history,
    get_user_info,
    update_user_info,
)
from claude_client import chat_with_claude, analyze_medical_image

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SETTING_AGE, SETTING_GENDER = range(2)

MAIN_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Вес"), KeyboardButton("Питание")],
        [KeyboardButton("Активность"), KeyboardButton("Анализы")],
        [KeyboardButton("Оценка здоровья"), KeyboardButton("План обследований")],
        [KeyboardButton("Мой профиль"), KeyboardButton("История")],
    ],
    resize_keyboard=True,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username, user.first_name)
    text = (
        "Здравствуйте, " + user.first_name + "!\n\n"
        "Я ваш личный ИИ-доктор. Могу помочь:\n\n"
        "Отслеживать вес, питание, активность\n"
        "Расшифровывать медицинские анализы по фото\n"
        "Составить план обследований\n"
        "Оценить ваше здоровье по шкале 1-10\n\n"
        "Важно: я ИИ-ассистент и не заменяю настоящего врача."
    )
    await update.message.reply_text(text, reply_markup=MAIN_KB)


async def handle_health_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    records = get_health_records(user_id, limit=20)
    history = get_conversation_history(user_id, limit=10)
    user_info = get_user_info(user_id)
    records_text = ""
    for r in records[:10]:
        records_text += "- " + r["record_type"] + ": " + r["value"] + "\n"
    msgs = [
        {"role": m["role"], "content": m["content"]}
        for m in history[-6:]
    ]
    msgs.append({
        "role": "user",
        "content": "Оцени моё здоровье по шкале 1-10 на основе данных:\n" + (records_text or "Данных пока нет"),
    })
    response = chat_with_claude(msgs, user_info)
    await update.message.reply_text(response, reply_markup=MAIN_KB)


async def handle_screening_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    if not user_info or not user_info["age"] or not user_info["gender"]:
        await update.message.reply_text(
            "Для составления плана укажите возраст и пол.\n"
            "Используйте команды /setage и /setgender"
        )
        return
    msgs = [{
        "role": "user",
        "content": (
            "Составь план обследований для человека: возраст "
            + str(user_info["age"])
            + " лет, пол: "
            + str(user_info["gender"])
        ),
    }]
    response = chat_with_claude(msgs, user_info)
    save_conversation(user_id, "user", "План обследований")
    save_conversation(user_id, "assistant", response)
    await update.message.reply_text(response, reply_markup=MAIN_KB)


async def handle_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user_info(user_id)
    text = (
        "Ваш профиль:\n\n"
        "Имя: " + (u["first_name"] if u else "Неизвестно") + "\n"
        "Возраст: " + str(u["age"] if u and u["age"] else "Не указан") + "\n"
        "Пол: " + str(u["gender"] if u and u["gender"] else "Не указан") + "\n\n"
        "Для обновления используйте /setage и /setgender"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KB)


async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    records = get_health_records(user_id, limit=10)
    if not records:
        await update.message.reply_text("Записей пока нет.", reply_markup=MAIN_KB)
        return
    text = "Ваши последние записи:\n\n"
    for r in records:
        text += str(r["recorded_at"])[:10] + " - " + r["record_type"] + ": " + r["value"] + "\n"
    await update.message.reply_text(text, reply_markup=MAIN_KB)


async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите ваш возраст:")
    return SETTING_AGE


async def receive_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        age = int(update.message.text.strip())
        if 1 <= age <= 120:
            update_user_info(update.effective_user.id, age=age)
            await update.message.reply_text(
                "Возраст сохранён: " + str(age) + " лет",
                reply_markup=MAIN_KB,
            )
        else:
            await update.message.reply_text("Введите корректный возраст (1-120)")
            return SETTING_AGE
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число")
        return SETTING_AGE
    return ConversationHandler.END


async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("Мужской"), KeyboardButton("Женский")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text("Выберите пол:", reply_markup=kb)
    return SETTING_GENDER


async def receive_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gender_map = {"мужской": "мужской", "женский": "женский"}
    gender = gender_map.get(update.message.text.strip().lower())
    if gender:
        update_user_info(update.effective_user.id, gender=gender)
        await update.message.reply_text("Пол сохранён: " + gender, reply_markup=MAIN_KB)
    else:
        await update.message.reply_text("Выберите Мужской или Женский")
        return SETTING_GENDER
    return ConversationHandler.END


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Анализирую изображение, подождите...")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    caption = update.message.caption or ""
    try:
        response = analyze_medical_image(bytes(image_bytes), "jpeg", caption)
        save_conversation(update.effective_user.id, "user", "[Фото анализа]")
        save_conversation(update.effective_user.id, "assistant", response)
        await update.message.reply_text(response, reply_markup=MAIN_KB)
    except Exception as e:
        logger.error("Image error: " + str(e))
        await update.message.reply_text(
            "Не удалось проанализировать фото. Попробуйте ещё раз.",
            reply_markup=MAIN_KB,
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    user_info = get_user_info(user_id)
    tl = text.lower().strip()

    if "вес" in tl:
        await update.message.reply_text("Введите ваш вес в кг (например: 70.5):")
        context.user_data["expecting"] = "вес"
        return
    if "питание" in tl:
        await update.message.reply_text("Опишите что вы сегодня ели:")
        context.user_data["expecting"] = "питание"
        return
    if "активность" in tl:
        await update.message.reply_text("Опишите вашу физическую активность:")
        context.user_data["expecting"] = "активность"
        return
    if "анализ" in tl:
        await update.message.reply_text("Отправьте фото результата анализа.")
        return
    if "оценка" in tl:
        await handle_health_score(update, context)
        return
    if "план" in tl:
        await handle_screening_plan(update, context)
        return
    if "профиль" in tl:
        await handle_profile(update, context)
        return
    if "история" in tl:
        await handle_history(update, context)
        return

    expecting = context.user_data.get("expecting")
    if expecting in ["вес", "питание", "активность"]:
        save_health_record(user_id, expecting, text)
        context.user_data.pop("expecting", None)
        history = get_conversation_history(user_id, limit=10)
        msgs = [{"role": m["role"], "content": m["content"]} for m in history]
        msgs.append({
            "role": "user",
            "content": "Я записал " + expecting + ": " + text + ". Прокомментируй кратко.",
        })
        response = chat_with_claude(msgs, user_info)
        save_conversation(user_id, "user", expecting + ": " + text)
        save_conversation(user_id, "assistant", response)
        await update.message.reply_text(response, reply_markup=MAIN_KB)
        return

    history = get_conversation_history(user_id, limit=20)
    msgs = [{"role": m["role"], "content": m["content"]} for m in history]
    msgs.append({"role": "user", "content": text})
    save_conversation(user_id, "user", text)
    try:
        response = chat_with_claude(msgs, user_info)
        save_conversation(user_id, "assistant", response)
        await update.message.reply_text(response, reply_markup=MAIN_KB)
    except Exception as e:
        logger.error("Claude error: " + str(e))
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте ещё раз.",
            reply_markup=MAIN_KB,
        )


def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    age_conv = ConversationHandler(
        entry_points=[CommandHandler("setage", set_age)],
        states={SETTING_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_age)]},
        fallbacks=[],
    )
    gender_conv = ConversationHandler(
        entry_points=[CommandHandler("setgender", set_gender)],
        states={SETTING_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_gender)]},
        fallbacks=[],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", handle_profile))
    app.add_handler(age_conv)
    app.add_handler(gender_conv)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
