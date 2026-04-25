import google.generativeai as genai
import os
import database

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiClient:
    @staticmethod
    async def get_medical_advice(user_id, message, is_photo=False, photo_data=None):
        profile = database.get_profile(user_id)
        
        # Формируем глубокий контекст
        context = "ПРОФИЛЬ ПАЦИЕНТА:\n"
        if profile:
            context += f"- Возраст: {profile.get('age', 'Не указан')}\n"
            context += f"- Пол: {profile.get('gender', 'Не указан')}\n"
            context += f"- Вес/Рост: {profile.get('weight')}/{profile.get('height')}\n"
            context += f"- Анамнез: {profile.get('chronic_diseases', 'Нет данных')}\n"
        
        instruction = f"""
        Ты — высококвалифицированный врач-терапевт. Твоя задача — вести пациента.
        {context}
        
        ТВОИ КОМПЕТЕНЦИИ:
        1. Интерпретация анализов крови, мочи, УЗИ, МРТ.
        2. Формирование плана обследований на основе возраста и жалоб.
        3. Отслеживание динамики веса и давления.
        4. Определение 'красных флагов' и немедленное направление к специалистам.

        ПРАВИЛА:
        - Если данных в профиле нет, настойчиво, но вежливо проси их предоставить.
        - Никогда не ставь окончательный диагноз, используй формулировки 'высокая вероятность', 'рекомендуется исключить'.
        - Обязательно добавляй юридический дисклеймер.
        """

        model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=instruction)
        
        try:
            if is_photo:
                response = model.generate_content([{"mime_type": "image/jpeg", "data": photo_data}, message])
            else:
                response = model.generate_content(message)
            return response.text
        except Exception as e:
            return f"⚠️ Ошибка медицинского модуля: {str(e)}"
