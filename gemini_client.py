import google.generativeai as genai
import os
import logging

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        # Список моделей для проверки (от новых к старым)
        self.available_models = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']

    async def generate_response(self, prompt, user_context, photo_bytes=None):
        system_msg = f"Ты — экспертный врач-терапевт. Контекст пациента: {user_context}. Будь точен, проси анализы, если их нет."
        
        for model_name in self.available_models:
            try:
                model = genai.GenerativeModel(model_name=model_name, system_instruction=system_msg)
                if photo_bytes:
                    content = [{"mime_type": "image/jpeg", "data": photo_bytes}, prompt]
                else:
                    content = prompt
                
                response = model.generate_content(content)
                return response.text
            except Exception as e:
                logger.error(f"Ошибка модели {model_name}: {e}")
                continue
        
        return "⚠️ Ошибка связи с медицинским модулем (404/Quota). Проверьте API ключ в Google Cloud."
