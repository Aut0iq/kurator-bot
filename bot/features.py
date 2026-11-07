"""Новые разделы API: уведомления для Android-приложения, вход сотрудников по логину, домашние задания,
журнал действий, резервные копии, итоги семестра, серии и значки.

Обработчики подмешиваются в класс Api (см. api.py): там есть self.db, self.bot, self.user(), self.member(), self.ctx().
"""
import asyncio
import logging
import os
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from aiohttp import web

import demo
import grades
import passwords
import polls
from logic import DATE_RE, WEEKDAYS, esc, semester_range
from perms import PERMS, ROLES, SUPER_IDS, can, is_super

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = ROOT / "backups"
BACKUP_KEEP = 14
BACKUP_RE = re.compile(r"^kurator-[\w.-]+\.db$")
LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._@-]{2,39}$")

ST_WORD = {"P": "был", "L": "опоздал", "A": "не был", "E": "уважит.", "N": "не ответил", None: "—"}
WD_IN = ["в понедельник", "во вторник", "в среду", "в четверг", "в пятницу", "в субботу", "в воскресенье"]
WD_NOM = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS_G = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def ok(**data) -> web.Response:
    return web.json_response({"ok": True, **data})


def fail(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def body(request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — пустое тело
        return {}


def dm(ds: str) -> str:
    return f"{ds[8:10]}.{ds[5:7]}"


def short_name(full: str) -> str:
    """«Иванов Иван Петрович» → «Иванов И.»"""
    p = (full or "").split()
    return p[0] + (f" {p[1][0]}." if len(p) > 1 and p[1] else "") if p else "?"


def plural(n: int, a: str, b: str, c: str) -> str:
    m, mm = n % 10, n % 100
    return a if m == 1 and mm != 11 else b if 2 <= m <= 4 and not 12 <= mm <= 14 else c


def push_on(m: dict) -> bool:
    """Уведомления в приложении: по умолчанию включены у студентов без Telegram (им больше неоткуда их получить)."""
    if m.get("push") is None:
        return passwords.is_synthetic(m["tg_id"])
    return bool(m["push"])


# ======================================================================== серии и значки
def student_records(db, sid: int, d1: str, d2: str) -> list[dict]:
    return db.q("SELECT a.date, a.status, a.source, l.subject, l.t_start FROM attendance a JOIN lessons l ON l.id=a.lesson_id "
                "WHERE a.student_id=? AND a.date BETWEEN ? AND ? ORDER BY a.date, l.t_start", (sid, d1, d2))


def streaks(recs: list[dict], marks: tuple = ()) -> tuple[int, int, dict]:
    """(текущая серия, лучшая серия, {порог: дата, когда серия впервые его достигла}) — пары подряд без пропусков.
    Уважительная причина серию не рвёт."""
    cur = best = 0
    reached: dict[int, str] = {}
    for r in recs:
        if r["status"] in ("P", "L"):
            cur += 1
            best = max(best, cur)
            for n in marks:
                if cur == n and n not in reached:
                    reached[n] = r["date"]
        elif r["status"] in ("A", "N"):
            cur = 0
    return cur, best, reached


BADGES = [  # ключ, эмодзи, название, описание, цель
    ("streak5", "🔥", "Разогрев", "5 пар подряд без пропусков", 5),
    ("streak10", "🔥", "В ударе", "10 пар подряд без пропусков", 10),
    ("streak25", "☄️", "Неудержимый", "25 пар подряд без пропусков", 25),
    ("streak50", "🏆", "Железная серия", "50 пар подряд без пропусков", 50),
    ("perfect_week", "💯", "Идеальная неделя", "Неделя (от 5 пар) — на всех парах вовремя", 1),
    ("punctual_month", "⏰", "Месяц без опозданий", "Месяц (от 8 пар) — ни одного опоздания и пропуска", 1),
    ("early_bird", "🌅", "Ранняя пташка", "10 пар до 9:00 — вовремя", 10),
    ("on_call", "⚡", "Всегда на связи", "Ответил(а) на 20 опросов", 20),
    ("homework", "📚", "Всё по плану", "Отметил(а) 10 выполненных заданий", 10),
    ("honors", "🎓", "Отличник месяца", "Средний балл за месяц от 4,5 без двоек", 1),
]


def achievements(db, g: dict, st: dict, today: date) -> dict:
    d1, d2 = semester_range(g, today)
    recs = student_records(db, st["id"], d1.isoformat(), d2.isoformat())
    cur, best, reached = streaks(recs, tuple(b[-1] for b in BADGES[:4]))
    have: dict[str, tuple[int, str | None]] = {}           # ключ → (прогресс, дата получения)
    for key, *_, need in BADGES[:4]:
        have[key] = (best, reached.get(need))

    weeks, months = defaultdict(list), defaultdict(list)
    for r in recs:
        d = date.fromisoformat(r["date"])
        weeks[d.isocalendar()[:2]].append(r)
        months[r["date"][:7]].append(r)
    good_weeks = [w for w, rs in weeks.items() if len(rs) >= 5 and all(r["status"] == "P" for r in rs)]
    have["perfect_week"] = (len(good_weeks), max(weeks[w][-1]["date"] for w in good_weeks) if good_weeks else None)
    good_months = [mo for mo, rs in months.items() if len(rs) >= 8 and all(r["status"] in ("P", "E") for r in rs)]
    have["punctual_month"] = (len(good_months), max(months[mo][-1]["date"] for mo in good_months) if good_months else None)
    early = [r for r in recs if r["t_start"] < "09:00" and r["status"] == "P"]
    have["early_bird"] = (len(early), early[9]["date"] if len(early) >= 10 else None)
    answers = [r for r in recs if r["source"] == "poll" and r["status"] in ("P", "L", "A", "E")]
    have["on_call"] = (len(answers), answers[19]["date"] if len(answers) >= 20 else None)
    done = db.q("SELECT done_at FROM homework_done WHERE student_id=? ORDER BY done_at", (st["id"],))
    have["homework"] = (len(done), datetime.fromtimestamp(done[9]["done_at"]).date().isoformat() if len(done) >= 10 else None)
    honors = None
    for gm in db.grade_months(g["id"]):
        row = db.q1("SELECT grades FROM grade_rows WHERE month_id=? AND student_id=?", (gm["id"], st["id"]))
        if not row:
            continue
        import json
        gl = json.loads(row["grades"])
        avg = grades.row_avg(gl)
        if avg is not None and avg >= 4.5 and not any(str(x).strip() in ("2", "0") for x in gl if x is not None):
            honors = honors or gm["month"] + "-28"
    have["honors"] = (1 if honors else 0, honors)

    out = []
    for key, emoji, title, desc, need in BADGES:
        prog, at = have.get(key, (0, None))
        out.append({"key": key, "emoji": emoji, "title": title, "desc": desc, "earned": at is not None, "at": at,
                    "progress": min(prog, need), "need": need})
    # следующая цель по серии — ближайший неполученный порог
    nxt = next((b for b in out[:4] if not b["earned"]), None)
    return {"streak": cur, "best": best, "badges": out, "earned": sum(1 for b in out if b["earned"]),
            "next_streak": nxt["need"] if nxt else None, "late_month": _no_late_days(recs, today)}


def _no_late_days(recs: list[dict], today: date) -> int:
    """Сколько дней подряд (по отмеченным парам) без опозданий и пропусков — для подписи «N дней без опозданий»."""
    last_bad = None
    for r in recs:
        if r["status"] in ("L", "A", "N"):
            last_bad = r["date"]
    if not recs:
        return 0
    start = date.fromisoformat(last_bad) + timedelta(days=1) if last_bad else date.fromisoformat(recs[0]["date"])
    return max(0, (today - start).days + 1)


# ======================================================================== итоги семестра («Wrapped»)
def wrapped_student(db, g: dict, st: dict, today: date) -> dict:
    d1, d2 = semester_range(g, today)
    recs = student_records(db, st["id"], d1.isoformat(), d2.isoformat())
    first = st["full_name"].split()[1] if len(st["full_name"].split()) > 1 else st["full_name"]
    slides = [{"emoji": "✨", "big": "Твой семестр", "text": f"{first}, вот как он прошёл в «Куратор +»",
               "sub": f"{g['name']} · {d1:%d.%m} – {d2:%d.%m.%Y}", "tone": "violet"}]
    share = []
    c = Counter(r["status"] for r in recs)
    counted = sum(c[k] for k in ("P", "L", "A", "N"))
    attended = c["P"] + c["L"]
    pct = round(100 * attended / counted) if counted else None
    if pct is not None and attended:
        if pct >= 60:
            slides.append({"emoji": "🎯", "big": f"{pct}%", "text": "пар ты посетил(а)",
                           "sub": f"Это {attended} {plural(attended, 'пара', 'пары', 'пар')} из {counted}", "tone": "green"})
            share.append(f"🎯 Был(а) на {pct}% пар")
        else:
            slides.append({"emoji": "🎒", "big": str(attended), "text": f"{plural(attended, 'пару', 'пары', 'пар')} ты посетил(а)",
                           "sub": "Каждая пара — шаг вперёд", "tone": "green"})
    # самый пунктуальный день
    by_wd = defaultdict(lambda: [0, 0])
    for r in recs:
        if r["status"] == "E":
            continue
        a = by_wd[date.fromisoformat(r["date"]).weekday()]
        a[1] += 1
        a[0] += r["status"] == "P"
    cand = [(v[0] / v[1], v[0], wd) for wd, v in by_wd.items() if v[1] >= 3 and v[0]]
    if cand:
        rate, n, wd = max(cand)
        slides.append({"emoji": "⏰", "big": WD_NOM[wd].capitalize(), "text": "твой самый пунктуальный день",
                       "sub": f"{round(rate * 100)}% пар {WD_IN[wd]} — вовремя", "tone": "blue"})
        share.append(f"⏰ Самый пунктуальный день — {WD_NOM[wd]}")
    # любимый предмет
    by_s = defaultdict(lambda: [0, 0])
    for r in recs:
        if r["status"] == "E":
            continue
        a = by_s[r["subject"]]
        a[1] += 1
        a[0] += r["status"] in ("P", "L")
    cand = [(v[0] / v[1], v[1], s) for s, v in by_s.items() if v[1] >= 3 and v[0] / v[1] >= .7]
    if cand:
        rate, n, s = max(cand)
        slides.append({"emoji": "💜", "big": s, "text": "предмет, который ты не пропускаешь",
                       "sub": "Ни одного пропуска!" if rate == 1 else f"{round(rate * 100)}% посещаемость", "tone": "pink"})
    # серия
    _, best, _ = streaks(recs)
    if best >= 3:
        slides.append({"emoji": "🔥", "big": str(best), "text": f"{plural(best, 'пара', 'пары', 'пар')} подряд без пропусков",
                       "sub": "Твоя лучшая серия за семестр", "tone": "orange"})
        share.append(f"🔥 Серия: {best} {plural(best, 'пара', 'пары', 'пар')} подряд")
    early = sum(1 for r in recs if r["t_start"] < "09:00" and r["status"] == "P")
    if early >= 3:
        slides.append({"emoji": "🌅", "big": str(early), "text": f"{plural(early, 'первая пара', 'первые пары', 'первых пар')} — вовремя",
                       "sub": "Ранняя пташка, уважение", "tone": "orange"})
    answers = sum(1 for r in recs if r["source"] == "poll" and r["status"] != "N")
    if answers >= 5:
        slides.append({"emoji": "⚡", "big": str(answers), "text": f"{plural(answers, 'ответ', 'ответа', 'ответов')} на опросы",
                       "sub": "Староста говорит спасибо", "tone": "blue"})
    # место в группе (только если лучше половины)
    if pct is not None:
        others = []
        for s in db.students(g["id"]):
            if s["id"] == st["id"]:
                continue
            o = Counter(r["status"] for r in db.q("SELECT a.status FROM attendance a WHERE a.student_id=? AND a.date BETWEEN ? AND ?",
                                                  (s["id"], d1.isoformat(), d2.isoformat())))
            n = sum(o[k] for k in ("P", "L", "A", "N"))
            if n:
                others.append(100 * (o["P"] + o["L"]) / n)
        if len(others) >= 3:
            better = round(100 * sum(1 for x in others if pct > x) / len(others))
            if better >= 50:
                slides.append({"emoji": "🚀", "big": f"{better}%", "text": "группы ты обошёл(ла) по посещаемости",
                               "sub": "Так держать!", "tone": "violet"})
    # оценки
    best_subj = None
    import json
    for gm in db.grade_months(g["id"])[:4]:
        row = db.q1("SELECT grades FROM grade_rows WHERE month_id=? AND student_id=?", (gm["id"], st["id"]))
        if not row:
            continue
        subjects = json.loads(db.q1("SELECT subjects FROM grade_months WHERE id=?", (gm["id"],))["subjects"])
        for s, v in zip(subjects, json.loads(row["grades"])):
            n = grades.numeric(v)
            if n is not None and n >= 4 and (not best_subj or n > best_subj[1]):
                best_subj = (s["name"], n)
    if best_subj:
        slides.append({"emoji": "🎓", "big": best_subj[0], "text": "твой сильный предмет",
                       "sub": f"Оценка {int(best_subj[1]) if float(best_subj[1]).is_integer() else best_subj[1]}", "tone": "green"})
    done = db.q1("SELECT COUNT(*) AS n FROM homework_done d JOIN homework h ON h.id=d.hw_id WHERE d.student_id=? AND h.due_date >= ?",
                 (st["id"], d1.isoformat()))["n"]
    if done >= 3:
        slides.append({"emoji": "📚", "big": str(done), "text": f"{plural(done, 'задание', 'задания', 'заданий')} сделано",
                       "sub": "И всё в срок", "tone": "blue"})
    ach = achievements(db, g, st, today)
    got = [b for b in ach["badges"] if b["earned"]]
    if got:
        slides.append({"emoji": "🏅", "big": f"{len(got)} {plural(len(got), 'значок', 'значка', 'значков')}",
                       "text": " ".join(b["emoji"] for b in got), "sub": ", ".join(b["title"] for b in got[:4]), "tone": "pink"})
        share.append(f"🏅 Значков: {len(got)}")
    if len(slides) == 1:
        slides.append({"emoji": "🌱", "big": "Всё впереди", "text": "Итоги появятся, когда наберётся несколько пар",
                       "sub": "Отвечай на опросы перед парами", "tone": "green"})
    slides.append({"emoji": "💫", "big": "Это твой семестр", "text": "Поделись итогами с друзьями", "final": True, "tone": "violet"})
    return {"kind": "student", "name": st["full_name"], "first": first, "group": g["name"],
            "from": d1.isoformat(), "to": d2.isoformat(), "slides": slides, "share": share}


def wrapped_group(db, g: dict, today: date) -> dict:
    d1, d2 = semester_range(g, today)
    recs = db.attendance_range(g["id"], d1.isoformat(), d2.isoformat())
    slides = [{"emoji": "✨", "big": "Семестр группы", "text": g["name"], "sub": f"{d1:%d.%m} – {d2:%d.%m.%Y}", "tone": "violet"}]
    share = []
    held = len({(r["lesson_id"], r["date"]) for r in recs})
    if held:
        slides.append({"emoji": "📅", "big": str(held), "text": f"{plural(held, 'пара отмечена', 'пары отмечено', 'пар отмечено')}",
                       "sub": f"{len(recs)} отметок в журнале", "tone": "blue"})
        share.append(f"📅 {held} {plural(held, 'пара', 'пары', 'пар')} в журнале")
    c = Counter(r["status"] for r in recs)
    n = sum(c[k] for k in ("P", "L", "A", "N"))
    if n:
        pct = round(100 * (c["P"] + c["L"]) / n)
        slides.append({"emoji": "🎯", "big": f"{pct}%", "text": "средняя посещаемость", "sub": "по всем парам семестра", "tone": "green"})
        share.append(f"🎯 Посещаемость {pct}%")
    by_wd = defaultdict(lambda: [0, 0])
    for r in recs:
        if r["status"] != "E":
            a = by_wd[date.fromisoformat(r["date"]).weekday()]
            a[1] += 1
            a[0] += r["status"] == "P"
    cand = [(v[0] / v[1], wd) for wd, v in by_wd.items() if v[1] >= 10]
    if cand:
        rate, wd = max(cand)
        slides.append({"emoji": "⏰", "big": WD_NOM[wd].capitalize(), "text": "самый пунктуальный день группы",
                       "sub": f"{round(rate * 100)}% — вовремя", "tone": "orange"})
    by_s = defaultdict(lambda: [0, 0])
    for r in recs:
        if r["status"] != "E":
            a = by_s[r["subject"]]
            a[1] += 1
            a[0] += r["status"] in ("P", "L")
    cand = [(v[0] / v[1], s) for s, v in by_s.items() if v[1] >= 10]
    if cand:
        rate, s = max(cand)
        slides.append({"emoji": "💜", "big": s, "text": "предмет, на который ходят лучше всего",
                       "sub": f"{round(rate * 100)}% посещаемость", "tone": "pink"})
    answers = sum(1 for r in recs if r["source"] == "poll" and r["status"] != "N")
    if answers:
        slides.append({"emoji": "⚡", "big": str(answers), "text": f"{plural(answers, 'ответ', 'ответа', 'ответов')} на опросы",
                       "sub": "Столько раз бот сэкономил вам перекличку", "tone": "blue"})
    hw = db.q1("SELECT COUNT(*) AS n FROM homework WHERE group_id=? AND due_date >= ?", (g["id"], d1.isoformat()))["n"]
    if hw:
        slides.append({"emoji": "📚", "big": str(hw), "text": f"{plural(hw, 'задание', 'задания', 'заданий')} выдано", "tone": "green"})
    if len(slides) == 1:
        slides.append({"emoji": "🌱", "big": "Всё впереди", "text": "Итоги появятся, когда в журнале наберутся отметки", "tone": "green"})
    slides.append({"emoji": "💫", "big": "Отличный семестр", "text": "Спасибо, что ведёте группу в «Куратор +»", "final": True, "tone": "violet"})
    return {"kind": "group", "name": g["name"], "group": g["name"], "from": d1.isoformat(), "to": d2.isoformat(),
            "slides": slides, "share": share}


# ======================================================================== статистика использования
def usage(db) -> dict:
    now = int(time.time())
    tz = ZoneInfo(os.getenv("DEFAULT_TZ", "Asia/Vladivostok").strip() or "Asia/Vladivostok")
    today = datetime.now(tz).date()
    demo_gid = db.setting("demo_gid") or -1
    real = "tg_id > -9000000000000"
    days = []
    for k in range(6, -1, -1):
        d = (today - timedelta(days=k)).isoformat()
        days.append({"day": d, "n": db.q1(f"SELECT COUNT(DISTINCT tg_id) AS c FROM presence WHERE day=? AND {real}", (d,))["c"]})
    week_from = (today - timedelta(days=6)).isoformat()
    groups = []
    for g in db.all_groups():
        if g["id"] == demo_gid:
            continue
        gid = g["id"]
        groups.append({
            "id": gid, "name": g["name"],
            "students": db.q1("SELECT COUNT(*) AS c FROM students WHERE group_id=? AND archived=0", (gid,))["c"],
            "linked": db.q1("SELECT COUNT(*) AS c FROM students WHERE group_id=? AND archived=0 AND tg_id IS NOT NULL", (gid,))["c"],
            "members": db.q1("SELECT COUNT(*) AS c FROM members WHERE group_id=?", (gid,))["c"],
            "active_week": db.q1("SELECT COUNT(DISTINCT p.tg_id) AS c FROM presence p JOIN members m ON m.tg_id=p.tg_id "
                                 "WHERE m.group_id=? AND p.day >= ?", (gid, week_from))["c"],
            "answers_week": db.q1("SELECT COUNT(*) AS c FROM attendance a JOIN lessons l ON l.id=a.lesson_id WHERE l.group_id=? "
                                  "AND a.source='poll' AND a.status != 'N' AND a.marked_at > ?", (gid, now - 7 * 86400))["c"],
            "marks_week": db.q1("SELECT COUNT(*) AS c FROM attendance a JOIN lessons l ON l.id=a.lesson_id WHERE l.group_id=? "
                                "AND a.marked_at > ?", (gid, now - 7 * 86400))["c"],
        })
    groups.sort(key=lambda x: -x["active_week"])
    return {
        "active_day": db.q1(f"SELECT COUNT(*) AS c FROM members WHERE last_seen > ? AND {real}", (now - 86400,))["c"],
        "active_week": db.q1(f"SELECT COUNT(DISTINCT tg_id) AS c FROM presence WHERE day >= ? AND {real}", (week_from,))["c"],
        "users": db.q1(f"SELECT COUNT(*) AS c FROM members WHERE {real} AND group_id != ?", (demo_gid,))["c"],
        "answers_week": sum(x["answers_week"] for x in groups),
        "marks_week": sum(x["marks_week"] for x in groups),
        "no_telegram": db.q1("SELECT COUNT(*) AS c FROM members WHERE tg_id <= ? AND tg_id > -9000000000000",
                             (passwords.SYN_BASE,))["c"],
        "app_week": db.q1(f"SELECT COUNT(DISTINCT tg_id) AS c FROM app_sessions WHERE last_used > ? AND {real}", (now - 7 * 86400,))["c"],
        "days": days, "groups": groups,
    }


# ======================================================================== резервные копии
def list_backups() -> list[dict]:
    if not BACKUP_DIR.exists():
        return []
    files = sorted(BACKUP_DIR.glob("kurator-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": f.name, "size": f.stat().st_size, "at": int(f.stat().st_mtime), "safety": "-pre" in f.name} for f in files]


def make_backup(db, suffix: str = "") -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    tz = ZoneInfo(os.getenv("DEFAULT_TZ", "Asia/Vladivostok").strip() or "Asia/Vladivostok")
    name = f"kurator-{datetime.now(tz):%Y%m%d-%H%M%S}{suffix}.db"
    path = BACKUP_DIR / name
    tmp = path.with_suffix(".tmp")
    db.backup_to(str(tmp))
    tmp.replace(path)
    regular = [f for f in sorted(BACKUP_DIR.glob("kurator-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)]
    for old in regular[BACKUP_KEEP + 2:]:                 # храним 14 копий (+ пара страховочных)
        try:
            old.unlink()
        except OSError:
            pass
    return path


# ======================================================================== домашние задания
def homework_view(db, m: dict, today: date, past: bool = False) -> dict:
    g = db.group(m["group_id"])
    st = db.student_by_tg(m["tg_id"])
    staff = can(m, "homework", "journal")
    d_from = (today - timedelta(days=60 if past else 3)).isoformat()
    rows = db.homework_list(g["id"], d_from)
    done = db.homework_done_ids(st["id"]) if st else {}
    counts = db.homework_done_counts(g["id"]) if staff else {}
    total = len(db.students(g["id"]))
    week_end = (today + timedelta(days=6 - today.weekday())).isoformat()
    out = []
    for r in rows:
        r = dict(r)
        r["done"] = r["id"] in done
        r["done_at"] = done.get(r["id"])
        if staff:
            r["done_count"], r["total"] = counts.get(r["id"], 0), total
        r["can_edit"] = can(m, "homework") or r["created_by"] == m["tg_id"]
        r["bucket"] = ("past" if r["due_date"] < today.isoformat() else "today" if r["due_date"] == today.isoformat()
                       else "week" if r["due_date"] <= week_end else "later")
        out.append(r)
    if not past:
        out = [r for r in out if r["bucket"] != "past" or not r["done"]]
    week = [r for r in out if r["bucket"] in ("today", "week") and not r["done"]]
    nxt = {}
    if can(m, "homework"):                  # ближайшая следующая пара по каждому предмету — срок по умолчанию
        for k in range(1, 22):
            d = today + timedelta(days=k)
            for l in polls.todays_lessons(db, g, d):
                nxt.setdefault(l["subject"], {"date": d.isoformat(), "lesson_id": l["id"], "t_start": l["t_start"]})
    return {"items": out, "today": today.isoformat(), "week_end": week_end, "todo_week": len(week),
            "can_add": can(m, "homework"), "is_student": bool(st), "subjects": db.subjects(g["id"]), "next": nxt}


def lesson_dt(g: dict, d: date, hhmm: str) -> int:
    h, mi = map(int, hhmm.split(":"))
    return int(datetime(d.year, d.month, d.day, h, mi, tzinfo=ZoneInfo(g["tz"])).timestamp())


class FeaturesMixin:
    # ------------------------------------------------------------------ журнал действий (хелпер)
    def audit(self, m: dict | None, action: str, text: str, students=None, gid="m") -> None:
        try:
            self.db.audit(m["group_id"] if gid == "m" and m else (None if gid == "m" else gid), m, action, text, students)
        except Exception:  # noqa: BLE001 — журнал не должен ломать основное действие
            log.exception("audit")

    def _need_super(self, request) -> dict:
        user = self.user(request)
        if user["id"] not in SUPER_IDS:
            raise web.HTTPForbidden(reason="Только для главного куратора")
        return user

    def _super_member(self, user: dict) -> dict:
        return self.db.member(user["id"]) or {"tg_id": user["id"], "full_name": user.get("first_name") or "Главный куратор"}

    # ------------------------------------------------------------------ push-уведомления в приложении
    async def push_feed(self, request):
        """Android-приложение раз в 15 минут забирает ближайшие опросы и новые события (объявления, переносы, задания)."""
        m = self.member(request)
        g, today = self.ctx(m)
        now = int(time.time())
        resp = {"ok": True, "push": push_on(m), "last": self.db.feed_last(), "now": now, "polls": [], "events": [],
                "group": g["name"]}
        if not resp["push"] or demo.is_demo(m["tg_id"]) or self.db.lock():
            return web.json_response(resp)
        st = self.db.student_by_tg(m["tg_id"])
        lead = int(g["remind_minutes"] or 0)
        if st and g["polls_enabled"] and lead:
            for d in (today, today + timedelta(days=1)):
                marks_cache = {}
                for l in polls.todays_lessons(self.db, g, d):
                    start = lesson_dt(g, d, l["t_start"])
                    poll_at, close_at = start - lead * 60, start + int(g["summary_minutes"] or 10) * 60
                    if close_at < now or poll_at > now + 36 * 3600:
                        continue
                    ds = d.isoformat()
                    mk = marks_cache.setdefault(l["id"], self.db.marks(l["id"], ds))
                    meta = " · ".join(x for x in (l.get("kind"), l.get("room") and f"ауд. {l['room']}") if x)
                    resp["polls"].append({
                        "lesson_id": l["id"], "date": ds, "at": poll_at, "close": close_at,
                        "title": f"{l['subject']} в {l['t_start']}",
                        "body": (meta + " · " if meta else "") + f"Будешь на паре? Ответ до {polls.close_time(g, l)}",
                        "answered": mk.get(st["id"])})
        since = request.query.get("since", "")
        if since.isdigit():
            resp["events"] = self.db.feed_since(g["id"], m["tg_id"], int(since))
        return web.json_response(resp)

    async def set_push(self, request):
        m = self.member(request)
        on = bool((await request.json()).get("on"))
        self.db.set_push(m["tg_id"], on)
        return ok(push=on)

    # ------------------------------------------------------------------ вход по логину для старост и кураторов
    def _is_staff_role(self, m: dict | None) -> bool:
        return bool(m) and (m["role"] in ("head", "deputy", "curator") or is_super(m))

    def _clean_login(self, value) -> str:
        login = str(value or "").strip().lower()
        if not LOGIN_RE.match(login) or not re.search(r"[a-z]", login):
            raise ValueError("Логин: 3–40 символов, латинские буквы, цифры, точка, «_», «-» или почта")
        return login

    async def my_login(self, request):
        user = self.user(request)
        m = self.db.member(user["id"])
        a = self.db.staff_auth(user["id"])
        return ok(login=a.get("login"), has_password=bool(a.get("pass_hash")), allowed=self._is_staff_role(m) and not passwords.is_synthetic(user["id"]))

    async def set_my_login(self, request):
        user = self.user(request)
        m = self.db.member(user["id"])
        if not self._is_staff_role(m) or passwords.is_synthetic(user["id"]):
            raise web.HTTPForbidden(reason="Вход по логину — для старост, заместителей и кураторов")
        data = await request.json()
        a = self.db.staff_auth(user["id"])
        if a.get("pass_hash") and not passwords.check_secret(str(data.get("old") or ""), a["pass_hash"]):
            return fail(400, "Текущий пароль указан неверно")
        login = self._clean_login(data.get("login") or a.get("login"))
        other = self.db.staff_by_login(login)
        if other and other["tg_id"] != user["id"]:
            return fail(400, "Этот логин уже занят — придумайте другой")
        pw = str(data.get("password") or "")
        if pw or not a.get("pass_hash"):
            problem = passwords.password_problem(pw, login)
            if problem:
                return fail(400, problem)
        self.db.set_staff_login(user["id"], login)
        if pw:
            self.db.set_staff_password(user["id"], passwords.hash_secret(pw))
        return ok(login=login)

    def _staff_login_try(self, ident: str, pw: str) -> str | None:
        """Токен, если ident — логин сотрудника и пароль подходит."""
        a = self.db.staff_by_login(ident)
        if not a or not a.get("pass_hash") or not passwords.check_secret(pw, a["pass_hash"]):
            return None
        m = self.db.member(a["tg_id"])
        name = (m or {}).get("full_name") or a["login"]
        return self.db.new_app_session(a["tg_id"], name.split()[0] if name else a["login"])

    async def admin_staff(self, request):
        self._need_super(request)
        groups = {g["id"]: g["name"] for g in self.db.all_groups()}
        demo_gid = self.db.setting("demo_gid")
        now = int(time.time())
        out = []
        for x in self.db.q("SELECT * FROM members WHERE (role IN ('head','deputy','curator') OR tg_id IN (%s)) AND tg_id > 0 ORDER BY full_name"
                           % ",".join(str(i) for i in SUPER_IDS or {0})):
            if x["group_id"] == demo_gid:
                continue
            a = self.db.staff_auth(x["tg_id"])
            st = self.db.student_by_tg(x["tg_id"])
            out.append({"tg_id": x["tg_id"], "name": (st or {}).get("full_name") or x["full_name"], "username": x["username"],
                        "role_name": "Главный куратор" if is_super(x) else ROLES.get(x["role"], x["role"]),
                        "group": groups.get(x["group_id"]), "login": a.get("login"), "has_password": bool(a.get("pass_hash")),
                        "code_until": a.get("code_expires") if a.get("code_hash") and (a.get("code_expires") or 0) > now else None,
                        "last_seen": x.get("last_seen")})
        return web.json_response({"staff": out})

    async def admin_staff_code(self, request):
        user = self._need_super(request)
        tg_id = int(request.match_info["tg_id"])
        m = self.db.member(tg_id)
        if not self._is_staff_role(m):
            raise web.HTTPNotFound(reason="Сотрудник не найден")
        data = await body(request)
        a = self.db.staff_auth(tg_id)
        login = a.get("login")
        if data.get("login"):
            login = self._clean_login(data["login"])
        if not login:
            base = re.sub(r"[^a-z0-9._-]", "", (m.get("username") or "").lower())
            login = base if len(base) >= 3 and re.search(r"[a-z]", base) else f"kurator{tg_id % 100000}"
        other = self.db.staff_by_login(login)
        if other and other["tg_id"] != tg_id:
            return fail(400, f"Логин «{login}» уже занят — укажите другой")
        self.db.set_staff_login(tg_id, login)
        code = passwords.new_code()
        expires = int(time.time()) + passwords.CODE_TTL
        self.db.set_staff_code(tg_id, passwords.hash_secret(code), expires, user["id"])
        self.audit(self._super_member(user), "code", f"Код входа по логину выдан · {m['full_name']} ({login})", gid=m["group_id"])
        return ok(code=code, login=login, expires=expires, name=m["full_name"], has_password=bool(a.get("pass_hash")))

    def _staff_code_set(self, login: str, code: str, pw: str):
        """Первый вход / сброс пароля сотрудника по коду от главного куратора. None — логин не найден."""
        a = self.db.staff_by_login(login)
        if not a:
            return None
        now = int(time.time())
        if not a.get("code_hash") or (a.get("code_expires") or 0) < now or a.get("code_tries", 0) >= passwords.CODE_TRIES \
                or not passwords.check_secret(code, a["code_hash"]):
            self.db.staff_code_try(a["tg_id"])
            return fail(401, "Код неверный или устарел. Попросите у главного куратора новый")
        problem = passwords.password_problem(pw, login)
        if problem:
            return fail(400, problem)
        self.db.set_staff_password(a["tg_id"], passwords.hash_secret(pw))
        self.db.x("DELETE FROM app_sessions WHERE tg_id=? AND device='password'", (a["tg_id"],))
        m = self.db.member(a["tg_id"])
        name = ((m or {}).get("full_name") or login).split()[0]
        return ok(token=self.db.new_app_session(a["tg_id"], name))

    # ------------------------------------------------------------------ домашние задания
    async def homework_list(self, request):
        m = self.member(request)
        _, today = self.ctx(m)
        return web.json_response(homework_view(self.db, m, today, past=request.query.get("past") == "1"))

    def _hw_data(self, m: dict, data: dict, today: date) -> dict:
        subject = " ".join(str(data.get("subject") or "").split())[:120]
        title = " ".join(str(data.get("title") or "").split())[:200]
        due = str(data.get("due_date") or "")
        if not subject:
            raise ValueError("Выберите предмет")
        if not title:
            raise ValueError("Напишите, что задано")
        if not DATE_RE.match(due):
            raise ValueError("Укажите срок сдачи")
        if due < (today - timedelta(days=30)).isoformat():
            raise ValueError("Срок сдачи уже давно прошёл")
        lid = data.get("lesson_id")
        if lid and not self.db.lesson(m["group_id"], int(lid)):
            lid = None
        ld = str(data.get("lesson_date") or "")
        return {"subject": subject, "title": title, "text": (str(data.get("text") or "").strip()[:2000] or None),
                "due_date": due, "lesson_id": int(lid) if lid else None, "lesson_date": ld if DATE_RE.match(ld) else None}

    async def homework_create(self, request):
        m = self.member(request, "homework")
        g, today = self.ctx(m)
        body = await request.json()
        data = self._hw_data(m, body, today)
        hid = self.db.save_homework(g["id"], data, m)
        when = f"{dm(data['due_date'])}"
        self.audit(m, "homework", f"Задание · {data['subject']}: {data['title']} (сдать до {when})")
        self.db.add_feed(g["id"], "homework", f"📚 {data['subject']}: новое задание", f"{data['title']} · сдать до {when}", author=m["tg_id"])
        sent = 0
        if body.get("notify", True):
            msg = (f"📚 <b>Новое задание · {esc(data['subject'])}</b>\n{esc(data['title'])}"
                   + (f"\n\n{esc(data['text'][:800])}" if data["text"] else "") + f"\n\n🗓 Сдать до <b>{when}</b>")
            from services import safe_send
            for x in self.db.members(g["id"]):
                if x["tg_id"] != m["tg_id"] and x["role"] == "student":
                    sent += await safe_send(self.bot, x["tg_id"], msg, parse_mode="HTML")
                    await asyncio.sleep(0.04)
        return ok(id=hid, sent=sent)

    async def homework_update(self, request):
        m = self.member(request)
        g, today = self.ctx(m)
        hw = self.db.homework(g["id"], int(request.match_info["hid"]))
        if not hw:
            raise web.HTTPNotFound(reason="Задание не найдено")
        if not can(m, "homework") and hw["created_by"] != m["tg_id"]:
            raise web.HTTPForbidden(reason="Недостаточно прав")
        data = self._hw_data(m, await request.json(), today)
        self.db.save_homework(g["id"], data, m, hw["id"])
        changed = [n for k, n in (("title", "текст"), ("due_date", "срок"), ("subject", "предмет"), ("text", "описание")) if hw[k] != data[k]]
        self.audit(m, "homework", f"Задание изменено · {data['subject']}: {data['title']}" + (f" ({', '.join(changed)})" if changed else ""))
        if hw["due_date"] != data["due_date"]:
            self.db.add_feed(g["id"], "homework", f"📚 {data['subject']}: срок изменён", f"{data['title']} · теперь до {dm(data['due_date'])}",
                             author=m["tg_id"])
        return ok()

    async def homework_delete(self, request):
        m = self.member(request)
        g, _ = self.ctx(m)
        hw = self.db.homework(g["id"], int(request.match_info["hid"]))
        if not hw:
            raise web.HTTPNotFound(reason="Задание не найдено")
        if not can(m, "homework") and hw["created_by"] != m["tg_id"]:
            raise web.HTTPForbidden(reason="Недостаточно прав")
        self.db.delete_homework(g["id"], hw["id"])
        self.audit(m, "homework", f"Задание удалено · {hw['subject']}: {hw['title']}")
        return ok()

    async def homework_done(self, request):
        m = self.member(request)
        g, today = self.ctx(m)
        st = self.db.student_by_tg(m["tg_id"])
        if not st:
            raise web.HTTPForbidden(reason="Отмечать выполнение могут студенты")
        hw = self.db.homework(g["id"], int(request.match_info["hid"]))
        if not hw:
            raise web.HTTPNotFound(reason="Задание не найдено")
        done = bool((await request.json()).get("done", True))
        before = achievements(self.db, g, st, today)["earned"] if done else 0
        self.db.set_homework_done(hw["id"], st["id"], done)
        new_badge = done and achievements(self.db, g, st, today)["earned"] > before
        return ok(done=done, new_badge=new_badge)

    # ------------------------------------------------------------------ журнал действий
    def _can_audit(self, m: dict) -> bool:
        return m["role"] in ("head", "deputy", "curator") or is_super(m)

    async def audit_list(self, request):
        m = self.member(request)
        if not self._can_audit(m):
            raise web.HTTPForbidden(reason="Журнал действий доступен старосте, заму и куратору")
        qs = request.query
        rows = self.db.audit_list(m["group_id"], limit=60, before=int(qs["before"]) if qs.get("before", "").isdigit() else None,
                                  student=int(qs["student"]) if qs.get("student", "").isdigit() else None,
                                  action=qs.get("action") or None, q=(qs.get("q") or "").strip()[:60] or None,
                                  with_global=is_super(m))
        for r in rows:
            r.pop("students", None)
        return web.json_response({"items": rows, "more": len(rows) == 60})

    # ------------------------------------------------------------------ резервные копии
    async def backups(self, request):
        self._need_super(request)
        return web.json_response({"items": list_backups(), "keep": BACKUP_KEEP})

    async def backup_now(self, request):
        user = self._need_super(request)
        path = await asyncio.to_thread(make_backup, self.db)
        self.audit(self._super_member(user), "backup", f"Резервная копия создана · {path.name}", gid=None)
        data = await body(request)
        if data.get("send"):
            await self._send_backup(user["id"], path)
        return ok(name=path.name, size=path.stat().st_size, items=list_backups())

    async def _send_backup(self, chat_id: int, path: Path) -> None:
        from aiogram.types import FSInputFile
        if path.stat().st_size > 49 * 1024 * 1024:
            raise ValueError("Копия больше 50 МБ — Telegram не пропустит, заберите её с сервера")
        await self.bot.send_document(chat_id, FSInputFile(str(path), filename=path.name),
                                     caption=f"💾 Резервная копия базы «Куратор +»\n{path.name}")

    def _backup_path(self, name: str) -> Path:
        if not BACKUP_RE.match(name or ""):
            raise web.HTTPBadRequest(reason="Неверное имя копии")
        p = BACKUP_DIR / name
        if not p.exists():
            raise web.HTTPNotFound(reason="Копия не найдена")
        return p

    async def backup_send(self, request):
        user = self._need_super(request)
        await self._send_backup(user["id"], self._backup_path(request.match_info["name"]))
        return ok()

    async def backup_restore(self, request):
        user = self._need_super(request)
        data = await request.json()
        if str(data.get("confirm") or "").strip().upper() != "ВОССТАНОВИТЬ":
            return fail(400, "Для подтверждения введите слово ВОССТАНОВИТЬ")
        src = self._backup_path(str(data.get("name") or ""))
        safety = await asyncio.to_thread(make_backup, self.db, "-pre")          # страховка: текущее состояние
        try:
            await asyncio.to_thread(self.db.restore_from, str(src))
        except ValueError as e:
            return fail(400, str(e))
        import presence
        presence._last.clear()
        log.warning("База восстановлена из %s главным куратором %s (страховочная копия %s)", src.name, user["id"], safety.name)
        self.audit(self._super_member(user), "backup", f"База восстановлена из копии {src.name} (до этого сохранена {safety.name})", gid=None)
        return ok(restored=src.name, safety=safety.name)

    # ------------------------------------------------------------------ итоги семестра, серии и значки
    async def wrapped(self, request):
        m = self.member(request)
        g, today = self.ctx(m)
        st = self.db.student_by_tg(m["tg_id"])
        if st and request.query.get("kind") != "group":
            return web.json_response(wrapped_student(self.db, g, st, today))
        if not can(m, "journal"):
            raise web.HTTPForbidden(reason="Итоги доступны студентам группы")
        return web.json_response(wrapped_group(self.db, g, today))

    async def achievements(self, request):
        m = self.member(request)
        g, today = self.ctx(m)
        st = self.db.student_by_tg(m["tg_id"])
        if not st:
            return web.json_response({"student": False})
        return web.json_response({"student": True, **achievements(self.db, g, st, today)})


_crash_seen: dict[str, float] = {}


async def client_error(request):
    """Android-приложение присылает текст ошибки, из-за которой оно закрылось, — попадёт в «Мониторинг»."""
    import api as _api
    is_app, code, name = _api.app_version(request)
    if not is_app:
        raise web.HTTPForbidden(reason="Только для приложения")
    data = await body(request)
    text = str(data.get("text") or "")[:3000]
    key = text[:200]
    if text and time.time() - _crash_seen.get(key, 0) > 600:      # одинаковые — не чаще раза в 10 минут
        _crash_seen[key] = time.time()
        log.error("Сбой Android-приложения %s:\n%s", name, text)
    return ok()


def parent_overview(db, st: dict, g: dict, today: date) -> dict:
    """Всё, что видит родитель: пары сегодня с отметками ребёнка, посещаемость, оценки, задания, объявления."""
    from logic import by_subject
    sid = st["id"]
    ds = today.isoformat()
    lessons = []
    for l in polls.todays_lessons(db, g, today, active=False):
        lessons.append({k: l.get(k) for k in ("id", "t_start", "t_end", "subject", "kind", "room", "teacher", "cancelled", "moved")}
                       | {"status": db.marks(l["id"], ds).get(sid)})
    d30 = (today - timedelta(days=29)).isoformat()
    recs = student_records(db, sid, d30, ds)
    c = Counter(r["status"] for r in recs)
    counted = sum(c[k] for k in ("P", "L", "A", "N"))
    s1, s2 = semester_range(g, today)
    srecs = student_records(db, sid, s1.isoformat(), s2.isoformat())
    sc = Counter(r["status"] for r in srecs)
    scount = sum(sc[k] for k in ("P", "L", "A", "N"))
    grades_out = None
    months = db.grade_months(g["id"])
    if months:
        v = grades.month_view(db, g["id"], months[0]["month"])
        row = next((r for r in (v or {}).get("rows", []) if r["student_id"] == sid), None)
        if row:
            grades_out = {"title": v["title"], "avg": row["avg"], "missed_total": row["missed_total"], "missed_bad": row["missed_bad"],
                          "items": [{"name": s["name"], "value": x} for s, x in zip(v["subjects"], row["grades"])]}
    done = db.homework_done_ids(sid)
    hw = [{"subject": h["subject"], "title": h["title"], "due_date": h["due_date"], "done": h["id"] in done}
          for h in db.homework_list(g["id"], (today - timedelta(days=3)).isoformat(), (today + timedelta(days=14)).isoformat())]
    ach = achievements(db, g, st, today)
    return {"student": st["full_name"], "group": g["name"], "today": ds, "lessons": lessons,
            "month": {k: c[k] for k in ("P", "L", "A", "E", "N")} | {"percent": round(100 * (c["P"] + c["L"]) / counted) if counted else None},
            "semester_percent": round(100 * (sc["P"] + sc["L"]) / scount) if scount else None,
            "subjects": by_subject(recs), "history": [{k: r[k] for k in ("date", "t_start", "subject", "status")} for r in reversed(recs[-20:])],
            "grades": grades_out, "homework": hw, "streak": ach["streak"], "badges": [b["emoji"] for b in ach["badges"] if b["earned"]],
            "announcements": [{"title": a["title"], "text": a["text"], "created_at": a["created_at"], "pinned": a["pinned"]}
                              for a in db.announcements(g["id"], 5)]}


class ParentMixin:
    """Вход родителя: номер студенческого ребёнка + пароль; первый пароль — по коду от старосты или куратора."""

    async def parent_code(self, request):
        m = self.member(request, "student_info", "students")
        st = self.db.student(m["group_id"], int(request.match_info["sid"]))
        if not st:
            raise web.HTTPNotFound(reason="Студент не найден")
        if not passwords.norm_record(st.get("record_no")):
            return fail(400, "Сначала укажите номер студенческого в карточке студента")
        code = passwords.new_code()
        expires = int(time.time()) + 3 * passwords.CODE_TTL                # родителю — 3 дня, код часто передают через ребёнка
        self.db.set_parent_code(st["id"], passwords.hash_secret(code), expires, m["tg_id"])
        self.audit(m, "code", f"Код входа для родителя выдан · {st['full_name']}", [st["id"]])
        return ok(code=code, expires=expires, record_no=st["record_no"], has_password=bool(self.db.parent_auth(st["id"]).get("pass_hash")))

    async def parent_login(self, request):
        data = await body(request)
        rec, pw = passwords.norm_record(data.get("record_no")), str(data.get("password") or "")
        if not rec or not pw:
            return fail(400, "Введите номер студенческого ребёнка и пароль")
        key = "parent:" + rec
        wait = passwords.locked(key)
        if wait:
            return fail(429, f"Слишком много попыток. Подождите {max(1, wait // 60)} мин.")
        cands = self.db.students_by_record(rec)
        for st in cands:
            a = self.db.parent_auth(st["id"])
            if a.get("pass_hash") and passwords.check_secret(pw, a["pass_hash"]):
                passwords.success(key)
                return ok(token=self.db.new_app_session(passwords.parent_id(st["id"]), "Родитель", "parent"))
        passwords.fail(key)
        if cands and not any(self.db.parent_auth(st["id"]).get("pass_hash") for st in cands):
            return fail(401, "Пароль ещё не задан. Получите код у старосты или куратора группы и нажмите «Первый вход»")
        return fail(401, "Неверный номер студенческого или пароль")

    async def parent_set_password(self, request):
        data = await body(request)
        rec, code, pw = passwords.norm_record(data.get("record_no")), str(data.get("code") or "").strip(), str(data.get("password") or "")
        if not rec or not code:
            return fail(400, "Введите номер студенческого ребёнка и код")
        key = "pcode:" + rec
        wait = passwords.locked(key)
        if wait:
            return fail(429, f"Слишком много попыток. Подождите {max(1, wait // 60)} мин.")
        now = int(time.time())
        target = None
        for st in self.db.students_by_record(rec):
            a = self.db.parent_auth(st["id"])
            if not a.get("code_hash") or (a.get("code_expires") or 0) < now or a.get("code_tries", 0) >= passwords.CODE_TRIES:
                continue
            if passwords.check_secret(code, a["code_hash"]):
                target = st
                break
            self.db.parent_code_try(st["id"])
        if not target:
            passwords.fail(key)
            return fail(401, "Код неверный или устарел. Попросите у старосты или куратора новый")
        problem = passwords.password_problem(pw, target["record_no"])
        if problem:
            return fail(400, problem)
        passwords.success(key)
        self.db.set_parent_password(target["id"], passwords.hash_secret(pw))
        uid = passwords.parent_id(target["id"])
        self.db.x("DELETE FROM app_sessions WHERE tg_id=?", (uid,))       # старые входы родителя — выйти
        return ok(token=self.db.new_app_session(uid, "Родитель", "parent"))

    async def parent_view(self, request):
        user = self.user(request)
        if not passwords.is_parent(user["id"]):
            raise web.HTTPForbidden(reason="Раздел для родителей")
        st = self.db.q1("SELECT * FROM students WHERE id=?", (passwords.parent_student(user["id"]),))
        if not st:
            raise web.HTTPNotFound(reason="Запись студента удалена")
        g = self.db.group(st["group_id"])
        from logic import today_in
        return web.json_response(parent_overview(self.db, st, g, today_in(g["tz"])))


def routes(a) -> list[tuple]:
    return [("POST", "/api/client-error", client_error),
        ("POST", "/api/students/{sid}/parent-code", a.parent_code), ("POST", "/api/parent/login", a.parent_login),
        ("POST", "/api/parent/set-password", a.parent_set_password), ("GET", "/api/parent", a.parent_view),
        ("GET", "/api/push/feed", a.push_feed), ("POST", "/api/me/push", a.set_push),
        ("GET", "/api/me/login", a.my_login), ("POST", "/api/me/login", a.set_my_login),
        ("GET", "/api/admin/staff", a.admin_staff), ("POST", "/api/admin/staff/{tg_id}/code", a.admin_staff_code),
        ("GET", "/api/homework", a.homework_list), ("POST", "/api/homework", a.homework_create),
        ("PUT", "/api/homework/{hid}", a.homework_update), ("DELETE", "/api/homework/{hid}", a.homework_delete),
        ("POST", "/api/homework/{hid}/done", a.homework_done),
        ("GET", "/api/audit", a.audit_list),
        ("GET", "/api/admin/backups", a.backups), ("POST", "/api/admin/backup", a.backup_now),
        ("POST", "/api/admin/backups/{name}/send", a.backup_send), ("POST", "/api/admin/restore", a.backup_restore),
        ("GET", "/api/wrapped", a.wrapped), ("GET", "/api/achievements", a.achievements),
    ]


# ======================================================================== фоновые задачи
async def homework_reminders(bot, db, g: dict, now: datetime) -> int:
    """Вечером накануне срока — напоминание тем, кто ещё не отметил задание выполненным."""
    from services import safe_send
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    items = db.homework_list(g["id"], tomorrow, tomorrow)
    if not items:
        return 0
    sent = 0
    members = {x["tg_id"]: x for x in db.members(g["id"])}
    for s in db.students(g["id"]):
        if not s["tg_id"] or s["tg_id"] not in members:
            continue
        done = db.homework_done_ids(s["id"])
        todo = [h for h in items if h["id"] not in done]
        if not todo:
            continue
        lines = "\n".join(f"• <b>{esc(h['subject'])}</b>: {esc(h['title'])}" for h in todo)
        db.add_feed(g["id"], "hw_due", "📚 Завтра сдавать", "; ".join(f"{h['subject']}: {h['title']}" for h in todo)[:500], target=s["tg_id"])
        if members[s["tg_id"]]["reminders"]:
            sent += await safe_send(bot, s["tg_id"], f"📚 <b>Завтра сдавать</b>\n{lines}\n\n<i>Сделали — отметьте в приложении «Задания».</i>",
                                    parse_mode="HTML")
            await asyncio.sleep(0.04)
    return sent
