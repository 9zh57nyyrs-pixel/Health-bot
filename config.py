import os
from dotenv import load_dotenv
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DATABASE_PATH = "health_bot.db"
CLAUDE_MODEL = "claude-opus-4-5"
MAX_TOKENS = 2048
