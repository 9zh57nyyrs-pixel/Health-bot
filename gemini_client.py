import google.generativeai as genai
import os

# Инициализация
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiClient:
    @staticmethod
    async def ask(prompt, user_id, photo_bytes=None):
        # Пробуем по очереди разные обращения к модели
        variants = ['gemini-1.5-flash', 'models/gemini-1.5-flash', 'gemini-pro']
        
        for model_name in variants:
            try:
                model = genai.GenerativeModel(model_name)
                if photo_bytes:
                    # Упрощенная отправка фото
                    response = model.generate_content([
                        "Проанализируй медицинский документ на фото.", 
                        {"mime_type": "image/jpeg", "data": photo_bytes}
                    ])
                else:
                    response = model.generate_content(prompt)
                
                return response.text
            except Exception as e:
                error_str = str(e)
                # Если это не ошибка 404, а что-то другое (например, ключ), стопаем
                if "404" not in error_str:
                    return f"Критическая ошибка: {error_str}"
                continue
        
        return "❌ Ошибка 404 сохраняется. Google блокирует доступ из этого региона или по этому ключу."
