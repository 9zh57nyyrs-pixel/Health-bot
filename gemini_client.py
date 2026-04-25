import google.generativeai as genai
import os
import database

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiClient:
    @staticmethod
    async def ask(prompt, user_id, photo_bytes=None):
        user_data = database.get_user(user_id)
        
        # Контекст о пользователе для ИИ
        context = "Данные пользователя: Неизвестны. СНАЧАЛА СОБЕРИ АНКЕТУ."
        if user_data:
            context = f"Данные пользователя: Возраст {user_data['age']}, Пол {user_data['gender']}, Вес {user_data['weight']}кг."

        system_instruction = f"""
        Ты — элитный врач-терапевт. Твоя цель: превентивная медицина.
        {context}
        
        ТВОИ ПРАВИЛА:
        1. ИНИЦИАТИВА: Если в данных профиля пусто, ты обязан вежливо, по очереди собрать: Возраст, Пол, Текущие жалобы, Хронические болезни.
        2. АНАЛИЗ: Если прислали фото, делай глубокий разбор.
        3. ПАМЯТЬ: Ссылайся на предыдущие данные (например: 'Твой вес снизился на 2кг, это хорошо').
        4. КРИТИКА: Будь строг, если пользователь нарушает режим, но поддерживай.
        """

        model = genai.GenerativeModel(model_name='gemini-1.5-flash', system_instruction=system_instruction)
        
        try:
            if photo_bytes:
                res = model.generate_content([{"mime_type": "image/jpeg", "data": photo_bytes}, "Разбери анализы"])
            else:
                res = model.generate_content(prompt)
            return res.text
        except Exception as e:
            return f"Ошибка: {str(e)}"
