"""Опрос перед парой и сводка старосте — главная механика бота.

За N минут до пары каждый привязанный студент получает сообщение с кнопками
«Буду / Опоздаю / Не смогу». Через M минут после начала пары опрос закрывается:
кто промолчал — получает «не ответил» (считается пропуском), а староста и помощник
получают сводку. Отдельно отслеживаются прогулы по предмету.
"""
import asyncio
import logging
from datetime import date, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from db import DB
from logic import apply_changes, esc, lessons_for_date, semester_range, today_in, truancy
from services import safe_send

log = logging.getLogger(__name__)
ANSWERS = {"P": "✅ Буду", "L": "⏰ Опоздаю", "A": "❌ Не смогу"}
ANSWER_DONE = {"P": "✅ Вы ответили: буду на паре", "L": "⏰ Вы ответили: опоздаю",
               "A": "❌ Вы ответили: не смогу прийти", "E": "📄 Уважительная причина принята",
               "N": "— Вы не ответили на опрос"}


def poll_kb(lid: int, d: str, current: str | None = None) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=("• " if current == k else "") + v, callback_data=f"poll:{lid}:{d}:{k}")
           for k, v in ANSWERS.items()]
    return InlineKeyboardMarkup(inline_keyboard=[row])


def reason_kb(lid: int, d: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Уважительная (справка, заявление)", callback_data=f"why:{lid}:{d}:E")],
        [InlineKeyboardButton(text="Без уважительной причины", callback_data=f"why:{lid}:{d}:A")],
        [InlineKeyboardButton(text="↩️ Изменить ответ", callback_data=f"why:{lid}:{d}:back")],
    ])


def poll_text(group: dict, lesson: dict, minutes_left: int | None = None) -> str:
    when = f"через {minutes_left} мин" if minutes_left else "скоро"
    meta = " · ".join(x for x in (lesson.get("kind"), lesson.get("room") and f"ауд. {lesson['room']}",
                                  lesson.get("teacher")) if x)
    text = (f"🔔 <b>{esc(lesson['subject'])}</b> — {when}, в {lesson['t_start']}\n"
            + (f"<i>{esc(meta)}</i>\n" if meta else "")
            + (f"📌 {esc(lesson['note'])}\n" if lesson.get("note") else "")
            + "\nБудешь на паре? Ответь одной кнопкой 👇\n"
            + f"<i>Если не ответить до {close_time(group, lesson)}, засчитается пропуск.</i>")
    return text


def close_time(group: dict, lesson: dict) -> str:
    h, m = map(int, lesson["t_start"].split(":"))
    total = h * 60 + m + int(group.get("summary_minutes") or 10)
    return f"{total // 60 % 24:02d}:{total % 60:02d}"


def poll_open(db: DB, lesson_id: int, d: str) -> bool:
    return db.happened(f"poll:{lesson_id}:{d}") and not db.happened(f"summary:{lesson_id}:{d}")


def can_answer(db: DB, group: dict, lesson: dict, d: str) -> bool:
    """Можно ли ответить на опрос. Уведомление в приложении может прийти на пару секунд раньше рассылки бота —
    тогда тоже принимаем ответ, если время опроса уже наступило."""
    if db.happened(f"summary:{lesson['id']}:{d}"):
        return False
    from logic import now_in
    now = now_in(group["tz"])
    if db.happened(f"poll:{lesson['id']}:{d}"):
        return d == now.date().isoformat()
    if d != now.date().isoformat() or not group.get("polls_enabled"):
        return False
    h, m = map(int, lesson["t_start"].split(":"))
    left = h * 60 + m - (now.hour * 60 + now.minute + now.second / 60)
    return -int(group.get("summary_minutes") or 10) < left <= int(group.get("remind_minutes") or 0) + 2


async def send_polls(bot: Bot, db: DB, group: dict, lesson: dict, d: str, minutes_left: int, webapp_url: str) -> int:
    text = poll_text(group, lesson, minutes_left)
    sent = 0
    students = [s for s in db.students(group["id"]) if bot and s["tg_id"] and s["tg_id"] > 0]
    linked = {s["tg_id"] for s in students}
    existing = db.marks(lesson["id"], d)
    for s in students:
        try:
            msg = await bot.send_message(s["tg_id"], text, reply_markup=poll_kb(lesson["id"], d, existing.get(s["id"])))
            db.save_poll_message(lesson["id"], d, s["tg_id"], msg.message_id)
            sent += 1
        except Exception as e:
            log.info("poll to %s failed: %s", s["tg_id"], e)
        await asyncio.sleep(0.05)
    for m in db.staff(group["id"], "attendance"):
        if m["tg_id"] not in linked and m["reminders"]:
            await safe_send(bot, m["tg_id"], f"⏰ Через {minutes_left} мин: <b>{esc(lesson['subject'])}</b> "
                                             f"({lesson['t_start']}). Опрос разослан студентам: {sent}.")
    return sent


def live_counts(db: DB, group: dict, lesson: dict, d: str) -> dict:
    students = db.students(group["id"])
    marks = db.marks_full(lesson["id"], d)
    c = {"P": [], "L": [], "A": [], "E": [], "N": [], "none": []}
    for s in students:
        m = marks.get(s["id"])
        key = m["status"] if m else "none"
        c[key].append({"id": s["id"], "full_name": s["full_name"], "linked": bool(s["tg_id"]),
                       "reason": m.get("reason") if m else None, "source": m.get("source") if m else None})
    return c


async def summarize(bot: Bot, db: DB, group: dict, lesson: dict, d: str, webapp_url: str) -> None:
    lid = lesson["id"]
    students = db.students(group["id"])
    marks = db.marks(lid, d)
    silent = [s for s in students if s["id"] not in marks]
    if silent:
        db.set_marks(lid, d, {s["id"]: "N" for s in silent}, 0, source="auto")
    final = db.marks(lid, d)
    by_tg = {s["tg_id"]: s for s in students if s["tg_id"]}
    for pm in (db.poll_messages(lid, d) if bot else []):
        st = by_tg.get(pm["tg_id"])
        status = final.get(st["id"]) if st else None
        try:
            await bot.edit_message_reply_markup(chat_id=pm["tg_id"], message_id=pm["message_id"], reply_markup=None)
            if status == "N":
                await bot.send_message(pm["tg_id"], f"⌛ Опрос по паре «{esc(lesson['subject'])}» закрыт — "
                                                    "отмечено «не ответил». Если вы на паре, подойдите к старосте.")
        except TelegramBadRequest:
            pass
        except Exception as e:
            log.info("close poll %s: %s", pm["tg_id"], e)

    c = live_counts(db, group, lesson, d)
    total = len(students)
    present = len(c["P"]) + len(c["L"])
    names = lambda key: ", ".join(esc(x["full_name"]) for x in c[key]) or "—"
    lines = [f"📋 <b>Сводка: {esc(lesson['subject'])}</b> ({lesson['t_start']})",
             f"На паре: <b>{present}</b> из {total}" + (f" · опаздывают {len(c['L'])}" if c["L"] else ""), ""]
    if c["L"]:
        lines.append(f"⏰ Опаздывают: {names('L')}")
    if c["A"]:
        lines.append(f"❌ Не придут: {names('A')}")
    if c["E"]:
        lines.append("📄 Уважительная: " + ", ".join(
            esc(x["full_name"]) + (f" ({esc(x['reason'][:40])})" if x["reason"] else "") for x in c["E"]))
    if c["N"]:
        lines.append(f"🤐 Не ответили: {names('N')}")
    if present == total and total:
        lines.append("🎉 Все на месте!")
    lines.append("\n<i>Поправить отметки можно в приложении → Журнал.</i>")

    limit = int(group.get("truancy_limit") or 3)
    d1, d2 = semester_range(group, date.fromisoformat(d))
    recs = [r for r in db.attendance_range(group["id"], d1.isoformat(), d) if r["subject"] == lesson["subject"]]
    newly = {x["id"] for x in c["A"] + c["N"]}
    alerts = []
    for row in truancy(students, recs, limit):
        for sub in row["subjects"]:
            if row["id"] in newly and sub["missed"] >= limit and \
                    db.once(f"truancy:{row['id']}:{sub['subject']}:{sub['missed']}"):
                alerts.append(f"⚠️ {esc(row['full_name'])}: {sub['missed']} пропуск(а) по «{esc(sub['subject'])}»")
    if alerts:
        lines += ["", "<b>Прогулы на грани:</b>"] + alerts

    kb = None
    if webapp_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="📱 Открыть журнал", web_app=WebAppInfo(url=webapp_url + "/#journal"))]])
    import re
    plain = re.sub(r"<[^>]+>", "", "\n".join(lines))
    for m in db.staff(group["id"]):
        if m["reminders"]:
            db.add_feed(group["id"], "summary", f"Сводка: {lesson['subject']} ({lesson['t_start']})",
                        plain, target=m["tg_id"])
            await safe_send(bot, m["tg_id"], "\n".join(lines), reply_markup=kb)


async def weekly_digest(bot: Bot, db: DB, group: dict) -> None:
    from logic import build_stats
    today = today_in(group["tz"])
    d1 = today - timedelta(days=6)
    recs = db.attendance_range(group["id"], d1.isoformat(), today.isoformat())
    if not recs:
        return
    stats = [s for s in build_stats(db.students(group["id"]), recs) if s["percent"] is not None]
    if not stats:
        return
    avg = round(sum(s["percent"] for s in stats) / len(stats), 1)
    worst = [s for s in stats if s["missed"]][:5]
    lines = [f"🗓 <b>Итоги недели · {esc(group['name'])}</b>", f"Средняя посещаемость: <b>{avg}%</b>",
             f"Отмечено пар: {len({(r['lesson_id'], r['date']) for r in recs})}"]
    if worst:
        lines += ["", "Больше всего пропусков:"] + [f"• {esc(s['full_name'])} — {s['missed']}" for s in worst]
    else:
        lines.append("\nБез пропусков — отличная неделя 🎉")
    import re
    plain = re.sub(r"<[^>]+>", "", "\n".join(lines))
    for m in db.staff(group["id"], "journal"):
        if m["reminders"]:
            db.add_feed(group["id"], "summary", f"Итоги недели · {group['name']}", plain, target=m["tg_id"])
            await safe_send(bot, m["tg_id"], "\n".join(lines))


def todays_lessons(db: DB, group: dict, d: date, active: bool = True) -> list[dict]:
    """Пары на день с учётом переносов и отмен. active=True — только те, что реально пройдут (для опросов)."""
    items = lessons_for_date(db.lessons(group["id"]), group, d, db.periods(group["id"]))
    apply_changes(items, db.changes_on(group["id"], d.isoformat()), db.moved_in(group["id"]))
    return [l for l in items if not (l.get("cancelled") or l.get("moved"))] if active else items
