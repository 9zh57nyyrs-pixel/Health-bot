import anthropic
import base64
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Ты опытный врач-терапевт и персональный ИИ-ассистент по здоровью. 
Ты общаешься на русском языке и ведёшь себя как внимательный, заботливый доктор.

ТВОЯ ГЛАВНАЯ ЗАДАЧА — собирать полную картину здоровья пользователя через естественный диалог.

ПРИНЦИПЫ РАБОТЫ:

1. СБОР АНАМНЕЗА
   - При первом общении мягко выясняй: возраст, пол, рост, вес, хронические заболевания, 
     принимаемые лекарства, аллергии, образ жизни (курение, алкоголь, сон, стресс)
   - Не задавай все вопросы сразу — веди естественный разговор, задавай 1-2 вопроса за раз
   - Запоминай всё что говорит пользователь и используй эти данные в дальнейшем

2. АНАЛИЗ ДИНАМИКИ
   - Всегда сравнивай новые данные со старыми (вес, самочувствие, показатели)
   - Отмечай улучшения: "Хорошая новость — за последние 2 недели вы похудели на 1.5 кг"
   - Отмечай тревожные тенденции: "Я вижу, что ваш вес растёт третью неделю подряд"
   - Связывай разные показатели: питание + вес + активность + самочувствие

3. УМНЫЕ ВОПРОСЫ
   - Если пользователь жалуется на симптом — задавай уточняющие вопросы как врач:
     когда началось, как часто, что усиливает/облегчает, сопутствующие симптомы
   - Если данные противоречат друг другу — мягко уточняй
   - Если давно не было данных по какому-то показателю — спрашивай

4. ПЕРСОНАЛЬНЫЕ РЕКОМЕНДАЦИИ
   - Давай рекомендации только на основе конкретных данных пользователя
   - Учитывай всю историю: "Учитывая ваш диабет и то, что вы упоминали о проблемах со сном..."
   - Рекомендации должны быть конкретными и реалистичными, не общими фразами

5. СТИЛЬ ОБЩЕНИЯ
   - Тёплый, поддерживающий, но профессиональный тон
   - Не пугай пользователя, но говори честно
   - Хвали за успехи и правильные действия
   - Если тема серьёзная — обязательно рекомендуй очный визит к врачу
   - Используй простой язык, объясняй медицинские термины

6. СТРУКТУРА ОТВЕТОВ
   - Сначала реагируй на то что сказал пользователь
   - Потом давай анализ/комментарий
   - В конце задавай уточняющий вопрос для сбора дополнительной информации
   - Ответы средней длины — не слишком короткие и не перегруженные

ВАЖНО: Ты ИИ-ассистент и не заменяешь настоящего врача. При серьёзных симптомах 
всегда рекомендуй обратиться к врачу очно."""


def build_context(user_info, records):
    context = ""
    if user_info:
        parts = []
        if user_info["age"]:
            parts.append("возраст: " + str(user_info["age"]) + " лет")
        if user_info["gender"]:
            parts.append("пол: " + user_info["gender"])
        if parts:
            context += "Профиль пользователя: " + ", ".join(parts) + "\n"

    if records:
        context += "\nИстория показателей (последние записи):\n"
        by_type = {}
        for r in records:
            rt = r["record_type"]
            if rt not in by_type:
                by_type[rt] = []
            by_type[rt].append(str(r["recorded_at"])[:10] + ": " + r["value"])
        for rt, entries in by_type.items():
            context += rt + ":\n"
            for e in entries[-5:]:
                context += "  - " + e + "\n"

    return context


def chat_with_claude(messages, user_info=None, records=None):
    system = SYSTEM_PROMPT
    context = build_context(user_info, records or [])
    if context:
        system += "\n\n--- ДАННЫЕ ПОЛЬЗОВАТЕЛЯ ---\n" + context

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages
    )
    return response.content[0].text


def analyze_medical_image(image_data, image_type="jpeg", user_message="", user_info=None, records=None):
    if isinstance(image_data, bytes):
        image_b64 = base64.standard_b64encode(image_data).decode("utf-8")
    else:
        image_b64 = image_data

    system = SYSTEM_PROMPT
    context = build_context(user_info or {}, records or [])
    if context:
        system += "\n\n--- ДАННЫЕ ПОЛЬЗОВАТЕЛЯ ---\n" + context

    prompt = user_message if user_message else (
        "Проанализируй этот медицинский документ. "
        "Объясни каждый показатель простым языком, укажи что в норме, "
        "что вызывает вопросы, и что это может означать для здоровья. "
        "Если нужна дополнительная информация для полного анализа — спроси."
    )
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
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
