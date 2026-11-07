"""Общая логика: проверка подписи Mini App, даты, чётность недель, статистика."""
import hashlib
import hmac
import json
import re
import time
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
STATUS_NAMES = {"P": "был", "A": "не был", "L": "опоздал", "E": "уваж.", "N": "не ответил"}
PERIOD_NAMES = {"holiday": "Каникулы", "session": "Сессия", "practice": "Практика"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def check_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict | None:
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    received = pairs.pop("hash", None)
    if not received:
        return None
    check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        return None
    if max_age and time.time() - int(pairs.get("auth_date", 0)) > max_age:
        return None
    try:
        return json.loads(pairs.get("user", "{}"))
    except json.JSONDecodeError:
        return None


def display_name(user: dict) -> str:
    name = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x)
    return name or user.get("username") or str(user.get("id"))


def now_in(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))


def today_in(tz: str) -> date:
    return now_in(tz).date()


def parse_date(s: str | None, default: date | None = None) -> date:
    if not s:
        if default is None:
            raise ValueError("нет даты")
        return default
    return date.fromisoformat(s)


def week_number(group: dict, d: date) -> int | None:
    """Номер учебной недели от начала семестра (1, 2, ...) или None, если старт не задан."""
    if not group.get("semester_start"):
        return None
    start = date.fromisoformat(group["semester_start"])
    start -= timedelta(days=start.weekday())
    return (d - start).days // 7 + 1


def day_period(periods: list[dict] | None, d: date) -> dict | None:
    s = d.isoformat()
    for p in periods or []:
        if p["d1"] <= s <= p["d2"]:
            return p
    return None


def in_semester(group: dict, d: date) -> bool:
    s = d.isoformat()
    if group.get("semester_start") and s < group["semester_start"]:
        return False
    if group.get("semester_end") and s > group["semester_end"]:
        return False
    return True


def lesson_on(lesson: dict, group: dict, d: date) -> bool:
    if lesson.get("date"):
        return lesson["date"] == d.isoformat()
    if lesson["weekday"] != d.weekday() or not in_semester(group, d):
        return False
    if lesson["parity"] == 0:
        return True
    wn = week_number(group, d)
    if wn is None:
        return True
    return (wn % 2 == 1) == (lesson["parity"] == 1)


def lessons_for_date(lessons: list[dict], group: dict, d: date, periods: list[dict] | None = None) -> list[dict]:
    """Пары на дату. В каникулы/сессию/практику регулярные пары не идут, разовые — идут."""
    off = day_period(periods, d) is not None
    out = [dict(l) for l in lessons if lesson_on(l, group, d) and (not off or l.get("date"))]
    return sorted(out, key=lambda l: l["t_start"])


def apply_changes(items: list[dict], changes: dict[int, dict], moved_in: dict[int, dict] | None = None) -> list[dict]:
    """Отмечает в списке пар отмены, переносы и смену аудитории на этот день."""
    for l in items:
        c = changes.get(l["id"])
        if c:
            l["change"] = {k: c[k] for k in ("id", "kind", "new_date", "new_start", "new_end", "new_room", "reason", "by_name")}
            if c["kind"] == "cancel":
                l["cancelled"] = True
            elif c["kind"] == "move":
                l["moved"] = True
            elif c["kind"] == "room" and c["new_room"]:
                l["room_was"], l["room"] = l.get("room"), c["new_room"]
        src = (moved_in or {}).get(l["id"])
        if src:
            l["moved_from"] = {"id": src["id"], "date": src["date"]}
    return items


def change_text(c: dict, lesson: dict) -> str:
    """Короткое описание изменения для сообщений бота."""
    d = date.fromisoformat(c["date"])
    when = f"{WEEKDAYS[d.weekday()].lower()} {d:%d.%m}, {lesson['t_start']}"
    if c["kind"] == "cancel":
        out = f"❌ <b>Пара отменена</b>\n{esc(lesson['subject'])} — {when}"
    elif c["kind"] == "move":
        nd = date.fromisoformat(c["new_date"])
        out = (f"🔁 <b>Пара перенесена</b>\n{esc(lesson['subject'])}: {when} → "
               f"<b>{WEEKDAYS[nd.weekday()].lower()} {nd:%d.%m}, {c['new_start']}–{c['new_end']}</b>"
               + (f", ауд. {esc(c['new_room'])}" if c.get("new_room") else ""))
    else:
        out = (f"🚪 <b>Другая аудитория</b>\n{esc(lesson['subject'])} — {when}: "
               + (f"ауд. {esc(lesson.get('room') or '—')} → " if lesson.get("room") else "") + f"<b>ауд. {esc(c['new_room'])}</b>")
    if c.get("reason"):
        out += f"\n<i>{esc(c['reason'])}</i>"
    return out


def validate_lesson(data: dict) -> dict:
    one_off = str(data.get("date") or "").strip() or None
    if one_off:
        if not DATE_RE.match(one_off):
            raise ValueError("Неверная дата")
        wd = date.fromisoformat(one_off).weekday()
        parity = 0
    else:
        try:
            wd = int(data.get("weekday"))
            parity = int(data.get("parity") or 0)
        except (TypeError, ValueError):
            raise ValueError("Неверный день недели")
    if not 0 <= wd <= 6 or parity not in (0, 1, 2):
        raise ValueError("Неверный день недели или чётность")
    t1, t2 = str(data.get("t_start", "")).strip()[:5], str(data.get("t_end", "")).strip()[:5]
    if len(t1) == 4: t1 = "0" + t1
    if len(t2) == 4: t2 = "0" + t2
    if not TIME_RE.match(t1) or not TIME_RE.match(t2) or t1 >= t2:
        raise ValueError("Время в формате ЧЧ:ММ, начало раньше конца")
    subject = str(data.get("subject") or "").strip()
    if not subject:
        raise ValueError("Укажите предмет")
    clean = lambda k, n=80: (str(data.get(k) or "").strip()[:n] or None)
    return {"weekday": wd, "t_start": t1, "t_end": t2, "subject": subject[:120], "kind": clean("kind"),
            "room": clean("room"), "teacher": clean("teacher"), "parity": parity, "note": clean("note", 300),
            "date": one_off}


def fmt_lesson(l: dict) -> str:
    room = l.get("room") and (f"ауд. {l['room']}" + (" (новая!)" if l.get("room_was") is not None or l.get("change", {}).get("kind") == "room" else ""))
    extra = ", ".join(x for x in (l.get("kind"), room, l.get("teacher")) if x)
    if l.get("cancelled"):
        return f"<s>{l['t_start']}–{l['t_end']} {esc(l['subject'])}</s>  ❌ <b>отменена</b>"
    if l.get("moved"):
        c = l["change"]
        nd = date.fromisoformat(c["new_date"])
        return f"<s>{l['t_start']}–{l['t_end']} {esc(l['subject'])}</s>  🔁 перенесена на <b>{nd:%d.%m} {c['new_start']}</b>"
    out = f"{l['t_start']}–{l['t_end']} <b>{esc(l['subject'])}</b>" + (f"\n      <i>{esc(extra)}</i>" if extra else "")
    if l.get("note"):
        out += f"\n      📌 {esc(l['note'])}"
    return out


def esc(s: str | None) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_stats(students: list[dict], records: list[dict]) -> list[dict]:
    """Посещаемость по студентам. Опоздание = присутствие, уважительная не снижает процент,
    «не ответил на опрос» = пропуск."""
    by = {s["id"]: {"id": s["id"], "full_name": s["full_name"], "P": 0, "A": 0, "L": 0, "E": 0, "N": 0}
          for s in students}
    for r in records:
        if r["student_id"] in by:
            by[r["student_id"]][r["status"]] += 1
    out = []
    for s in by.values():
        total = s["P"] + s["A"] + s["L"] + s["E"] + s["N"]
        attended = s["P"] + s["L"]
        s["total"] = total
        s["missed"] = s["A"] + s["N"]
        s["percent"] = round(100 * attended / (total - s["E"]), 1) if total - s["E"] > 0 else None
        out.append(s)
    out.sort(key=lambda s: (s["percent"] if s["percent"] is not None else 101, s["full_name"]))
    return out


def by_subject(records: list[dict]) -> list[dict]:
    """Посещаемость по предметам (для одного студента или всей группы)."""
    agg: dict[str, dict] = {}
    for r in records:
        a = agg.setdefault(r["subject"], {"subject": r["subject"], "P": 0, "L": 0, "A": 0, "E": 0, "N": 0})
        a[r["status"]] += 1
    out = []
    for a in agg.values():
        counted = a["P"] + a["L"] + a["A"] + a["N"]
        a["missed"] = a["A"] + a["N"]
        a["percent"] = round(100 * (a["P"] + a["L"]) / counted, 1) if counted else None
        out.append(a)
    return sorted(out, key=lambda a: (a["percent"] if a["percent"] is not None else 101, a["subject"]))


def truancy(students: list[dict], records: list[dict], limit: int) -> list[dict]:
    """Кто на грани: пропуски (не был + не ответил) по предмету >= limit-1."""
    names = {s["id"]: s["full_name"] for s in students}
    cnt: dict[tuple[int, str], int] = {}
    for r in records:
        if r["status"] in ("A", "N") and r["student_id"] in names:
            k = (r["student_id"], r["subject"])
            cnt[k] = cnt.get(k, 0) + 1
    out: dict[int, dict] = {}
    for (sid, subj), n in cnt.items():
        if n >= max(1, limit - 1):
            row = out.setdefault(sid, {"id": sid, "full_name": names[sid], "subjects": [], "worst": 0})
            row["subjects"].append({"subject": subj, "missed": n, "over": n >= limit})
            row["worst"] = max(row["worst"], n)
    for r in out.values():
        r["subjects"].sort(key=lambda x: -x["missed"])
    return sorted(out.values(), key=lambda r: (-r["worst"], r["full_name"]))


def semester_range(group: dict, today: date) -> tuple[date, date]:
    d1 = date.fromisoformat(group["semester_start"]) if group.get("semester_start") else today - timedelta(days=120)
    d2 = min(today, date.fromisoformat(group["semester_end"])) if group.get("semester_end") else today
    return d1, d2
