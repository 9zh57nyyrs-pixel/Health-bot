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
    save_profile,
    add_message,
    get_recent_messages,
    get_all_messages,
    clear_messages,
)
from claude_client import chat, chat_with_image, update_profile

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAIN_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Моё здоровье"), KeyboardButton("Моя история")],
        [KeyboardButton("Новый сеанс")],
    ],
    resize_keyboard=True,
)


def get_profile(user_id):
    u = get_user(user_id)
    if u and u["profile"]:
        return u["profile"]
    return ""


async def reply(update, text):
    # Telegram ограничение — 4096 символов
    if len(text) <= 4096:
        await update.message.reply_text(text, reply_markup=MAIN_KB)
    else:
        parts = [text[i:i+4096] for i in range(0, len(text), 4096)]
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                await update.message.reply_text(part, reply_markup=MAIN_KB)
            else:
                await update.message.reply_text(part)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username, user.first_name)

    history = get_recent_messages(user.id, limit=3)
    profile = get_profile(user.id)

    if history:
        first_msg = "С возвращением, " + user.first_name + "! Как вы себя чувствуете?"
        history_msgs = get_recent_messages(user.id, limit=30)
        history_msgs.append({"role": "user", "content": first_msg})
        add_message(user.id, "user", first_msg)
        response = chat(history_msgs, profile)
    else:
        first_msg = "Привет! Я хочу начать следить за своим здоровьем."
        history_msgs = [{"role": "user", "content": first_msg}]
        add_message(user.id, "user", first_msg)
        response = chat(history_msgs, profile)

    add_message(user.id, "assistant", response)
    await reply(update, response)


async def my_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = get_profile(user_id)
    history = get_recent_messages(user_id, limit=30)

    request = "Дай мне полный анализ моего здоровья на основе всего что ты знаешь обо мне. Что хорошо, что вызывает вопросы, и что посоветуешь?"
    history.append({"role": "user", "content": request})
    add_message(user_id, "user", request)

    response = chat(history, profile)
    add_message(user_id, "assistant", response)
    await reply(update, response)


async def my_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = get_profile(user_id)

    if profile and profile.strip():
        text = "Что я знаю о вашем здоровье:\n\n" + profile
    else:
        all_msgs = get_all_messages(user_id)
        if not all_msgs:
            await reply(update, "История пуста. Просто напишите мне — расскажите как себя чувствуете, я начну собирать вашу историю здоровья.")
            return
        text = "Профиль ещё формируется. Поговорите со мной немного больше и я запомню все важные данные о вашем здоровье."

    await reply(update, text)


async def new_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = get_profile(user_id)
    history = get_recent_messages(user_id, limit=30)

    if history:
        new_profile = update_profile(history, profile)
        save_profile(user_id, new_profile)

    clear_messages(user_id)

    await reply(
        update,
        "Сохранил все важные данные о вашем здоровье и начинаю новый сеанс.\n\nКак вы себя чувствуете сегодня?"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = get_profile(user_id)
    history = get_recent_messages(user_id, limit=20)

    await update.message.reply_text("Анализирую документ...")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = bytes(await file.download_as_bytearray())
        caption = update.message.caption or ""

        add_message(user_id, "user", "[Фото анализа]" + (" " + caption if caption else ""))
        response = chat_with_image(image_bytes, caption, history, profile)
        add_message(user_id, "assistant", response)

        # Обновляем профиль после анализа
        updated_history = get_recent_messages(user_id, limit=30)
        new_profile = update_profile(updated_history, profile)
        save_profile(user_id, new_profile)

        await reply(update, response)
    except Exception as e:
        logger.error("Photo error: " + str(e))
        await reply(update, "Не удалось обработать фото. Попробуйте ещё раз или напишите результаты текстом.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    tl = text.lower().strip()

    if tl in ("моё здоровье", "мое здоровье"):
        await my_health(update, context)
        return
    if tl == "моя история":
        await my_history(update, context)
        return
    if tl == "новый сеанс":
        await new_session(update, context)
        return

    profile = get_profile(user_id)
    history = get_recent_messages(user_id, limit=30)
    history.append({"role": "user", "content": text})

    add_message(user_id, "user", text)

    try:
        response = chat(history, profile)
        add_message(user_id, "assistant", response)

        # Каждые 6 сообщений обновляем профиль
        all_msgs = get_all_messages(user_id)
        if len(all_msgs) % 6 == 0:
            updated_history = get_recent_messages(user_id, limit=30)
            new_profile = update_profile(updated_history, profile)
            save_profile(user_id, new_profile)

        await reply(update, response)
    except Exception as e:
        logger.error("Claude error: " + str(e))
        await reply(update, "Произошла ошибка. Попробуйте ещё раз.")


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
