"""Создаёт первую группу и её владельца без Telegram — вход по логину и паролю.

Запуск на сервере из папки проекта:
    python bot/setup_admin.py "ИВТ-21" ivanov 'S3cret-Pass'
                      название ^     логин ^    пароль ^

Дальше владелец открывает сайт → «Войти по паролю» → вводит логин и пароль,
добавляет студентов и раздаёт им коды первого входа (студенты тоже заходят без Telegram).
Если позже вписать BOT_TOKEN в .env — бот и уведомления в Telegram подключатся сами.
"""
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import features
import passwords
from config import load_config
from db import DB
from perms import ALL, dump


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    name, login, pw = (a.strip() for a in sys.argv[1:4])
    if not (1 <= len(name) <= 80):
        print("Название группы — 1-80 символов")
        return 1
    login = login.lower()
    if not features.LOGIN_RE.match(login):
        print("Логин: 3-40 символов a-z, цифры и ._@-, с буквы")
        return 1
    problem = passwords.password_problem(pw, login)
    if problem:
        print("Пароль не подходит:", problem)
        return 1

    cfg = load_config()
    db = DB(cfg.db_path)
    if db.staff_by_login(login):
        print(f"Логин «{login}» уже занят — выберите другой")
        return 1
    if db.all_groups():
        print("Группы уже есть — этого достаточно, новый аккаунт создаёт староста из приложения.")
        return 1

    uid = passwords.STAFF_BASE - secrets.randbelow(10**9)
    g = db.create_group(name, cfg.default_tz, uid, login, None, "curator", dump(ALL))
    db.set_staff_login(uid, login)
    db.set_staff_password(uid, passwords.hash_secret(pw))
    url = __import__("os").getenv("WEBAPP_URL", "").rstrip("/") or f"http://{cfg.host}:{cfg.port}"
    print(f"Группа «{g['name']}» создана. Владелец: {login}")
    print(f"   Вход: {url} -> «Войти по паролю» -> логин и пароль из командной строки")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
