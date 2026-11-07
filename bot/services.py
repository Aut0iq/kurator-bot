"""Действия, которые нужны и чат-боту, и Mini App."""
import asyncio
import logging
from datetime import date

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile

from db import DB
from excel import build_report
from logic import esc

log = logging.getLogger(__name__)


async def safe_send(bot: Bot, chat_id: int, text: str, **kw) -> bool:
    if chat_id <= -8_000_000_000_000:          # демо-участники и студенты без Telegram — писать некому
        return False
    for _ in range(3):
        try:
            await bot.send_message(chat_id, text, **kw)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError:
            return False  # пользователь заблокировал бота
        except Exception as e:  # noqa: BLE001
            log.warning("send to %s failed: %s", chat_id, e)
            return False
    return False


async def announce(bot: Bot, db: DB, gid: int, author: dict, text: str, title: str | None = None,
                   pinned: bool = False) -> int:
    group = db.group(gid)
    aid = db.add_announcement(gid, author["tg_id"], title, text, pinned)
    head = f"📢 <b>{esc(title)}</b>" if title else f"📢 <b>Объявление · {esc(group['name'])}</b>"
    msg = f"{head}\n\n{esc(text)}\n\n— <i>{esc(author['full_name'])}</i>"
    sent = 0
    for m in db.members(gid):
        if m["tg_id"] == author["tg_id"]:
            continue
        if await safe_send(bot, m["tg_id"], msg, parse_mode="HTML"):
            sent += 1
        await asyncio.sleep(0.05)  # не упираемся в лимиты Telegram
    db.set_delivered(aid, sent)
    db.add_feed(gid, "announce", "📢 " + (title or "Объявление"), text[:500], author=author["tg_id"])
    return sent


async def send_file(bot: Bot, chat_id: int, f: dict) -> None:
    caption = f"📚 {f['subject']} · {f['title']}"[:1000]
    if f["file_type"] == "photo":
        await bot.send_photo(chat_id, f["file_id"], caption=caption)
    else:
        await bot.send_document(chat_id, f["file_id"], caption=caption)


async def send_report(bot: Bot, db: DB, gid: int, chat_id: int, d1: date, d2: date) -> None:
    group = db.group(gid)
    data = build_report(group, db.students(gid, include_archived=True),
                        db.attendance_range(gid, d1.isoformat(), d2.isoformat()), d1, d2)
    name = f"poseshaemost_{d1:%d.%m}-{d2:%d.%m.%Y}.xlsx"
    await bot.send_document(chat_id, BufferedInputFile(data, filename=name),
                            caption=f"📊 Посещаемость «{group['name']}» за {d1:%d.%m.%Y} – {d2:%d.%m.%Y}")


async def send_grades(bot: Bot, db: DB, gid: int, chat_id: int, month: str) -> None:
    import grades
    group = db.group(gid)
    view = grades.month_view(db, gid, month)
    if not view:
        raise ValueError("Ведомость за этот месяц не найдена")
    curator = next((m["full_name"] for m in db.members(gid) if m["role"] == "curator"), None)
    rows = [{"name": r["full_name"], "record_no": r["record_no"], "grades": r["grades"], "missed_total": r["missed_total"],
             "missed_bad": r["missed_bad"], "note": r["note"]} for r in view["rows"] if not r["archived"]]
    data = grades.build_sheet(group, month, view["subjects"], rows, curator)
    s = view["summary"]
    await bot.send_document(chat_id, BufferedInputFile(data, filename=f"vedomost_{group['name']}_{month}.xlsx"),
                            caption=f"📒 Сведения успеваемости «{group['name']}» за {view['title'].lower()}\n"
                                    f"Средний балл: {s['avg'] or '—'} · качество знаний: {s['quality'] or '—'}% · "
                                    f"успеваемость: {s['progress'] or '—'}%")


async def set_lock(db: DB, bot: Bot, on: bool, text: str, notify: bool, by: int) -> int:
    """Главный куратор закрывает / открывает доступ всем, кроме главных кураторов. Возвращает, скольким написали."""
    import time
    from perms import SUPER_IDS
    db.set_setting("lock", {"on": on, "text": text, "at": int(time.time()), "by": by})
    log.warning("Доступ %s главным куратором %s", "ЗАКРЫТ" if on else "открыт", by)
    sent = 0
    if notify:
        msg = (f"🔒 <b>Доступ к боту временно закрыт</b>\n\n{esc(text)}" if on and text else
               "🔒 <b>Доступ к боту временно закрыт.</b>\nМы сообщим, когда всё снова заработает." if on else
               "✅ <b>Бот снова работает!</b> Можно пользоваться как обычно.")
        for uid in db.all_member_ids():
            if uid in SUPER_IDS:
                continue
            if await safe_send(bot, uid, msg, parse_mode="HTML"):
                sent += 1
            await asyncio.sleep(0.05)                 # не упираемся в лимиты Telegram
    return sent


async def notify_change(bot: Bot, db: DB, gid: int, lesson: dict, change: dict, author_tg: int, cancelled: bool = False) -> int:
    """Рассылает группе уведомление об отмене / переносе / смене аудитории (или о том, что всё вернули как было)."""
    from logic import change_text
    if cancelled:
        from datetime import date as _d
        d = _d.fromisoformat(change["date"])
        msg = f"↩️ <b>Изменение отменено</b>\n{esc(lesson['subject'])} {d:%d.%m}, {lesson['t_start']} — по расписанию, как обычно."
    else:
        msg = change_text(change, lesson)
    import re
    plain = re.sub(r"<[^>]+>", "", msg).split("\n", 1)
    db.add_feed(gid, "change", plain[0], plain[1] if len(plain) > 1 else None, author=author_tg)
    sent = 0
    for m in db.members(gid):
        if m["tg_id"] == author_tg:
            continue
        if await safe_send(bot, m["tg_id"], msg, parse_mode="HTML"):
            sent += 1
        await asyncio.sleep(0.04)
    return sent
