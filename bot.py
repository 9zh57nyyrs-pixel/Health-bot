import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from config import TELEGRAM_TOKEN
from database import (
    init_db,
    save_user,
    get_user,
    update_profile,
    save_message,
    get_history,
    get_full_history,
    clear_history,
)
from claude_client import ask_claude, ask_claude_with_image, extract_profile

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAIN_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Моё здоровье"), KeyboardButton("История")],
        [KeyboardButton("Новый диалог")],
    ],
    resize_keyboard=True,
)


def build_messages(history):
    msgs = []
    for row in history:
        msgs.append({"role": row["role"], "content": row["content"]})
    return msgs


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username, user.first_name)
    u = get_user(user.id)

    history = get_history(user.id, limit=5)

    if history:
        greeting = (
            "С возвращением, " + user.first_name + "! "
            "Я помню нашу историю. Расскажите, как вы себя чувствуете?"
        )
        await update.message.reply_text(greeting, reply_markup=MAIN_KB)
    else:
        profile = u["profile"] if u and u["profile"] else ""
        messages = [{"role": "user", "content": "Привет, я хочу следить за своим здоровьем."}]
        response = ask_claude(messages, profile)

        save_message(user.id, "user", "Привет, я хочу следить за своим здоровьем.")
        save_message(user.id, "assistant", response)

        await update.message.reply_text(response, reply_markup=MAIN_KB)


async def handle_my_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    profile = u["profile"] if u and u["profile"] else ""
    history = get_history(user_id, limit=30)
    messages = build_messages(history)

    request = "Дай мне полный анализ моего здоровья на основе всего что ты знаешь обо мне. Что хорошо, что вызывает вопросы, что нужно улучшить?"
    messages.append({"role": "user", "content": request})

    response = ask_claude(messages, profile)

    save_message(user_id, "user", request)
    save_message(user_id, "assistant", response)

    await update.message.reply_text(response, reply_markup=MAIN_KB)


async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    profile = u["profile"] if u and u["profile"] else ""

    if not profile:
        rows = get_full_history(user_id)
        if not rows:
            await update.message.reply_text(
                "История пока пуста. Начните общаться со мной и я буду запоминать всё о вашем здоровье.",
                reply_markup=MAIN_KB,
            )
            return
        profile_text = "Данных в профиле пока нет, но вот последние сообщения."
    else:
        profile_text = profile

    text = "Что я знаю о вашем здоровье:\n\n" + profile_text
    if len(text) > 4000:
        text = text[:4000] + "..."

    await update.message.reply_text(text, reply_markup=MAIN_KB)


async def handle_new_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    profile = u["profile"] if u and u["profile"] else ""

    history = get_history(user_id, limit=30)
    if history:
        messages = build_messages(history)
        new_profile = extract_profile(messages, profile)
        update_profile(user_id, new_profile)

    clear_history(user_id)

    await update.message.reply_text(
        "Начинаем новый диалог. Я сохранил все важные данные о вашем здоровье.\n\nКак вы себя чувствуете?",
        reply_markup=MAIN_KB,
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    profile = u["profile"] if u and u["profile"] else ""
    history = get_history(user_id, limit=20)
    messages = build_messages(history)

    await update.message.reply_text("Анализирую документ, подождите...")

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await file.download_as_bytearray())
    caption = update.message.caption or ""

    try:
        response = ask_claude_with_image(image_bytes, caption, messages, profile)

        save_message(user_id, "user", "[Фото анализа] " + caption)
        save_message(user_id, "assistant", response)

        u2 = get_user(user_id)
        profile2 = u2["profile"] if u2 and u2["profile"] else ""
        all_msgs = build_messages(get_history(user_id, limit=30))
        new_profile = extract_profile(all_msgs, profile2)
        update_profile(user_id, new_profile)

        await update.message.reply_text(response, reply_markup=MAIN_KB)
    except Exception as e:
        logger.error("Photo error: " + str(e))
        await update.message.reply_text(
            "Не удалось обработать фото. Попробуйте ещё раз.",
            reply_markup=MAIN_KB,
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    tl = text.lower().strip()

    if tl == "моё здоровье" or tl == "мое здоровье":
        await handle_my_health(update, context)
        return
    if tl == "история":
        await handle_history(update, context)
        return
    if tl == "новый диалог":
        await handle_new_dialog(update, context)
        return

    u = get_user(user_id)
    profile = u["profile"] if u and u["profile"] else ""
    history = get_history(user_id, limit=30)
    messages = build_messages(history)
    messages.append({"role": "user", "content": text})

    save_message(user_id, "user", text)

    try:
        response = ask_claude(messages, profile)
        save_message(user_id, "assistant", response)

        if len(messages) % 6 == 0:
            all_msgs = build_messages(get_history(user_id, limit=30))
            new_profile = extract_profile(all_msgs, profile)
            update_profile(user_id, new_profile)

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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
