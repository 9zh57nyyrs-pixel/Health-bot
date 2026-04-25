import google.generativeai as genai
import os

# Прямая настройка
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiClient:
    @staticmethod
    async def ask(prompt, user_id, photo_bytes=None):
        try:
            # Важно: используем 'models/gemini-1.5-flash' с полным путем
            model = genai.GenerativeModel('models/gemini-1.5-flash')
            
            if photo_bytes:
                # Новый формат передачи мультимодальных данных
                content = [
                    {"mime_type": "image/jpeg", "data": photo_bytes},
                    "Ты профессиональный врач-ассистент. Проанализируй это фото анализов."
                ]
                response = model.generate_content(content)
            else:
                # Обычный текстовый запрос
                response = model.generate_content(prompt)
            
            return response.text

        except Exception as e:
            error_msg = str(e)
            # Если 404 — пробуем последнюю попытку через старую модель Pro
            if "404" in error_msg:
                try:
                    fallback = genai.GenerativeModel('models/gemini-pro')
                    res = fallback.generate_content(prompt if prompt else "Привет")
                    return res.text
                except:
                    return "❌ Ошибка: Google API всё еще не видит модели. Попробуйте создать НОВЫЙ проект в AI Studio, а не просто новый ключ."
            
            return f"Ошибка AI: {error_msg}"
