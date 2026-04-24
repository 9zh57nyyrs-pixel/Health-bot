import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv(“TELEGRAM_TOKEN”)
ANTHROPIC_API_KEY = os.getenv(“ANTHROPIC_API_KEY”)

if not TELEGRAM_TOKEN:
raise ValueError(“TELEGRAM_TOKEN не задан в .env файле!”)

if not ANTHROPIC_API_KEY:
raise ValueError(“ANTHROPIC_API_KEY не задан в .env файле!”)