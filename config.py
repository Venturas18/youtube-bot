

import os
from dotenv import load_dotenv


load_dotenv()


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not TELEGRAM_BOT_TOKEN or not YOUTUBE_API_KEY:
    raise ValueError("❌ ОШИБКА: TELEGRAM_BOT_TOKEN или YOUTUBE_API_KEY не найдены в окружении! Проверьте файл .env или настройки хостинга.")