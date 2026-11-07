"""Кто в сети: время последнего действия в боте / Mini App / приложении (видно старосте и куратору)."""
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

ONLINE_SEC = 150                    # «в сети», если был активен за последние 2,5 минуты (Mini App шлёт пинг раз в минуту)
_WRITE_EVERY = 30                   # не пишем в базу чаще, чем раз в 30 с на человека
_last: dict[int, float] = {}
_TZ = ZoneInfo(os.getenv("DEFAULT_TZ", "Asia/Vladivostok").strip() or "Asia/Vladivostok")


def touch(db, tg_id: int, via: str) -> None:
    now = time.time()
    if now - _last.get(tg_id, 0) < _WRITE_EVERY:
        return
    _last[tg_id] = now
    try:
        if not db.touch(tg_id, via, datetime.now(_TZ).date().isoformat(), int(now)):
            _last.pop(tg_id, None)          # ещё не в группе — запишем, как только вступит
    except Exception:  # noqa: BLE001 — статистика присутствия не должна ломать запросы
        pass
