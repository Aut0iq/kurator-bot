"""Хранилище на SQLite (встроено в Python, ничего ставить не нужно).

Запросы маленькие и быстрые, поэтому вызываются синхронно — для бота
одной или нескольких групп этого с большим запасом хватает.
Старые базы обновляются автоматически (см. _migrate).
"""
import json
import os
import secrets
import sqlite3
import time
from datetime import date
from pathlib import Path
from typing import Any, Iterable

STATUSES = ("P", "L", "A", "E", "N")

ATTENDANCE_SQL = """
CREATE TABLE IF NOT EXISTS attendance (
    lesson_id   INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    status      TEXT NOT NULL CHECK (status IN ('P','L','A','E','N')),
    source      TEXT NOT NULL DEFAULT 'manual',   -- manual / poll / code / auto
    reason      TEXT,
    file_id     TEXT,
    marked_by   INTEGER,
    marked_at   INTEGER NOT NULL,
    PRIMARY KEY (lesson_id, date, student_id)
);
"""

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS groups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    invite_code     TEXT NOT NULL UNIQUE,
    tz              TEXT NOT NULL,
    semester_start  TEXT,
    semester_end    TEXT,
    remind_minutes  INTEGER NOT NULL DEFAULT 15,   -- за сколько минут слать опрос
    summary_minutes INTEGER NOT NULL DEFAULT 10,   -- сводка через N минут после начала
    truancy_limit   INTEGER NOT NULL DEFAULT 3,    -- порог пропусков по предмету
    polls_enabled   INTEGER NOT NULL DEFAULT 1,
    staff_code      TEXT,                          -- приглашение для куратора / зама
    created_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    tg_id       INTEGER PRIMARY KEY,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('head','deputy','curator','student')),
    full_name   TEXT,
    username    TEXT,
    reminders   INTEGER NOT NULL DEFAULT 1,
    perms       TEXT                           -- JSON-список прав; NULL = права роли по умолчанию
);

CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    full_name   TEXT NOT NULL,
    tg_id       INTEGER UNIQUE,
    phone       TEXT,
    note        TEXT,
    archived    INTEGER NOT NULL DEFAULT 0,    -- 1 = отчислен
    record_no   TEXT,                          -- № студенческого билета
    email       TEXT,
    birth_date  TEXT,                          -- YYYY-MM-DD
    parent_name TEXT,
    parent_phone TEXT
);

CREATE TABLE IF NOT EXISTS lessons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    weekday     INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    t_start     TEXT NOT NULL,
    t_end       TEXT NOT NULL,
    subject     TEXT NOT NULL,
    kind        TEXT,
    room        TEXT,
    teacher     TEXT,
    parity      INTEGER NOT NULL DEFAULT 0,    -- 0 каждую, 1 нечётная, 2 чётная
    note        TEXT,                          -- видна студентам
    date        TEXT                           -- если задана — разовая пара только в этот день
);
""" + ATTENDANCE_SQL + """
CREATE TABLE IF NOT EXISTS checkins (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    lesson_id   INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    code        TEXT NOT NULL,
    expires_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS events_sent (
    key         TEXT PRIMARY KEY,
    at          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS poll_messages (
    lesson_id   INTEGER NOT NULL,
    date        TEXT NOT NULL,
    tg_id       INTEGER NOT NULL,
    message_id  INTEGER NOT NULL,
    PRIMARY KEY (lesson_id, date, tg_id)
);

CREATE TABLE IF NOT EXISTS periods (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('holiday','session','practice')),
    title       TEXT,
    d1          TEXT NOT NULL,
    d2          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS announcements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    author_id   INTEGER NOT NULL,
    title       TEXT,
    text        TEXT NOT NULL,
    pinned      INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL,
    delivered   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS grade_months (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    month       TEXT NOT NULL,                 -- YYYY-MM
    subjects    TEXT NOT NULL,                 -- JSON [{"name":..,"teacher":..}]
    updated_at  INTEGER NOT NULL,
    updated_by  INTEGER,
    UNIQUE (group_id, month)
);

CREATE TABLE IF NOT EXISTS grade_rows (
    month_id    INTEGER NOT NULL REFERENCES grade_months(id) ON DELETE CASCADE,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    grades      TEXT NOT NULL,                 -- JSON-список, по порядку предметов: "5","4","0","зач",null
    missed_total INTEGER,                      -- пропущено часов всего
    missed_bad  INTEGER,                       -- из них без уважительной причины
    note        TEXT,
    PRIMARY KEY (month_id, student_id)
);

CREATE TABLE IF NOT EXISTS app_logins (
    code        TEXT PRIMARY KEY,              -- одноразовый код входа в приложение
    created_at  INTEGER NOT NULL,
    tg_id       INTEGER,
    token       TEXT
);

CREATE TABLE IF NOT EXISTS app_sessions (
    token_hash  TEXT PRIMARY KEY,              -- sha256 от токена; сам токен хранится только в приложении
    tg_id       INTEGER NOT NULL,
    first_name  TEXT,
    last_name   TEXT,
    username    TEXT,
    created_at  INTEGER NOT NULL,
    last_used   INTEGER NOT NULL,
    device      TEXT
);

CREATE TABLE IF NOT EXISTS lesson_changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id        INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    lesson_id       INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    date            TEXT NOT NULL,                 -- день, когда пара должна была быть
    kind            TEXT NOT NULL,                 -- cancel / move / room
    new_date        TEXT,
    new_start       TEXT,
    new_end         TEXT,
    new_room        TEXT,
    moved_lesson_id INTEGER,                       -- разовая пара, созданная при переносе
    reason          TEXT,
    by_tg           INTEGER,
    by_name         TEXT,
    created_at      INTEGER NOT NULL,
    UNIQUE (lesson_id, date)
);

CREATE TABLE IF NOT EXISTS presence (
    tg_id       INTEGER NOT NULL,
    day         TEXT NOT NULL,                     -- ГГГГ-ММ-ДД (часовой пояс бота)
    first_at    INTEGER NOT NULL,
    last_at     INTEGER NOT NULL,
    PRIMARY KEY (tg_id, day)
);

CREATE TABLE IF NOT EXISTS student_auth (
    student_id   INTEGER PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
    pass_hash    TEXT,                          -- scrypt; NULL — пароль ещё не задан
    pass_set_at  INTEGER,
    code_hash    TEXT,                          -- одноразовый код от старосты / куратора
    code_expires INTEGER,
    code_tries   INTEGER NOT NULL DEFAULT 0,
    code_by      INTEGER
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS consents (
    tg_id       INTEGER PRIMARY KEY,
    version     TEXT NOT NULL,                 -- редакция документов (legal.VERSION)
    at          INTEGER NOT NULL,              -- когда дано согласие (unix time)
    via         TEXT                           -- app / telegram
);

CREATE TABLE IF NOT EXISTS files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    subject     TEXT NOT NULL,
    title       TEXT NOT NULL,
    file_id     TEXT NOT NULL,
    file_type   TEXT NOT NULL,                 -- document / photo
    size        INTEGER,
    uploader    INTEGER NOT NULL,
    uploader_name TEXT,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS feed (                  -- события для уведомлений Android-приложения
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    target      INTEGER,                       -- кому (tg_id); NULL — всей группе
    author      INTEGER,
    kind        TEXT NOT NULL,                 -- announce / change / homework / hw_due
    title       TEXT NOT NULL,
    body        TEXT,
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS feed_group ON feed(group_id, id);

CREATE TABLE IF NOT EXISTS homework (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    subject     TEXT NOT NULL,
    lesson_id   INTEGER,                       -- к какой паре (необязательно)
    lesson_date TEXT,
    title       TEXT NOT NULL,
    text        TEXT,
    due_date    TEXT NOT NULL,                 -- ГГГГ-ММ-ДД
    created_by  INTEGER,
    author_name TEXT,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER
);
CREATE INDEX IF NOT EXISTS homework_due ON homework(group_id, due_date);

CREATE TABLE IF NOT EXISTS homework_done (
    hw_id       INTEGER NOT NULL REFERENCES homework(id) ON DELETE CASCADE,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    done_at     INTEGER NOT NULL,
    PRIMARY KEY (hw_id, student_id)
);

CREATE TABLE IF NOT EXISTS audit (                 -- журнал действий: кто, когда и что изменил
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER,                       -- NULL — действие главного куратора для всего сервиса
    at          INTEGER NOT NULL,
    actor       INTEGER,
    actor_name  TEXT,
    action      TEXT NOT NULL,                 -- marks / grades / student / delete / role / perms / schedule / change / announce / lock / backup / homework / code
    text        TEXT NOT NULL,
    students    TEXT                           -- ",12,15," — для поиска по студенту
);
CREATE INDEX IF NOT EXISTS audit_group ON audit(group_id, id);

CREATE TABLE IF NOT EXISTS parent_auth (           -- вход родителя: номер студенческого ребёнка + пароль родителя
    student_id   INTEGER PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
    pass_hash    TEXT,
    pass_set_at  INTEGER,
    code_hash    TEXT,
    code_expires INTEGER,
    code_tries   INTEGER NOT NULL DEFAULT 0,
    code_by      INTEGER
);

CREATE TABLE IF NOT EXISTS staff_auth (            -- вход по логину и паролю для старост и кураторов
    tg_id        INTEGER PRIMARY KEY,
    login        TEXT UNIQUE,
    pass_hash    TEXT,
    pass_set_at  INTEGER,
    code_hash    TEXT,
    code_expires INTEGER,
    code_tries   INTEGER NOT NULL DEFAULT 0,
    code_by      INTEGER
);
"""


def _row(r):
    return dict(r) if r else None


def _rows(rs):
    return [dict(r) for r in rs]


def _code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


class DB:
    def __init__(self, path: str):
        self.path = path
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.files_dir = Path(d or ".") / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self._migrate_before()
        self.conn.executescript(SCHEMA)
        self._migrate_after()

    def _cols(self, table: str) -> set[str]:
        return {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}

    def _migrate_before(self) -> None:
        row = self.conn.execute("SELECT sql FROM sqlite_master WHERE name='members'").fetchone()
        if row and "'curator'" not in row["sql"]:
            self.conn.executescript(
                "ALTER TABLE members RENAME TO members_old;"
                "CREATE TABLE members (tg_id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,"
                " role TEXT NOT NULL CHECK (role IN ('head','deputy','curator','student')), full_name TEXT, username TEXT,"
                " reminders INTEGER NOT NULL DEFAULT 1, perms TEXT);"
                "INSERT INTO members(tg_id,group_id,role,full_name,username,reminders) "
                "SELECT tg_id,group_id,CASE role WHEN 'assistant' THEN 'deputy' ELSE role END,full_name,username,reminders FROM members_old;"
                "DROP TABLE members_old;"
            )
        row = self.conn.execute("SELECT sql FROM sqlite_master WHERE name='attendance'").fetchone()
        if row and "'N'" not in row["sql"]:
            self.conn.executescript(
                "ALTER TABLE attendance RENAME TO attendance_old;" + ATTENDANCE_SQL +
                "INSERT INTO attendance(lesson_id,date,student_id,status,marked_by,marked_at) "
                "SELECT lesson_id,date,student_id,status,marked_by,marked_at FROM attendance_old;"
                "DROP TABLE attendance_old;"
            )

    def _migrate_after(self) -> None:
        add = {
            "groups": [("semester_end", "TEXT"), ("summary_minutes", "INTEGER NOT NULL DEFAULT 10"),
                       ("truancy_limit", "INTEGER NOT NULL DEFAULT 3"), ("polls_enabled", "INTEGER NOT NULL DEFAULT 1"),
                       ("staff_code", "TEXT")],
            "lessons": [("note", "TEXT"), ("date", "TEXT")],
            "members": [("last_seen", "INTEGER"), ("last_via", "TEXT"), ("push", "INTEGER")],
            "announcements": [("title", "TEXT"), ("pinned", "INTEGER NOT NULL DEFAULT 0")],
            "students": [("record_no", "TEXT"), ("email", "TEXT"), ("birth_date", "TEXT"),
                         ("parent_name", "TEXT"), ("parent_phone", "TEXT")],
            "files": [("path", "TEXT")],
            "attendance": [("file_path", "TEXT")],
        }
        for table, cols in add.items():
            have = self._cols(table)
            for name, typ in cols:
                if name not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
        for g in self.conn.execute("SELECT id FROM groups WHERE staff_code IS NULL").fetchall():
            self.conn.execute("UPDATE groups SET staff_code=? WHERE id=?", (_code(), g["id"]))

    def q(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        return _rows(self.conn.execute(sql, tuple(params)).fetchall())

    def q1(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        return _row(self.conn.execute(sql, tuple(params)).fetchone())

    def x(self, sql: str, params: Iterable[Any] = ()) -> int:
        return self.conn.execute(sql, tuple(params)).lastrowid

    def once(self, key: str) -> bool:
        """True, если событие с этим ключом случается впервые (и запоминает его)."""
        try:
            self.x("INSERT INTO events_sent(key, at) VALUES (?,?)", (key, int(time.time())))
            return True
        except sqlite3.IntegrityError:
            return False

    def happened(self, key: str) -> bool:
        return self.q1("SELECT 1 AS x FROM events_sent WHERE key=?", (key,)) is not None

    def create_group(self, name: str, tz: str, head_id: int, head_name: str, username: str | None,
                     role: str = "head", perms: str | None = None) -> dict:
        from perms import SUPER_IDS
        if head_id in SUPER_IDS:
            role, perms = "curator", None
        self.conn.execute("BEGIN")
        try:
            gid = self.x("INSERT INTO groups(name, invite_code, staff_code, tz, created_at) VALUES (?,?,?,?,?)",
                         (name, _code(), _code(), tz, int(time.time())))
            self.x("INSERT OR REPLACE INTO members(tg_id, group_id, role, full_name, username, perms) VALUES (?,?,?,?,?,?)",
                   (head_id, gid, role, head_name, username, perms))
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return self.group(gid)

    def group(self, gid: int) -> dict | None:
        return self.q1("SELECT * FROM groups WHERE id=?", (gid,))

    def group_by_code(self, code: str) -> dict | None:
        return self.q1("SELECT * FROM groups WHERE invite_code=? COLLATE NOCASE", (code.strip(),))

    def group_by_staff_code(self, code: str) -> dict | None:
        return self.q1("SELECT * FROM groups WHERE staff_code=? COLLATE NOCASE", (code.strip(),))

    def update_group(self, gid: int, **fields) -> None:
        allowed = {"name", "tz", "semester_start", "semester_end", "remind_minutes", "summary_minutes",
                   "truancy_limit", "polls_enabled"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            self.x(f"UPDATE groups SET {sets} WHERE id=?", (*fields.values(), gid))

    def regenerate_invite(self, gid: int, staff: bool = False) -> str:
        code = _code()
        self.x(f"UPDATE groups SET {'staff_code' if staff else 'invite_code'}=? WHERE id=?", (code, gid))
        return code

    def all_groups(self) -> list[dict]:
        return self.q("SELECT * FROM groups")

    def member(self, tg_id: int) -> dict | None:
        return self.q1("SELECT * FROM members WHERE tg_id=?", (tg_id,))

    def add_member(self, tg_id: int, gid: int, role: str, full_name: str, username: str | None) -> None:
        from perms import SUPER_IDS
        if tg_id in SUPER_IDS:
            role = "curator"
        self.x("INSERT OR REPLACE INTO members(tg_id, group_id, role, full_name, username) VALUES (?,?,?,?,?)",
               (tg_id, gid, role, full_name, username))

    def leave(self, tg_id: int) -> None:
        self.x("UPDATE students SET tg_id=NULL WHERE tg_id=?", (tg_id,))
        self.x("DELETE FROM members WHERE tg_id=?", (tg_id,))

    def setting(self, key: str, default=None):
        r = self.q1("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(r["value"]) if r else default

    def set_setting(self, key: str, value) -> None:
        self.x("INSERT OR REPLACE INTO settings(key, value) VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))

    def lock(self) -> dict | None:
        """Закрытый доступ: {"text", "at"} или None, если сервис открыт."""
        v = self.setting("lock")
        return v if v and v.get("on") else None

    def all_member_ids(self) -> list[int]:
        return [r["tg_id"] for r in self.q("SELECT DISTINCT tg_id FROM members")]

    def consent_of(self, tg_id: int) -> str | None:
        r = self.q1("SELECT version FROM consents WHERE tg_id=?", (tg_id,))
        return r["version"] if r else None

    def set_consent(self, tg_id: int, version: str, via: str) -> None:
        self.x("INSERT OR REPLACE INTO consents(tg_id, version, at, via) VALUES (?,?,?,?)",
               (tg_id, version, int(time.time()), via))

    def forget(self, tg_id: int) -> None:
        """Отзыв согласия: удаляем запись студента (с отметками и оценками), членство, входы и само согласие."""
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.x("DELETE FROM students WHERE tg_id=?", (tg_id,))
        self.x("DELETE FROM members WHERE tg_id=?", (tg_id,))
        self.x("DELETE FROM app_sessions WHERE tg_id=?", (tg_id,))
        self.x("DELETE FROM app_logins WHERE tg_id=?", (tg_id,))
        self.x("DELETE FROM poll_messages WHERE tg_id=?", (tg_id,))
        self.x("DELETE FROM consents WHERE tg_id=?", (tg_id,))
        self.x("DELETE FROM staff_auth WHERE tg_id=?", (tg_id,))
        self.x("DELETE FROM feed WHERE target=?", (tg_id,))

    def delete_group(self, gid: int) -> None:
        """Удаляет группу целиком: участников, студентов, расписание, журнал, оценки, файлы, объявления."""
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.x("DELETE FROM poll_messages WHERE lesson_id IN (SELECT id FROM lessons WHERE group_id=?)", (gid,))
        self.x("DELETE FROM groups WHERE id=?", (gid,))

    def members(self, gid: int) -> list[dict]:
        return self.q(
            "SELECT m.*, s.id AS student_id, s.full_name AS student_name FROM members m "
            "LEFT JOIN students s ON s.tg_id = m.tg_id WHERE m.group_id=? ORDER BY "
            "CASE m.role WHEN 'head' THEN 0 WHEN 'deputy' THEN 1 WHEN 'curator' THEN 2 ELSE 3 END, m.full_name", (gid,))

    def staff(self, gid: int, *perms: str) -> list[dict]:
        """Участники, у которых есть хотя бы одно из прав (по умолчанию — журнал или отметки)."""
        from perms import can
        perms = perms or ("journal", "attendance")
        return [m for m in self.q("SELECT * FROM members WHERE group_id=?", (gid,)) if can(m, *perms)]

    def apply_super_curators(self) -> int:
        """Главные кураторы из CURATOR_IDS: роль «Куратор», все права (через perms.is_super)."""
        from perms import SUPER_IDS
        n = 0
        for tg in SUPER_IDS:
            cur = self.member(tg)
            if cur and (cur["role"] != "curator" or cur["perms"] is not None):
                self.x("UPDATE members SET role='curator', perms=NULL WHERE tg_id=?", (tg,))
                n += 1
        return n

    def set_role(self, gid: int, tg_id: int, role: str) -> None:
        self.x("UPDATE members SET role=?, perms=NULL WHERE tg_id=? AND group_id=?", (role, tg_id, gid))

    def set_perms(self, gid: int, tg_id: int, perms: str | None) -> None:
        self.x("UPDATE members SET perms=? WHERE tg_id=? AND group_id=?", (perms, tg_id, gid))

    def set_reminders(self, tg_id: int, on: bool) -> None:
        self.x("UPDATE members SET reminders=? WHERE tg_id=?", (1 if on else 0, tg_id))

    def students(self, gid: int, include_archived: bool = False) -> list[dict]:
        sql = "SELECT * FROM students WHERE group_id=?" + ("" if include_archived else " AND archived=0")
        return self.q(sql + " ORDER BY full_name COLLATE NOCASE", (gid,))

    def student(self, gid: int, sid: int) -> dict | None:
        return self.q1("SELECT * FROM students WHERE id=? AND group_id=?", (sid, gid))

    def student_by_tg(self, tg_id: int) -> dict | None:
        return self.q1("SELECT * FROM students WHERE tg_id=?", (tg_id,))

    def add_students(self, gid: int, names: list[str]) -> int:
        existing = {s["full_name"].lower() for s in self.students(gid, True)}
        n = 0
        for name in names:
            name = " ".join(name.split())
            if not name or name.lower() in existing:
                continue
            self.x("INSERT INTO students(group_id, full_name) VALUES (?,?)", (gid, name[:120]))
            existing.add(name.lower())
            n += 1
        return n

    def add_self_student(self, gid: int, name: str, tg_id: int, force_new: bool = False) -> dict:
        """Студент сам вписывает ФИО. Ищем его в списке (ведомости) по фамилии и инициалам без учёта регистра.

        Возвращает {"id", "matched", "name"} или {"choose": [...]} — если подходят несколько записей.
        """
        import names
        name = names.pretty(" ".join(name.split())[:120])
        import passwords
        free = [s for s in self.students(gid, include_archived=True)
                if not s["tg_id"] or s["tg_id"] == tg_id or passwords.is_synthetic(s["tg_id"])]
        cand = [] if force_new else names.candidates(name, free)
        if len(cand) > 1:
            return {"choose": [{"id": s["id"], "full_name": s["full_name"], "record_no": s.get("record_no")} for s in cand]}
        self.x("UPDATE students SET tg_id=NULL WHERE tg_id=?", (tg_id,))
        if cand:
            st = cand[0]
            if passwords.is_synthetic(st["tg_id"]):
                self.adopt_account(st["tg_id"], tg_id)
            better = names.pretty(names.fuller(names.surname_first(name, st["full_name"]), st["full_name"]))
            self.x("UPDATE students SET tg_id=?, archived=0, full_name=? WHERE id=?", (tg_id, better, st["id"]))
            return {"id": st["id"], "matched": True, "name": better, "was": st["full_name"]}
        sid = self.x("INSERT INTO students(group_id, full_name, tg_id) VALUES (?,?,?)", (gid, name, tg_id))
        return {"id": sid, "matched": False, "name": name}

    def merge_students(self, gid: int, keep: int, drop: int) -> None:
        """Объединяет две записи одного человека: отметки, оценки, Telegram и данные переходят в keep."""
        import names
        k, dr = self.student(gid, keep), self.student(gid, drop)
        if not k or not dr or keep == drop:
            return
        self.conn.execute("BEGIN")
        try:
            self.x("INSERT OR IGNORE INTO attendance(lesson_id,date,student_id,status,source,reason,file_id,marked_by,marked_at) "
                   "SELECT lesson_id,date,?,status,source,reason,file_id,marked_by,marked_at FROM attendance WHERE student_id=?", (keep, drop))
            self.x("INSERT OR IGNORE INTO grade_rows(month_id,student_id,grades,missed_total,missed_bad,note) "
                   "SELECT month_id,?,grades,missed_total,missed_bad,note FROM grade_rows WHERE student_id=?", (keep, drop))
            fields = {c: dr[c] for c in ("phone", "note", "record_no", "email", "birth_date", "parent_name", "parent_phone")
                      if not k.get(c) and dr.get(c)}
            tg = k["tg_id"] or dr["tg_id"]
            self.x("DELETE FROM students WHERE id=?", (drop,))
            fields["full_name"] = names.pretty(names.fuller(dr["full_name"], k["full_name"]))
            sets = ", ".join(f"{c}=?" for c in fields)
            self.x(f"UPDATE students SET {sets}, tg_id=?, archived=0 WHERE id=?", (*fields.values(), tg, keep))
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def auto_merge(self, gid: int) -> list[str]:
        """Студент записался сам («антонюк алексей»), а в ведомости он «АНТОНЮК А.С.» — склеиваем, если пара однозначна."""
        import names
        sts = self.students(gid, include_archived=True)
        graded = {r["student_id"] for r in self.q("SELECT DISTINCT r.student_id FROM grade_rows r JOIN grade_months m ON m.id=r.month_id "
                                                   "WHERE m.group_id=?", (gid,))}
        linked_no_grades = [s for s in sts if s["tg_id"] and s["id"] not in graded]
        free_graded = [s for s in sts if not s["tg_id"] and s["id"] in graded]
        merged = []
        for s in linked_no_grades:
            cand = [x for x in free_graded if names.same_person(s["full_name"], x["full_name"])]
            if len(cand) == 1 and len([y for y in linked_no_grades if names.same_person(y["full_name"], cand[0]["full_name"])]) == 1:
                self.merge_students(gid, cand[0]["id"], s["id"])
                free_graded.remove(cand[0])
                merged.append(f"{s['full_name']} = {cand[0]['full_name']}")
        return merged

    def update_student(self, gid: int, sid: int, **fields) -> None:
        allowed = {"full_name", "phone", "note", "archived", "record_no", "email", "birth_date", "parent_name", "parent_phone"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            self.x(f"UPDATE students SET {sets} WHERE id=? AND group_id=?", (*fields.values(), sid, gid))

    def delete_student(self, gid: int, sid: int) -> None:
        import passwords
        self.x("DELETE FROM app_sessions WHERE tg_id=?", (passwords.parent_id(sid),))
        self.x("DELETE FROM consents WHERE tg_id=?", (passwords.parent_id(sid),))
        self.x("DELETE FROM students WHERE id=? AND group_id=?", (sid, gid))

    def claim_student(self, gid: int, sid: int, tg_id: int) -> bool:
        import passwords
        st = self.student(gid, sid)
        if not st or (st["tg_id"] and st["tg_id"] != tg_id and not passwords.is_synthetic(st["tg_id"])):
            return False
        if passwords.is_synthetic(st["tg_id"]):
            self.adopt_account(st["tg_id"], tg_id)
        self.x("UPDATE students SET tg_id=NULL WHERE tg_id=?", (tg_id,))
        self.x("UPDATE students SET tg_id=? WHERE id=?", (tg_id, sid))
        return True

    def students_by_record(self, record_norm: str) -> list[dict]:
        import passwords
        return [s for s in self.q("SELECT * FROM students WHERE record_no IS NOT NULL AND record_no != '' AND archived=0")
                if passwords.norm_record(s["record_no"]) == record_norm]

    def student_auth(self, sid: int) -> dict:
        return self.q1("SELECT * FROM student_auth WHERE student_id=?", (sid,)) or {}

    def auth_flags(self, gid: int) -> dict[int, dict]:
        return {r["student_id"]: {"password": bool(r["pass_hash"]), "code_until": r["code_expires"] if r["code_hash"] else None}
                for r in self.q("SELECT a.* FROM student_auth a JOIN students s ON s.id = a.student_id WHERE s.group_id=?", (gid,))}

    def parent_flags(self, gid: int) -> dict[int, dict]:
        return {r["student_id"]: {"password": bool(r["pass_hash"]), "code_until": r["code_expires"] if r["code_hash"] else None}
                for r in self.q("SELECT a.* FROM parent_auth a JOIN students s ON s.id = a.student_id WHERE s.group_id=?", (gid,))}

    def set_login_code(self, sid: int, code_hash: str, expires: int, by: int) -> None:
        self.x("INSERT INTO student_auth(student_id, code_hash, code_expires, code_tries, code_by) VALUES (?,?,?,0,?) "
               "ON CONFLICT(student_id) DO UPDATE SET code_hash=excluded.code_hash, code_expires=excluded.code_expires, "
               "code_tries=0, code_by=excluded.code_by", (sid, code_hash, expires, by))

    def code_try(self, sid: int) -> None:
        self.x("UPDATE student_auth SET code_tries = code_tries + 1 WHERE student_id=?", (sid,))

    def set_password(self, sid: int, pass_hash: str) -> None:
        self.x("INSERT INTO student_auth(student_id, pass_hash, pass_set_at) VALUES (?,?,?) "
               "ON CONFLICT(student_id) DO UPDATE SET pass_hash=excluded.pass_hash, pass_set_at=excluded.pass_set_at, "
               "code_hash=NULL, code_expires=NULL, code_tries=0", (sid, pass_hash, int(time.time())))

    def account_for_student(self, st: dict) -> int:
        """ID аккаунта студента: его Telegram, а если Telegram нет — собственный (без Telegram)."""
        import passwords
        if st.get("tg_id"):
            uid = st["tg_id"]
        else:
            uid = passwords.synthetic_id(st["id"])
            self.x("UPDATE students SET tg_id=? WHERE id=?", (uid, st["id"]))
        if not self.member(uid):
            self.x("INSERT INTO members(tg_id, group_id, role, full_name, username) VALUES (?,?,?,?,?)",
                   (uid, st["group_id"], "student", st["full_name"].split()[1] if len(st["full_name"].split()) > 1 else st["full_name"], None))
        return uid

    def adopt_account(self, old_uid: int, new_uid: int) -> None:
        """Студент без Telegram потом зашёл через Telegram: переносим его вход, согласие и сессии на Telegram."""
        if old_uid == new_uid:
            return
        if self.member(new_uid):
            self.x("DELETE FROM members WHERE tg_id=?", (old_uid,))
        else:
            self.x("UPDATE members SET tg_id=? WHERE tg_id=?", (new_uid, old_uid))
        self.x("UPDATE app_sessions SET tg_id=? WHERE tg_id=?", (new_uid, old_uid))
        self.x("INSERT OR IGNORE INTO consents(tg_id, version, at, via) SELECT ?, version, at, via FROM consents WHERE tg_id=?", (new_uid, old_uid))
        self.x("DELETE FROM consents WHERE tg_id=?", (old_uid,))
        self.x("DELETE FROM presence WHERE tg_id=?", (old_uid,))

    def new_app_session(self, uid: int, first_name: str, device: str = "password") -> str:
        import hashlib
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        self.x("INSERT INTO app_sessions(token_hash, tg_id, first_name, last_name, username, created_at, last_used, device) "
               "VALUES (?,?,?,?,?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), uid, first_name, None, None, now, now, device))
        return token

    def unlink_student(self, gid: int, sid: int) -> None:
        self.x("UPDATE students SET tg_id=NULL WHERE id=? AND group_id=?", (sid, gid))

    def lessons(self, gid: int, include_oneoff: bool = True) -> list[dict]:
        sql = "SELECT * FROM lessons WHERE group_id=?" + ("" if include_oneoff else " AND date IS NULL")
        return self.q(sql + " ORDER BY weekday, t_start", (gid,))

    def lesson(self, gid: int, lid: int) -> dict | None:
        return self.q1("SELECT * FROM lessons WHERE id=? AND group_id=?", (lid, gid))

    def save_lesson(self, gid: int, data: dict, lid: int | None = None) -> int:
        cols = ("weekday", "t_start", "t_end", "subject", "kind", "room", "teacher", "parity", "note", "date")
        vals = [data.get(c) for c in cols]
        if lid:
            sets = ", ".join(f"{c}=?" for c in cols)
            self.x(f"UPDATE lessons SET {sets} WHERE id=? AND group_id=?", (*vals, lid, gid))
            return lid
        return self.x(f"INSERT INTO lessons(group_id, {', '.join(cols)}) VALUES (?{',?' * len(cols)})", (gid, *vals))

    def delete_lesson(self, gid: int, lid: int) -> None:
        self.x("DELETE FROM lessons WHERE id=? AND group_id=?", (lid, gid))

    def change_on(self, lid: int, d: str) -> dict | None:
        return self.q1("SELECT * FROM lesson_changes WHERE lesson_id=? AND date=?", (lid, d))

    def changes_on(self, gid: int, d: str) -> dict[int, dict]:
        return {c["lesson_id"]: c for c in self.q("SELECT * FROM lesson_changes WHERE group_id=? AND date=?", (gid, d))}

    def moved_in(self, gid: int) -> dict[int, dict]:
        """Разовые пары, появившиеся из-за переноса: id новой пары → изменение."""
        return {c["moved_lesson_id"]: c for c in self.q(
            "SELECT * FROM lesson_changes WHERE group_id=? AND moved_lesson_id IS NOT NULL", (gid,))}

    def changes_between(self, gid: int, d1: str, d2: str) -> list[dict]:
        return self.q("SELECT c.*, l.subject, l.t_start, l.t_end, l.room, l.kind AS lesson_kind FROM lesson_changes c "
                      "JOIN lessons l ON l.id = c.lesson_id WHERE c.group_id=? AND "
                      "((c.date BETWEEN ? AND ?) OR (c.new_date BETWEEN ? AND ?)) ORDER BY c.date, l.t_start",
                      (gid, d1, d2, d1, d2))

    def delete_change(self, gid: int, cid: int) -> dict | None:
        c = self.q1("SELECT * FROM lesson_changes WHERE id=? AND group_id=?", (cid, gid))
        if not c:
            return None
        self.conn.execute("PRAGMA foreign_keys=ON")
        if c["moved_lesson_id"]:
            self.delete_lesson(gid, c["moved_lesson_id"])
        self.x("DELETE FROM lesson_changes WHERE id=?", (cid,))
        return c

    def set_change(self, gid: int, lesson: dict, d: str, kind: str, by: dict, reason: str | None = None,
                   new_date: str | None = None, new_start: str | None = None, new_end: str | None = None,
                   new_room: str | None = None) -> dict:
        old = self.change_on(lesson["id"], d)
        if old:
            self.delete_change(gid, old["id"])
        moved = None
        if kind == "move":
            moved = self.save_lesson(gid, {
                "weekday": date.fromisoformat(new_date).weekday(), "t_start": new_start, "t_end": new_end,
                "subject": lesson["subject"], "kind": lesson.get("kind"), "room": new_room or lesson.get("room"),
                "teacher": lesson.get("teacher"), "parity": 0, "date": new_date,
                "note": f"Перенос с {date.fromisoformat(d):%d.%m} {lesson['t_start']}"})
        cid = self.x("INSERT INTO lesson_changes(group_id, lesson_id, date, kind, new_date, new_start, new_end, new_room, "
                     "moved_lesson_id, reason, by_tg, by_name, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (gid, lesson["id"], d, kind, new_date, new_start, new_end, new_room, moved, reason,
                      by.get("tg_id"), by.get("full_name"), int(time.time())))
        return self.q1("SELECT * FROM lesson_changes WHERE id=?", (cid,))

    def touch(self, tg_id: int, via: str, day: str, now: int) -> bool:
        """Отмечает активность. False — человек ещё не в группе (тогда не пишем историю)."""
        if not self.conn.execute("UPDATE members SET last_seen=?, last_via=? WHERE tg_id=?", (now, via, tg_id)).rowcount:
            return False
        self.x("INSERT INTO presence(tg_id, day, first_at, last_at) VALUES (?,?,?,?) "
               "ON CONFLICT(tg_id, day) DO UPDATE SET last_at=excluded.last_at", (tg_id, day, now, now))
        return True

    def presence(self, gid: int, since_day: str) -> dict[int, list[dict]]:
        out: dict[int, list[dict]] = {}
        for r in self.q("SELECT p.* FROM presence p JOIN members m ON m.tg_id = p.tg_id "
                        "WHERE m.group_id=? AND p.day >= ? ORDER BY p.day DESC", (gid, since_day)):
            out.setdefault(r["tg_id"], []).append({"day": r["day"], "first": r["first_at"], "last": r["last_at"]})
        return out

    def prune_presence(self, before_day: str) -> None:
        self.x("DELETE FROM presence WHERE day < ?", (before_day,))

    def subjects(self, gid: int) -> list[str]:
        return [r["subject"] for r in self.q(
            "SELECT DISTINCT subject FROM lessons WHERE group_id=? ORDER BY subject COLLATE NOCASE", (gid,))]

    def periods(self, gid: int) -> list[dict]:
        return self.q("SELECT * FROM periods WHERE group_id=? ORDER BY d1", (gid,))

    def add_period(self, gid: int, kind: str, title: str | None, d1: str, d2: str) -> int:
        return self.x("INSERT INTO periods(group_id, kind, title, d1, d2) VALUES (?,?,?,?,?)", (gid, kind, title, d1, d2))

    def delete_period(self, gid: int, pid: int) -> None:
        self.x("DELETE FROM periods WHERE id=? AND group_id=?", (pid, gid))

    def marks(self, lesson_id: int, date: str) -> dict[int, str]:
        rs = self.q("SELECT student_id, status FROM attendance WHERE lesson_id=? AND date=?", (lesson_id, date))
        return {r["student_id"]: r["status"] for r in rs}

    def marks_full(self, lesson_id: int, date: str) -> dict[int, dict]:
        rs = self.q("SELECT * FROM attendance WHERE lesson_id=? AND date=?", (lesson_id, date))
        return {r["student_id"]: r for r in rs}

    def mark(self, lesson_id: int, date: str, student_id: int) -> dict | None:
        return self.q1("SELECT * FROM attendance WHERE lesson_id=? AND date=? AND student_id=?",
                       (lesson_id, date, student_id))

    def set_marks(self, lesson_id: int, date: str, marks: dict[int, str | None], by: int, source: str = "manual") -> None:
        now = int(time.time())
        self.conn.execute("BEGIN")
        try:
            for sid, st in marks.items():
                if not st:
                    self.x("DELETE FROM attendance WHERE lesson_id=? AND date=? AND student_id=?", (lesson_id, date, sid))
                elif st in STATUSES:
                    self.x(
                        "INSERT INTO attendance(lesson_id, date, student_id, status, source, marked_by, marked_at) "
                        "VALUES (?,?,?,?,?,?,?) ON CONFLICT(lesson_id, date, student_id) DO UPDATE SET "
                        "status=excluded.status, source=excluded.source, marked_by=excluded.marked_by, "
                        "marked_at=excluded.marked_at",
                        (lesson_id, date, sid, st, source, by, now))
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def set_reason(self, lesson_id: int, date: str, sid: int, reason: str | None, file_id: str | None,
                   file_path: str | None = None) -> None:
        self.x("UPDATE attendance SET reason=COALESCE(?, reason), file_id=COALESCE(?, file_id), "
               "file_path=COALESCE(?, file_path) WHERE lesson_id=? AND date=? AND student_id=?",
               (reason, file_id, file_path, lesson_id, date, sid))

    def marked_counts(self, gid: int, date: str) -> dict[int, dict]:
        rs = self.q("SELECT a.lesson_id, a.status, COUNT(*) AS n FROM attendance a JOIN lessons l ON l.id=a.lesson_id "
                    "WHERE l.group_id=? AND a.date=? GROUP BY a.lesson_id, a.status", (gid, date))
        out: dict[int, dict] = {}
        for r in rs:
            out.setdefault(r["lesson_id"], {})[r["status"]] = r["n"]
        return out

    def attendance_range(self, gid: int, date_from: str, date_to: str) -> list[dict]:
        return self.q(
            "SELECT a.*, l.subject, l.t_start, l.t_end, l.kind FROM attendance a JOIN lessons l ON l.id=a.lesson_id "
            "WHERE l.group_id=? AND a.date BETWEEN ? AND ? ORDER BY a.date, l.t_start", (gid, date_from, date_to))

    def marked_dates(self, gid: int, date_from: str, date_to: str) -> dict[str, int]:
        rs = self.q("SELECT a.date, COUNT(*) AS n FROM attendance a JOIN lessons l ON l.id=a.lesson_id "
                    "WHERE l.group_id=? AND a.date BETWEEN ? AND ? GROUP BY a.date", (gid, date_from, date_to))
        return {r["date"]: r["n"] for r in rs}

    def open_checkin(self, gid: int, lesson_id: int, date: str, minutes: int) -> dict:
        self.x("DELETE FROM checkins WHERE group_id=? AND (expires_at < ? OR (lesson_id=? AND date=?))",
               (gid, int(time.time()), lesson_id, date))
        code = f"{secrets.randbelow(10000):04d}"
        cid = self.x("INSERT INTO checkins(group_id, lesson_id, date, code, expires_at) VALUES (?,?,?,?,?)",
                     (gid, lesson_id, date, code, int(time.time()) + minutes * 60))
        return self.q1("SELECT * FROM checkins WHERE id=?", (cid,))

    def active_checkins(self, gid: int) -> list[dict]:
        return self.q("SELECT * FROM checkins WHERE group_id=? AND expires_at>=?", (gid, int(time.time())))

    def close_checkin(self, gid: int, cid: int) -> None:
        self.x("DELETE FROM checkins WHERE id=? AND group_id=?", (cid, gid))

    def find_checkin(self, gid: int, code: str) -> dict | None:
        return self.q1("SELECT * FROM checkins WHERE group_id=? AND code=? AND expires_at>=? ORDER BY id DESC",
                       (gid, code.strip(), int(time.time())))

    def save_poll_message(self, lesson_id: int, date: str, tg_id: int, message_id: int) -> None:
        self.x("INSERT OR REPLACE INTO poll_messages VALUES (?,?,?,?)", (lesson_id, date, tg_id, message_id))

    def poll_messages(self, lesson_id: int, date: str) -> list[dict]:
        return self.q("SELECT * FROM poll_messages WHERE lesson_id=? AND date=?", (lesson_id, date))

    def add_announcement(self, gid: int, author: int, title: str | None, text: str, pinned: bool) -> int:
        return self.x("INSERT INTO announcements(group_id, author_id, title, text, pinned, created_at) VALUES (?,?,?,?,?,?)",
                      (gid, author, title, text, 1 if pinned else 0, int(time.time())))

    def set_delivered(self, aid: int, n: int) -> None:
        self.x("UPDATE announcements SET delivered=? WHERE id=?", (n, aid))

    def announcements(self, gid: int, limit: int = 30) -> list[dict]:
        return self.q("SELECT a.*, m.full_name AS author_name FROM announcements a LEFT JOIN members m ON m.tg_id=a.author_id "
                      "WHERE a.group_id=? ORDER BY a.pinned DESC, a.id DESC LIMIT ?", (gid, limit))

    def update_announcement(self, gid: int, aid: int, **fields) -> None:
        fields = {k: v for k, v in fields.items() if k in {"pinned"}}
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            self.x(f"UPDATE announcements SET {sets} WHERE id=? AND group_id=?", (*fields.values(), aid, gid))

    def delete_announcement(self, gid: int, aid: int) -> None:
        self.x("DELETE FROM announcements WHERE id=? AND group_id=?", (aid, gid))

    def add_file(self, gid: int, subject: str, title: str, file_id: str, file_type: str, size: int | None,
                 uploader: int, uploader_name: str, path: str | None = None) -> int:
        return self.x("INSERT INTO files(group_id, subject, title, file_id, file_type, size, uploader, uploader_name, created_at, path) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (gid, subject[:120], title[:200], file_id, file_type, size, uploader, uploader_name, int(time.time()), path))

    def files(self, gid: int) -> list[dict]:
        return self.q("SELECT * FROM files WHERE group_id=? ORDER BY subject COLLATE NOCASE, id DESC", (gid,))

    def file(self, gid: int, fid: int) -> dict | None:
        return self.q1("SELECT * FROM files WHERE id=? AND group_id=?", (fid, gid))

    def delete_file(self, gid: int, fid: int) -> None:
        self.x("DELETE FROM files WHERE id=? AND group_id=?", (fid, gid))

    def grade_months(self, gid: int) -> list[dict]:
        return self.q("SELECT id, month, updated_at FROM grade_months WHERE group_id=? ORDER BY month DESC", (gid,))

    def grade_month(self, gid: int, month: str) -> dict | None:
        r = self.q1("SELECT * FROM grade_months WHERE group_id=? AND month=?", (gid, month))
        if r:
            r["subjects"] = json.loads(r["subjects"])
        return r

    def save_grade_month(self, gid: int, month: str, subjects: list[dict], by: int | None) -> int:
        cur = self.grade_month(gid, month)
        if cur:
            self.x("UPDATE grade_months SET subjects=?, updated_at=?, updated_by=? WHERE id=?",
                   (json.dumps(subjects, ensure_ascii=False), int(time.time()), by, cur["id"]))
            return cur["id"]
        return self.x("INSERT INTO grade_months(group_id, month, subjects, updated_at, updated_by) VALUES (?,?,?,?,?)",
                      (gid, month, json.dumps(subjects, ensure_ascii=False), int(time.time()), by))

    def delete_grade_month(self, gid: int, month: str) -> None:
        self.x("DELETE FROM grade_months WHERE group_id=? AND month=?", (gid, month))

    def touch_grade_month(self, mid: int, by: int | None) -> None:
        self.x("UPDATE grade_months SET updated_at=?, updated_by=? WHERE id=?", (int(time.time()), by, mid))

    def grade_rows(self, mid: int) -> dict[int, dict]:
        out = {}
        for r in self.q("SELECT * FROM grade_rows WHERE month_id=?", (mid,)):
            r["grades"] = json.loads(r["grades"])
            out[r["student_id"]] = r
        return out

    def save_grade_row(self, mid: int, sid: int, grades: list, missed_total=None, missed_bad=None, note=None) -> None:
        self.x("INSERT INTO grade_rows(month_id, student_id, grades, missed_total, missed_bad, note) VALUES (?,?,?,?,?,?) "
               "ON CONFLICT(month_id, student_id) DO UPDATE SET grades=excluded.grades, missed_total=excluded.missed_total, "
               "missed_bad=excluded.missed_bad, note=excluded.note",
               (mid, sid, json.dumps(grades, ensure_ascii=False), missed_total, missed_bad, note))

    def app_login_start(self) -> str:
        self.x("DELETE FROM app_logins WHERE created_at < ?", (int(time.time()) - 900,))
        code = secrets.token_urlsafe(12).replace("-", "a").replace("_", "b")
        self.x("INSERT INTO app_logins(code, created_at) VALUES (?,?)", (code, int(time.time())))
        return code

    def app_login(self, code: str) -> dict | None:
        r = self.q1("SELECT * FROM app_logins WHERE code=?", (code,))
        if r and time.time() - r["created_at"] > 900:
            self.x("DELETE FROM app_logins WHERE code=?", (code,))
            return None
        return r

    def app_login_approve(self, code: str, user: dict, device: str | None = None) -> bool:
        import hashlib
        r = self.app_login(code)
        if not r or r["token"]:
            return False
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        self.x("INSERT INTO app_sessions(token_hash, tg_id, first_name, last_name, username, created_at, last_used, device) "
               "VALUES (?,?,?,?,?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user["id"], user.get("first_name"),
                                           user.get("last_name"), user.get("username"), now, now, device))
        self.x("UPDATE app_logins SET tg_id=?, token=? WHERE code=?", (user["id"], token, code))
        return True

    def app_login_take(self, code: str) -> str | None:
        """Приложение забирает токен один раз."""
        r = self.app_login(code)
        if r and r["token"]:
            self.x("DELETE FROM app_logins WHERE code=?", (code,))
            return r["token"]
        return None

    def app_session(self, token: str) -> dict | None:
        import hashlib
        h = hashlib.sha256(token.encode()).hexdigest()
        r = self.q1("SELECT * FROM app_sessions WHERE token_hash=?", (h,))
        if r and time.time() - r["last_used"] > 90 * 86400:
            self.app_logout(token)
            return None
        if r and time.time() - r["last_used"] > 60:
            self.x("UPDATE app_sessions SET last_used=? WHERE token_hash=?", (int(time.time()), h))
        return r

    def app_logout(self, token: str) -> None:
        import hashlib
        self.x("DELETE FROM app_sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def app_sessions_of(self, tg_id: int) -> list[dict]:
        return self.q("SELECT token_hash, created_at, last_used, device FROM app_sessions WHERE tg_id=? ORDER BY last_used DESC", (tg_id,))

    def app_logout_all(self, tg_id: int) -> int:
        n = len(self.app_sessions_of(tg_id))
        self.x("DELETE FROM app_sessions WHERE tg_id=?", (tg_id,))
        return n

    def audit(self, gid: int | None, actor: dict | None, action: str, text: str, students: list[int] | None = None) -> None:
        name = None
        if actor:
            st = self.student_by_tg(actor["tg_id"]) if actor.get("tg_id") else None
            name = (st or {}).get("full_name") or actor.get("full_name")
        ids = "," + ",".join(str(int(s)) for s in students) + "," if students else None
        self.x("INSERT INTO audit(group_id, at, actor, actor_name, action, text, students) VALUES (?,?,?,?,?,?,?)",
               (gid, int(time.time()), (actor or {}).get("tg_id"), name, action, text[:1500], ids))

    def audit_list(self, gid: int, limit: int = 60, before: int | None = None, student: int | None = None,
                   action: str | None = None, q: str | None = None, with_global: bool = False) -> list[dict]:
        where, params = ["(group_id=?" + (" OR group_id IS NULL)" if with_global else ")")], [gid]
        if before:
            where.append("id < ?"); params.append(before)
        if student:
            where.append("students LIKE ?"); params.append(f"%,{int(student)},%")
        if action:
            where.append("action=?"); params.append(action)
        if q:
            where.append("(text LIKE ? OR actor_name LIKE ?)"); params += [f"%{q}%", f"%{q}%"]
        return self.q(f"SELECT * FROM audit WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?", (*params, limit))

    def prune_audit(self, before_ts: int) -> None:
        self.x("DELETE FROM audit WHERE at < ?", (before_ts,))

    def add_feed(self, gid: int, kind: str, title: str, body: str | None = None, target: int | None = None,
                 author: int | None = None) -> int:
        return self.x("INSERT INTO feed(group_id, target, author, kind, title, body, created_at) VALUES (?,?,?,?,?,?,?)",
                      (gid, target, author, kind, title[:200], (body or "")[:600] or None, int(time.time())))

    def feed_last(self) -> int:
        return (self.q1("SELECT MAX(id) AS m FROM feed") or {}).get("m") or 0

    def feed_since(self, gid: int, uid: int, since: int, limit: int = 20) -> list[dict]:
        return self.q("SELECT id, kind, title, body, created_at FROM feed WHERE group_id=? AND id > ? AND created_at > ? "
                      "AND (target IS NULL OR target=?) AND (author IS NULL OR author != ?) ORDER BY id LIMIT ?",
                      (gid, since, int(time.time()) - 3 * 86400, uid, uid, limit))

    def prune_feed(self, before_ts: int) -> None:
        self.x("DELETE FROM feed WHERE created_at < ?", (before_ts,))

    def set_push(self, tg_id: int, on: bool) -> None:
        self.x("UPDATE members SET push=? WHERE tg_id=?", (1 if on else 0, tg_id))

    def homework_list(self, gid: int, d_from: str | None = None, d_to: str | None = None) -> list[dict]:
        sql, params = "SELECT * FROM homework WHERE group_id=?", [gid]
        if d_from:
            sql += " AND due_date >= ?"; params.append(d_from)
        if d_to:
            sql += " AND due_date <= ?"; params.append(d_to)
        return self.q(sql + " ORDER BY due_date, subject COLLATE NOCASE, id", params)

    def homework(self, gid: int, hid: int) -> dict | None:
        return self.q1("SELECT * FROM homework WHERE id=? AND group_id=?", (hid, gid))

    def save_homework(self, gid: int, data: dict, by: dict, hid: int | None = None) -> int:
        cols = ("subject", "lesson_id", "lesson_date", "title", "text", "due_date")
        vals = [data.get(c) for c in cols]
        now = int(time.time())
        if hid:
            sets = ", ".join(f"{c}=?" for c in cols)
            self.x(f"UPDATE homework SET {sets}, updated_at=? WHERE id=? AND group_id=?", (*vals, now, hid, gid))
            return hid
        return self.x(f"INSERT INTO homework(group_id, {', '.join(cols)}, created_by, author_name, created_at) "
                      f"VALUES (?{',?' * len(cols)},?,?,?)", (gid, *vals, by.get("tg_id"), by.get("full_name"), now))

    def delete_homework(self, gid: int, hid: int) -> None:
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.x("DELETE FROM homework WHERE id=? AND group_id=?", (hid, gid))

    def homework_done_ids(self, sid: int) -> dict[int, int]:
        return {r["hw_id"]: r["done_at"] for r in self.q("SELECT hw_id, done_at FROM homework_done WHERE student_id=?", (sid,))}

    def homework_done_counts(self, gid: int) -> dict[int, int]:
        return {r["hw_id"]: r["n"] for r in self.q(
            "SELECT d.hw_id, COUNT(*) AS n FROM homework_done d JOIN homework h ON h.id=d.hw_id WHERE h.group_id=? GROUP BY d.hw_id", (gid,))}

    def set_homework_done(self, hid: int, sid: int, done: bool) -> None:
        if done:
            self.x("INSERT OR IGNORE INTO homework_done(hw_id, student_id, done_at) VALUES (?,?,?)", (hid, sid, int(time.time())))
        else:
            self.x("DELETE FROM homework_done WHERE hw_id=? AND student_id=?", (hid, sid))

    def staff_auth(self, tg_id: int) -> dict:
        return self.q1("SELECT * FROM staff_auth WHERE tg_id=?", (tg_id,)) or {}

    def staff_by_login(self, login: str) -> dict | None:
        return self.q1("SELECT * FROM staff_auth WHERE login=?", ((login or "").strip().lower(),))

    def set_staff_login(self, tg_id: int, login: str) -> None:
        self.x("INSERT INTO staff_auth(tg_id, login) VALUES (?,?) ON CONFLICT(tg_id) DO UPDATE SET login=excluded.login",
               (tg_id, login))

    def set_staff_password(self, tg_id: int, pass_hash: str) -> None:
        self.x("INSERT INTO staff_auth(tg_id, pass_hash, pass_set_at) VALUES (?,?,?) ON CONFLICT(tg_id) DO UPDATE SET "
               "pass_hash=excluded.pass_hash, pass_set_at=excluded.pass_set_at, code_hash=NULL, code_expires=NULL, code_tries=0",
               (tg_id, pass_hash, int(time.time())))

    def set_staff_code(self, tg_id: int, code_hash: str, expires: int, by: int) -> None:
        self.x("INSERT INTO staff_auth(tg_id, code_hash, code_expires, code_tries, code_by) VALUES (?,?,?,0,?) "
               "ON CONFLICT(tg_id) DO UPDATE SET code_hash=excluded.code_hash, code_expires=excluded.code_expires, "
               "code_tries=0, code_by=excluded.code_by", (tg_id, code_hash, expires, by))

    def staff_code_try(self, tg_id: int) -> None:
        self.x("UPDATE staff_auth SET code_tries = code_tries + 1 WHERE tg_id=?", (tg_id,))

    def parent_auth(self, sid: int) -> dict:
        return self.q1("SELECT * FROM parent_auth WHERE student_id=?", (sid,)) or {}

    def set_parent_code(self, sid: int, code_hash: str, expires: int, by: int) -> None:
        self.x("INSERT INTO parent_auth(student_id, code_hash, code_expires, code_tries, code_by) VALUES (?,?,?,0,?) "
               "ON CONFLICT(student_id) DO UPDATE SET code_hash=excluded.code_hash, code_expires=excluded.code_expires, "
               "code_tries=0, code_by=excluded.code_by", (sid, code_hash, expires, by))

    def parent_code_try(self, sid: int) -> None:
        self.x("UPDATE parent_auth SET code_tries = code_tries + 1 WHERE student_id=?", (sid,))

    def set_parent_password(self, sid: int, pass_hash: str) -> None:
        self.x("INSERT INTO parent_auth(student_id, pass_hash, pass_set_at) VALUES (?,?,?) ON CONFLICT(student_id) DO UPDATE SET "
               "pass_hash=excluded.pass_hash, pass_set_at=excluded.pass_set_at, code_hash=NULL, code_expires=NULL, code_tries=0",
               (sid, pass_hash, int(time.time())))

    def backup_to(self, path: str) -> None:
        dst = sqlite3.connect(path)
        try:
            self.conn.backup(dst)
        finally:
            dst.close()

    def restore_from(self, path: str) -> None:
        """Заменяет содержимое базы копией (на том же соединении) и доводит схему до текущей версии."""
        src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            ok = src.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise ValueError("Копия повреждена: " + str(ok)[:100])
            if not src.execute("SELECT 1 FROM sqlite_master WHERE name='groups'").fetchone():
                raise ValueError("Это не база «Куратор +»")
            src.backup(self.conn)
        finally:
            src.close()
        self._migrate_before()
        self.conn.executescript(SCHEMA)
        self._migrate_after()
