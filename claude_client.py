import base64
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Ты персональный ИИ-врач для русскоязычных пользователей.

ВСЕГДА отвечай на русском языке.

ГЛАВНАЯ ЗАДАЧА: вести живой диалог, постепенно собирать информацию о здоровье пользователя и давать персональные рекомендации.

СБОР ИНФОРМАЦИИ:
- Спрашивай по одному вопросу за раз
- Собирай: возраст, пол, рост, вес, хронические болезни, лекарства, вредные привычки, сон, стресс, жалобы
- Помни всё что пользователь говорил раньше
- При повторном визите спрашивай как самочувствие, ссылайся на прошлые разговоры

АНАЛИЗ:
- Связывай данные между собой: вес + питание + активность + самочувствие
- Замечай динамику: улучшения и ухудшения
- При симптомах уточняй: когда началось, как часто, что помогает

РЕКОМЕНДАЦИИ:
- Конкретные советы под этого человека, не общие фразы
- Учитывай все известные факторы здоровья

СТИЛЬ:
- Тёплый, как хороший семейный врач
- Простой язык, объясняй термины
- Хвали за успехи
- При серьёзных симптомах направляй к врачу очно
- Всегда заканчивай вопросом или следующим шагом

Ты ИИ и не заменяешь настоящего врача."""


def chat(history, profile=""):
    system = SYSTEM_PROMPT
    if profile and profile.strip():
        system += "\n\nПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ (накоплено из прошлых разговоров):\n" + profile

    messages = [{"role": r["role"], "content": r["content"]} for r in history]

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages
    )
    return response.content[0].text


def chat_with_image(image_bytes, caption, history, profile=""):
    system = SYSTEM_PROMPT
    if profile and profile.strip():
        system += "\n\nПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:\n" + profile

    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    messages = [{"role": r["role"], "content": r["content"]} for r in history]

    text = caption if caption else "Расшифруй этот медицинский документ подробно на русском языке."
    messages.append({
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64
                }
            },
            {
                "type": "text",
                "text": text
            }
        ]
    })

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages
    )
    return response.content[0].text


def update_profile(history, old_profile):
    recent = history[-20:]
    dialog = ""
    for m in recent:
        who = "Пользователь" if m["role"] == "user" else "Врач"
        dialog += who + ": " + m["content"] + "\n"

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=600,
        system="Ты извлекаешь медицинские факты. Отвечай только на русском. Только факты, без советов.",
        messages=[{
            "role": "user",
            "content": (
                "Старый профиль:\n" + (old_profile or "нет данных") +
                "\n\nНовый диалог:\n" + dialog +
                "\n\nОбнови профиль — добавь новые факты о здоровье. "
                "Формат: короткие строки. Возраст, пол, рост, вес, диагнозы, лекарства, привычки, жалобы, анализы. "
                "Если новых данных нет — верни старый профиль без изменений."
            )
        }]
    )
    return response.content[0].text
