"""HTTP API для Mini App + раздача статики webapp/."""
import logging
import os
import time
import re
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from aiohttp import web
from aiogram import Bot
from aiogram.types import BufferedInputFile

import grades
import demo
import features
from features import FeaturesMixin, push_on, short_name, ST_WORD, dm
import legal
import passwords
import presence
import monitor
import polls
import services
from db import DB, STATUSES
from excel import schedule_template
from logic import (DATE_RE, TIME_RE, build_stats, by_subject, check_init_data, day_period, display_name, now_in,
                   parse_date, semester_range, today_in, truancy, validate_lesson, week_number)
from perms import SUPER_IDS, ALL, DEFAULTS, FULL_ROLES, PERMS, ROLES, can, catalog, dump, is_staff, is_super, perms_of
from state import set_pending

log = logging.getLogger(__name__)
WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"


@web.middleware
async def error_mw(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPException as e:
        if not request.path.startswith("/api/"):
            raise
        extra = {"locked": True} if e.status == 423 else {}
        if e.status == 426:
            extra = {"update": True}
        return web.json_response({"error": e.reason, **extra}, status=e.status)
    except ValueError as e:
        return web.json_response({"error": str(e) or "Неверные данные"}, status=400)
    except (KeyError, TypeError):
        log.exception("bad request")
        return web.json_response({"error": "Неверные данные запроса"}, status=400)
    except Exception:  # noqa: BLE001
        log.exception("API error")
        return web.json_response({"error": "Внутренняя ошибка сервера"}, status=500)


def ok(**data) -> web.Response:
    return web.json_response({"ok": True, **data})


def fail(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


def to_min(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


_GZ: dict[str, tuple[float, bytes, bytes, str]] = {}       # путь → (mtime, исходник, gzip, etag)
_TYPES = {".js": "application/javascript", ".css": "text/css", ".html": "text/html", ".svg": "image/svg+xml",
          ".json": "application/json", ".webp": "image/webp", ".png": "image/png", ".ico": "image/x-icon", ".txt": "text/plain"}


def static_response(request, path: Path, cache: str) -> web.Response:
    """Файл из webapp/: текст сжимается gzip один раз и держится в памяти, повторные запросы — 304."""
    import gzip
    import hashlib
    st = path.stat()
    hit = _GZ.get(str(path))
    if not hit or hit[0] != st.st_mtime:
        raw = path.read_bytes()
        ctype = _TYPES.get(path.suffix.lower(), "application/octet-stream")
        packed = gzip.compress(raw, 6) if ctype.startswith(("text/", "application/javascript", "application/json", "image/svg")) else b""
        hit = (st.st_mtime, raw, packed, '"' + hashlib.md5(raw).hexdigest()[:16] + '"')
        _GZ[str(path)] = hit
    _, raw, packed, etag = hit
    ctype = _TYPES.get(path.suffix.lower(), "application/octet-stream")
    headers = {"Cache-Control": cache, "ETag": etag, "Vary": "Accept-Encoding"}
    if request.headers.get("If-None-Match") == etag:
        return web.Response(status=304, headers=headers)
    if packed and "gzip" in request.headers.get("Accept-Encoding", ""):
        headers["Content-Encoding"] = "gzip"
        return web.Response(body=packed, headers=headers, content_type=ctype, charset="utf-8" if not ctype.startswith("image") else None)
    return web.Response(body=raw, headers=headers, content_type=ctype,
                        charset="utf-8" if ctype.startswith(("text/", "application/javascript", "application/json")) else None)


def apk_path():
    """Собранный на сервере dist/kurator.apk, иначе готовый android/kurator.apk из проекта."""
    root = WEBAPP_DIR.parent
    built = root / "dist" / "kurator.apk"
    return built if built.exists() else root / "android" / "kurator.apk"


WD_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
DEFAULT_LOCK_TEXT = "Сервис временно закрыт. Попробуйте позже."


class Locked(web.HTTPClientError):
    """423 — доступ закрыт главным куратором."""
    status_code = 423
    status = 423


class NeedUpdate(web.HTTPClientError):
    """426 — старая версия Android-приложения: до обновления только экран «Обновите приложение»."""
    status_code = 426
    status = 426


def apk_meta() -> dict:
    """Сведения о последней версии APK (файл kurator.json рядом с kurator.apk)."""
    import json
    p = apk_path().with_suffix(".json")
    try:
        meta = json.loads(p.read_text(encoding="utf-8")) if p.exists() and apk_path().exists() else {}
    except (OSError, ValueError):
        meta = {}
    return meta


def app_version(request) -> tuple[bool, int, str]:
    """(это наше Android-приложение?, код версии, название версии) по заголовку User-Agent."""
    ua = request.headers.get("User-Agent", "")
    m = re.search(r"KuratorApp/([\w.]+)", ua)
    if not m:
        return False, 0, ""
    code = re.search(r"code (\d+)", ua)
    return True, int(code.group(1)) if code else 0, m.group(1)     # старые версии не сообщали код → 0


class Api(FeaturesMixin, features.ParentMixin):
    def __init__(self, db: DB, bot: Bot, token: str, default_tz: str, bot_username: str):
        self.db, self.bot, self.token, self.default_tz = db, bot, token, default_tz
        self.bot_username = bot_username

    # ---------- авторизация
    def user(self, request: web.Request) -> dict:
        """Пользователь запроса; если главный куратор закрыл доступ — пускаем только его."""
        u = self.auth_user(request)
        if demo.is_demo(u["id"]) and request.method != "GET" and request.path not in ("/api/consent", "/api/applogin/logout"):
            raise web.HTTPForbidden(reason="Демо-режим: изменения не сохраняются 🙂")
        is_app, code, _ = app_version(request)
        if is_app:
            meta = apk_meta()
            if meta.get("min_code") and code < int(meta["min_code"]):
                raise NeedUpdate(f"Вышла новая версия приложения {meta.get('version_name', '')}. Обновите, чтобы продолжить.")
        presence.touch(self.db, u["id"], "app" if u.get("via") == "app" else "tg")
        lock = self.db.lock()
        if lock and u["id"] not in SUPER_IDS:
            raise Locked(lock.get("text") or DEFAULT_LOCK_TEXT)
        return u

    def auth_user(self, request: web.Request) -> dict:
        """Пользователь из Telegram Mini App (подпись initData) или из приложения (токен сессии)."""
        init = request.headers.get("X-Init-Data", "")
        if init:
            user = check_init_data(init, self.token)
            if user and "id" in user:
                return user
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and len(auth) > 20:
            s = self.db.app_session(auth[7:].strip())
            if s:
                return {"id": s["tg_id"], "first_name": s["first_name"] or "", "last_name": s["last_name"],
                        "username": s["username"], "via": "app"}
        raise web.HTTPUnauthorized(reason="Войдите через Telegram")

    # ---------- вход в приложение (Android / браузер)
    async def applogin_start(self, request):
        code = self.db.app_login_start()
        return ok(code=code, bot=self.bot_username, link=f"https://t.me/{self.bot_username}?start=applogin_{code}",
                  tg_link=f"tg://resolve?domain={self.bot_username}&start=applogin_{code}")

    async def applogin_status(self, request):
        code = request.query.get("code", "")
        r = self.db.app_login(code)
        if not r:
            return web.json_response({"status": "expired"})
        token = self.db.app_login_take(code)
        return web.json_response({"status": "ok", "token": token} if token else {"status": "pending"})

    async def app_logout(self, request):
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            self.db.app_logout(auth[7:].strip())
        return ok()

    async def app_info(self, request):
        apk = apk_path()
        info = {"apk": apk.exists()}
        if apk.exists():
            meta = apk_meta()
            info.update(size=apk.stat().st_size, updated=int(apk.stat().st_mtime), url=f"/app.apk?v={meta.get('version_code', int(apk.stat().st_mtime))}",
                        version_code=meta.get("version_code"), version_name=meta.get("version_name"),
                        min_code=meta.get("min_code"), notes=meta.get("notes") or [])
        # соцсети для стартовой страницы: SOCIAL_TELEGRAM=https://t.me/… SOCIAL_VK=… SOCIAL_YOUTUBE=… SOCIAL_RUTUBE=… SOCIAL_TIKTOK=… в .env
        info["social"] = [{"key": k, "url": v} for k in ("telegram", "vk", "youtube", "rutube", "tiktok", "dzen", "site")
                          if (v := os.getenv("SOCIAL_" + k.upper(), "").strip()).startswith(("https://", "http://", "tg://"))]
        is_app, code, name = app_version(request)
        if is_app:
            info["installed"] = {"code": code, "name": name}
            info["update_available"] = bool(info.get("version_code") and code < int(info["version_code"]))
            info["update_required"] = bool(info.get("min_code") and code < int(info["min_code"]))
        return web.json_response(info)

    async def apk(self, request):
        apk = apk_path()
        if not apk.exists():
            raise web.HTTPNotFound(reason="Приложение ещё не собрано")
        return web.FileResponse(apk, headers={"Content-Type": "application/vnd.android.package-archive",
                                              "Content-Disposition": 'attachment; filename="kurator.apk"'})

    def member(self, request: web.Request, *perms: str) -> dict:
        """Текущий участник. Если переданы права — нужно хотя бы одно из них."""
        m = self.db.member(self.user(request)["id"])
        if not m:
            raise web.HTTPForbidden(reason="Вы не состоите в группе")
        if perms and not can(m, *perms):
            raise web.HTTPForbidden(reason="Недостаточно прав")
        return m

    def invite_link(self, g: dict) -> str:
        return f"https://t.me/{self.bot_username}?start=join_{g['invite_code']}"

    def staff_link(self, g: dict) -> str:
        return f"https://t.me/{self.bot_username}?start=staff_{g['staff_code']}"

    def ctx(self, m: dict):
        g = self.db.group(m["group_id"])
        return g, today_in(g["tz"])

    # ---------- профиль
    async def me(self, request):
        user = self.user(request)
        consent = self.db.consent_of(user["id"]) == legal.VERSION
        if passwords.is_parent(user["id"]):                    # родитель: только просмотр данных ребёнка
            st = self.db.q1("SELECT * FROM students WHERE id=?", (passwords.parent_student(user["id"]),))
            g = self.db.group(st["group_id"]) if st else None
            return web.json_response({"user": user, "member": None, "consent": consent, "bot": self.bot_username,
                                      "parent": {"student": st["full_name"], "group": g["name"]} if st and g else None})
        m = self.db.member(user["id"])
        if not m:
            return web.json_response({"user": user, "member": None, "consent": consent, "bot": self.bot_username})
        g, today = self.ctx(m)
        my = perms_of(m)
        group = dict(g)
        group["invite_link"] = self.invite_link(g) if "invite" in my else None
        if "invite" not in my:
            group.pop("invite_code", None)
        if "roles" in my:
            group["staff_link"] = self.staff_link(g)
        else:
            group.pop("staff_code", None)
        students = self.db.students(g["id"])
        resp = {
            "user": user, "member": m, "student": self.db.student_by_tg(user["id"]), "group": group,
            "perms": sorted(my), "role_name": ("Главный куратор" if is_super(m) else ROLES.get(m["role"], m["role"])),
            "super": is_super(m), "via": user.get("via", "telegram"), "consent": consent, "lock": self.db.lock() if user["id"] in SUPER_IDS else None, "demo": demo.is_demo(user["id"]),
            "no_telegram": passwords.is_synthetic(user["id"]),
            "has_password": bool(self.db.student_auth((self.db.student_by_tg(user["id"]) or {}).get("id") or 0).get("pass_hash")), "consent_at": (self.db.q1("SELECT at FROM consents WHERE tg_id=?", (user["id"],)) or {}).get("at"),
            "push": push_on(m),
            "staff_login": ({"login": (sa := self.db.staff_auth(user["id"])).get("login"), "has_password": bool(sa.get("pass_hash"))}
                            if self._is_staff_role(m) and not passwords.is_synthetic(user["id"]) and not demo.is_demo(user["id"]) else None),
            "today": today.isoformat(), "week": week_number(g, today), "bot": self.bot_username,
            "period": day_period(self.db.periods(g["id"]), today),
            "subjects": self.db.subjects(g["id"]),
        }
        if is_staff(m):
            resp["onboarding"] = {
                "students": len(students), "linked": sum(1 for s in students if s["tg_id"]),
                "lessons": len(self.db.lessons(g["id"], include_oneoff=False)),
                "polls": bool(self.db.q1("SELECT 1 AS x FROM attendance a JOIN lessons l ON l.id=a.lesson_id "
                                         "WHERE l.group_id=? LIMIT 1", (g["id"],))),
                "semester": bool(g["semester_start"]),
            }
        return web.json_response(resp)

    async def create_group(self, request):
        user = self.user(request)
        if self.db.member(user["id"]):
            return fail(400, "Вы уже состоите в группе. Сначала выйдите из неё.")
        data = await request.json()
        name = str(data.get("name", "")).strip()[:80]
        if not name:
            return fail(400, "Введите название группы")
        role = "curator" if data.get("role") == "curator" else "head"
        # куратор, создавший группу, получает все права (иначе некому будет её настроить)
        g = self.db.create_group(name, self.default_tz, user["id"], display_name(user), user.get("username"),
                                 role, dump(ALL) if role == "curator" else None)
        return ok(group=g)

    async def join(self, request):
        user = self.user(request)
        data = await request.json()
        code = str(data.get("code", "")).replace("join_", "").replace("staff_", "").strip()
        g, role = self.db.group_by_code(code), "student"
        if not g:
            g, role = self.db.group_by_staff_code(code), "curator"
        if not g:
            return fail(404, "Код группы не найден")
        cur = self.db.member(user["id"])
        if cur and cur["group_id"] != g["id"]:
            return fail(400, "Вы уже в другой группе. Сначала выйдите из неё.")
        if not cur:
            self.db.add_member(user["id"], g["id"], role, display_name(user), user.get("username"))
        return ok(group=g["name"], role=(self.db.member(user["id"]) or {}).get("role", role))

    async def register(self, request):
        """Студент вписывает своё ФИО (или привязывается к уже внесённому)."""
        m = self.member(request)
        data = await request.json()
        name = " ".join(str(data.get("full_name", "")).split())
        if len(name) < 3 or len(name.split()) < 2:
            return fail(400, "Введите фамилию и имя полностью")
        res = self.db.add_self_student(m["group_id"], name, m["tg_id"], force_new=bool(data.get("new")))
        if "choose" in res:
            return ok(choose=res["choose"])
        return ok(student_id=res["id"], matched=res["matched"], name=res["name"])

    # ---------- вход по номеру студенческого и паролю
    async def pw_login(self, request):
        data = await request.json()
        ident = str(data.get("login") or data.get("record_no") or "").strip()
        rec, pw = passwords.norm_record(ident), str(data.get("password") or "")
        if not rec or not pw:
            return fail(400, "Введите номер студенческого (или логин) и пароль")
        wait = passwords.locked("pw:" + rec)
        if wait:
            return fail(429, f"Слишком много попыток. Подождите {max(1, wait // 60)} мин.")
        token = self._staff_login_try(ident.lower(), pw)            # логин старосты / куратора
        if token:
            passwords.success("pw:" + rec)
            return ok(token=token)
        cands = self.db.students_by_record(rec)
        with_pw = [(st, self.db.student_auth(st["id"])) for st in cands]
        with_pw = [(st, a) for st, a in with_pw if a.get("pass_hash")]
        for st, a in with_pw:
            if passwords.check_secret(pw, a["pass_hash"]):
                passwords.success("pw:" + rec)
                uid = self.db.account_for_student(st)
                return ok(token=self.db.new_app_session(uid, st["full_name"].split()[1] if len(st["full_name"].split()) > 1 else st["full_name"]))
        passwords.fail("pw:" + rec)
        if cands and not with_pw:
            return fail(401, "Пароль ещё не задан. Получите код у старосты или куратора и нажмите «Первый вход или забыли пароль»")
        return fail(401, "Неверный номер студенческого (логин) или пароль")

    async def pw_set(self, request):
        """Первый вход и восстановление: номер + одноразовый код от старосты/куратора + новый пароль."""
        data = await request.json()
        ident = str(data.get("login") or data.get("record_no") or "").strip()
        rec, code, pw = passwords.norm_record(ident), str(data.get("code") or "").strip(), str(data.get("password") or "")
        if not rec or not code:
            return fail(400, "Введите номер студенческого (или логин) и код")
        wait = passwords.locked("code:" + rec)
        if wait:
            return fail(429, f"Слишком много попыток. Подождите {max(1, wait // 60)} мин.")
        staff = self._staff_code_set(ident.lower(), code, pw)        # логин старосты / куратора
        if staff is not None:
            if staff.status == 401:
                passwords.fail("code:" + rec)
            elif staff.status == 200:
                passwords.success("code:" + rec)
            return staff
        now = int(time.time())
        target = None
        for st in self.db.students_by_record(rec):
            a = self.db.student_auth(st["id"])
            if not a.get("code_hash") or (a.get("code_expires") or 0) < now or a.get("code_tries", 0) >= passwords.CODE_TRIES:
                continue
            if passwords.check_secret(code, a["code_hash"]):
                target = st
                break
            self.db.code_try(st["id"])
        if not target:
            passwords.fail("code:" + rec)
            return fail(401, "Код неверный или устарел. Попросите у старосты или куратора новый")
        problem = passwords.password_problem(pw, target["record_no"])
        if problem:
            return fail(400, problem)
        passwords.success("code:" + rec)
        self.db.set_password(target["id"], passwords.hash_secret(pw))
        uid = self.db.account_for_student(target)
        self.db.x("DELETE FROM app_sessions WHERE tg_id=? AND device='password'", (uid,))   # старые входы по паролю — выйти
        return ok(token=self.db.new_app_session(uid, target["full_name"].split()[1] if len(target["full_name"].split()) > 1 else target["full_name"]))

    async def login_code(self, request):
        m = self.member(request, "student_info", "students")
        st = self.db.student(m["group_id"], int(request.match_info["sid"]))
        if not st:
            raise web.HTTPNotFound(reason="Студент не найден")
        if not passwords.norm_record(st.get("record_no")):
            return fail(400, "Сначала укажите номер студенческого в карточке студента")
        others = [x for x in self.db.students_by_record(passwords.norm_record(st["record_no"])) if x["id"] != st["id"]]
        if others:
            return fail(400, "Такой номер студенческого уже есть у другого студента — проверьте номер")
        code = passwords.new_code()
        expires = int(time.time()) + passwords.CODE_TTL
        self.db.set_login_code(st["id"], passwords.hash_secret(code), expires, m["tg_id"])
        self.audit(m, "code", f"Код входа по номеру студенческого выдан · {st['full_name']}", [st["id"]])
        return ok(code=code, expires=expires, record_no=st["record_no"], has_password=bool(self.db.student_auth(st["id"]).get("pass_hash")))

    async def change_password(self, request):
        user = self.user(request)
        st = self.db.student_by_tg(user["id"])
        if not st:
            raise web.HTTPForbidden(reason="Только для студентов")
        data = await request.json()
        a = self.db.student_auth(st["id"])
        if not a.get("pass_hash"):
            # пароля ещё нет: вошедший через Telegram студент уже подтвердил, кто он, — код от старосты не нужен
            if passwords.is_synthetic(user["id"]):
                raise web.HTTPForbidden(reason="Получите код у старосты или куратора")
            if not passwords.norm_record(st.get("record_no")):
                return fail(400, "У вас не указан номер студенческого — попросите старосту или куратора внести его в вашу карточку")
            if [x for x in self.db.students_by_record(passwords.norm_record(st["record_no"])) if x["id"] != st["id"]]:
                return fail(400, "Такой номер студенческого есть у другого студента — попросите старосту проверить номер")
        elif not passwords.check_secret(str(data.get("old") or ""), a["pass_hash"]):
            return fail(400, "Текущий пароль указан неверно")
        problem = passwords.password_problem(str(data.get("new") or ""), st.get("record_no") or "")
        if problem:
            return fail(400, problem)
        self.db.set_password(st["id"], passwords.hash_secret(str(data["new"])))
        return ok()

    async def demo_start(self, request):
        try:
            data = await request.json()
        except Exception:
            data = {}
        token = demo.start(self.db, "student" if data.get("role") == "student" else "head")
        return ok(token=token)

    async def consent(self, request):
        user = self.user(request)
        data = await request.json()
        if not (data.get("pd") and data.get("terms")):
            return fail(400, "Нужно отметить оба пункта")
        self.db.set_consent(user["id"], legal.VERSION, "app" if user.get("via") == "app" else "telegram")
        return ok()

    async def lock_get(self, request):
        if self.auth_user(request)["id"] not in SUPER_IDS:
            raise web.HTTPForbidden(reason="Только для главного куратора")
        return ok(lock=self.db.setting("lock", {"on": False}), users=len(self.db.all_member_ids()))

    async def lock_set(self, request):
        user = self.auth_user(request)
        if user["id"] not in SUPER_IDS:
            raise web.HTTPForbidden(reason="Только для главного куратора")
        data = await request.json()
        on = bool(data.get("on"))
        text = " ".join(str(data.get("text") or "").split())[:300]
        await services.set_lock(self.db, self.bot, on, text, bool(data.get("notify")), user["id"])
        self.audit(self._super_member(user), "lock", ("Доступ закрыт для всех" + (f": «{text}»" if text else "")) if on else "Доступ открыт", gid=None)
        return ok(lock=self.db.setting("lock"))

    async def server(self, request):
        user = self.user(request)
        if user["id"] not in SUPER_IDS:
            raise web.HTTPForbidden(reason="Только для главного куратора")
        return web.json_response(await monitor.snapshot(self.db, self.bot, self.db.path))

    async def legal_page(self, request):
        name = request.match_info["name"]
        if name not in legal.DOCS:
            raise web.HTTPNotFound()
        site = os.getenv("WEBAPP_URL", "").strip().rstrip("/") or \
            f"{request.headers.get('X-Forwarded-Proto', request.scheme)}://{request.host}"
        return web.Response(text=legal.render(name, site, self.bot_username), content_type="text/html",
                            headers={"Cache-Control": "no-cache"})

    async def leave(self, request):
        m = self.member(request)
        try:
            data = await request.json()
        except Exception:
            data = {}
        others = [x for x in self.db.members(m["group_id"]) if x["tg_id"] != m["tg_id"]]
        if not others:                                    # в группе никого больше нет
            if data.get("delete_group"):
                self.db.delete_group(m["group_id"])
                return ok(deleted=True)
            return fail(409, "Вы один в группе — её можно только удалить")
        if m["role"] == "head" and sum(1 for x in self.db.members(m["group_id"]) if x["role"] == "head") == 1 \
                and not any(is_super(x) for x in self.db.members(m["group_id"])):
            return fail(400, "Вы единственный староста — сначала назначьте другого")
        self.db.leave(m["tg_id"])
        return ok()

    async def reminders(self, request):
        m = self.member(request)
        self.db.set_reminders(m["tg_id"], bool((await request.json()).get("on")))
        return ok()

    # ---------- группа
    async def update_group(self, request):
        m = self.member(request, "settings")
        data = await request.json()
        f = {}
        if data.get("name"):
            f["name"] = str(data["name"]).strip()[:80]
        for k in ("semester_start", "semester_end"):
            if k in data:
                f[k] = parse_date(data[k]).isoformat() if data[k] else None
        for k, lo, hi in (("remind_minutes", 0, 180), ("summary_minutes", 1, 90), ("truancy_limit", 1, 50)):
            if k in data:
                v = int(data[k])
                if not lo <= v <= hi:
                    return fail(400, f"Значение должно быть от {lo} до {hi}")
                f[k] = v
        if "polls_enabled" in data:
            f["polls_enabled"] = 1 if data["polls_enabled"] else 0
        if "tz" in data:
            ZoneInfo(str(data["tz"]))
            f["tz"] = str(data["tz"])
        if f.get("semester_start") and f.get("semester_end") and f["semester_start"] > f["semester_end"]:
            return fail(400, "Начало семестра позже конца")
        g0 = self.db.group(m["group_id"])
        self.db.update_group(m["group_id"], **f)
        names = {"name": "название", "semester_start": "начало семестра", "semester_end": "конец семестра", "remind_minutes": "время опроса",
                 "summary_minutes": "время сводки", "truancy_limit": "порог прогулов", "polls_enabled": "опросы", "tz": "часовой пояс"}
        changed = [names.get(k, k) for k, v in f.items() if g0.get(k) != v]
        if changed:
            self.audit(m, "settings", "Настройки группы · " + ", ".join(changed))
        return ok()

    async def new_invite(self, request):
        staff = bool((await request.json()).get("staff"))
        m = self.member(request, "roles" if staff else "settings")
        self.db.regenerate_invite(m["group_id"], staff)
        g = self.db.group(m["group_id"])
        return ok(invite_link=self.invite_link(g), invite_code=g["invite_code"],
                  staff_link=self.staff_link(g) if can(m, "roles") else None)

    # ---------- участники, роли и права
    async def members(self, request):
        m = self.member(request, "roles")
        rows = self.db.members(m["group_id"])
        for r in rows:
            r["perms_list"] = sorted(perms_of(r))
            r["super"] = is_super(r)
            r["custom"] = r["perms"] is not None and r["role"] not in FULL_ROLES and not r["super"]
            r["role_name"] = "Главный куратор" if r["super"] else ROLES.get(r["role"], r["role"])
        return web.json_response({"members": rows, "catalog": catalog(),
                                  "defaults": {k: sorted(v) for k, v in DEFAULTS.items()}})

    def _who(self, member: dict) -> str:
        st = self.db.student_by_tg(member["tg_id"])
        return (st or {}).get("full_name") or member.get("full_name") or str(member["tg_id"])

    def _target(self, m: dict, tg_id: int) -> dict:
        target = self.db.member(tg_id)
        if not target or target["group_id"] != m["group_id"]:
            raise web.HTTPNotFound(reason="Участник не найден")
        if tg_id == m["tg_id"]:
            raise web.HTTPBadRequest(reason="Свою роль и права изменить нельзя")
        if is_super(target):
            raise web.HTTPForbidden(reason="Главного куратора изменить или удалить нельзя")
        if target["role"] == "head" and m["role"] != "head" and not is_super(m):
            raise web.HTTPForbidden(reason="Роль старосты может изменить только староста")
        return target

    async def set_role(self, request):
        m = self.member(request, "roles")
        data = await request.json()
        tg_id, role = int(data["tg_id"]), data.get("role")
        if role not in ROLES:
            return fail(400, "Неизвестная роль")
        if role == "head" and m["role"] != "head" and not is_super(m):
            return fail(403, "Назначить старосту может только староста или главный куратор")
        t = self._target(m, tg_id)
        self.db.set_role(m["group_id"], tg_id, role)
        if t["role"] != role:
            self.audit(m, "role", f"Роль · {self._who(t)}: {ROLES.get(t['role'], t['role']).lower()} → {ROLES[role].lower()}",
                       [s["id"]] if (s := self.db.student_by_tg(tg_id)) else None)
        return ok()

    async def set_perms(self, request):
        m = self.member(request, "roles")
        data = await request.json()
        target = self._target(m, int(data["tg_id"]))
        if target["role"] in FULL_ROLES:
            return fail(400, f"У роли «{ROLES[target['role']]}» всегда все права")
        before = perms_of(target)
        if data.get("reset"):
            self.db.set_perms(m["group_id"], target["tg_id"], None)
        else:
            perms = [p for p in (data.get("perms") or []) if p in ALL]
            self.db.set_perms(m["group_id"], target["tg_id"], dump(perms))
        after = perms_of(self.db.member(target["tg_id"]))
        diff = [f"+{PERMS[p][0].lower()}" for p in ALL if p in after - before] + [f"−{PERMS[p][0].lower()}" for p in ALL if p in before - after]
        if diff:
            self.audit(m, "perms", f"Права · {self._who(target)}: " + "; ".join(diff))
        return ok(perms=sorted(perms_of(self.db.member(target["tg_id"]))))

    async def kick(self, request):
        m = self.member(request, "roles")
        t = self._target(m, int(request.match_info["tg_id"]))
        who = self._who(t)
        self.db.leave(int(request.match_info["tg_id"]))
        self.audit(m, "delete", f"Исключён из группы · {who}")
        return ok()

    # ---------- студенты
    async def students(self, request):
        m = self.member(request)
        rows = self.db.students(m["group_id"], include_archived=request.query.get("archived") == "1")
        if not can(m, "students", "student_info", "remove_students", "journal", "attendance"):
            rows = [{"id": s["id"], "full_name": s["full_name"], "linked": bool(s["tg_id"]),
                     "me": s["tg_id"] == m["tg_id"]} for s in rows]
            return web.json_response({"students": rows})
        # отметка «есть в последней ведомости» — чтобы видеть лишних
        months = self.db.grade_months(m["group_id"])
        in_grades = set()
        if months:
            gm = self.db.grade_month(m["group_id"], months[0]["month"])
            in_grades = set(self.db.grade_rows(gm["id"]))
        import names
        auth = self.db.auth_flags(m["group_id"])
        pauth = self.db.parent_flags(m["group_id"])
        for s in rows:
            s["auth"] = auth.get(s["id"], {"password": False, "code_until": None})
            s["parent_auth"] = pauth.get(s["id"], {"password": False, "code_until": None})
            s["in_grades"] = s["id"] in in_grades if months else None
            s["dupes"] = [o["id"] for o in rows if o["id"] != s["id"] and names.same_person(s["full_name"], o["full_name"])]
        return web.json_response({"students": rows, "grades_month": months[0]["month"] if months else None})

    async def add_students(self, request):
        m = self.member(request, "students")
        names = [n for n in str((await request.json()).get("names", "")).splitlines() if n.strip()]
        if not names:
            return fail(400, "Введите хотя бы одно ФИО")
        n = self.db.add_students(m["group_id"], names[:300])
        if n:
            self.audit(m, "student", f"Добавлено студентов: {n}")
        return ok(added=n)

    INFO_FIELDS = {"full_name": 120, "record_no": 30, "phone": 30, "email": 80, "birth_date": 10,
                   "parent_name": 120, "parent_phone": 30, "note": 300}

    async def update_student(self, request):
        """Данные студента — право student_info (или students); отчисление и отвязка — только students."""
        m = self.member(request, "students", "student_info")
        sid = int(request.match_info["sid"])
        before = self.db.student(m["group_id"], sid)
        if not before:
            return fail(404, "Студент не найден")
        data = await request.json()
        fields = {}
        for k, n in self.INFO_FIELDS.items():
            if k in data:
                v = " ".join(str(data[k] or "").split())[:n]
                fields[k] = v or None
        if "full_name" in fields and (not fields["full_name"] or len(fields["full_name"]) < 3):
            return fail(400, "ФИО не может быть пустым")
        if fields.get("birth_date"):
            parse_date(fields["birth_date"])
        if fields.get("email") and "@" not in fields["email"]:
            return fail(400, "Проверьте адрес почты")
        if ("archived" in data or data.get("unlink")) and not can(m, "students"):
            return fail(403, "Отчислять и отвязывать может только тот, кто управляет списком студентов")
        if "archived" in data:
            fields["archived"] = 1 if data["archived"] else 0
        self.db.update_student(m["group_id"], sid, **fields)
        if data.get("unlink"):
            self.db.unlink_student(m["group_id"], sid)
        labels = {"full_name": "ФИО", "record_no": "№ студенческого", "phone": "телефон", "email": "почта", "birth_date": "дата рождения",
                  "parent_name": "родитель", "parent_phone": "телефон родителя", "note": "заметка"}
        what = []
        for k, v in fields.items():
            if (before.get(k) or None) == v:
                continue
            if k == "full_name":
                what.append(f"ФИО: {before['full_name']} → {v}")
            elif k == "archived":
                what.append("отчислен(а)" if v else "восстановлен(а)")
            else:
                what.append(labels[k])
        if data.get("unlink") and before.get("tg_id"):
            what.append("отвязан Telegram")
        if what:
            self.audit(m, "student", f"Данные студента · {short_name(before['full_name'])}: " + ", ".join(what), [sid])
        return ok(student=self.db.student(m["group_id"], sid))

    def _remove_student(self, m: dict, sid: int) -> bool:
        """Удаляет запись студента и, если это просто студент, — его доступ к группе."""
        st = self.db.student(m["group_id"], sid)
        if not st:
            return False
        if st["tg_id"]:
            mem = self.db.member(st["tg_id"])
            if mem and mem["group_id"] == m["group_id"]:
                if mem["role"] != "student" or mem["tg_id"] == m["tg_id"] or is_super(mem):
                    raise web.HTTPForbidden(reason="Это запись участника с ролью — сначала смените ему роль")
                self.db.leave(st["tg_id"])
        self.db.delete_student(m["group_id"], sid)
        return True

    async def delete_student(self, request):
        m = self.member(request, "students", "remove_students")
        sid = int(request.match_info["sid"])
        st = self.db.student(m["group_id"], sid)
        if not self._remove_student(m, sid):
            return fail(404, "Студент не найден")
        self.audit(m, "delete", f"Удалён студент · {st['full_name']} (с отметками и оценками)", [sid])
        return ok()

    async def delete_students(self, request):
        m = self.member(request, "students", "remove_students")
        ids = [int(x) for x in (await request.json()).get("ids", [])][:200]
        names = {s["id"]: s["full_name"] for s in self.db.students(m["group_id"], True)}
        done = [sid for sid in ids if self._remove_student(m, sid)]
        if done:
            self.audit(m, "delete", f"Удалено студентов: {len(done)} · " + ", ".join(short_name(names.get(i, "?")) for i in done[:15])
                       + (f" и ещё {len(done) - 15}" if len(done) > 15 else ""), done)
        return ok(deleted=len(done))

    async def merge_student(self, request):
        """Склеить две записи одного студента (например, «антонюк алексей» и «АНТОНЮК А.С.» из ведомости)."""
        m = self.member(request, "students", "student_info")
        data = await request.json()
        keep, drop = int(data["keep"]), int(data["drop"])
        a, b = self.db.student(m["group_id"], keep), self.db.student(m["group_id"], drop)
        if not a or not b or keep == drop:
            return fail(400, "Выберите две разные записи")
        if a["tg_id"] and b["tg_id"]:
            return fail(400, "Обе записи привязаны к разным Telegram — так склеить нельзя")
        self.db.merge_students(m["group_id"], keep, drop)
        self.audit(m, "student", f"Записи объединены · {b['full_name']} → {a['full_name']}", [keep, drop])
        return ok(student=self.db.student(m["group_id"], keep))

    async def claim(self, request):
        m = self.member(request)
        if not self.db.claim_student(m["group_id"], int(request.match_info["sid"]), m["tg_id"]):
            return fail(400, "Этот студент уже привязан к другому аккаунту")
        return ok()

    # ---------- расписание
    async def lessons(self, request):
        m = self.member(request)
        g, today = self.ctx(m)
        rows = [l for l in self.db.lessons(g["id"]) if not l["date"] or l["date"] >= today.isoformat()]
        changes = self.db.changes_between(g["id"], (today - timedelta(days=1)).isoformat(), (today + timedelta(days=90)).isoformat())
        return web.json_response({"lessons": rows, "periods": self.db.periods(g["id"]), "changes": changes,
                                  "moved_in": list(self.db.moved_in(g["id"]))})

    # ---------- переносы и отмены
    async def lesson_change(self, request):
        m = self.member(request, "changes", "schedule")
        g, today = self.ctx(m)
        lesson = self.db.lesson(g["id"], int(request.match_info["lid"]))
        if not lesson:
            raise web.HTTPNotFound(reason="Пара не найдена")
        data = await request.json()
        d = str(data.get("date") or "")
        kind = data.get("kind")
        if not DATE_RE.match(d) or kind not in ("cancel", "move", "room"):
            raise ValueError("Неверные данные")
        if d < (today - timedelta(days=1)).isoformat():
            raise ValueError("Нельзя менять прошедшие пары")
        clean = lambda k, n=60: (" ".join(str(data.get(k) or "").split())[:n] or None)
        kw = {"reason": clean("reason", 200)}
        if kind == "move":
            nd, t1, t2 = str(data.get("new_date") or ""), str(data.get("new_start") or "")[:5], str(data.get("new_end") or "")[:5]
            if not DATE_RE.match(nd) or not TIME_RE.match(t1) or not TIME_RE.match(t2) or t1 >= t2:
                raise ValueError("Укажите новую дату и время (начало раньше конца)")
            if nd == d and t1 == lesson["t_start"]:
                raise ValueError("Новое время совпадает со старым")
            kw.update(new_date=nd, new_start=t1, new_end=t2, new_room=clean("new_room", 30))
        elif kind == "room":
            kw["new_room"] = clean("new_room", 30)
            if not kw["new_room"]:
                raise ValueError("Укажите аудиторию")
        c = self.db.set_change(g["id"], lesson, d, kind, m, **kw)
        what = {"cancel": "отменена", "room": f"аудитория {kw.get('new_room')}",
                "move": f"перенесена на {dm(kw.get('new_date') or d)} {kw.get('new_start')}"}[kind]
        self.audit(m, "change", f"Изменение пары · {lesson['subject']} {dm(d)} {lesson['t_start']}: {what}")
        sent = 0
        if data.get("notify", True):
            sent = await services.notify_change(self.bot, self.db, g["id"], lesson, c, m["tg_id"])
        return ok(change=c, sent=sent)

    async def delete_change(self, request):
        m = self.member(request, "changes", "schedule")
        g, _ = self.ctx(m)
        c = self.db.delete_change(g["id"], int(request.match_info["cid"]))
        if not c:
            raise web.HTTPNotFound(reason="Изменение не найдено")
        lesson = self.db.lesson(g["id"], c["lesson_id"])
        if lesson:
            self.audit(m, "change", f"Изменение отменено · {lesson['subject']} {dm(c['date'])} {lesson['t_start']} — как по расписанию")
        notify = request.query.get("notify", "1") != "0"
        sent = await services.notify_change(self.bot, self.db, g["id"], lesson, c, m["tg_id"], cancelled=True) if notify and lesson else 0
        return ok(sent=sent)

    # ---------- кто в сети (староста, зам, куратор)
    async def ping(self, request):
        self.user(request)
        return ok()

    async def online(self, request):
        m = self.member(request)
        if m["role"] not in ("head", "deputy", "curator") and not is_super(m):
            raise web.HTTPForbidden(reason="Только для старосты и куратора")
        g, today = self.ctx(m)
        since = (today - timedelta(days=6)).isoformat()
        days = self.db.presence(g["id"], since)
        studs = {s["tg_id"]: s for s in self.db.students(g["id"]) if s.get("tg_id")}
        now = int(time.time())
        people = []
        for x in self.db.members(g["id"]):
            seen = x.get("last_seen")
            people.append({"tg_id": x["tg_id"], "name": (studs.get(x["tg_id"]) or {}).get("full_name") or x["full_name"],
                           "username": x.get("username"), "role": x["role"], "role_name": ROLES.get(x["role"], x["role"]),
                           "super": is_super(x), "last_seen": seen, "via": x.get("last_via"),
                           "online": bool(seen and now - seen <= presence.ONLINE_SEC), "days": days.get(x["tg_id"], [])})
        people.sort(key=lambda p: -(p["last_seen"] or 0))
        return web.json_response({"now": now, "online_sec": presence.ONLINE_SEC, "people": people,
                                  "linked_students": len(studs), "tz": g["tz"]})

    async def save_lesson(self, request):
        m = self.member(request, "schedule")
        lid = request.match_info.get("lid")
        data = validate_lesson(await request.json())
        old = self.db.lesson(m["group_id"], int(lid)) if lid else None
        if lid and not old:
            return fail(404, "Пара не найдена")
        new_id = self.db.save_lesson(m["group_id"], data, int(lid) if lid else None)
        when = (dm(data["date"]) if data.get("date") else WD_SHORT[int(data["weekday"])]) + " " + str(data["t_start"])
        self.audit(m, "schedule", f"Расписание · {'изменена' if old else 'добавлена'} пара {data['subject']} ({when})")
        return ok(id=new_id)

    async def delete_lesson(self, request):
        m = self.member(request, "schedule")
        l = self.db.lesson(m["group_id"], int(request.match_info["lid"]))
        self.db.delete_lesson(m["group_id"], int(request.match_info["lid"]))
        if l:
            when = (dm(l["date"]) if l.get("date") else WD_SHORT[l["weekday"]]) + " " + l["t_start"]
            self.audit(m, "schedule", f"Расписание · удалена пара {l['subject']} ({when})")
        return ok()

    async def schedule_template(self, request):
        m = self.member(request, "schedule")
        data = schedule_template(self.db.lessons(m["group_id"], include_oneoff=False))
        set_pending(m["tg_id"], "import")
        await self.bot.send_document(
            m["tg_id"], BufferedInputFile(data, filename="raspisanie.xlsx"),
            caption="🗓 Шаблон расписания. Заполните его в Excel (или Google Таблицах) и пришлите файл "
                    "сюда в ответ — я загружу пары.\n\n⚠️ Текущее регулярное расписание будет заменено.")
        return ok()

    async def periods(self, request):
        m = self.member(request)
        return web.json_response({"periods": self.db.periods(m["group_id"])})

    async def add_period(self, request):
        m = self.member(request, "schedule")
        data = await request.json()
        kind = data.get("kind")
        if kind not in ("holiday", "session", "practice"):
            return fail(400, "Неизвестный тип периода")
        d1, d2 = parse_date(data.get("d1")), parse_date(data.get("d2"))
        if d1 > d2:
            d1, d2 = d2, d1
        pid = self.db.add_period(m["group_id"], kind, (str(data.get("title") or "").strip()[:60] or None),
                                 d1.isoformat(), d2.isoformat())
        return ok(id=pid)

    async def delete_period(self, request):
        m = self.member(request, "schedule")
        self.db.delete_period(m["group_id"], int(request.match_info["pid"]))
        return ok()

    def lessons_on(self, g: dict, d: date) -> list[dict]:
        return polls.todays_lessons(self.db, g, d)

    async def day(self, request):
        m = self.member(request)
        g, today = self.ctx(m)
        d = parse_date(request.query.get("date"), today)
        ds = d.isoformat()
        items = polls.todays_lessons(self.db, g, d, active=False)
        counts = self.db.marked_counts(g["id"], ds)
        my = self.db.student_by_tg(m["tg_id"])
        checkins = {c["lesson_id"]: c for c in self.db.active_checkins(g["id"]) if c["date"] == ds}
        for l in items:
            l["counts"] = counts.get(l["id"], {})
            l["poll_open"] = polls.poll_open(self.db, l["id"], ds)
            if my:
                l["my_status"] = self.db.marks(l["id"], ds).get(my["id"])
            c = checkins.get(l["id"])
            if c:
                l["checkin"] = {"id": c["id"], "expires_at": c["expires_at"],
                                **({"code": c["code"]} if can(m, "attendance") else {})}
        return web.json_response({"date": ds, "week": week_number(g, d), "lessons": items,
                                  "period": day_period(self.db.periods(g["id"]), d),
                                  "total_students": len(self.db.students(g["id"]))})

    async def live(self, request):
        """Текущая/ближайшая пара сегодня и живая сводка по ней."""
        m = self.member(request)
        g, today = self.ctx(m)
        now = now_in(g["tz"])
        nm = now.hour * 60 + now.minute
        items = self.lessons_on(g, today)
        lead = int(g["remind_minutes"] or 0)
        cur = next((l for l in items if to_min(l["t_start"]) - lead <= nm <= to_min(l["t_end"])), None)
        nxt = next((l for l in items if to_min(l["t_start"]) - lead > nm), None)
        resp = {"date": today.isoformat(), "now": now.strftime("%H:%M"), "lesson": None, "next": nxt,
                "left_today": sum(1 for l in items if to_min(l["t_end"]) >= nm), "total_today": len(items),
                "period": day_period(self.db.periods(g["id"]), today)}
        if cur:
            ds = today.isoformat()
            started = nm >= to_min(cur["t_start"])
            phase = "poll" if polls.poll_open(self.db, cur["id"], ds) else ("live" if started else "soon")
            resp["lesson"] = cur
            resp["phase"] = phase
            resp["minutes_to_start"] = to_min(cur["t_start"]) - nm
            resp["minutes_to_end"] = to_min(cur["t_end"]) - nm
            resp["close_at"] = polls.close_time(g, cur)
            c = polls.live_counts(self.db, g, cur, ds)
            if is_staff(m):
                resp["counts"] = c
            else:
                resp["counts"] = {k: len(v) for k, v in c.items()}
                st = self.db.student_by_tg(m["tg_id"])
                resp["my_status"] = self.db.marks(cur["id"], ds).get(st["id"]) if st else None
        return web.json_response(resp)

    # ---------- журнал
    async def journal_month(self, request):
        m = self.member(request, "journal", "attendance")
        g, today = self.ctx(m)
        month = request.query.get("month") or today.strftime("%Y-%m")
        first = date.fromisoformat(month + "-01")
        last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        marked = self.db.marked_dates(g["id"], first.isoformat(), last.isoformat())
        lessons, periods = self.db.lessons(g["id"]), self.db.periods(g["id"])
        from logic import lessons_for_date
        days = {}
        d = first
        while d <= last:
            n = len(lessons_for_date(lessons, g, d, periods))
            p = day_period(periods, d)
            if n or marked.get(d.isoformat()) or p:
                days[d.isoformat()] = {"lessons": n, "marked": marked.get(d.isoformat(), 0),
                                       "period": p["kind"] if p else None}
            d += timedelta(days=1)
        return web.json_response({"month": month, "today": today.isoformat(), "days": days})

    async def journal_day(self, request):
        m = self.member(request, "journal", "attendance")
        g, today = self.ctx(m)
        d = parse_date(request.query.get("date"), today)
        ds = d.isoformat()
        items = self.lessons_on(g, d)
        # пары, у которых есть отметки, но которых нет в расписании (удалены/перенесены)
        extra_ids = {r["lesson_id"] for r in self.db.attendance_range(g["id"], ds, ds)} - {l["id"] for l in items}
        for lid in extra_ids:
            l = self.db.lesson(g["id"], lid)
            if l:
                items.append(l)
        marks = {}
        for l in items:
            marks[l["id"]] = {sid: {"status": r["status"], "reason": r["reason"], "has_file": bool(r["file_id"]),
                                    "source": r["source"]} for sid, r in self.db.marks_full(l["id"], ds).items()}
        return web.json_response({"date": ds, "lessons": sorted(items, key=lambda l: l["t_start"]),
                                  "students": [{"id": s["id"], "full_name": s["full_name"]} for s in self.db.students(g["id"])],
                                  "marks": marks, "period": day_period(self.db.periods(g["id"]), d)})

    # ---------- посещаемость
    async def get_attendance(self, request):
        m = self.member(request, "attendance", "journal")
        lid = int(request.query["lesson_id"])
        d = parse_date(request.query.get("date")).isoformat()
        if not self.db.lesson(m["group_id"], lid):
            return fail(404, "Пара не найдена")
        marks = self.db.marks_full(lid, d)
        rows = [{"id": s["id"], "full_name": s["full_name"], "status": (marks.get(s["id"]) or {}).get("status"),
                 "reason": (marks.get(s["id"]) or {}).get("reason"), "linked": bool(s["tg_id"]),
                 "source": (marks.get(s["id"]) or {}).get("source")}
                for s in self.db.students(m["group_id"])]
        return web.json_response({"students": rows})

    async def set_attendance(self, request):
        m = self.member(request, "attendance")
        data = await request.json()
        lid = int(data["lesson_id"])
        d = parse_date(data.get("date")).isoformat()
        if not self.db.lesson(m["group_id"], lid):
            return fail(404, "Пара не найдена")
        valid = {s["id"] for s in self.db.students(m["group_id"], True)}
        marks = {int(k): (v if v in STATUSES else None) for k, v in (data.get("marks") or {}).items() if int(k) in valid}
        old = self.db.marks(lid, d)
        self.db.set_marks(lid, d, marks, m["tg_id"])
        self._audit_marks(m, lid, d, old, marks)
        return ok(saved=len(marks))

    def _audit_marks(self, m: dict, lid: int, d: str, old: dict, marks: dict) -> None:
        added = [sid for sid, v in marks.items() if v and sid not in old]
        changed = [sid for sid, v in marks.items() if sid in old and old[sid] != v]
        if not added and not changed:
            return
        l = self.db.lesson(m["group_id"], lid) or {"subject": "?", "t_start": ""}
        names = {s["id"]: s["full_name"] for s in self.db.students(m["group_id"], True)}
        parts = []
        if added:
            parts.append(f"отмечено {len(added)}" if len(added) > 3 else
                         "; ".join(f"{short_name(names.get(s, '?'))}: {ST_WORD[marks[s]]}" for s in added))
        if changed:
            parts.append("изменено: " + "; ".join(f"{short_name(names.get(s, '?'))}: {ST_WORD[old[s]]} → {ST_WORD.get(marks[s], '—')}"
                                                  for s in changed[:12]) + (f" и ещё {len(changed) - 12}" if len(changed) > 12 else ""))
        self.audit(m, "marks", f"Отметки · {l['subject']} {dm(d)} {l['t_start']}: " + " · ".join(parts), added + changed)

    async def attendance_file(self, request):
        m = self.member(request, "journal", "attendance")
        data = await request.json()
        lid = int(data["lesson_id"])
        if not self.db.lesson(m["group_id"], lid):
            return fail(404, "Пара не найдена")
        r = self.db.mark(lid, parse_date(data["date"]).isoformat(), int(data["student_id"]))
        if not r or not r["file_id"]:
            return fail(404, "Файл не найден")
        st = self.db.student(m["group_id"], int(data["student_id"]))
        cap = f"📄 Справка: {st['full_name'] if st else ''}" + (f"\n{r['reason']}" if r["reason"] else "")
        try:
            await self.bot.send_photo(m["tg_id"], r["file_id"], caption=cap[:1000])
        except Exception:  # noqa: BLE001
            await self.bot.send_document(m["tg_id"], r["file_id"], caption=cap[:1000])
        return ok()

    async def stats(self, request):
        m = self.member(request)
        g, today = self.ctx(m)
        d2 = parse_date(request.query.get("to"), today)
        d1 = parse_date(request.query.get("from"), d2 - timedelta(days=30))
        recs = self.db.attendance_range(g["id"], d1.isoformat(), d2.isoformat())
        base = {"from": d1.isoformat(), "to": d2.isoformat()}
        if can(m, "journal"):
            stats = build_stats(self.db.students(g["id"]), recs)
            # динамика по дням: доля присутствующих
            daily: dict[str, list[int]] = {}
            for r in recs:
                a = daily.setdefault(r["date"], [0, 0])
                if r["status"] != "E":
                    a[1] += 1
                    a[0] += r["status"] in ("P", "L")
            trend = [{"date": k, "percent": round(100 * v[0] / v[1], 1)} for k, v in sorted(daily.items()) if v[1]]
            return web.json_response({**base, "stats": stats, "subjects": by_subject(recs), "trend": trend})
        st = self.db.student_by_tg(m["tg_id"])
        if not st:
            return web.json_response({**base, "stats": [], "history": [], "subjects": []})
        mine = [r for r in recs if r["student_id"] == st["id"]]
        return web.json_response({**base, "stats": build_stats([st], mine), "subjects": by_subject(mine),
                                  "history": [{k: r[k] for k in ("date", "t_start", "subject", "status")}
                                              for r in reversed(mine)]})

    async def truancy(self, request):
        m = self.member(request, "journal")
        g, today = self.ctx(m)
        d1, d2 = semester_range(g, today)
        recs = self.db.attendance_range(g["id"], d1.isoformat(), d2.isoformat())
        limit = int(g["truancy_limit"] or 3)
        return web.json_response({"limit": limit, "from": d1.isoformat(),
                                  "rows": truancy(self.db.students(g["id"]), recs, limit)})

    async def export(self, request):
        m = self.member(request, "export")
        data = await request.json()
        d1, d2 = parse_date(data.get("from")), parse_date(data.get("to"))
        if d1 > d2:
            d1, d2 = d2, d1
        await services.send_report(self.bot, self.db, m["group_id"], m["tg_id"], d1, d2)
        return ok()

    # ---------- самоотметка по коду
    async def open_checkin(self, request):
        m = self.member(request, "attendance")
        data = await request.json()
        lid = int(data["lesson_id"])
        if not self.db.lesson(m["group_id"], lid):
            return fail(404, "Пара не найдена")
        minutes = max(1, min(int(data.get("minutes", 10)), 120))
        return ok(checkin=self.db.open_checkin(m["group_id"], lid, parse_date(data.get("date")).isoformat(), minutes))

    async def close_checkin(self, request):
        m = self.member(request, "attendance")
        self.db.close_checkin(m["group_id"], int(request.match_info["cid"]))
        return ok()

    async def checkin(self, request):
        m = self.member(request)
        result = do_checkin(self.db, m, str((await request.json()).get("code", "")))
        if isinstance(result, str):
            return fail(400, result)
        return ok(subject=result["subject"])

    # ---------- ответ на опрос из приложения
    async def poll_answer(self, request):
        m = self.member(request)
        data = await request.json()
        res = do_poll_answer(self.db, m, int(data["lesson_id"]), parse_date(data["date"]).isoformat(), data.get("status"))
        if isinstance(res, str):
            return fail(400, res)
        return ok()

    # ---------- объявления
    async def announce(self, request):
        m = self.member(request, "announce")
        data = await request.json()
        text = str(data.get("text", "")).strip()
        if not text:
            return fail(400, "Пустое объявление")
        title = str(data.get("title") or "").strip()[:100] or None
        sent = await services.announce(self.bot, self.db, m["group_id"], m, text[:3500], title, bool(data.get("pinned")))
        self.audit(m, "announce", f"Объявление · {title or text[:80]}")
        return ok(sent=sent)

    async def announcements(self, request):
        m = self.member(request)
        return web.json_response({"items": self.db.announcements(m["group_id"])})

    async def update_announcement(self, request):
        m = self.member(request, "announce")
        data = await request.json()
        self.db.update_announcement(m["group_id"], int(request.match_info["aid"]), pinned=1 if data.get("pinned") else 0)
        return ok()

    async def delete_announcement(self, request):
        m = self.member(request, "announce")
        aid = int(request.match_info["aid"])
        a = self.db.q1("SELECT title, text FROM announcements WHERE id=? AND group_id=?", (aid, m["group_id"]))
        self.db.delete_announcement(m["group_id"], aid)
        if a:
            self.audit(m, "delete", f"Удалено объявление · {a['title'] or a['text'][:80]}")
        return ok()

    # ---------- база знаний
    async def files(self, request):
        m = self.member(request)
        rows = self.db.files(m["group_id"])
        for r in rows:
            r.pop("file_id", None)
            r["can_delete"] = can(m, "files") or r["uploader"] == m["tg_id"]
        return web.json_response({"files": rows, "subjects": self.db.subjects(m["group_id"])})

    async def send_file(self, request):
        m = self.member(request)
        f = self.db.file(m["group_id"], int(request.match_info["fid"]))
        if not f:
            return fail(404, "Файл не найден")
        await services.send_file(self.bot, m["tg_id"], f)
        return ok()

    async def delete_file(self, request):
        m = self.member(request)
        f = self.db.file(m["group_id"], int(request.match_info["fid"]))
        if not f:
            return fail(404, "Файл не найден")
        if not can(m, "files") and f["uploader"] != m["tg_id"]:
            return fail(403, "Удалить может автор или староста")
        self.db.delete_file(m["group_id"], f["id"])
        return ok()

    async def upload_file(self, request):
        m = self.member(request)
        subject = str((await request.json()).get("subject") or "").strip()[:120]
        if not subject:
            return fail(400, "Выберите предмет")
        set_pending(m["tg_id"], "upload", subject=subject)
        await self.bot.send_message(m["tg_id"], f"📚 Пришлите сюда файл или фото для раздела «{subject}» — "
                                                "методичку, конспект, задание. Можно несколько подряд.\n"
                                                "Подпись к файлу станет его названием.")
        return ok()

    # ---------- успеваемость
    def _month(self, value) -> str:
        v = str(value or "").strip()
        if not re.match(r"^20\d\d-(0[1-9]|1[0-2])$", v):
            raise ValueError("Месяц в формате ГГГГ-ММ")
        return v

    async def grade_months(self, request):
        m = self.member(request)
        rows = self.db.grade_months(m["group_id"])
        return web.json_response({"months": [{"month": r["month"], "title": grades.month_title(r["month"]),
                                              "updated_at": r["updated_at"]} for r in rows]})

    async def grades_get(self, request):
        m = self.member(request)
        months = self.db.grade_months(m["group_id"])
        month = request.query.get("month") or (months[0]["month"] if months else None)
        if not month:
            return web.json_response({"month": None, "months": []})
        view = grades.month_view(self.db, m["group_id"], self._month(month))
        mlist = [{"month": r["month"], "title": grades.month_title(r["month"])} for r in months]
        if not view:
            return web.json_response({"month": month, "months": mlist, "empty": True})
        if can(m, "journal", "grades"):
            return web.json_response({**view, "months": mlist})
        st = self.db.student_by_tg(m["tg_id"])
        mine = next((r for r in view["rows"] if st and r["student_id"] == st["id"]), None)
        group_avg = view["summary"]["avg"]
        rank = None
        if mine and mine["avg"] is not None:
            better = sum(1 for r in view["rows"] if r["avg"] is not None and r["avg"] > mine["avg"])
            rank = {"place": better + 1, "of": sum(1 for r in view["rows"] if r["avg"] is not None)}
        return web.json_response({"month": view["month"], "title": view["title"], "months": mlist,
                                  "subjects": [{"name": s["name"], "teacher": s["teacher"], "avg": s["avg"]} for s in view["subjects"]],
                                  "me": mine, "group_avg": group_avg, "rank": rank})

    async def grades_student(self, request):
        """Оценки одного студента по всем месяцам (динамика)."""
        m = self.member(request)
        sid = int(request.match_info["sid"])
        st = self.db.student_by_tg(m["tg_id"])
        if not can(m, "journal", "grades") and not (st and st["id"] == sid):
            return fail(403, "Недостаточно прав")
        out = []
        for r in reversed(self.db.grade_months(m["group_id"])):
            v = grades.month_view(self.db, m["group_id"], r["month"])
            row = next((x for x in v["rows"] if x["student_id"] == sid), None) if v else None
            if row:
                out.append({"month": r["month"], "title": v["title"], "avg": row["avg"], "missed_total": row["missed_total"],
                            "missed_bad": row["missed_bad"], "fails": row["fails"],
                            "grades": [{"name": s["name"], "value": g} for s, g in zip(v["subjects"], row["grades"])]})
        return web.json_response({"history": out})

    async def grades_create(self, request):
        m = self.member(request, "grades")
        data = await request.json()
        month = self._month(data.get("month"))
        if self.db.grade_month(m["group_id"], month):
            return fail(400, "Ведомость за этот месяц уже есть")
        prev = self.db.grade_months(m["group_id"])
        subjects = None
        if prev:
            subjects = self.db.grade_month(m["group_id"], prev[0]["month"])["subjects"]
        if not subjects:
            seen = {}
            for l in self.db.lessons(m["group_id"]):
                seen.setdefault(l["subject"], l.get("teacher"))
            subjects = [{"name": k, "teacher": v} for k, v in seen.items()]
        if not subjects:
            return fail(400, "Добавьте расписание или загрузите ведомость из Excel — нужен список предметов")
        mid = self.db.save_grade_month(m["group_id"], month, subjects, m["tg_id"])
        for s in self.db.students(m["group_id"]):
            self.db.save_grade_row(mid, s["id"], [None] * len(subjects))
        return ok(month=month)

    async def grades_cell(self, request):
        m = self.member(request, "grades")
        data = await request.json()
        gm = self.db.grade_month(m["group_id"], self._month(data.get("month")))
        if not gm:
            return fail(404, "Ведомость не найдена")
        sid = int(data["student_id"])
        if not self.db.student(m["group_id"], sid):
            return fail(404, "Студент не найден")
        rows = self.db.grade_rows(gm["id"])
        r = rows.get(sid) or {"grades": [None] * len(gm["subjects"]), "missed_total": None, "missed_bad": None, "note": None}
        g = list(r["grades"]) + [None] * (len(gm["subjects"]) - len(r["grades"]))
        if "index" in data:
            j = int(data["index"])
            if not 0 <= j < len(gm["subjects"]):
                return fail(400, "Нет такого предмета")
            g[j] = grades.norm_grade(data.get("value"))
        def num(k, cur):
            if k not in data:
                return cur
            v = data[k]
            return None if v in (None, "") else max(0, min(int(v), 999))
        note = (str(data["note"]).strip()[:40] or None) if "note" in data else r["note"]
        mt, mb = num("missed_total", r["missed_total"]), num("missed_bad", r["missed_bad"])
        self.db.save_grade_row(gm["id"], sid, g, mt, mb, note)
        self.db.touch_grade_month(gm["id"], m["tg_id"])
        old_g = list(r["grades"]) + [None] * (len(gm["subjects"]) - len(r["grades"]))
        what = [f"{gm['subjects'][j]['name']}: {old_g[j] or '—'} → {g[j] or '—'}" for j in range(len(g)) if old_g[j] != g[j]]
        if mt != r["missed_total"]:
            what.append(f"пропущено часов: {r['missed_total'] if r['missed_total'] is not None else '—'} → {mt if mt is not None else '—'}")
        if mb != r["missed_bad"]:
            what.append(f"без уваж.: {r['missed_bad'] if r['missed_bad'] is not None else '—'} → {mb if mb is not None else '—'}")
        if note != r["note"]:
            what.append("примечание")
        if what:
            st = self.db.student(m["group_id"], sid)
            self.audit(m, "grades", f"Оценки · {short_name(st['full_name'])}, {grades.month_title(gm['month']).lower()}: " + "; ".join(what), [sid])
        return ok(avg=grades.row_avg(g))

    async def grades_subjects(self, request):
        m = self.member(request, "grades")
        data = await request.json()
        gm = self.db.grade_month(m["group_id"], self._month(data.get("month")))
        if not gm:
            return fail(404, "Ведомость не найдена")
        subjects = gm["subjects"]
        rows = self.db.grade_rows(gm["id"])
        if data.get("add"):
            name = str(data["add"].get("name") or "").strip()[:120]
            if not name:
                return fail(400, "Введите название предмета")
            subjects.append({"name": name, "teacher": (str(data["add"].get("teacher") or "").strip()[:60] or None)})
            for sid, r in rows.items():
                self.db.save_grade_row(gm["id"], sid, list(r["grades"]) + [None], r["missed_total"], r["missed_bad"], r["note"])
        elif "remove" in data:
            j = int(data["remove"])
            if not 0 <= j < len(subjects):
                return fail(400, "Нет такого предмета")
            subjects.pop(j)
            for sid, r in rows.items():
                g = list(r["grades"]); g = g[:j] + g[j + 1:]
                self.db.save_grade_row(gm["id"], sid, g, r["missed_total"], r["missed_bad"], r["note"])
        self.db.save_grade_month(m["group_id"], gm["month"], subjects, m["tg_id"])
        return ok()

    async def grades_fill_missed(self, request):
        m = self.member(request, "grades")
        month = self._month((await request.json()).get("month"))
        return ok(updated=grades.fill_missed_from_journal(self.db, m["group_id"], month))

    async def grades_delete(self, request):
        m = self.member(request, "grades")
        month = self._month(request.match_info["month"])
        if self.db.grade_month(m["group_id"], month):
            self.db.delete_grade_month(m["group_id"], month)
            self.audit(m, "delete", f"Удалена ведомость за {grades.month_title(month).lower()}")
        return ok()

    async def grades_upload(self, request):
        m = self.member(request, "grades")
        set_pending(m["tg_id"], "grades")
        await self.bot.send_message(m["tg_id"], "📒 Пришлите сюда файл ведомости успеваемости (.xlsx) — "
                                                "«Сведения успеваемости студентов группы … за месяц». "
                                                "Я разберу оценки, пропуски и примечания и покажу их каждому студенту.")
        return ok()

    async def grades_export(self, request):
        m = self.member(request, "grades", "export")
        month = self._month((await request.json()).get("month"))
        await services.send_grades(self.bot, self.db, m["group_id"], m["tg_id"], month)
        return ok()

    # ---------- статика (сжатие gzip + долгий кэш для файлов с ?v=…)
    async def index(self, request):
        return static_response(request, WEBAPP_DIR / "index.html", "no-cache")

    async def static(self, request):
        rel = request.match_info["path"]
        p = (WEBAPP_DIR / rel).resolve()
        if WEBAPP_DIR.resolve() not in p.parents or not p.is_file():
            raise web.HTTPNotFound()
        # версия в адресе (?v=28) — файл не изменится, браузер и приложение берут его из кэша без запроса
        cache = "public, max-age=31536000, immutable" if request.query.get("v") else "public, max-age=300"
        return static_response(request, p, cache)


def do_checkin(db: DB, member: dict, code: str) -> dict | str:
    st = db.student_by_tg(member["tg_id"])
    if not st:
        return "Сначала укажите своё ФИО в приложении"
    c = db.find_checkin(member["group_id"], code)
    if not c:
        return "Код неверный или уже истёк"
    lesson = db.lesson(member["group_id"], c["lesson_id"])
    if db.marks(c["lesson_id"], c["date"]).get(st["id"]) != "P":
        db.set_marks(c["lesson_id"], c["date"], {st["id"]: "P"}, member["tg_id"], source="code")
    return lesson


def do_poll_answer(db: DB, member: dict, lid: int, d: str, status: str | None, allow_e: bool = False) -> dict | str:
    """Ответ студента на опрос. Возвращает пару или текст ошибки."""
    if status not in (("P", "L", "A", "E") if allow_e else ("P", "L", "A")):
        return "Неизвестный ответ"
    st = db.student_by_tg(member["tg_id"])
    lesson = db.lesson(member["group_id"], lid)
    if not st or not lesson:
        return "Пара или студент не найдены"
    if not polls.can_answer(db, db.group(member["group_id"]), lesson, d):
        return "Опрос уже закрыт — если нужно поправить, напишите старосте"
    cur = db.mark(lid, d, st["id"])
    if cur and cur["source"] in ("manual", "code") and cur["marked_by"] != member["tg_id"]:
        return "Староста уже отметил вас на этой паре"
    db.set_marks(lid, d, {st["id"]: status}, member["tg_id"], source="poll")
    return lesson


def build_app(db: DB, bot: Bot, token: str, default_tz: str, bot_username: str) -> web.Application:
    a = Api(db, bot, token, default_tz, bot_username)
    app = web.Application(middlewares=[error_mw], client_max_size=1024 * 256)
    r = app.router
    r.add_get("/", a.index)
    r.add_get("/app.apk", a.apk)
    r.add_get("/legal/{name}", a.legal_page)
    r.add_get("/static/{path:.+}", a.static)
    routes = [
        ("GET", "/api/me", a.me),
        ("POST", "/api/applogin/start", a.applogin_start), ("GET", "/api/applogin/status", a.applogin_status),
        ("POST", "/api/applogin/logout", a.app_logout), ("GET", "/api/app-info", a.app_info), ("POST", "/api/group", a.create_group), ("PATCH", "/api/group", a.update_group),
        ("POST", "/api/group/invite", a.new_invite), ("POST", "/api/join", a.join), ("POST", "/api/me/register", a.register),
        ("POST", "/api/leave", a.leave), ("POST", "/api/consent", a.consent), ("POST", "/api/demo/start", a.demo_start),
        ("POST", "/api/auth/password", a.pw_login), ("POST", "/api/auth/set-password", a.pw_set),
        ("POST", "/api/students/{sid}/login-code", a.login_code), ("POST", "/api/me/password", a.change_password), ("GET", "/api/server", a.server), ("GET", "/api/lock", a.lock_get), ("POST", "/api/lock", a.lock_set), ("POST", "/api/me/reminders", a.reminders),
        ("GET", "/api/members", a.members), ("POST", "/api/members/role", a.set_role), ("POST", "/api/members/perms", a.set_perms),
        ("DELETE", "/api/members/{tg_id}", a.kick),
        ("GET", "/api/students", a.students), ("POST", "/api/students", a.add_students),
        ("PATCH", "/api/students/{sid}", a.update_student), ("DELETE", "/api/students/{sid}", a.delete_student),
        ("POST", "/api/students/{sid}/claim", a.claim), ("POST", "/api/students/delete", a.delete_students),
        ("POST", "/api/students/merge", a.merge_student),
        ("GET", "/api/lessons", a.lessons), ("POST", "/api/lessons/{lid}/change", a.lesson_change),
        ("DELETE", "/api/changes/{cid}", a.delete_change), ("GET", "/api/ping", a.ping), ("GET", "/api/online", a.online), ("POST", "/api/lessons", a.save_lesson),
        ("PUT", "/api/lessons/{lid}", a.save_lesson), ("DELETE", "/api/lessons/{lid}", a.delete_lesson),
        ("POST", "/api/schedule/template", a.schedule_template),
        ("GET", "/api/periods", a.periods), ("POST", "/api/periods", a.add_period),
        ("DELETE", "/api/periods/{pid}", a.delete_period),
        ("GET", "/api/day", a.day), ("GET", "/api/live", a.live),
        ("GET", "/api/journal/month", a.journal_month), ("GET", "/api/journal/day", a.journal_day),
        ("GET", "/api/attendance", a.get_attendance), ("POST", "/api/attendance", a.set_attendance),
        ("POST", "/api/attendance/file", a.attendance_file),
        ("GET", "/api/stats", a.stats), ("GET", "/api/truancy", a.truancy), ("POST", "/api/export", a.export),
        ("POST", "/api/checkin/open", a.open_checkin), ("DELETE", "/api/checkin/{cid}", a.close_checkin),
        ("POST", "/api/checkin", a.checkin), ("POST", "/api/poll", a.poll_answer),
        ("POST", "/api/announce", a.announce), ("GET", "/api/announcements", a.announcements),
        ("PATCH", "/api/announcements/{aid}", a.update_announcement),
        ("DELETE", "/api/announcements/{aid}", a.delete_announcement),
        ("GET", "/api/grades/months", a.grade_months), ("GET", "/api/grades", a.grades_get),
        ("GET", "/api/grades/student/{sid}", a.grades_student), ("POST", "/api/grades/month", a.grades_create),
        ("PATCH", "/api/grades/cell", a.grades_cell), ("POST", "/api/grades/subjects", a.grades_subjects),
        ("POST", "/api/grades/fill-missed", a.grades_fill_missed), ("DELETE", "/api/grades/{month}", a.grades_delete),
        ("POST", "/api/grades/upload", a.grades_upload), ("POST", "/api/grades/export", a.grades_export),
        ("GET", "/api/files", a.files), ("POST", "/api/files/upload", a.upload_file),
        ("POST", "/api/files/{fid}/send", a.send_file), ("DELETE", "/api/files/{fid}", a.delete_file),
    ]
    routes += features.routes(a)
    for method, path, handler in routes:
        r.add_route(method, path, handler)
    return app
