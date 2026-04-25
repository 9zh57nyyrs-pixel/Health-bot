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
        [KeyboardButton("Моё здоровье"), KeyboardButton("Добавить данные")],
        [KeyboardButton("Мои анализы"), KeyboardButton("План обследований")],
        [KeyboardButton("Мой профиль"), KeyboardButton("История")],
    ],
    resize_keyboard=True,
)


def get_user_context(user_id):
    user_info = get_user_info(user_id)
    records = get_health_records(user_id, limit=50)
    history = get_conversation_history(user_id, limit=30)
    return user_info, records, history


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username, user.first_name)
    user_info = get_user_info(user.id)

    if user_info and user_info["age"]:
        text = (
            "С возвращением, " + user.first_name + "!\n\n"
            "Я помню вашу историю здоровья и готов продолжить работу. "
            "Расскажите, как вы себя чувствуете, или выберите действие в меню."
        )
    else:
        text = (
            "Здравствуйте, " + user.first_name + "!\n\n"
            "Я ваш персональный ИИ-врач. Я буду следить за вашим здоровьем, "
            "анализировать показатели и давать персональные рекомендации.\n\n"
            "Чтобы начать, расскажите немного о себе — сколько вам лет? "
            "Это поможет мне давать точные рекомендации."
        )
    await update.message.reply_text(text, reply_markup=MAIN_KB)


async def handle_my_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info, records, history = get_user_context(user_id)

    msgs = [{"role": m["role"], "content": m["content"]} for m in history[-10:]]
    msgs.append({
        "role": "user",
        "content": (
            "Дай мне общую оценку моего здоровья на основе всех имеющихся данных. "
            "Отметь динамику, что улучшилось, что требует внимания, "
            "и задай вопрос о том, что ещё важно знать для полной картины."
        ),
    })
    response = chat_with_claude(msgs, user_info, records)
    save_conversation(user_id, "user", "Запрос оценки здоровья")
    save_conversation(user_id, "assistant", response)
    await update.message.reply_text(response, reply_markup=MAIN_KB)


async def handle_add_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Что хотите записать? Просто напишите в свободной форме, например:\n\n"
        "- Вес 74 кг\n"
        "- Сегодня бегал 30 минут\n"
        "- На завтрак овсянка и кофе\n"
        "- Болит голова с утра\n"
        "- Давление 130/85\n\n"
        "Я запишу данные и прокомментирую их с учётом вашей истории."
    )
    context.user_data["mode"] = "add_data"


async def handle_show_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Отправьте фото анализа или медицинского документа.\n"
        "Я расшифрую показатели и объясню что они означают для вашего здоровья."
    )


async def handle_screening_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info, records, history = get_user_context(user_id)

    msgs = [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
    msgs.append({
        "role": "user",
        "content": "Составь для меня персональный план обследований и профилактики на этот год.",
    })
    response = chat_with_claude(msgs, user_info, records)
    save_conversation(user_id, "user", "Запрос плана обследований")
    save_conversation(user_id, "assistant", response)
    await update.message.reply_text(response, reply_markup=MAIN_KB)


async def handle_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user_info(user_id)
    records = get_health_records(user_id, limit=100)

    weight_records = [r for r in records if "вес" in r["record_type"].lower()]
    last_weight = weight_records[0]["value"] if weight_records else "не указан"

    text = (
        "Ваш профиль:\n\n"
        "Имя: " + (u["first_name"] if u else "Неизвестно") + "\n"
        "Возраст: " + str(u["age"] if u and u["age"] else "Не указан") + "\n"
        "Пол: " + str(u["gender"] if u and u["gender"] else "Не указан") + "\n"
        "Последний вес: " + last_weight + "\n"
        "Всего записей: " + str(len(records)) + "\n\n"
        "Для обновления возраста: /setage\n"
        "Для обновления пола: /setgender"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KB)


async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    records = get_health_records(user_id, limit=15)
    if not records:
        await update.message.reply_text(
            "Записей пока нет. Начните вести дневник здоровья — "
            "просто напишите мне о своём самочувствии, весе или активности.",
            reply_markup=MAIN_KB,
        )
        return
    text = "Последние записи:\n\n"
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
    await update.message.reply_text("Анализирую документ, подождите...")
    user_id = update.effective_user.id
    user_info, records, _ = get_user_context(user_id)

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    caption = update.message.caption or ""

    try:
        response = analyze_medical_image(
            bytes(image_bytes), "jpeg", caption, user_info, records
        )
        save_conversation(user_id, "user", "[Фото медицинского документа] " + caption)
        save_conversation(user_id, "assistant", response)
        await update.message.reply_text(response, reply_markup=MAIN_KB)
    except Exception as e:
        logger.error("Image error: " + str(e))
        await update.message.reply_text(
            "Не удалось проанализировать фото. Попробуйте ещё раз.",
            reply_markup=MAIN_KB,
        )


def detect_health_data(text):
    tl = text.lower()
    if any(w in tl for w in ["кг", "вешу", "вес ", "весом"]):
        return "вес"
    if any(w in tl for w in ["завтрак", "обед", "ужин", "съел", "поел", "питание", "калор"]):
        return "питание"
    if any(w in tl for w in ["бегал", "тренировк", "спортзал", "ходил", "шагов", "физ", "активност"]):
        return "активность"
    if any(w in tl for w in ["давление", "пульс", "температур", "сахар", "глюкоз"]):
        return "показатели"
    if any(w in tl for w in ["болит", "боль", "плохо", "симптом", "тошнит", "кружится"]):
        return "симптомы"
    if any(w in tl for w in ["сплю", "сон", "не сплю", "бессонниц", "устал"]):
        return "сон"
    return None


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    tl = text.lower().strip()
    user_info, records, history = get_user_context(user_id)

    if tl in ["моё здоровье", "мое здоровье"]:
        await handle_my_health(update, context)
        return
    if tl == "добавить данные":
        await handle_add_data(update, context)
        return
    if tl == "мои анализы":
        await handle_show_analysis(update, context)
        return
    if tl == "план обследований":
        await handle_screening_plan(update, context)
        return
    if tl == "мой профиль":
        await handle_profile(update, context)
        return
    if tl == "история":
        await handle_history(update, context)
        return

    record_type = detect_health_data(text)
    if record_type:
        save_health_record(user_id, record_type, text[:500])

    msgs = [{"role": m["role"], "content": m["content"]} for m in history[-20:]]
    msgs.append({"role": "user", "content": text})
    save_conversation(user_id, "user", text)

    try:
        response = chat_with_claude(msgs, user_info, records)
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
