import anthropic
import base64
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Ты ИИ-ассистент и личный врач для русскоязычных пользователей.
ВСЕГДА отвечай на русском языке, независимо от языка пользователя.

Ты помогаешь:
- Отслеживать вес, питание и физическую активность
- Расшифровывать медицинские анализы по фото
- Составлять план обследований по возрасту и полу
- Оценивать здоровье по шкале 1-10
- Отвечать на медицинские вопросы

Важные правила:
- ВСЕГДА пиши на русском языке
- Напоминай, что ты ИИ и не заменяешь настоящего врача
- При серьёзных симптомах всегда рекомендуй обратиться к врачу
- Будь тёплым, эмпатичным и понятным
- Используй простой язык, объясняй медицинские термины
- При оценке здоровья объясняй каждый балл"""


def chat_with_claude(messages, user_info=None):
    system = SYSTEM_PROMPT
    if user_info and (user_info["age"] or user_info["gender"]):
        age = user_info["age"] or "не указан"
        gender = user_info["gender"] or "не указан"
        system += "\n\nПрофиль пользователя: возраст " + str(age) + ", пол: " + str(gender)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages
    )
    return response.content[0].text


def analyze_medical_image(image_data, image_type="jpeg", user_message=""):
    if isinstance(image_data, bytes):
        image_b64 = base64.standard_b64encode(image_data).decode("utf-8")
    else:
        image_b64 = image_data
    prompt = user_message if user_message else (
        "Проанализируй этот медицинский документ или результат анализа. "
        "Объясни значения на русском языке и укажи, если что-то требует внимания."
    )
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/" + image_type,
                        "data": image_b64
                    }
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        }]
    )
    return response.content[0].text
