"""Вход без Telegram: номер студенческого + пароль.

Первый пароль и восстановление — только по одноразовому коду, который выдаёт староста или куратор
(номер студенческого не секрет, поэтому без кода зарегистрироваться за другого нельзя).

Пароли хранятся только как хеш scrypt (стандартная библиотека Python), коды — тоже хешем.
"""
import hashlib
import hmac
import re
import secrets
import time

SYN_BASE = -8_000_000_000_000     # «аккаунт» студента без Telegram: SYN_BASE - id студента (вне диапазона Telegram)
PARENT_BASE = -8_500_000_000_000  # вход родителя: PARENT_BASE - id студента (только просмотр данных ребёнка)
CODE_TTL = 24 * 3600              # код действует сутки
CODE_TRIES = 5                    # попыток ввода кода
MAX_FAILS, LOCK_SEC = 5, 600      # 5 неверных паролей → пауза 10 минут

_fails: dict[str, list[float]] = {}
_LOOKALIKE = str.maketrans("ABCEHKMOPTXY", "АВСЕНКМОРТХУ")


def synthetic_id(student_id: int) -> int:
    return SYN_BASE - int(student_id)


def is_synthetic(tg_id) -> bool:
    try:
        return PARENT_BASE < int(tg_id) <= SYN_BASE
    except (TypeError, ValueError):
        return False


def parent_id(student_id: int) -> int:
    return PARENT_BASE - int(student_id)


def is_parent(tg_id) -> bool:
    try:
        return -9_000_000_000_000 < int(tg_id) <= PARENT_BASE
    except (TypeError, ValueError):
        return False


def parent_student(tg_id) -> int:
    return PARENT_BASE - int(tg_id)


def norm_record(no: str) -> str:
    """«а-309 », «А 309» и «А-309» — один и тот же номер."""
    s = re.sub(r"[\s\-–—_./]", "", str(no or "")).upper()
    return s.translate(_LOOKALIKE)          # латинская «A» и русская «А» — одна буква


def hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    d = hashlib.scrypt(secret.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${d.hex()}"


def check_secret(secret: str, stored: str | None) -> bool:
    try:
        algo, salt, digest = (stored or "").split("$")
        if algo != "scrypt":
            return False
        d = hashlib.scrypt(secret.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(d.hex(), digest)
    except (ValueError, TypeError):
        return False


def new_code() -> str:
    return f"{secrets.randbelow(10 ** 6):06d}"


def password_problem(password: str, record_no: str) -> str | None:
    if len(password) < 8:
        return "Пароль — не короче 8 символов"
    if len(password) > 128:
        return "Слишком длинный пароль"
    if norm_record(password) == norm_record(record_no):
        return "Пароль не должен совпадать с номером студенческого"
    if password.isdigit() and len(set(password)) <= 2:
        return "Слишком простой пароль"
    return None


def locked(key: str) -> int:
    """Сколько секунд ещё ждать после серии неверных попыток (0 — можно)."""
    now = time.time()
    tries = [t for t in _fails.get(key, []) if now - t < LOCK_SEC]
    _fails[key] = tries
    return int(LOCK_SEC - (now - tries[0])) if len(tries) >= MAX_FAILS else 0


def fail(key: str) -> None:
    _fails.setdefault(key, []).append(time.time())


def success(key: str) -> None:
    _fails.pop(key, None)
