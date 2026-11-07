"""Юридические документы: согласие на обработку ПДн, политика, пользовательское соглашение.

Тексты — webapp/legal/*.html. Данные оператора берутся из .env:
  OPERATOR_NAME     — ФИО (или название организации) оператора персональных данных
  OPERATOR_INFO     — необязательно: город, ИНН/ОГРНИП и т. п. (пишется после имени через запятую)
  OPERATOR_CONTACT  — e-mail или другой способ связи; по умолчанию — бот
  SERVER_LOCATION   — где стоит сервер с базой (по умолчанию «Российской Федерации»)
Если тексты существенно меняются — увеличьте VERSION: всех попросят подтвердить согласие заново.
"""
import html
import os
from pathlib import Path

VERSION = "2026-10-28"
DATE = "28 октября 2026 г."
DOCS = {"consent", "privacy", "terms"}
DIR = Path(__file__).resolve().parent.parent / "webapp" / "legal"


def render(name: str, site: str, bot: str) -> str:
    if name not in DOCS:
        raise KeyError(name)
    e = lambda v: html.escape(v.strip())
    operator = os.getenv("OPERATOR_NAME", "").strip() or "Администратор сервиса «Куратор +»"
    info = os.getenv("OPERATOR_INFO", "").strip()
    contact = os.getenv("OPERATOR_CONTACT", "").strip()
    if contact:
        contact_html = (f'<a href="mailto:{e(contact)}">{e(contact)}</a>' if "@" in contact and " " not in contact and not contact.startswith("@")
                        else e(contact))
    else:
        contact_html = f'сообщение в Telegram-боте <a href="https://t.me/{e(bot)}">@{e(bot)}</a>'
    values = {
        "STYLE": (DIR / "_style.css").read_text(encoding="utf-8"),
        "OPERATOR": e(operator),
        "OPERATOR_INFO": (", " + e(info)) if info else "",
        "CONTACT": contact_html,
        "SITE": e(site or ""),
        "BOT": e(bot or ""),
        "DATE": DATE,
        "SERVER_LOCATION": e(os.getenv("SERVER_LOCATION", "").strip() or "Российской Федерации"),
    }
    text = (DIR / f"{name}.html").read_text(encoding="utf-8")
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    return text
