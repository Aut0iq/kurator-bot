"""Фоновый планировщик: опросы перед парами, сводки, недельные итоги."""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot

import polls
from db import DB
from logic import esc, now_in
from services import safe_send

log = logging.getLogger(__name__)


def minutes_until(now: datetime, hhmm: str) -> float:
    h, m = map(int, hhmm.split(":"))
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return (target - now).total_seconds() / 60


async def tick(bot: Bot, db: DB, webapp_url: str) -> None:
    from datetime import date as _date, timedelta as _td
    if db.once(f"prune_presence:{_date.today()}"):       # история «кто в сети» — 30 дней
        import time as _t
        db.prune_presence((_date.today() - _td(days=30)).isoformat())
        db.prune_feed(int(_t.time()) - 14 * 86400)           # события для уведомлений приложения — 14 дней
        db.prune_audit(int(_t.time()) - 365 * 86400)         # журнал действий — год
    if db.lock():                       # доступ закрыт главным куратором — опросы и сводки на паузе
        return
    demo_gid = db.setting("demo_gid")
    for g in db.all_groups():
        if g["id"] == demo_gid:            # демо-группа: никаких опросов и рассылок
            continue
        now = now_in(g["tz"])
        today = now.date()
        d = today.isoformat()

        # Домашние задания: вечером накануне срока — напоминание
        if now.hour >= 18 and db.once(f"hwrem:{g['id']}:{d}"):
            import features
            await features.homework_reminders(bot, db, g, now)

        # Итоги недели — в воскресенье после 18:00
        if today.weekday() == 6 and now.hour >= 18 and db.once(f"digest:{g['id']}:{today.isocalendar()[:2]}"):
            await polls.weekly_digest(bot, db, g)

        for l in polls.todays_lessons(db, g, today):
            left = minutes_until(now, l["t_start"])
            lead = int(g["remind_minutes"] or 0)
            summary_after = int(g["summary_minutes"] or 10)

            # 1) опрос: в окне [начало-lead, начало+summary)
            if g["polls_enabled"] and lead and -summary_after < left <= lead and db.once(f"poll:{l['id']}:{d}"):
                await polls.send_polls(bot, db, g, l, d, max(1, round(left)), webapp_url)

            # 2) сводка: через summary_after минут после начала
            if -summary_after - 90 <= left <= -summary_after:
                if db.happened(f"poll:{l['id']}:{d}"):
                    if db.once(f"summary:{l['id']}:{d}"):
                        await polls.summarize(bot, db, g, l, d, webapp_url)
                elif not db.marks(l["id"], d) and db.once(f"nomark:{l['id']}:{d}"):
                    for m in db.staff(g["id"], "attendance"):
                        await safe_send(bot, m["tg_id"], f"📝 Посещаемость на паре «{esc(l['subject'])}» "
                                                         f"({l['t_start']}) ещё не отмечена.")


async def scheduler(bot: Bot, db: DB, webapp_url: str) -> None:
    while True:
        try:
            await tick(bot, db, webapp_url)
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        await asyncio.sleep(20)
