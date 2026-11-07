import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env")
elif (ROOT / ".env.example").exists():
    logging.warning("Файл .env не найден — читаю настройки из .env.example. Лучше переименуйте его в .env")
    load_dotenv(ROOT / ".env.example")


@dataclass(frozen=True)
class Config:
    bot_token: str
    webapp_url: str
    host: str
    port: int
    db_path: str
    default_tz: str


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or ":" not in token or "AAAA..." in token:
        logging.warning("BOT_TOKEN не задан — работаем без Telegram-бота (только приложение и сайт).")
        token = ""
    return Config(
        bot_token=token,
        webapp_url=os.getenv("WEBAPP_URL", "").strip().rstrip("/"),
        host=os.getenv("HOST", "0.0.0.0").strip(),
        port=int(os.getenv("PORT", "8080")),
        db_path=str(ROOT / os.getenv("DB_PATH", "data/kurator.db").strip()),
        default_tz=os.getenv("DEFAULT_TZ", "Asia/Vladivostok").strip(),
    )
