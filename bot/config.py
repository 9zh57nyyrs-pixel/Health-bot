
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    ADMIN_ID = os.getenv("ADMIN_ID")
    MODE = os.getenv("MODE", "polling")
    
    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не задан!")
        if not cls.GEMINI_API_KEY and not cls.OPENROUTER_API_KEY:
            raise ValueError("GEMINI_API_KEY или OPENROUTER_API_KEY должен быть задан!")
