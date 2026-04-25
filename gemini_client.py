import google.generativeai as genai
import os

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ВАЖНО: Это "личность" вашего бота. 
SYSTEM_INSTRUCTION = """
Ты — специализированный ИИ-врач, персональный ассистент пользователя в Telegram. 
Твои задачи:
1. Анализ медицинских анализов по фото: интерпретируй показатели, указывай на отклонения от нормы.
2. Мониторинг здоровья: помогай фиксировать вес, питание и активность.
3. План обследований: на основе возраста и пола пользователя предлагай чекапы.
4. Оценка здоровья: оценивай состояние пользователя по шкале от 1 до 10.
5. Безопасность: Если пользователь пишет о критических симптомах (острая боль в груди, удушье), первым делом рекомендуй вызвать скорую помощь (103/112).

Твой стиль: профессиональный, поддерживающий, лаконичный. 
ВАЖНО: Всегда добавляй дисклеймер, что ты ИИ, а не живой врач, и твои советы носят информационный характер.
"""

class GeminiClient:
    @staticmethod
    async def ask(prompt, user_id, photo_bytes=None):
        try:
            # Находим доступную модель
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            target_model = 'models/gemini-1.5-flash' if 'models/gemini-1.5-flash' in available_models else available_models[0]

            # Инициализируем модель с СИСТЕМНОЙ ИНСТРУКЦИЕЙ
            model = genai.GenerativeModel(
                model_name=target_model,
                system_instruction=SYSTEM_INSTRUCTION
            )
            
            if photo_bytes:
                content = [
                    {"mime_type": "image/jpeg", "data": photo_bytes},
                    "Проанализируй эти анализы как врач-ассистент."
                ]
                response = model.generate_content(content)
            else:
                response = model.generate_content(prompt if prompt else "Привет!")
            
            return response.text

        except Exception as e:
            return f"Ошибка AI: {str(e)}"
