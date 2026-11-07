"""Демо-режим: выдуманная группа с расписанием, журналом, оценками и объявлениями.

Кнопка «Посмотреть демо» на стартовом экране выдаёт временный вход за демо-старосту или демо-студента.
В демо всё можно смотреть, но ничего нельзя изменить (API отвечает «Демо-режим: изменения не сохраняются»).
Группа пересобирается раз в день, чтобы даты в журнале были свежими. Опросы и рассылки для неё не работают.
Все люди и данные выдуманы.
"""
import hashlib
import os
import random
import secrets
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DEMO_HEAD = -9_000_000_000_001
DEMO_STUDENT = -9_000_000_000_002
_BASE = -9_000_000_000_100

TZ = os.getenv("DEFAULT_TZ", "Asia/Vladivostok").strip() or "Asia/Vladivostok"
NAME = "Демо-группа ИС-21"


def is_demo(tg_id) -> bool:
    try:
        return int(tg_id) <= -9_000_000_000_000
    except (TypeError, ValueError):
        return False


def demo_gid(db) -> int | None:
    return db.setting("demo_gid")


STUDENTS = ["Алексеев Артём", "Белова Анна", "Васильев Дмитрий", "Громова Ксения", "Денисов Максим", "Егорова Софья",
            "Жуков Никита", "Зайцева Полина", "Ильин Кирилл", "Королёва Дарья", "Лебедев Иван", "Морозова Алиса",
            "Новиков Егор", "Орлова Виктория"]
SUBJECTS = [
    ("Математика", "Соколова Т. В.", "Лекция", "305"), ("Программирование", "Кузнецов А. И.", "Лаб", "214"),
    ("Базы данных", "Петрова Н. С.", "Сем", "214"), ("Английский язык", "Смит Э. Р.", "Сем", "118"),
    ("История", "Волков С. П.", "Лекция", "402"), ("Физкультура", "Орлов Д. Н.", "Сем", "Спортзал"),
    ("Компьютерные сети", "Фёдоров И. А.", "Лаб", "210"),
]
SLOTS = [("08:30", "10:00"), ("10:10", "11:40"), ("11:50", "13:20"), ("13:40", "15:10")]
WEEK = {
    0: [(0, 0, 0), (1, 1, 0), (3, 2, 0)],
    1: [(4, 0, 0), (2, 1, 0), (1, 2, 1), (6, 2, 2)],
    2: [(0, 0, 0), (5, 1, 0), (2, 2, 0), (3, 3, 2)],
    3: [(6, 0, 0), (1, 1, 0), (4, 2, 1), (0, 2, 2)],
    4: [(2, 0, 0), (3, 1, 0), (6, 2, 0)],
}


def ensure(db) -> int:
    """Демо-группа на сегодня (пересобирается раз в сутки)."""
    today = datetime.now(ZoneInfo(TZ)).date()
    gid = demo_gid(db)
    if gid and db.group(gid) and db.setting("demo_built") == today.isoformat():
        return gid
    if gid and db.group(gid):
        db.delete_group(gid)
    db.x("DELETE FROM members WHERE tg_id <= -9000000000000")
    db.x("DELETE FROM presence WHERE tg_id <= -9000000000000")
    gid = _build(db, today)
    db.set_setting("demo_gid", gid)
    db.set_setting("demo_built", today.isoformat())
    return gid


def start(db, role: str) -> str:
    """Временный вход в демо: токен как у приложения (живёт 12 часов)."""
    ensure(db)
    uid = DEMO_STUDENT if role == "student" else DEMO_HEAD
    db.x("DELETE FROM app_sessions WHERE tg_id <= -9000000000000 AND created_at < ?", (int(time.time()) - 12 * 3600,))
    token = "demo_" + secrets.token_urlsafe(24)
    now = int(time.time())
    first = "Гость" if role == "student" else "Гость"
    db.x("INSERT INTO app_sessions(token_hash, tg_id, first_name, last_name, username, created_at, last_used, device) "
         "VALUES (?,?,?,?,?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), uid, first, None, None, now, now, "demo"))
    import legal
    db.set_consent(uid, legal.VERSION, "demo")
    return token


def _build(db, today: date) -> int:
    rnd = random.Random(today.toordinal())
    year = today.year if today.month >= 9 else today.year - 1
    g = db.create_group(NAME, TZ, DEMO_HEAD, "Гость (староста)", None)
    gid = g["id"]
    db.x("UPDATE groups SET semester_start=?, semester_end=? WHERE id=?", (f"{year}-09-01", f"{year}-12-28", gid))

    db.add_students(gid, STUDENTS)
    studs = db.students(gid)
    now = int(time.time())
    day = lambda d: d.isoformat()
    db.x("INSERT INTO members(tg_id, group_id, role, full_name, username) VALUES (?,?,?,?,?)",
         (_BASE - 1, gid, "curator", "Иванова Елена Петровна", None))
    for i, s in enumerate(studs):
        if i >= 11:
            continue
        tid = DEMO_STUDENT if i == 0 else _BASE - 100 - i
        db.x("UPDATE students SET tg_id=? WHERE id=?", (tid, s["id"]))
        if tid != DEMO_STUDENT:
            db.x("INSERT INTO members(tg_id, group_id, role, full_name, username) VALUES (?,?,?,?,?)",
                 (tid, gid, "student", s["full_name"].split()[1], None))
    db.x("INSERT OR REPLACE INTO members(tg_id, group_id, role, full_name, username) VALUES (?,?,?,?,?)",
         (DEMO_STUDENT, gid, "student", "Гость (студент)", None))
    if studs:
        db.x("UPDATE students SET record_no=?, email=? WHERE id=?", ("ИС-21-001", "student@example.com", studs[0]["id"]))

    for tid, ago in [(_BASE - 1, 40), (_BASE - 101, 20), (_BASE - 102, 70), (_BASE - 103, 3600 * 2),
                     (_BASE - 104, 3600 * 5), (_BASE - 105, 86400 + 3600), (_BASE - 106, 86400 * 3), (_BASE - 107, 600)]:
        db.x("UPDATE members SET last_seen=?, last_via=? WHERE tg_id=?", (now - ago, rnd.choice(["tg", "app", "bot"]), tid))
        for k in range(rnd.randint(2, 6)):
            d = today - timedelta(days=k)
            t1 = int(datetime(d.year, d.month, d.day, rnd.randint(7, 10), rnd.randint(0, 59), tzinfo=ZoneInfo(TZ)).timestamp())
            db.x("INSERT OR REPLACE INTO presence(tg_id, day, first_at, last_at) VALUES (?,?,?,?)",
                 (tid, day(d), t1, min(now - ago if k == 0 else t1 + rnd.randint(1800, 25000), t1 + 30000)))

    lesson_ids = {}
    for wd, items in WEEK.items():
        for si, slot, parity in items:
            subj, teacher, kind, room = SUBJECTS[si]
            lid = db.save_lesson(gid, {"weekday": wd, "t_start": SLOTS[slot][0], "t_end": SLOTS[slot][1], "subject": subj,
                                       "kind": kind, "room": room, "teacher": teacher, "parity": parity, "date": None,
                                       "note": "Принести ноутбук" if subj == "Программирование" and wd == 0 else None})
            lesson_ids[(wd, slot, parity)] = lid

    from logic import lessons_for_date
    g = db.group(gid)
    lessons = db.lessons(gid)
    hm = datetime.now(ZoneInfo(TZ)).strftime("%H:%M")
    weights = [("P", 80), ("L", 7), ("A", 8), ("E", 5)]
    lazy = {studs[5]["id"], studs[9]["id"]} if len(studs) > 9 else set()
    for back in range(21, -1, -1):
        d = today - timedelta(days=back)
        for l in lessons_for_date(lessons, g, d, []):
            if back == 0 and l["t_start"] > hm:
                continue
            marks = {}
            for s in studs:
                w = [(k, v * (3 if k == "A" and s["id"] in lazy else 1)) for k, v in weights]
                marks[s["id"]] = rnd.choices([k for k, _ in w], [v for _, v in w])[0]
            db.set_marks(l["id"], d.isoformat(), marks, DEMO_HEAD, source=rnd.choice(["poll", "manual"]))

    subj_list = [{"name": s[0], "teacher": s[1]} for s in SUBJECTS[:6]]
    prev = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    for month in (prev, today.strftime("%Y-%m")):
        mid = db.save_grade_month(gid, month, subj_list, DEMO_HEAD)
        for s in studs:
            base = 4.6 if s["id"] not in lazy else 3.4
            grades = []
            for _ in subj_list:
                x = rnd.gauss(base, .7)
                grades.append("5" if x >= 4.5 else "4" if x >= 3.6 else "3" if x >= 2.7 else "2")
            if rnd.random() < .12:
                grades[rnd.randrange(len(grades))] = "зач"
            missed = rnd.choice([0, 0, 2, 4, 6, 8]) + (10 if s["id"] in lazy else 0)
            db.save_grade_row(mid, s["id"], grades, missed, missed // 2 if missed else 0, None)

    db.add_announcement(gid, DEMO_HEAD, "Собрание группы", "В четверг после 3-й пары в 305 аудитории. Явка обязательна!", True)
    db.add_announcement(gid, DEMO_HEAD, None, "Справки за прошлую неделю нужно сдать до пятницы.", False)
    db.add_period(gid, "holiday", "Зимние каникулы", f"{year}-12-29", f"{year + 1}-01-11")
    for k in range(1, 6):
        d = today + timedelta(days=k)
        todays = lessons_for_date(lessons, g, d, [])
        if todays:
            db.set_change(gid, todays[-1], d.isoformat(), "cancel", {"tg_id": DEMO_HEAD, "full_name": "Гость (староста)"},
                          reason="Преподаватель на курсах повышения квалификации")
            break
    return gid
