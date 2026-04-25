import os
import sys
import logging

# Прямой вывод в консоль (отключаем буферизацию)
os.environ['PYTHONUNBUFFERED'] = '1'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

print("--- СИСТЕМНЫЙ ЛОГ: ЗАПУСК ПРОВЕРКИ ---", flush=True)

try:
    from telegram.ext import Application
    import google.generativeai as genai
    print("--- БИБЛИОТЕКИ ЗАГРУЖЕНЫ ---", flush=True)
except Exception as e:
    print(f"--- ОШИБКА ИМПОРТА: {e} ---", flush=True)
    sys.exit(1)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
G_KEY = os.environ.get("GEMINI_API_KEY")

if not TOKEN:
    print("--- ОШИБКА: TELEGRAM_TOKEN НЕ НАЙДЕН ---", flush=True)
    sys.exit(1)

async def main():
    try:
        print("--- ПОПЫТКА ПОДКЛЮЧЕНИЯ К TELEGRAM ---", flush=True)
        app = Application.builder().token(TOKEN).build()
        print("--- БОТ УСПЕШНО АВТОРИЗОВАН ---", flush=True)
        # Упрощенный запуск для проверки
        await app.initialize()
        await app.updater.start_polling()
        await app.start()
        print("--- БОТ В СЕТИ И СЛУШАЕТ СООБЩЕНИЯ ---", flush=True)
    except Exception as e:
        print(f"--- КРИТИЧЕСКАЯ ОШИБКА: {e} ---", flush=True)

if __name__ == '__main__':
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
