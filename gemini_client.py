import google.generativeai as genai
import os
from google.generativeai.types import RequestOptions

# Настройка ключа
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

class GeminiClient:
    @staticmethod
    async def ask(prompt, user_id, photo_bytes=None):
        # Используем простую версию имени модели без лишних префиксов
        model_name = 'models/gemini-1.5-flash'
        
        try:
            # Принудительно задаем версию API v1 (вместо v1beta)
            model = genai.GenerativeModel(model_name=model_name)
            options = RequestOptions(api_version='v1')
            
            if photo_bytes:
                contents = [
                    "Ты врач-ассистент. Проанализируй анализы на фото.",
                    {"mime_type": "image/jpeg", "data": photo_bytes}
                ]
                # Передаем опции с версией API
                response = model.generate_content(contents, request_options=options)
            else:
                response = model.generate_content(prompt, request_options=options)
            
            return response.text
            
        except Exception as e:
            # Если v1 не сработал, это 100% проблема региона или ключа
            error_msg = str(e)
            if "404" in error_msg:
                return ("❌ Ошибка 404: Google API не видит модель в этом регионе.\n"
                        "Попробуйте зайти в Google AI Studio и создать НОВЫЙ ключ, "
                        "предварительно убедившись, что API Gemini включен.")
            return f"Ошибка AI: {error_msg}"
