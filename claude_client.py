import google.generativeai as genai
import os

# Инициализация Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiClient:
    @staticmethod
    async def ask(prompt, user_id, photo_bytes=None):
        # Используем модель Gemini 1.5 Flash (быстрая и эффективная)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        try:
            if photo_bytes:
                # Если передано фото (например, анализы)
                contents = [
                    "Ты профессиональный врач-ассистент. Проанализируй это фото медицинских анализов. "
                    "Объясни значения, выдели отклонения и дай рекомендации, к какому врачу обратиться. "
                    "НЕ заменяй реальный поход к врачу.",
                    {"mime_type": "image/jpeg", "data": photo_bytes}
                ]
                response = model.generate_content(contents)
            else:
                # Обычный текст
                response = model.generate_content(prompt)
            
            return response.text
        except Exception as e:
            return f"Ошибка AI: {str(e)}"
