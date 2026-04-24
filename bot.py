import logging
import base64
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
Application, CommandHandler, MessageHandler,
filters, ContextTypes, ConversationHandler
)
from database import Database
from claude_client import ClaudeClient
from config import TELEGRAM_TOKEN

logging.basicConfig(
format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
level=logging.INFO
)
logger = logging.getLogger(**name**)

db = Database()
claude = ClaudeClient()

# Conversation states

SETUP_NAME, SETUP_AGE, SETUP_GENDER, SETUP_HEIGHT, SETUP_WEIGHT = range(5)
LOG_WEIGHT, LOG_FOOD, LOG_ACTIVITY = range(5, 8)

def get_main_keyboard():
keyboard = [
[KeyboardButton("💬 Чат с врачом"), KeyboardButton("📊 Моя статистика")],
[KeyboardButton("⚖️ Записать вес"), KeyboardButton("🍎 Записать питание")],
[KeyboardButton("🏃 Записать активность"), KeyboardButton("🔬 Загрузить анализы")],
[KeyboardButton("🧪 План обследований"), KeyboardButton("❤️ Оценка здоровья")],
[KeyboardButton("👤 Мой профиль")]
]
return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
user = db.get_user(user_id)

```
if user:
    await update.message.reply_text(
        f"👋 С возвращением, {user['name']}!\n\nЯ ваш личный AI-врач. Чем могу помочь?",
        reply_markup=get_main_keyboard()
    )
else:
    await update.message.reply_text(
        "👋 Здравствуйте! Я ваш личный AI-врач.\n\n"
        "Я помогу вам следить за здоровьем, весом, питанием и физической активностью.\n\n"
        "Давайте начнём с создания вашего профиля.\n\n"
        "Как вас зовут?"
    )
    return SETUP_NAME
```

async def setup_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
context.user_data[‘name’] = update.message.text.strip()
await update.message.reply_text(“Сколько вам лет?”)
return SETUP_AGE

async def setup_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
try:
age = int(update.message.text.strip())
if age < 1 or age > 120:
raise ValueError
context.user_data[‘age’] = age
keyboard = ReplyKeyboardMarkup(
[[KeyboardButton(“Мужской”), KeyboardButton(“Женский”)]],
resize_keyboard=True, one_time_keyboard=True
)
await update.message.reply_text(“Укажите ваш пол:”, reply_markup=keyboard)
return SETUP_GENDER
except ValueError:
await update.message.reply_text(“Пожалуйста, введите корректный возраст (число).”)
return SETUP_AGE

async def setup_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
gender = update.message.text.strip()
if gender not in [“Мужской”, “Женский”]:
await update.message.reply_text(“Пожалуйста, выберите ‘Мужской’ или ‘Женский’.”)
return SETUP_GENDER
context.user_data[‘gender’] = gender
await update.message.reply_text(“Укажите ваш рост в сантиметрах (например: 175):”)
return SETUP_HEIGHT

async def setup_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
try:
height = float(update.message.text.strip())
if height < 50 or height > 250:
raise ValueError
context.user_data[‘height’] = height
await update.message.reply_text(“Укажите ваш текущий вес в килограммах (например: 70.5):”)
return SETUP_WEIGHT
except ValueError:
await update.message.reply_text(“Пожалуйста, введите корректный рост в см.”)
return SETUP_HEIGHT

async def setup_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
try:
weight = float(update.message.text.strip())
if weight < 20 or weight > 300:
raise ValueError

```
    user_id = update.effective_user.id
    data = context.user_data
    db.create_user(
        user_id=user_id,
        name=data['name'],
        age=data['age'],
        gender=data['gender'],
        height=data['height'],
        weight=weight
    )
    db.log_weight(user_id, weight)

    await update.message.reply_text(
        f"✅ Профиль создан!\n\n"
        f"👤 Имя: {data['name']}\n"
        f"📅 Возраст: {data['age']} лет\n"
        f"⚧ Пол: {data['gender']}\n"
        f"📏 Рост: {data['height']} см\n"
        f"⚖️ Вес: {weight} кг\n\n"
        f"Теперь вы можете общаться со мной как с вашим личным врачом!",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END
except ValueError:
    await update.message.reply_text("Пожалуйста, введите корректный вес в кг.")
    return SETUP_WEIGHT
```

async def log_weight_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(“Введите ваш текущий вес в кг (например: 72.3):”)
return LOG_WEIGHT

async def log_weight_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
try:
weight = float(update.message.text.strip())
if weight < 20 or weight > 300:
raise ValueError

```
    user_id = update.effective_user.id
    db.log_weight(user_id, weight)
    db.update_user_weight(user_id, weight)

    # Get trend
    history = db.get_weight_history(user_id, limit=5)
    trend = ""
    if len(history) >= 2:
        diff = weight - history[-2]['weight']
        if diff > 0:
            trend = f"\n📈 +{diff:.1f} кг с прошлого раза"
        elif diff < 0:
            trend = f"\n📉 {diff:.1f} кг с прошлого раза"
        else:
            trend = "\n➡️ Вес не изменился"

    await update.message.reply_text(
        f"✅ Вес записан: {weight} кг{trend}",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END
except ValueError:
    await update.message.reply_text("Пожалуйста, введите корректное число.")
    return LOG_WEIGHT
```

async def log_food_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
“Опишите что вы съели (можно подробно или кратко).\n”
“Например: ‘Овсянка с бананом и кофе с молоком’ или ‘Куриная грудка 200г, рис 150г, салат’”
)
return LOG_FOOD

async def log_food_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
food_text = update.message.text.strip()
db.log_food(user_id, food_text)

```
await update.message.reply_text(
    f"✅ Питание записано!\n\n🍽 {food_text}\n\nЕсли хотите получить анализ питания, напишите мне в чате.",
    reply_markup=get_main_keyboard()
)
return ConversationHandler.END
```

async def log_activity_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
“Опишите вашу физическую активность.\n”
“Например: ‘Бег 30 минут’ или ‘Силовая тренировка 1 час, грудь и трицепс’”
)
return LOG_ACTIVITY

async def log_activity_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
activity_text = update.message.text.strip()
db.log_activity(user_id, activity_text)

```
await update.message.reply_text(
    f"✅ Активность записана!\n\n🏃 {activity_text}",
    reply_markup=get_main_keyboard()
)
return ConversationHandler.END
```

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
user = db.get_user(user_id)
if not user:
await update.message.reply_text(“Сначала создайте профиль командой /start”)
return

```
weight_history = db.get_weight_history(user_id, limit=7)
recent_food = db.get_recent_food(user_id, limit=5)
recent_activity = db.get_recent_activity(user_id, limit=5)

stats = f"📊 *Ваша статистика*\n\n"
stats += f"👤 {user['name']}, {user['age']} лет\n"
stats += f"📏 Рост: {user['height']} см\n"
stats += f"⚖️ Текущий вес: {user['weight']} кг\n"

if user['height'] and user['weight']:
    bmi = user['weight'] / ((user['height'] / 100) ** 2)
    stats += f"📈 ИМТ: {bmi:.1f}\n"

if weight_history:
    stats += f"\n⚖️ *История веса (последние 7 записей):*\n"
    for entry in weight_history[-7:]:
        stats += f"  • {entry['date']}: {entry['weight']} кг\n"

if recent_food:
    stats += f"\n🍽 *Последние приёмы пищи:*\n"
    for entry in recent_food:
        stats += f"  • {entry['date']}: {entry['description'][:50]}...\n" if len(entry['description']) > 50 else f"  • {entry['date']}: {entry['description']}\n"

if recent_activity:
    stats += f"\n🏃 *Последние тренировки:*\n"
    for entry in recent_activity:
        stats += f"  • {entry['date']}: {entry['description'][:50]}...\n" if len(entry['description']) > 50 else f"  • {entry['date']}: {entry['description']}\n"

await update.message.reply_text(stats, parse_mode='Markdown', reply_markup=get_main_keyboard())
```

async def show_checkup_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Generate personalized checkup plan based on age, gender, data”””
user_id = update.effective_user.id
user = db.get_user(user_id)
if not user:
await update.message.reply_text(“Сначала создайте профиль командой /start”)
return

```
await update.message.reply_text("🧪 Составляю персональный план обследований...")
await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

weight_history = db.get_weight_history(user_id, limit=5)
recent_food = db.get_recent_food(user_id, limit=3)
recent_activity = db.get_recent_activity(user_id, limit=3)
recent_analyses = db.get_recent_analyses(user_id, limit=5)

try:
    plan = await claude.get_checkup_plan(
        user_profile=user,
        weight_history=weight_history,
        recent_food=recent_food,
        recent_activity=recent_activity,
        recent_analyses=recent_analyses
    )
    await update.message.reply_text(
        f"🧪 *Ваш план обследований*\n\n{plan}",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )
except Exception as e:
    logger.error(f"Error in checkup plan: {e}")
    await update.message.reply_text("Ошибка при составлении плана. Попробуйте позже.", reply_markup=get_main_keyboard())
```

async def show_health_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Show AI-generated health score with alerts and positives”””
user_id = update.effective_user.id
user = db.get_user(user_id)
if not user:
await update.message.reply_text(“Сначала создайте профиль командой /start”)
return

```
await update.message.reply_text("❤️ Анализирую ваше состояние здоровья...")
await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

weight_history = db.get_weight_history(user_id, limit=10)
recent_food = db.get_recent_food(user_id, limit=5)
recent_activity = db.get_recent_activity(user_id, limit=5)
recent_analyses = db.get_recent_analyses(user_id, limit=5)

try:
    score_data = await claude.get_health_score(
        user_profile=user,
        weight_history=weight_history,
        recent_food=recent_food,
        recent_activity=recent_activity,
        recent_analyses=recent_analyses
    )

    score = score_data.get("score", 0)
    # Choose emoji by score
    if score >= 8:
        score_emoji = "🟢"
    elif score >= 5:
        score_emoji = "🟡"
    else:
        score_emoji = "🔴"

    msg = f"❤️ *Оценка вашего здоровья*\n\n"
    msg += f"{score_emoji} *Общая оценка: {score}/10*\n\n"

    bmi_status = score_data.get("bmi_status")
    activity_status = score_data.get("activity_status")
    nutrition_status = score_data.get("nutrition_status")
    if bmi_status:
        msg += f"⚖️ ИМТ: {bmi_status}\n"
    if activity_status:
        msg += f"🏃 Активность: {activity_status}\n"
    if nutrition_status:
        msg += f"🍎 Питание: {nutrition_status}\n"

    alerts = score_data.get("alerts", [])
    if alerts:
        msg += "\n⚠️ *На что обратить внимание:*\n"
        for a in alerts:
            msg += f"  • {a}\n"

    positives = score_data.get("positives", [])
    if positives:
        msg += "\n✅ *Что хорошо:*\n"
        for p in positives:
            msg += f"  • {p}\n"

    top_rec = score_data.get("top_recommendation")
    if top_rec:
        msg += f"\n💡 *Главная рекомендация:*\n{top_rec}"

    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=get_main_keyboard())
except Exception as e:
    logger.error(f"Error in health score: {e}")
    await update.message.reply_text("Ошибка при оценке здоровья. Попробуйте позже.", reply_markup=get_main_keyboard())
```

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
user = db.get_user(user_id)
if not user:
await update.message.reply_text(“Сначала создайте профиль командой /start”)
return

```
bmi_text = ""
if user['height'] and user['weight']:
    bmi = user['weight'] / ((user['height'] / 100) ** 2)
    if bmi < 18.5:
        bmi_status = "Недостаточный вес"
    elif bmi < 25:
        bmi_status = "Нормальный вес ✅"
    elif bmi < 30:
        bmi_status = "Избыточный вес"
    else:
        bmi_status = "Ожирение"
    bmi_text = f"\n📊 ИМТ: {bmi:.1f} ({bmi_status})"

profile = (
    f"👤 *Ваш профиль*\n\n"
    f"Имя: {user['name']}\n"
    f"Возраст: {user['age']} лет\n"
    f"Пол: {user['gender']}\n"
    f"Рост: {user['height']} см\n"
    f"Вес: {user['weight']} кг"
    f"{bmi_text}"
)
await update.message.reply_text(profile, parse_mode='Markdown', reply_markup=get_main_keyboard())
```

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handle photos - analyze as medical tests/documents”””
user_id = update.effective_user.id
user = db.get_user(user_id)

```
await update.message.reply_text("🔬 Анализирую ваш документ/анализ...")

try:
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    image_base64 = base64.b64encode(file_bytes).decode('utf-8')

    caption = update.message.caption or ""

    user_context = ""
    if user:
        user_context = f"Пациент: {user['name']}, {user['age']} лет, {user['gender']}, рост {user['height']} см, вес {user['weight']} кг."

    response = await claude.analyze_medical_image(image_base64, caption, user_context)

    # Save to DB
    db.log_analysis(user_id, caption or "Фото анализов", response)

    await update.message.reply_text(
        f"🔬 *Результат анализа:*\n\n{response}",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )
except Exception as e:
    logger.error(f"Error analyzing photo: {e}")
    await update.message.reply_text(
        "Не удалось обработать изображение. Попробуйте ещё раз.",
        reply_markup=get_main_keyboard()
    )
```

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handle regular text messages - chat with AI doctor”””
user_id = update.effective_user.id
user = db.get_user(user_id)
text = update.message.text

```
# Handle menu buttons
if text == "📊 Моя статистика":
    await show_stats(update, context)
    return
elif text == "👤 Мой профиль":
    await show_profile(update, context)
    return
elif text == "⚖️ Записать вес":
    await log_weight_start(update, context)
    context.user_data['state'] = LOG_WEIGHT
    return
elif text == "🍎 Записать питание":
    await log_food_start(update, context)
    context.user_data['state'] = LOG_FOOD
    return
elif text == "🏃 Записать активность":
    await log_activity_start(update, context)
    context.user_data['state'] = LOG_ACTIVITY
    return
elif text == "🔬 Загрузить анализы":
    await update.message.reply_text(
        "📎 Отправьте фото ваших анализов или медицинских документов.\n"
        "Можете добавить подпись с дополнительным контекстом."
    )
    return
elif text == "🧪 План обследований":
    await show_checkup_plan(update, context)
    return
elif text == "❤️ Оценка здоровья":
    await show_health_score(update, context)
    return
elif text == "💬 Чат с врачом":
    await update.message.reply_text(
        "💬 Задайте любой вопрос о вашем здоровье. Я ваш личный AI-врач!"
    )
    return

# Check inline states
state = context.user_data.get('state')
if state == LOG_WEIGHT:
    await log_weight_save(update, context)
    context.user_data.pop('state', None)
    return
elif state == LOG_FOOD:
    await log_food_save(update, context)
    context.user_data.pop('state', None)
    return
elif state == LOG_ACTIVITY:
    await log_activity_save(update, context)
    context.user_data.pop('state', None)
    return

# Regular AI chat
if not user:
    await update.message.reply_text("Пожалуйста, начните с команды /start для создания профиля.")
    return

await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

# Build context
weight_history = db.get_weight_history(user_id, limit=5)
recent_food = db.get_recent_food(user_id, limit=3)
recent_activity = db.get_recent_activity(user_id, limit=3)
recent_analyses = db.get_recent_analyses(user_id, limit=2)
chat_history = db.get_chat_history(user_id, limit=10)

try:
    response = await claude.chat(
        user_message=text,
        user_profile=user,
        weight_history=weight_history,
        recent_food=recent_food,
        recent_activity=recent_activity,
        recent_analyses=recent_analyses,
        chat_history=chat_history
    )

    # Save to chat history
    db.save_chat_message(user_id, "user", text)
    db.save_chat_message(user_id, "assistant", response)

    await update.message.reply_text(response, reply_markup=get_main_keyboard())
except Exception as e:
    logger.error(f"Error in chat: {e}")
    await update.message.reply_text(
        "Произошла ошибка. Попробуйте позже.",
        reply_markup=get_main_keyboard()
    )
```

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
context.user_data.clear()
await update.message.reply_text(“Действие отменено.”, reply_markup=get_main_keyboard())
return ConversationHandler.END

def main():
app = Application.builder().token(TELEGRAM_TOKEN).build()

```
# Setup conversation handler
setup_conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        SETUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_name)],
        SETUP_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_age)],
        SETUP_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_gender)],
        SETUP_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_height)],
        SETUP_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_weight)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

weight_conv = ConversationHandler(
    entry_points=[CommandHandler("weight", log_weight_start)],
    states={
        LOG_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_weight_save)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

food_conv = ConversationHandler(
    entry_points=[CommandHandler("food", log_food_start)],
    states={
        LOG_FOOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_food_save)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

activity_conv = ConversationHandler(
    entry_points=[CommandHandler("activity", log_activity_start)],
    states={
        LOG_ACTIVITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_activity_save)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

app.add_handler(setup_conv)
app.add_handler(weight_conv)
app.add_handler(food_conv)
app.add_handler(activity_conv)
app.add_handler(CommandHandler("checkup", show_checkup_plan))
app.add_handler(CommandHandler("health", show_health_score))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

logger.info("🏥 Health Bot запущен!")
app.run_polling(allowed_updates=Update.ALL_TYPES)
```

if **name** == ‘**main**’:
main()