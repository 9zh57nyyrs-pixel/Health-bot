import google.generativeai as genai
import os

# Инициализация
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

class GeminiClient:
    @staticmethod
    async def ask(prompt, user_id, photo_bytes=None):
        # Пробуем использовать модель 1.5-flash, которая наиболее стабильна
        # Если 1.5-flash выдает 404, пробуем 1.5-pro
        model_name = 'gemini-1.5-flash'
        
        try:
            model = genai.GenerativeModel(model_name)
            
            if photo_bytes:
                # Для работы с изображениями в версии 1.5
                contents = [
                    {
                        "parts": [
                            {"text": "Ты медицинский эксперт. Проанализируй анализы на фото, выдели отклонения и дай советы."},
                            {"inline_data": {"mime_type": "image/jpeg", "data": photo_bytes}}
                        ]
                    }
                ]
                response = model.generate_content(contents)
            else:
                # Обычный текст
                response = model.generate_content(prompt)
            
            return response.text
            
        except Exception as e:
            # Если flash не найден, пробуем универсальный поиск доступной модели
            if "404" in str(e):
                return "Ошибка: Модель Gemini 1.5 Flash не найдена. Проверьте правильность API ключа или региональные ограничения в Railway."
            return f"Ошибка AI: {str(e)}"
