import google.generativeai as genai
import os
import database

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiClient:
    @staticmethod
    async def ask(prompt, user_id, photo_bytes=None):
        # 1. Загружаем данные пользователя из базы
        user_data = database.get_user(user_id)
        
        # 2. Формируем контекст для ИИ
        if user_data:
            profile_info = f"Пациент: {user_data['age']} лет, пол {user_data['gender']}, вес {user_data['weight']} кг."
        else:
            profile_info = "Профиль пациента пуст. Твоя задача — собрать данные (возраст, пол, вес, жалобы)."

        system_instruction = f"""
        Ты — элитный врач-терапевт. Твоя задача — вести пациента.
        {profile_info}
        
        ПРАВИЛА ПОВЕДЕНИЯ:
        - Если данных профиля нет, начни опрос. Не спрашивай всё сразу, задавай по 1-2 вопроса.
        - Если прислали фото анализов — проведи детальный разбор.
        - Будь проактивен: сам предлагай, какие анализы сдать исходя из возраста.
        - Всегда добавляй дисклеймер: 'Я — ИИ, проконсультируйтесь с врачом'.
        """

        try:
            model = genai.GenerativeModel(model_name='gemini-1.5-flash', system_instruction=system_instruction)
            
            if photo_bytes:
                response = model.generate_content([
                    {"mime_type": "image/jpeg", "data": photo_bytes},
                    "Разбери анализы и сравни с нормой."
                ])
            else:
                response = model.generate_content(prompt)
            
            return response.text
        except Exception as e:
            return f"Ошибка ИИ: {str(e)}"
