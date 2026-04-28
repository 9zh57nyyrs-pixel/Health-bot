from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_gender_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мужской"), KeyboardButton(text="Женский")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_severity_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1 - Легкая")],
            [KeyboardButton(text="2 - Умеренная")],
            [KeyboardButton(text="3 - Сильная")],
            [KeyboardButton(text="4 - Очень сильная")],
            [KeyboardButton(text="5 - Невыносимая")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_duration_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Менее 1 часа")],
            [KeyboardButton(text="1-6 часов")],
            [KeyboardButton(text="6-24 часа")],
            [KeyboardButton(text="1-3 дня")],
            [KeyboardButton(text="3-7 дней")],
            [KeyboardButton(text="Более недели")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Начать опрос")],
            [KeyboardButton(text="История опросов")],
            [KeyboardButton(text="Помощь")]
        ],
        resize_keyboard=True
    )

def get_emergency_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Позвонить 103", url="tel:103")],
            [InlineKeyboardButton(text="Найти больницу", url="https://yandex.ru/maps/search/больница")]
        ]
    )
