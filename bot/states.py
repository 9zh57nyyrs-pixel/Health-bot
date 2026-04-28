from aiogram.fsm.state import State, StatesGroup

class MedicalSurvey(StatesGroup):
    greeting = State()
    age = State()
    gender = State()
    main_complaint = State()
    symptom_duration = State()
    symptom_severity = State()
    additional_symptoms = State()
    chronic_diseases = State()
    medications = State()
    allergies = State()
    analysis = State()
