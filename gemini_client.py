import google.generativeai as genai
import os
import logging

# Настройка логирования для отладки на Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY отсутствует в переменных окружения!")
        genai.configure(api_key=api_key)
        
    async def get_response(self, prompt, context_data, photo_bytes=None):
        # Список моделей для проверки доступности
        model_names = ['gemini-1.5-flash', 'gemini-1.5-pro']
        
        system_instruction = f"""
        Ты — главный врач-терапевт. Твоя задача: проактивное ведение пациента.
        ДАННЫЕ ПАЦИЕНТА: {context_data}
        
        ТВОЙ ПРОТОКОЛ:
        1. Если данных нет, начни опрос (возраст, вес, жалобы).
        2. При получении анализов — делай сравнительную таблицу с нормой.
        3. Если симптомы опасны — направляй к очному врачу.
        """
        
        for m_name in model_names:
            try:
                model = genai.GenerativeModel(
                    model_name=m_name,
                    system_instruction=system_instruction
                )
                
                if photo_bytes:
                    content = [{"mime_type": "image/jpeg", "data": photo_bytes}, prompt]
                else:
                    content = prompt
                
                response = model.generate_content(content)
                return response.text
            except Exception as e:
                logger.warning(f"Модель {m_name} недоступна: {e}")
                continue
        
        return "❌ Ошибка: Все модели Gemini недоступны. Проверьте регион сервера или API ключ."
