from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from bot.states import MedicalSurvey
from bot.keyboards import (
    get_gender_keyboard, get_severity_keyboard, get_duration_keyboard,
    get_main_menu_keyboard, get_emergency_keyboard
)
from bot.scenarios import GREETING_TEXT, EMERGENCY_TEXT, QUESTIONS, RESULT_INTRO, HELP_TEXT
from bot.llm_integration import analyze_symptoms
from bot.utils import check_red_flags, format_medical_report

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(GREETING_TEXT, reply_markup=get_main_menu_keyboard())

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT)

@router.message(F.text == "Помощь")
async def help_button(message: Message):
    await message.answer(HELP_TEXT)

@router.message(F.text == "Начать опрос")
async def start_survey(message: Message, state: FSMContext):
    await state.set_state(MedicalSurvey.age)
    await message.answer(QUESTIONS["age"])

@router.message(F.text == "История опросов")
async def history_button(message: Message):
    await message.answer("📋 История опросов пока не реализована. Скоро добавим!")

@router.message(MedicalSurvey.age)
async def process_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        if age < 0 or age > 120:
            await message.answer("Пожалуйста, введите реальный возраст (0-120)")
            return
        await state.update_data(age=age)
        await state.set_state(MedicalSurvey.gender)
        await message.answer(QUESTIONS["gender"], reply_markup=get_gender_keyboard())
    except ValueError:
        await message.answer("Пожалуйста, введите число (например: 25)")

@router.message(MedicalSurvey.gender)
async def process_gender(message: Message, state: FSMContext):
    if message.text not in ["Мужской", "Женский"]:
        await message.answer("Пожалуйста, выберите пол с помощью кнопок")
        return
    
    await state.update_data(gender=message.text)
    await state.set_state(MedicalSurvey.main_complaint)
    await message.answer(QUESTIONS["main_complaint"])

@router.message(MedicalSurvey.main_complaint)
async def process_complaint(message: Message, state: FSMContext):
    complaint = message.text
    red_flags = check_red_flags(complaint)
    
    if red_flags:
        await message.answer(EMERGENCY_TEXT, reply_markup=get_emergency_keyboard())
    
    await state.update_data(main_complaint=complaint)
    await state.set_state(MedicalSurvey.symptom_duration)
    await message.answer(QUESTIONS["duration"], reply_markup=get_duration_keyboard())

@router.message(MedicalSurvey.symptom_duration)
async def process_duration(message: Message, state: FSMContext):
    await state.update_data(duration=message.text)
    await state.set_state(MedicalSurvey.symptom_severity)
    await message.answer(QUESTIONS["severity"], reply_markup=get_severity_keyboard())

@router.message(MedicalSurvey.symptom_severity)
async def process_severity(message: Message, state: FSMContext):
    severity_text = message.text
    
    if "1" in severity_text:
        severity = 1
    elif "2" in severity_text:
        severity = 2
    elif "3" in severity_text:
        severity = 3
    elif "4" in severity_text:
        severity = 4
    elif "5" in severity_text:
        severity = 5
    else:
        await message.answer("Пожалуйста, выберите тяжесть с помощью кнопок")
        return
    
    await state.update_data(severity=severity)
    await state.set_state(MedicalSurvey.additional_symptoms)
    await message.answer(QUESTIONS["additional_symptoms"])

@router.message(MedicalSurvey.additional_symptoms)
async def process_additional(message: Message, state: FSMContext):
    await state.update_data(additional_symptoms=message.text)
    await state.set_state(MedicalSurvey.chronic_diseases)
    await message.answer(QUESTIONS["chronic_diseases"])

@router.message(MedicalSurvey.chronic_diseases)
async def process_chronic(message: Message, state: FSMContext):
    await state.update_data(chronic_diseases=message.text)
    await state.set_state(MedicalSurvey.medications)
    await message.answer(QUESTIONS["medications"])

@router.message(MedicalSurvey.medications)
async def process_medications(message: Message, state: FSMContext):
    await state.update_data(medications=message.text)
    await state.set_state(MedicalSurvey.allergies)
    await message.answer(QUESTIONS["allergies"])

@router.message(MedicalSurvey.allergies)
async def process_allergies(message: Message, state: FSMContext):
    await state.update_data(allergies=message.text)
    await state.set_state(MedicalSurvey.analysis)
    
    data = await state.get_data()
    await message.answer(RESULT_INTRO)
    
    analysis = await analyze_symptoms(data)
    report = format_medical_report(data, analysis)
    
    await message.answer(report, reply_markup=get_main_menu_keyboard())
    
    if analysis.get("urgency") == "emergency":
        await message.answer(EMERGENCY_TEXT, reply_markup=get_emergency_keyboard())
    
    await state.clear()

@router.message()
async def unknown_message(message: Message):
    await message.answer(
        "Я не понял ваше сообщение. Используйте меню или нажмите /start",
        reply_markup=get_main_menu_keyboard()
    )
