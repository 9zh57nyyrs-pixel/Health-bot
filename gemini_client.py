"""
gemini_client.py — Robust Gemini API wrapper with:
  - Automatic model fallback (gemini-1.5-flash → gemini-1.5-pro → gemini-pro)
  - System instruction as elite medical therapist
  - Multimodal image analysis
  - Async-safe via asyncio.to_thread
"""

import asyncio
import base64
import logging
from typing import Optional

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

logger = logging.getLogger(__name__)

# ─── Model Priority List ──────────────────────────────────────────────────────
# Listed in preference order; first available will be used.
CANDIDATE_MODELS = [
    "models/gemini-1.5-flash",
    "models/gemini-1.5-flash-latest",
    "gemini-1.5-flash",
    "models/gemini-1.5-pro",
    "gemini-1.5-pro",
    "models/gemini-pro",
    "gemini-pro",
]

# ─── Safety Settings (relaxed for medical context) ───────────────────────────
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
}

# ─── System Prompt ────────────────────────────────────────────────────────────
SYSTEM_INSTRUCTION = """Ты — элитный врач-терапевт с 30-летним опытом и энциклопедическими знаниями в области медицины. 
Ты работаешь в формате персонального медицинского ассистента через Telegram.

ТВОИ ПРИНЦИПЫ:
1. Всегда учитывай данные профиля пациента (возраст, пол, вес, рост, хронические заболевания).
2. Давай развёрнутые, структурированные ответы с медицинской точки зрения.
3. Используй понятный язык — объясняй термины простыми словами.
4. При описании симптомов — предлагай возможные причины от наиболее до наименее вероятных.
5. Всегда указывай, когда симптомы требуют срочного обращения к врачу или вызова скорой.
6. При анализе фотографий медицинских документов — расшифровывай показатели, указывай нормы, отмечай отклонения.
7. Не назначай конкретные дозировки лекарств без личного осмотра — рекомендуй классы препаратов.
8. Будь проактивен: задавай уточняющие вопросы для более точной оценки состояния.
9. Форматируй ответы с использованием Markdown: **жирный** для важного, • для списков.
10. В конце каждого ответа добавляй краткую рекомендацию по следующим шагам.

ЗАПРЕЩЕНО:
- Отказываться отвечать на медицинские вопросы без веской причины.
- Давать общие отписки типа «обратитесь к врачу» без конкретной информации.
- Пугать пациента без оснований.

ОБЯЗАТЕЛЬНЫЙ ДИСКЛЕЙМЕР (добавляй только при первом ответе или при серьёзных симптомах):
⚠️ _Мои ответы носят информационный характер и не заменяют очную консультацию врача._
"""

# ─── Generation Config ────────────────────────────────────────────────────────
GENERATION_CONFIG = genai.types.GenerationConfig(
    temperature=0.7,
    top_p=0.95,
    top_k=40,
    max_output_tokens=2048,
)


class GeminiClient:
    """Thread-safe Gemini client with automatic model fallback."""

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model_name = self._find_available_model()
        self._model = self._create_model(self.model_name)
        logger.info(f"GeminiClient initialized with model: {self.model_name}")

    def _find_available_model(self) -> str:
        """
        Query the Gemini API for available models and return the best match.
        Falls back through CANDIDATE_MODELS list.
        """
        try:
            available = {m.name for m in genai.list_models()}
            logger.info(f"Available Gemini models: {available}")

            for candidate in CANDIDATE_MODELS:
                # Check both 'models/name' and bare 'name' formats
                normalized = candidate if candidate.startswith("models/") else f"models/{candidate}"
                if normalized in available or candidate in available:
                    logger.info(f"Selected model: {candidate} (found in available list)")
                    return candidate

            # Last resort: return first candidate and let the API complain if needed
            logger.warning("Could not find preferred models in available list. Using first candidate.")
            return CANDIDATE_MODELS[0]

        except Exception as e:
            logger.error(f"Failed to list models: {e}. Using default fallback.")
            return CANDIDATE_MODELS[0]

    def _create_model(self, model_name: str) -> genai.GenerativeModel:
        """Instantiate GenerativeModel with system instruction."""
        return genai.GenerativeModel(
            model_name=model_name,
            generation_config=GENERATION_CONFIG,
            safety_settings=SAFETY_SETTINGS,
            system_instruction=SYSTEM_INSTRUCTION,
        )

    def _build_history_for_gemini(
        self, history: list[tuple[str, str, str]]
    ) -> list[dict]:
        """Convert DB history tuples to Gemini-compatible format."""
        gemini_history = []
        for role, content, _ in history:
            # Gemini uses 'model' instead of 'assistant'
            gemini_role = "model" if role == "assistant" else "user"
            gemini_history.append({
                "role": gemini_role,
                "parts": [content],
            })
        return gemini_history

    def _sync_chat(
        self,
        user_message: str,
        history: list[tuple[str, str, str]],
        patient_context: str,
    ) -> str:
        """Synchronous Gemini chat call (runs in thread pool)."""
        # Build history without the last user message (we inject it with context)
        gemini_history = self._build_history_for_gemini(history[:-1] if history else [])

        # Enrich user message with patient context
        enriched_message = (
            f"[ДАННЫЕ ПАЦИЕНТА ДЛЯ КОНТЕКСТА: {patient_context}]\n\n"
            f"Вопрос пациента: {user_message}"
        )

        try:
            chat_session = self._model.start_chat(history=gemini_history)
            response = chat_session.send_message(enriched_message)
            return response.text
        except Exception as e:
            logger.error(f"Primary model ({self.model_name}) failed: {e}")
            # Try fallback models
            return self._fallback_chat(enriched_message, gemini_history)

    def _fallback_chat(self, message: str, history: list[dict]) -> str:
        """Try remaining models in CANDIDATE_MODELS list."""
        for candidate in CANDIDATE_MODELS:
            if candidate == self.model_name:
                continue
            try:
                logger.info(f"Trying fallback model: {candidate}")
                fallback_model = self._create_model(candidate)
                chat_session = fallback_model.start_chat(history=history)
                response = chat_session.send_message(message)
                # Update primary model for future requests
                self.model_name = candidate
                self._model = fallback_model
                logger.info(f"Switched to fallback model: {candidate}")
                return response.text
            except Exception as e:
                logger.warning(f"Fallback model {candidate} also failed: {e}")
                continue

        return (
            "⚠️ К сожалению, все доступные модели ИИ временно недоступны. "
            "Пожалуйста, попробуйте позже.\n\n"
            "Если ситуация срочная — позвоните в скорую помощь: *103* или *112*."
        )

    def _sync_analyze_image(
        self,
        image_bytes: bytes,
        patient_context: str,
        caption: str,
    ) -> str:
        """Synchronous image analysis call."""
        prompt_parts = [
            (
                f"[ДАННЫЕ ПАЦИЕНТА: {patient_context}]\n\n"
                "Пациент прислал медицинский документ/анализ для расшифровки.\n"
            ),
        ]

        if caption:
            prompt_parts.append(f"Комментарий пациента: {caption}\n\n")

        prompt_parts.append(
            "Пожалуйста:\n"
            "1. Определи тип документа (анализ крови, ЭКГ, рентген и т.д.)\n"
            "2. Расшифруй основные показатели\n"
            "3. Укажи нормальные референсные значения\n"
            "4. Отметь отклонения и их возможное клиническое значение\n"
            "5. Дай рекомендации по дальнейшим действиям\n"
        )

        # Determine MIME type (simplistic: assume JPEG, works for most photos)
        mime_type = "image/jpeg"
        if image_bytes[:4] == b'\x89PNG':
            mime_type = "image/png"
        elif image_bytes[:2] == b'\xff\xd8':
            mime_type = "image/jpeg"

        image_part = {
            "mime_type": mime_type,
            "data": image_bytes,
        }

        try:
            response = self._model.generate_content(["\n".join(str(p) for p in prompt_parts), image_part])
            return response.text
        except Exception as e:
            logger.error(f"Image analysis failed with {self.model_name}: {e}")
            # Try vision-capable fallback
            for candidate in CANDIDATE_MODELS:
                if candidate == self.model_name:
                    continue
                try:
                    logger.info(f"Trying fallback for image: {candidate}")
                    fallback = self._create_model(candidate)
                    response = fallback.generate_content(
                        ["\n".join(str(p) for p in prompt_parts), image_part]
                    )
                    return response.text
                except Exception as fe:
                    logger.warning(f"Image fallback {candidate} failed: {fe}")
                    continue

            return (
                "⚠️ Не удалось проанализировать изображение. "
                "Убедитесь, что фото чёткое и хорошо освещённое, затем попробуйте снова."
            )

    # ─── Public Async Interface ───────────────────────────────────────────────

    async def chat(
        self,
        user_message: str,
        history: list[tuple[str, str, str]],
        patient_context: str,
    ) -> str:
        """Async wrapper for text consultation."""
        return await asyncio.to_thread(
            self._sync_chat,
            user_message=user_message,
            history=history,
            patient_context=patient_context,
        )

    async def analyze_image(
        self,
        image_bytes: bytes,
        patient_context: str,
        caption: str = "",
    ) -> str:
        """Async wrapper for multimodal image analysis."""
        return await asyncio.to_thread(
            self._sync_analyze_image,
            image_bytes=image_bytes,
            patient_context=patient_context,
            caption=caption,
        )
