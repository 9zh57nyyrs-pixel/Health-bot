import base64
import urllib.request
import json
import os

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

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


def gemini_post(body):
    url = GEMINI_URL + "?key=" + GEMINI_API_KEY
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["candidates"][0]["content"]["parts"][0]["text"]


def build_contents(history, profile=""):
    contents = []
    if profile and profile.strip():
        contents.append({
            "role": "user",
            "parts": [{"text": "Мой профиль здоровья:\n" + profile}]
        })
        contents.append({
            "role": "model",
            "parts": [{"text": "Понял, буду учитывать все данные вашего профиля."}]
        })
    for msg in history:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })
    return contents


def chat(history, profile=""):
    contents = build_contents(history, profile)
    body = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 1024,
            "temperature": 0.7
        }
    }
    return gemini_post(body)


def chat_with_image(image_bytes, caption, history, profile=""):
    contents = build_contents(history, profile)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    text = caption if caption else "Расшифруй этот медицинский документ подробно на русском языке."
    contents.append({
        "role": "user",
        "parts": [
            {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": image_b64
                }
            },
            {"text": text}
        ]
    })
    body = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 1024,
            "temperature": 0.7
        }
    }
    return gemini_post(body)


def update_profile(history, old_profile):
    recent = history[-20:]
    dialog = ""
    for m in recent:
        who = "Пользователь" if m["role"] == "user" else "Врач"
        dialog += who + ": " + m["content"] + "\n"
    body = {
        "contents": [{
            "role": "user",
            "parts": [{"text": (
                "Старый профиль:\n" + (old_profile or "нет данных") +
                "\n\nНовый диалог:\n" + dialog +
                "\n\nОбнови профиль. Добавь новые медицинские факты: возраст, пол, рост, вес, диагнозы, лекарства, привычки, жалобы. "
                "Только факты, без советов. Если новых данных нет — верни старый профиль."
            )}]
        }],
        "generationConfig": {"maxOutputTokens": 500}
    }
    return gemini_post(body)
