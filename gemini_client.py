import google.generativeai as genai
import os
import database

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiClient:
    @staticmethod
    async def get_response(user_id, text_input=None, photo_bytes=None):
        profile, metrics = database.get_full_context(user_id)
        
        # Формируем клиническую картину для ИИ
        context = "КЛИНИЧЕСКАЯ КАРТИНА ПАЦИЕНТА:\n"
        if profile:
            context += f"- Возраст: {profile['age']}, Пол: {profile['gender']}, Вес: {profile['weight']}\n"
            context += f"- Хронические заболевания: {profile['chronic_diseases'] or 'Не указано'}\n"
        else:
            context += "- ДАННЫЕ ОТСУТСТВУЮТ. ТРЕБУЕТСЯ АНКЕТИРОВАНИЕ.\n"
        
        system_prompt = f"""
        Ты — ведущий врач-терапевт с 20-летним стажем. Твоя цель — превентивное здоровье.
        {context}
        
        ТВОИ ЗАДАЧИ:
        1. ИНИЦИАТИВА: Если в профиле не хватает данных (возраст, вес, пол), ты обязан ПРЕРВАТЬ любой разговор и вежливо запросить эти данные по одному.
        2. АНАЛИЗ ФОТО: Если прислали анализы, разбери каждый пункт, сравни с нормами и выдели критические отклонения.
        3. РЕКОМЕНДАЦИИ: На основе возраста (например, если >40 лет), сам предлагай ежегодный чекап (УЗИ, ПСА, Маммография).
        4. СТИЛЬ: Профессиональный, но человечный. Избегай воды.
        
        ВНИМАНИЕ: Если пациент жалуется на симптомы 'красных флагов' (боль за грудиной, онемение лица), немедленно требуй вызвать скорую.
        """

        try:
            model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=system_prompt)
            
            if photo_bytes:
                content = [{"mime_type": "image/jpeg", "data": photo_bytes}, 
                           text_input if text_input else "Проанализируй документ."]
                response = model.generate_content(content)
            else:
                response = model.generate_content(text_input)
            
            return response.text
        except Exception as e:
            return f"⚠️ Ошибка медицинского модуля: {str(e)}"
