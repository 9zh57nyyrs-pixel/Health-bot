import google.generativeai as genai
import os

# Настройка
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiClient:
    @staticmethod
    async def ask(prompt, user_id, photo_bytes=None):
        # Самое стабильное имя модели
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        try:
            if photo_bytes:
                # Упрощенный формат для фото
                contents = [
                    {"mime_type": "image/jpeg", "data": photo_bytes},
                    "Ты врач-ассистент. Проанализируй фото анализов."
                ]
                response = model.generate_content(contents)
            else:
                response = model.generate_content(prompt)
            
            return response.text
        except Exception as e:
            return f"Ошибка Gemini: {str(e)}"
