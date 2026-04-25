import google.generativeai as genai
import os

# Подключаем ключ
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

class GeminiClient:
    @staticmethod
    async def ask(prompt, user_id, photo_bytes=None):
        # Список моделей от самой новой к самой стабильной
        model_names = [
            'gemini-1.5-flash-latest', 
            'gemini-1.5-flash', 
            'gemini-pro'
        ]
        
        last_error = ""
        
        for name in model_names:
            try:
                model = genai.GenerativeModel(model_name=name)
                
                if photo_bytes:
                    # Современный формат передачи медиа для Gemini 1.5
                    contents = [
                        {
                            "role": "user",
                            "parts": [
                                {"text": "Ты медицинский эксперт. Проанализируй фото анализов, выдели отклонения и дай советы."},
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
                last_error = str(e)
                continue # Пробуем следующую модель из списка
        
        return f"Ошибка перебора моделей: {last_error}. Проверьте, активен ли Gemini API в Google AI Studio."
