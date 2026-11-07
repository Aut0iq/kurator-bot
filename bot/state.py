"""Кратковременные состояния диалога (ожидание файла, причины пропуска и т.п.).

Хранятся в памяти: после перезапуска бота просто сбрасываются — это не страшно.
"""
import time

_PENDING: dict[int, dict] = {}
TTL = 30 * 60


def set_pending(tg_id: int, kind: str, **data) -> None:
    _PENDING[tg_id] = {"kind": kind, "at": time.time(), **data}


def get_pending(tg_id: int, kind: str | None = None) -> dict | None:
    p = _PENDING.get(tg_id)
    if not p or time.time() - p["at"] > TTL or (kind and p["kind"] != kind):
        return None
    return p


def clear_pending(tg_id: int) -> None:
    _PENDING.pop(tg_id, None)
