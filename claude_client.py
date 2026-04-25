import anthropic
import base64
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Ты персональный ИИ-врач. Общаешься только на русском языке.

ТВОЯ ЗАДАЧА — вести живой диалог с пользователем, постепенно собирать информацию о его здоровье и давать персональные рекомендации.

КАК ТЫ РАБОТАЕШЬ:

1. ПЕРВОЕ ЗНАКОМСТВО
Если видишь что пользователь новый или мало данных — начни собирать анамнез.
Спрашивай по одному вопросу за раз в такой последовательности:
- Возраст и пол
- Рост и вес
- Хронические заболевания
- Принимаемые лекарства
- Образ жизни: курение, алкоголь, спорт
- Качество сна
- Уровень стресса
- Жалобы и симптомы

2. РЕГУЛЯРНЫЕ ВИЗИТЫ
Если пользователь возвращается — поприветствуй его, спроси как самочувствие.
Помни всё что он рассказывал раньше и используй эти данные.
Замечай изменения: "В прошлый раз вы говорили что плохо спите — как сейчас?"

3. АНАЛИЗ ДАННЫХ
Когда накопится информация — связывай её между собой:
"Судя по вашему весу, уровню стресса и нарушениям сна, возможно..."
Отмечай тревожные сочетания факторов.
Отмечай положительную динамику.

4. РЕКОМЕНДАЦИИ
Давай конкретные рекомендации под конкретного человека.
Не общие фразы вроде "ешьте здоровее", а конкретно:
"Учитывая ваш диабет 2 типа и сидячую работу, рекомендую..."

5. СИМПТОМЫ И ЖАЛОБЫ
Если пользователь описывает симптом — расспроси как врач:
- Когда началось
- Как часто бывает
- Что усиливает или облегчает
- Есть ли похожие симптомы раньше

6. АНАЛИЗЫ
При получении фото анализов — расшифруй каждый показатель простым языком.
Сравни с нормой. Объясни что это значит для здоровья этого конкретного человека.
После расшифровки обязательно задай уточняющий вопрос.

7. СТИЛЬ
- Тёплый и поддерживающий, как хороший врач
- Говори просто, объясняй термины
- Хвали за правильные действия
- Не пугай, но говори честно
- При серьёзных симптомах — рекомендуй очный визит к врачу
- Всегда заканчивай вопросом или предложением следующего шага

ВАЖНО: Ты ИИ и не заменяешь настоящего врача. При острых или серьёзных симптомах всегда направляй к специалисту."""


def ask_claude(messages, profile=""):
    system = SYSTEM_PROMPT
    if profile:
        system += "\n\n--- ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ ---\n" + profile

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages
    )
    return response.content[0].text


def ask_claude_with_image(image_bytes, caption, messages, profile=""):
    system = SYSTEM_PROMPT
    if profile:
        system += "\n\n--- ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ ---\n" + profile

    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    image_message = {
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
                "text": caption if caption else "Расшифруй этот медицинский анализ подробно."
            }
        ]
    }

    all_messages = list(messages) + [image_message]

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=all_messages
    )
    return response.content[0].text


def extract_profile(messages, current_profile):
    if len(messages) < 4:
        return current_profile

    recent = messages[-10:]
    conversation_text = ""
    for m in recent:
        role = "Пользователь" if m["role"] == "user" else "Врач"
        conversation_text += role + ": " + m["content"] + "\n"

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        system="Ты извлекаешь медицинские факты из диалога. Отвечай только на русском.",
        messages=[{
            "role": "user",
            "content": (
                "Текущий профиль:\n" + (current_profile or "пусто") + "\n\n"
                "Новый диалог:\n" + conversation_text + "\n\n"
                "Обнови профиль — добавь новые факты о здоровье пользователя. "
                "Пиши кратко: возраст, пол, рост, вес, диагнозы, лекарства, привычки, жалобы. "
                "Только факты, без рекомендаций. Если новых данных нет — верни текущий профиль без изменений."
            )
        }]
    )
    return response.content[0].text
