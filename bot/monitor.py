"""Мониторинг сервера для главного куратора: нагрузка, память, диск, база, копии, службы, сайт, ошибки.

Снимок — snapshot() (экран «Ещё → Сервер» и команда /server).
Фоновая проверка — watch(): раз в минуту; при проблемах пишет главным кураторам (не чаще раза в 6 часов
на одну проблему) и сообщает, когда всё снова в порядке.
"""
import asyncio
import collections
import html
import logging
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import aiohttp

from perms import SUPER_IDS

ROOT = Path(__file__).resolve().parent.parent
STARTED = time.time()
log = logging.getLogger(__name__)

ERRORS: collections.deque = collections.deque(maxlen=30)


class ErrorTap(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.ERROR)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage().splitlines()[0][:300]
            if record.exc_info and record.exc_info[1] is not None:
                e = record.exc_info[1]
                msg += f" — {type(e).__name__}: {str(e)[:200]}"
            ERRORS.append({"at": int(record.created), "where": record.name, "text": msg})
        except Exception:
            pass


def install_error_tap() -> None:
    logging.getLogger().addHandler(ErrorTap())


def _read(path: str) -> str:
    try:
        return Path(path).read_text()
    except OSError:
        return ""


_cpu_prev: tuple[int, int] | None = None


def _cpu_times() -> tuple[int, int] | None:
    line = _read("/proc/stat").splitlines()[:1]
    if not line or not line[0].startswith("cpu "):
        return None
    v = [int(x) for x in line[0].split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return sum(v), idle


async def cpu_percent() -> float | None:
    """Загрузка процессора между двумя вызовами (первый раз — за 0,4 с)."""
    global _cpu_prev
    now = _cpu_times()
    if now is None:
        return None
    prev = _cpu_prev
    if prev is None:
        await asyncio.sleep(0.4)
        prev, now = now, _cpu_times()
    _cpu_prev = now
    total, idle = now[0] - prev[0], now[1] - prev[1]
    return round(100 * (1 - idle / total), 1) if total > 0 else 0.0


def meminfo() -> dict:
    vals = {}
    for line in _read("/proc/meminfo").splitlines():
        k, _, rest = line.partition(":")
        if rest.strip():
            vals[k] = int(rest.split()[0]) * 1024
    if not vals:
        return {}
    total, avail = vals.get("MemTotal", 0), vals.get("MemAvailable", vals.get("MemFree", 0))
    st, sf = vals.get("SwapTotal", 0), vals.get("SwapFree", 0)
    return {"total": total, "used": total - avail, "pct": round(100 * (total - avail) / total, 1) if total else 0,
            "swap_total": st, "swap_used": st - sf, "swap_pct": round(100 * (st - sf) / st, 1) if st else 0}


def process_info() -> dict:
    info = {"pid": os.getpid(), "uptime": int(time.time() - STARTED)}
    for line in _read("/proc/self/status").splitlines():
        if line.startswith("VmRSS:"):
            info["rss"] = int(line.split()[1]) * 1024
        elif line.startswith("Threads:"):
            info["threads"] = int(line.split()[1])
    return info


def services() -> list[dict]:
    """Состояние служб systemd, которые есть на сервере."""
    if not shutil.which("systemctl"):
        return []
    units = [("kurator", "Бот"), ("caddy", "Caddy (HTTPS)"), ("nginx", "nginx"),
             ("kurator-backup.timer", "Ночная копия базы"), ("kurator-domain.timer", "Ожидание домена")]
    out = []
    for unit, title in units:
        try:
            r = subprocess.run(["systemctl", "show", unit, "-p", "LoadState", "-p", "ActiveState", "-p", "SubState"],
                               capture_output=True, text=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            continue
        props = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)
        if props.get("LoadState") != "loaded":
            continue
        out.append({"unit": unit, "title": title, "state": props.get("ActiveState", "?"), "sub": props.get("SubState", "")})
    return out


def backups() -> dict:
    files = sorted((ROOT / "backups").glob("kurator-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {"count": 0}
    last = files[0]
    return {"count": len(files), "last_at": int(last.stat().st_mtime), "last_size": last.stat().st_size,
            "total": sum(f.stat().st_size for f in files)}


def db_info(db, db_path: str) -> dict:
    size = sum(Path(db_path + s).stat().st_size for s in ("", "-wal", "-shm") if Path(db_path + s).exists())
    count = lambda t: db.q1(f"SELECT COUNT(*) AS c FROM {t}")["c"]
    day = int(time.time()) - 86400
    active = db.q1("SELECT COUNT(DISTINCT tg_id) AS c FROM app_sessions WHERE last_used > ?", (day,))["c"]
    return {"size": size, "groups": count("groups"), "members": count("members"), "students": count("students"),
            "lessons": count("lessons"), "marks": count("attendance"), "files": count("files"),
            "app_sessions": count("app_sessions"), "app_active_day": active}


_net_cache: dict = {}


async def site_check(url: str) -> dict:
    if not url.startswith("http"):
        return {"ok": None, "url": url}
    hit = _net_cache.get("site")
    if hit and time.time() - hit["checked"] < 60:
        return hit
    t0 = time.perf_counter()
    res = {"url": url, "checked": int(time.time())}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(url + "/api/app-info", headers={"ngrok-skip-browser-warning": "1"}) as r:
                res.update(ok=r.status == 200, status=r.status)
    except Exception as e:
        res.update(ok=False, error=type(e).__name__ + (f": {e}" if str(e) else ""))
    res["ms"] = round((time.perf_counter() - t0) * 1000)
    _net_cache["site"] = res
    return res


async def telegram_check(bot) -> dict:
    if bot is None:
        return {"ok": None, "checked": int(time.time())}
    hit = _net_cache.get("tg")
    if hit and time.time() - hit["checked"] < 60:
        return hit
    t0 = time.perf_counter()
    res = {"checked": int(time.time())}
    try:
        await asyncio.wait_for(bot.get_me(), 8)
        res["ok"] = True
    except Exception as e:
        res.update(ok=False, error=type(e).__name__)
    res["ms"] = round((time.perf_counter() - t0) * 1000)
    _net_cache["tg"] = res
    return res


_usage_cache: dict = {}


def _usage(db) -> dict:
    """Статистика использования (пересчёт не чаще раза в минуту)."""
    hit = _usage_cache.get("v")
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    import features
    try:
        v = features.usage(db)
    except Exception:
        logging.getLogger(__name__).exception("usage")
        v = None
    _usage_cache["v"] = (time.time(), v)
    return v


async def snapshot(db, bot, db_path: str) -> dict:
    url = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
    try:
        load = [round(x, 2) for x in os.getloadavg()]
    except (OSError, AttributeError):
        load = None
    disk = shutil.disk_usage(ROOT)
    up = _read("/proc/uptime").split()
    site, tg = await asyncio.gather(site_check(url), telegram_check(bot))
    snap = {
        "now": int(time.time()),
        "host": {"name": socket.gethostname(), "os": f"{platform.system()} {platform.release()}",
                 "python": sys.version.split()[0], "uptime": int(float(up[0])) if up else None},
        "cpu": {"count": os.cpu_count() or 1, "pct": await cpu_percent(), "load": load},
        "mem": meminfo(),
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free, "pct": round(100 * disk.used / disk.total, 1)},
        "proc": process_info(),
        "db": db_info(db, db_path),
        "backups": backups(),
        "usage": _usage(db),
        "services": await asyncio.to_thread(services),
        "site": site, "telegram": tg,
        "errors": list(ERRORS)[-10:][::-1],
        "errors_hour": sum(1 for e in ERRORS if e["at"] > time.time() - 3600),
    }
    snap["problems"] = problems(snap)
    return snap


def problems(s: dict) -> list[dict]:
    """Список проблем: key — для антиспама уведомлений, level — warn / crit."""
    p = []
    if s["disk"]["pct"] >= 95:
        p.append({"key": "disk", "level": "crit", "text": f"Диск почти заполнен: {s['disk']['pct']}%"})
    elif s["disk"]["pct"] >= 85:
        p.append({"key": "disk", "level": "warn", "text": f"Диск заполнен на {s['disk']['pct']}%"})
    mem = s.get("mem") or {}
    if mem.get("pct", 0) >= 92:
        p.append({"key": "mem", "level": "crit" if mem["pct"] >= 97 else "warn", "text": f"Мало памяти: занято {mem['pct']}%"})
    load, cpus = s["cpu"].get("load"), s["cpu"]["count"]
    if load and load[1] > cpus * 1.5:
        p.append({"key": "load", "level": "warn", "text": f"Высокая нагрузка: {load[1]} при {cpus} ядрах"})
    if s["site"].get("ok") is False:
        p.append({"key": "site", "level": "crit", "text": f"Mini App не открывается: {s['site'].get('status') or str(s['site'].get('error', ''))[:80]}"})
    if s["telegram"].get("ok") is False:
        p.append({"key": "tg", "level": "crit", "text": "Нет связи с Telegram"})
    for sv in s["services"]:
        if sv["unit"] in ("caddy", "nginx") and sv["state"] != "active":
            p.append({"key": "svc:" + sv["unit"], "level": "crit", "text": f"Служба {sv['title']} не работает ({sv['state']})"})
    b = s["backups"]
    if b.get("count") and s["now"] - b["last_at"] > 36 * 3600:
        p.append({"key": "backup", "level": "warn", "text": "Резервной копии базы не было больше суток"})
    if s["errors_hour"] >= 10:
        p.append({"key": "errors", "level": "warn", "text": f"Много ошибок в логах: {s['errors_hour']} за час"})
    return p


def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "—"
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if n < 1024 or unit == "ТБ":
            return (f"{n:.0f}" if unit in ("Б", "КБ") else f"{n:.1f}".replace(".", ",")) + " " + unit
        n /= 1024
    return str(n)


def fmt_dur(sec: int | None) -> str:
    if sec is None:
        return "—"
    d, rem = divmod(int(sec), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return f"{d} дн {h} ч" if d else (f"{h} ч {m} мин" if h else f"{m} мин")


def text_report(s: dict) -> str:
    st = "✅ Всё работает" if not s["problems"] else "\n".join(("🔴 " if p["level"] == "crit" else "🟡 ") + html.escape(p["text"]) for p in s["problems"])
    mem, cpu, disk = s.get("mem") or {}, s["cpu"], s["disk"]
    lines = [
        f"🖥 <b>Сервер {s['host']['name']}</b>", st, "",
        f"Процессор: {cpu['pct'] if cpu['pct'] is not None else '—'}% · {cpu['count']} ядер" + (f" · нагрузка {', '.join(map(str, cpu['load']))}" if cpu["load"] else ""),
        f"Память: {fmt_bytes(mem.get('used'))} из {fmt_bytes(mem.get('total'))} ({mem.get('pct', '—')}%)",
        f"Диск: {fmt_bytes(disk['used'])} из {fmt_bytes(disk['total'])} ({disk['pct']}%)",
        f"Сервер работает: {fmt_dur(s['host']['uptime'])} · бот: {fmt_dur(s['proc']['uptime'])} ({fmt_bytes(s['proc'].get('rss'))})",
        "",
        f"Mini App: {'✅' if s['site'].get('ok') else '❌' if s['site'].get('ok') is False else '—'} {s['site'].get('ms', '')} мс · "
        f"Telegram: {'✅' if s['telegram'].get('ok') else '❌' if s['telegram'].get('ok') is False else '—'} {s['telegram'].get('ms', '')} мс",
        f"База: {fmt_bytes(s['db']['size'])} · групп {s['db']['groups']} · участников {s['db']['members']} · студентов {s['db']['students']}",
    ]
    b = s["backups"]
    lines.append(f"Копии базы: {b['count']}, последняя {time.strftime('%d.%m %H:%M', time.localtime(b['last_at']))}" if b.get("count") else "Копий базы пока нет")
    if s["errors"]:
        lines.append(f"Ошибок за час: {s['errors_hour']}")
    return "\n".join(lines)


async def watch(db, bot, db_path: str) -> None:
    from services import safe_send
    sent: dict[str, float] = {}
    await asyncio.sleep(90)
    while True:
        try:
            s = await snapshot(db, bot, db_path)
            now = time.time()
            keys = set()
            for p in s["problems"]:
                keys.add(p["key"])
                if now - sent.get(p["key"], 0) > 6 * 3600:
                    sent[p["key"]] = now
                    icon = "🔴" if p["level"] == "crit" else "🟡"
                    for uid in SUPER_IDS:
                        await safe_send(bot, uid, f"{icon} <b>Сервер:</b> {html.escape(p['text'])}\n\nПодробнее: /server")
            for k in [k for k in sent if k not in keys]:
                del sent[k]
                for uid in SUPER_IDS:
                    await safe_send(bot, uid, "✅ <b>Сервер:</b> проблема решилась — " + {
                        "disk": "место на диске", "mem": "память", "load": "нагрузка", "site": "Mini App снова открывается",
                        "tg": "связь с Telegram", "backup": "резервная копия", "errors": "ошибки в логах"}.get(
                        k, "служба " + k[4:] + " снова работает" if k.startswith("svc:") else k))
        except Exception:
            log.warning("monitor tick failed", exc_info=True)
        await asyncio.sleep(60)
