"""Роли и права доступа.

Роли: староста, зам. старосты (те же права, что у старосты), куратор, студент.
Куратору и студенту староста может выдать или забрать любые права по отдельности.
"""
import json
import os

import config

SUPER_IDS = {int(x) for x in os.getenv("CURATOR_IDS", "").replace(" ", "").split(",") if x.isdigit()}

ROLES = {"head": "Староста", "deputy": "Зам. старосты", "curator": "Куратор", "student": "Студент"}
FULL_ROLES = ("head", "deputy")

PERMS = {
    "journal":    ("Видеть журнал и статистику", "Журнал, живая сводка, прогулы, проценты по студентам, сводки после пар"),
    "attendance": ("Отмечать посещаемость", "Ставить и исправлять отметки, открывать код на доску"),
    "export":     ("Выгружать отчёты", "Excel для деканата"),
    "grades":     ("Вести успеваемость", "Загружать и править ведомость оценок, выгружать её"),
    "announce":   ("Публиковать объявления", "Рассылка всей группе, закрепление"),
    "schedule":   ("Редактировать расписание", "Пары, каникулы, сессии, импорт из Excel"),
    "homework":   ("Домашние задания", "Выдавать задания с дедлайнами, править и удалять их"),
    "changes":    ("Переносы и отмены пар", "Отменить или перенести пару, сменить аудиторию — группа получит уведомление"),
    "student_info": ("Изменять данные студентов", "ФИО, № студенческого, телефон, почта, дата рождения, контакты родителей, заметка"),
    "remove_students": ("Удалять лишних студентов", "Убирать из группы чужих и ошибочные записи — и запись, и доступ к боту"),
    "students":   ("Управлять списком студентов", "Добавлять, отчислять, отвязывать Telegram, удалять"),
    "invite":     ("Приглашать студентов", "Видеть код и ссылку-приглашение"),
    "files":      ("Модерировать базу знаний", "Удалять чужие файлы"),
    "settings":   ("Настройки группы", "Опросы, семестр, часовой пояс, перевыпуск ссылок"),
    "roles":      ("Назначать роли и права", "Управлять участниками и их правами"),
}
ALL = list(PERMS)
DEFAULTS = {
    "head": set(ALL),
    "deputy": set(ALL),
    "curator": {"journal", "export", "announce", "invite", "grades", "student_info", "remove_students", "changes", "homework"},
    "student": set(),
}


def is_super(member: dict | None) -> bool:
    return bool(member) and member.get("tg_id") in SUPER_IDS


def perms_of(member: dict | None) -> set[str]:
    if not member:
        return set()
    role = member.get("role")
    if role in FULL_ROLES or is_super(member):
        return set(ALL)
    raw = member.get("perms")
    if raw:
        try:
            return {p for p in json.loads(raw) if p in PERMS}
        except (ValueError, TypeError):
            pass
    return set(DEFAULTS.get(role, set()))


def can(member: dict | None, *perms: str) -> bool:
    """True, если есть хотя бы одно из перечисленных прав."""
    have = perms_of(member)
    return any(p in have for p in perms)


def is_staff(member: dict | None) -> bool:
    """Видит интерфейс управления (журнал/отметки), а не студенческий."""
    return can(member, "journal", "attendance")


def dump(perms: set[str] | list[str] | None) -> str | None:
    if perms is None:
        return None
    return json.dumps(sorted(p for p in perms if p in PERMS))


def catalog() -> list[dict]:
    return [{"key": k, "title": t, "hint": d} for k, (t, d) in PERMS.items()]
