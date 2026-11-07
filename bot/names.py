"""Сопоставление ФИО: «АНТОНЮК А.С.», «Антонюк Алексей Сергеевич», «антонюк алексей», «Алексей Антонюк».

Сравнение без учёта регистра, «ё» = «е», латинские буквы-двойники (A, C, E, O, P…) = русские.
Совпадение — одинаковая фамилия и непротиворечивые инициалы (А.С. ~ Алексей ~ Алексей Сергеевич).
"""
import re

_LAT = str.maketrans("ABCEHKMOPTXYaceopxyё", "АВСЕНКМОРТХУасеорхуе")


def _clean(name: str) -> list[str]:
    s = (name or "").translate(_LAT).replace("Ё", "Е")
    return [p for p in re.split(r"[\s.,]+", s) if p and re.search(r"[А-Яа-яA-Za-z]", p)]


def key(name: str) -> tuple[str, str]:
    """→ (фамилия в нижнем регистре, инициалы) — для формы «Фамилия Имя Отчество»."""
    parts = _clean(name)
    if not parts:
        return "", ""
    return parts[0].lower(), "".join(p[0].lower() for p in parts[1:3])


def keys(name: str) -> list[tuple[str, str]]:
    """Варианты ключа: «Фамилия Имя» и «Имя Фамилия»."""
    parts = _clean(name)
    if not parts:
        return []
    out = [(parts[0].lower(), "".join(p[0].lower() for p in parts[1:3]))]
    if len(parts) >= 2:
        out.append((parts[-1].lower(), "".join(p[0].lower() for p in parts[:-1][:2])))
    return out


def initials_ok(a: str, b: str) -> bool:
    return not a or not b or a.startswith(b) or b.startswith(a)


def same_person(a: str, b: str) -> bool:
    ka = keys(a)
    sb, ib = key(b)
    return any(s == sb and initials_ok(i, ib) for s, i in ka)


def candidates(name: str, students: list[dict]) -> list[dict]:
    """Студенты из списка, подходящие под введённое ФИО. Сначала точные по полному ФИО."""
    norm = lambda s: " ".join(_clean(s)).lower()
    exact = [s for s in students if norm(s["full_name"]) == norm(name)]
    if exact:
        return exact
    return [s for s in students if same_person(name, s["full_name"])]


def fuller(a: str, b: str) -> str:
    """Какое из двух написаний подробнее (полные имя/отчество лучше инициалов)."""
    score = lambda n: sum(len(p) for p in _clean(n)[1:3]) + (0 if n.isupper() else 1)
    return a if score(a) > score(b) else b


def pretty(name: str) -> str:
    """«антонюк алексей» → «Антонюк Алексей»; «АНТОНЮК А.С.» → «Антонюк А.С.»."""
    words = " ".join(name.split()).split(" ")
    out = []
    for w in words:
        if "." in w and len(w) <= 5:
            out.append(w.upper())
        else:
            out.append("-".join(x[:1].upper() + x[1:].lower() for x in w.split("-")))
    return " ".join(out)


def surname_first(typed: str, reference: str) -> str:
    """«Никита Бабкин» при записи «БАБКИН Н.С» → «Бабкин Никита»."""
    parts = typed.split()
    if len(parts) >= 2 and key(typed)[0] != key(reference)[0] and _clean(parts[-1])[0].lower() == key(reference)[0]:
        return " ".join([parts[-1]] + parts[:-1])
    return typed
