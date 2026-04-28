import aiohttp
import json
from bot.config import Config

async def analyze_symptoms(symptoms_data: dict) -> dict:
    """
    Анализирует симптомы через Gemini API (Google)
    """
    
    prompt = f"""Ты - медицинский ассистент. Ты НЕ врач и НЕ ставишь диагнозы.
    Твоя задача - проанализировать жалобы пациента и дать ОБЩУЮ информацию.
    
    ДАННЫЕ ПАЦИЕНТА:
    - Возраст: {symptoms_data.get('age', 'не указан')}
    - Пол: {symptoms_data.get('gender', 'не указан')}
    - Основная жалоба: {symptoms_data.get('main_complaint', 'не указана')}
    - Длительность: {symptoms_data.get('duration', 'не указана')}
    - Тяжесть (1-5): {symptoms_data.get('severity', 'не указана')}
    - Дополнительные симптомы: {symptoms_data.get('additional_symptoms', 'нет')}
    - Хронические заболевания: {symptoms_data.get('chronic_diseases', 'нет')}
    - Принимаемые препараты: {symptoms_data.get('medications', 'нет')}
    - Аллергии: {symptoms_data.get('allergies', 'нет')}
    
    ВАЖНЫЕ ПРАВИЛА:
    1. НИКОГДА не ставь диагноз
    2. НИКОГДА не назначай лечение (дозировки, курсы)
    3. Используй фразы "возможно", "стоит проверить", "рекомендуется"
    4. Всегда направляй к врачу
    5. При серьезных симптомах - настаивай на немедленном обращении
    
    Ответь строго в формате JSON:
    {{
        "urgency": "low|medium|high|emergency",
        "possible_areas": ["область1", "область2"],
        "recommended_specialist": "название специалиста",
        "analysis": "краткий анализ симптомов",
        "recommendations": ["рекомендация1", "рекомендация2"],
        "warnings": ["предупреждение1"],
        "disclaimer": "текст дисклеймера"
    }}
    """
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Content-Type": "application/json"
            }
            
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 1000
                }
            }
            
            # Используем Gemini API
            api_key = Config.GEMINI_API_KEY
            
            if not api_key:
                return {
                    "urgency": "medium",
                    "possible_areas": ["требуется осмотр"],
                    "recommended_specialist": "Терапевт",
                    "analysis": "API ключ не настроен. Рекомендуется консультация врача.",
                    "recommendations": ["Обратитесь к врачу"],
                    "warnings": [],
                    "disclaimer": "Это не медицинская консультация."
                }
            
            async with session.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
                headers=headers,
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Извлекаем текст из ответа Gemini
                    try:
                        content = data["candidates"][0]["content"]["parts"][0]["text"]
                        
                        # Пытаемся распарсить JSON
                        content = content.replace("```json", "").replace("```", "").strip()
                        result = json.loads(content)
                        return result
                    except (KeyError, json.JSONDecodeError):
                        return {
                            "urgency": "medium",
                            "possible_areas": ["требуется осмотр"],
                            "recommended_specialist": "Терапевт",
                            "analysis": content if 'content' in dir() else "Анализ требует уточнения. Обратитесь к врачу.",
                            "recommendations": ["Обратитесь к врачу для осмотра"],
                            "warnings": [],
                            "disclaimer": "Это не медицинская консультация. Обратитесь к врачу."
                        }
                else:
                    error_text = await response.text()
                    return {
                        "urgency": "medium",
                        "possible_areas": ["требуется осмотр"],
                        "recommended_specialist": "Терапевт",
                        "analysis": f"Ошибка API: {error_text}. Рекомендуется консультация врача.",
                        "recommendations": ["Запишитесь к терапевту"],
                        "warnings": [],
                        "disclaimer": "Это не медицинская консультация."
                    }
    except Exception as e:
        return {
            "urgency": "medium",
            "possible_areas": ["требуется осмотр"],
            "recommended_specialist": "Терапевт",
            "analysis": f"Ошибка анализа: {str(e)}. Рекомендуется консультация врача.",
            "recommendations": ["Обратитесь к врачу"],
            "warnings": [],
            "disclaimer": "Это не медицинская консультация."
        }
