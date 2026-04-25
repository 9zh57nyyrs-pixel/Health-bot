import google.generativeai as genai
import os

# Настройка
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

class GeminiClient:
    @staticmethod
    async def ask(prompt, user_id, photo_bytes=None):
        try:
            # ПРИНУДИТЕЛЬНО находим актуальное имя модели Flash
            # Google может называть её 'models/gemini-1.5-flash-latest' или иначе
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            
            # Ищем что-то похожее на 1.5 flash или 1.0 pro
            target_model = None
            for m in ['models/gemini-1.5-flash', 'models/gemini-1.5-flash-latest', 'models/gemini-pro']:
                if m in available_models:
                    target_model = m
                    break
            
            if not target_model:
                target_model = available_models[0] # Берем любую доступную, если наши не нашлись

            model = genai.GenerativeModel(target_model)
            
            if photo_bytes:
                content = [
                    {"mime_type": "image/jpeg", "data": photo_bytes},
                    "Ты врач-ассистент. Проанализируй фото анализов."
                ]
                response = model.generate_content(content)
            else:
                response = model.generate_content(prompt if prompt else "Привет")
            
            return response.text

        except Exception as e:
            return f"❌ Ошибка API: {str(e)}\nДоступные модели: {', '.join(available_models[:3]) if 'available_models' in locals() else 'нет'}"
