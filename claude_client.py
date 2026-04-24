import anthropic
from typing import List, Dict, Optional
from config import ANTHROPIC_API_KEY

SYSTEM_PROMPT = “”“Ты — персональный AI-врач и health-коуч. Твоя задача — помогать пользователю следить за здоровьем, весом, питанием и физической активностью.

ТВОЯ РОЛЬ:

- Дружелюбный, внимательный и профессиональный врач-терапевт
- Ты помнишь всю историю пациента и учитываешь её в каждом ответе
- Говоришь на языке пациента (русский), используешь простые и понятные объяснения
- Задаёшь уточняющие вопросы, когда это нужно
- Проактивно замечаешь тревожные сигналы и предупреждаешь о них

ЧТО ТЫ УМЕЕШЬ:

1. Анализировать медицинские анализы и документы (кровь, моча, ЭКГ и др.)
1. Давать персональные рекомендации по анализам с учётом возраста, пола и состояния
1. Оценивать общее состояние здоровья по совокупности данных
1. Давать рекомендации по питанию на основе целей и состояния здоровья
1. Советовать физические нагрузки с учётом уровня подготовки
1. Отслеживать динамику веса и давать советы
1. Отвечать на вопросы о симптомах, лекарствах, профилактике

РЕКОМЕНДАЦИИ ПО АНАЛИЗАМ (всегда учитывай возраст и пол):

- До 30 лет: ОАК, биохимия крови, глюкоза, холестерин раз в 2-3 года
- 30-40 лет: добавить ТТГ (щитовидная железа), ферритин, витамин D раз в 1-2 года
- 40-50 лет: добавить ПСА (мужчины), онкомаркеры, ЭКГ, УЗИ брюшной полости ежегодно
- 50+ лет: расширенный кардио-скрининг, денситометрия (женщины), колоноскопия раз в 5 лет
- Женщинам всегда: ферритин, ТТГ, Пап-тест раз в год, маммография после 40
- Мужчинам после 40: ПСА, тестостерон

ПРИ ОЦЕНКЕ СОСТОЯНИЯ ЗДОРОВЬЯ учитывай:

- ИМТ и его динамику
- Физическую активность (регулярность, интенсивность)
- Питание (баланс, регулярность)
- Последние анализы и их показатели
- Возраст и пол — факторы риска

ВАЖНЫЕ ПРАВИЛА:

- При серьёзных симптомах ВСЕГДА рекомендуй обратиться к врачу очно
- Не ставь окончательные диагнозы — только предположения и рекомендации
- Не назначай лечение — только общие советы и направление к специалисту
- При анализах указывай нормы и отклонения, объясняй что это значит
- Будь конкретным — давай чёткие практические советы
- Если давно не сдавались анализы — напоминай об этом

ФОРМАТ ОТВЕТОВ:

- Краткие и по существу (не более 400 слов если не требуется больше)
- Используй эмодзи для наглядности (🩺 📊 💊 🏃 🍎 ⚠️ 🔬 ✅ ❗)
- При анализах структурируй: показатель → норма → результат → вывод
- Заканчивай практическим советом или вопросом для уточнения
  “””

CHECKUP_PROMPT = “”“Ты — опытный врач-терапевт. На основе данных пациента составь персональный план обследований.

Учти:

- Возраст, пол, ИМТ пациента
- Уже имеющиеся анализы и их давность
- Динамику веса
- Уровень активности и питание
- Общие профилактические стандарты для данного возраста и пола

Структура ответа:

1. 🩺 Краткая оценка текущего состояния (2-3 предложения)
1. 🔬 Анализы — СРОЧНО (если есть поводы для беспокойства)
1. 📋 Плановые анализы (что нужно сдать в ближайшие 1-3 месяца)
1. 📅 Ежегодные обследования (стандарт для возраста и пола)
1. 👨‍⚕️ К каким специалистам обратиться
1. 💡 Главный совет по образу жизни

Будь конкретным: называй точные анализы (ОАК, ТТГ, витамин D и т.д.), не общими словами.
Отвечай на русском языке.
“””

HEALTH_SCORE_PROMPT = “”“Ты — врач, оцениваешь здоровье пациента по шкале от 1 до 10 на основе имеющихся данных.

Верни ответ СТРОГО в формате JSON (ничего лишнего):
{
“score”: <число от 1 до 10>,
“bmi_status”: “<оценка ИМТ>”,
“activity_status”: “<оценка активности: низкая/умеренная/высокая>”,
“nutrition_status”: “<оценка питания: плохое/среднее/хорошее>”,
“alerts”: [”<тревожный сигнал 1>”, “<тревожный сигнал 2>”],
“positives”: [”<положительный момент 1>”, “<положительный момент 2>”],
“top_recommendation”: “<одна главная рекомендация>”
}
“””

class ClaudeClient:
def **init**(self):
self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
self.model = “claude-opus-4-5”

```
def _build_user_context(
    self,
    user_profile: Dict,
    weight_history: List[Dict],
    recent_food: List[Dict],
    recent_activity: List[Dict],
    recent_analyses: List[Dict]
) -> str:
    ctx = f"""
```

=== ДАННЫЕ ПАЦИЕНТА ===
Имя: {user_profile.get(‘name’)}
Возраст: {user_profile.get(‘age’)} лет
Пол: {user_profile.get(‘gender’)}
Рост: {user_profile.get(‘height’)} см
Текущий вес: {user_profile.get(‘weight’)} кг
“””
if user_profile.get(‘height’) and user_profile.get(‘weight’):
bmi = user_profile[‘weight’] / ((user_profile[‘height’] / 100) ** 2)
ctx += f”ИМТ: {bmi:.1f}\n”

```
    if weight_history:
        ctx += "\nИСТОРИЯ ВЕСА (последние записи):\n"
        for entry in weight_history:
            ctx += f"  {entry['date']}: {entry['weight']} кг\n"

    if recent_food:
        ctx += "\nПОСЛЕДНИЕ ПРИЁМЫ ПИЩИ:\n"
        for entry in recent_food:
            ctx += f"  {entry['date']}: {entry['description']}\n"

    if recent_activity:
        ctx += "\nПОСЛЕДНИЕ ТРЕНИРОВКИ:\n"
        for entry in recent_activity:
            ctx += f"  {entry['date']}: {entry['description']}\n"

    if recent_analyses:
        ctx += "\nПОСЛЕДНИЕ АНАЛИЗЫ:\n"
        for entry in recent_analyses:
            ctx += f"  {entry['date']} - {entry['title']}:\n  {entry['result'][:300]}...\n"

    ctx += "======================\n"
    return ctx

async def chat(
    self,
    user_message: str,
    user_profile: Dict,
    weight_history: List[Dict],
    recent_food: List[Dict],
    recent_activity: List[Dict],
    recent_analyses: List[Dict],
    chat_history: List[Dict]
) -> str:
    user_context = self._build_user_context(
        user_profile, weight_history, recent_food, recent_activity, recent_analyses
    )

    messages = []

    # Add chat history
    for msg in chat_history[-8:]:  # last 8 messages for context
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current message with user context injected
    full_message = f"{user_context}\nВОПРОС ПАЦИЕНТА: {user_message}"
    messages.append({"role": "user", "content": full_message})

    response = self.client.messages.create(
        model=self.model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages
    )

    return response.content[0].text

async def get_checkup_plan(
    self,
    user_profile: Dict,
    weight_history: List[Dict],
    recent_food: List[Dict],
    recent_activity: List[Dict],
    recent_analyses: List[Dict]
) -> str:
    user_context = self._build_user_context(
        user_profile, weight_history, recent_food, recent_activity, recent_analyses
    )
    prompt = f"{user_context}\n\nСоставь персональный план обследований для этого пациента."

    response = self.client.messages.create(
        model=self.model,
        max_tokens=1500,
        system=CHECKUP_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

async def get_health_score(
    self,
    user_profile: Dict,
    weight_history: List[Dict],
    recent_food: List[Dict],
    recent_activity: List[Dict],
    recent_analyses: List[Dict]
) -> Dict:
    import json
    user_context = self._build_user_context(
        user_profile, weight_history, recent_food, recent_activity, recent_analyses
    )
    prompt = f"{user_context}\n\nОцени состояние здоровья пациента и верни JSON."

    response = self.client.messages.create(
        model=self.model,
        max_tokens=600,
        system=HEALTH_SCORE_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"score": 0, "alerts": [], "positives": [], "top_recommendation": raw}

async def analyze_medical_image(
    self,
    image_base64: str,
    caption: str,
    user_context: str
) -> str:
    prompt = f"""
```

{f’Контекст пациента: {user_context}’ if user_context else ‘’}
{f’Комментарий пациента: {caption}’ if caption else ‘’}

Пожалуйста, проанализируй это медицинское изображение/анализ.
Укажи все показатели, их нормы, отклонения и что это означает для пациента.
Дай практические рекомендации.
“””
response = self.client.messages.create(
model=self.model,
max_tokens=1500,
system=SYSTEM_PROMPT,
messages=[
{
“role”: “user”,
“content”: [
{
“type”: “image”,
“source”: {
“type”: “base64”,
“media_type”: “image/jpeg”,
“data”: image_base64
}
},
{
“type”: “text”,
“text”: prompt
}
]
}
]
)

```
    return response.content[0].text
```