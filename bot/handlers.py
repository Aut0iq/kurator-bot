"""Команды и диалоги чат-бота."""
import io
from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

import polls
import legal
import presence
import monitor
import services
from api import do_checkin, do_poll_answer
from db import DB
from excel import parse_schedule
from logic import (PERIOD_NAMES, STATUS_NAMES, WEEKDAYS, build_stats, esc, fmt_lesson, lessons_for_date,
                   today_in, week_number)
from perms import ROLES, can
from state import clear_pending, get_pending, set_pending

HELP = (
    "<b>Куратор +</b> — помощник старосты и куратора\n\n"
    "Перед каждой парой я сам спрашиваю студентов, будут ли они, и присылаю старосте сводку. "
    "Всё остальное — в приложении (кнопка «Открыть» внизу).\n\n"
    "<b>Для всех</b>\n"
    "/today · /tomorrow · /week — расписание\n"
    "/here 1234 — отметиться по коду с доски (или просто пришлите 4 цифры)\n"
    "/stats — моя посещаемость\n"
    "/grades — мои оценки за месяц\n"
    "/remind on|off — напоминания\n"
    "/app — приложение для Android и вход из браузера\n"
    "📎 Пришлите файл — сохраню его в базу знаний группы\n\n"
    "<b>Для старосты, зама и куратора</b> (по правам)\n"
    "/invite — приглашение для группы\n"
    "/announce текст — объявление всем\n"
    "/export [дней] — отчёт в Excel\n"
    "/import — загрузить расписание из Excel\n"
    "/stats — у кого низкая посещаемость"
)


def setup_router(db: DB, webapp_url: str, bot_username: str) -> Router:
    r = Router()

    async def lock_guard(handler, event, data):
        from perms import SUPER_IDS
        lock = db.lock()
        user = getattr(event, "from_user", None)
        if user:
            presence.touch(db, user.id, "bot")
        if not lock or not user or user.id in SUPER_IDS:
            return await handler(event, data)
        text = "🔒 <b>Бот временно закрыт.</b>\n" + (esc(lock["text"]) if lock.get("text") else "Попробуйте позже.")
        if isinstance(event, CallbackQuery):
            await event.answer("🔒 Бот временно закрыт", show_alert=True)
        elif isinstance(event, Message):
            await event.answer(text)
        return None

    r.message.outer_middleware(lock_guard)
    r.callback_query.outer_middleware(lock_guard)

    def app_kb(text: str = "📱 Открыть приложение", path: str = "") -> InlineKeyboardMarkup | None:
        if not webapp_url:
            return None
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=text, web_app=WebAppInfo(url=webapp_url + "/" + path.lstrip("/")))]])

    def claim_kb(gid: int) -> InlineKeyboardMarkup | None:
        free = [s for s in db.students(gid) if not s["tg_id"]][:40]
        if not free:
            return None
        rows = [[InlineKeyboardButton(text="Это я: " + s["full_name"], callback_data=f"claim:{s['id']}")] for s in free]
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def ask_name(msg: Message, gid: int, prefix: str = ""):
        set_pending(msg.chat.id, "register")
        kb = claim_kb(gid)
        text = prefix + "✍️ Напишите в ответ свои <b>фамилию и имя</b> (как в журнале), например: <i>Иванов Иван</i>."
        if kb:
            text += "\n\nИли найдите себя в списке, который уже внёс староста:"
        await msg.answer(text, reply_markup=kb)

    def legal_links() -> str:
        if not webapp_url.startswith("http"):
            return "согласие на обработку персональных данных, политика и пользовательское соглашение"
        return (f'<a href="{webapp_url}/legal/consent">согласие на обработку персональных данных</a> '
                f'(<a href="{webapp_url}/legal/privacy">политика</a>) и '
                f'<a href="{webapp_url}/legal/terms">пользовательское соглашение</a>')

    async def ask_consent(msg: Message, arg: str):
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Согласен(на), продолжить", callback_data=f"consent:{arg}"[:64])]])
        await msg.answer("📄 <b>Перед тем как вступить в группу</b>\n\n"
                         f"Бот хранит ваше ФИО, отметки о посещаемости и оценки. Нажимая кнопку, вы даёте {legal_links()}.\n\n"
                         "Мне есть 14 лет; если мне нет 18 — родитель не возражает.\n"
                         "<i>Отозвать согласие и удалить свои данные можно в любой момент командой /forget.</i>",
                         reply_markup=kb, disable_web_page_preview=True)

    @r.callback_query(F.data.startswith("consent:"))
    async def consent_cb(cb: CallbackQuery):
        db.set_consent(cb.from_user.id, legal.VERSION, "telegram")
        await safe_edit(cb.message, "✅ Спасибо! Согласие получено.")
        await cb.answer()
        await do_start(cb.message, cb.from_user, cb.data.split(":", 1)[1])

    @r.message(Command("lock"))
    async def lock_cmd(msg: Message, command: CommandObject):
        from perms import SUPER_IDS
        if msg.from_user.id not in SUPER_IDS:
            return await msg.answer("Команда только для главного куратора.")
        text = (command.args or "").strip()
        await services.set_lock(db, msg.bot, True, text, False, msg.from_user.id)
        await msg.answer("🔒 <b>Доступ закрыт</b> для всех, кроме вас.\n"
                         + (f"Пользователи увидят: «{esc(text)}»\n" if text else "Текст для пользователей: /lock ваш текст\n")
                         + "Опросы и сводки на паузе. Открыть: /unlock", parse_mode="HTML")

    @r.message(Command("unlock"))
    async def unlock_cmd(msg: Message):
        from perms import SUPER_IDS
        if msg.from_user.id not in SUPER_IDS:
            return await msg.answer("Команда только для главного куратора.")
        await services.set_lock(db, msg.bot, False, "", False, msg.from_user.id)
        await msg.answer("✅ Доступ открыт — бот снова работает для всех.")

    @r.message(Command("server"))
    async def server_cmd(msg: Message):
        from perms import SUPER_IDS
        if msg.from_user.id not in SUPER_IDS:
            return await msg.answer("Команда только для главного куратора.")
        wait = await msg.answer("⏳ Собираю данные…")
        s = await monitor.snapshot(db, msg.bot, db.path)
        await safe_edit(wait, monitor.text_report(s))

    @r.message(Command("privacy"))
    async def privacy_cmd(msg: Message):
        await msg.answer(f"📄 Документы сервиса: {legal_links()}.\n\n"
                         "Отозвать согласие и удалить свои данные: /forget", disable_web_page_preview=True)

    @r.message(Command("forget"))
    async def forget_cmd(msg: Message):
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Да, удалить мои данные", callback_data="forget:yes"),
            InlineKeyboardButton(text="Отмена", callback_data="forget:no")]])
        await msg.answer("⚠️ <b>Отзыв согласия на обработку персональных данных</b>\n\n"
                         "Будут удалены: ваше членство в группе, ваша запись в журнале вместе с отметками и оценками, "
                         "входы в приложение. Это нельзя отменить. Продолжить?", reply_markup=kb)

    @r.callback_query(F.data.startswith("forget:"))
    async def forget_cb(cb: CallbackQuery):
        if cb.data != "forget:yes":
            await safe_edit(cb.message, "Отменено — данные не тронуты.")
            return await cb.answer()
        uid = cb.from_user.id
        m = db.member(uid)
        if m:
            others = [x for x in db.members(m["group_id"]) if x["tg_id"] != uid]
            if m["role"] == "head" and others and not any(x["role"] == "head" for x in others):
                await safe_edit(cb.message, "Вы единственный староста группы. Сначала назначьте другого старосту "
                                            "(приложение → Ещё → Участники) или удалите группу, затем повторите /forget.")
                return await cb.answer()
            if not others:
                db.delete_group(m["group_id"])
        db.forget(uid)
        await safe_edit(cb.message, "✅ Согласие отозвано, ваши данные удалены. Чтобы снова пользоваться ботом, вступите в группу по приглашению.")
        await cb.answer("Готово")

    @r.message(CommandStart())
    async def start(msg: Message, command: CommandObject):
        await do_start(msg, msg.from_user, (command.args or "").strip())

    async def do_start(msg: Message, user, arg: str):
        if arg == "forget":
            return await forget_cmd(msg)
        if (arg.startswith("join_") or arg.startswith("staff_")) and db.consent_of(user.id) != legal.VERSION \
                and not db.member(user.id):
            return await ask_consent(msg, arg)
        if arg.startswith("applogin_"):
            code = arg[9:]
            if not db.app_login(code):
                return await msg.answer("Ссылка для входа устарела. Нажмите «Войти через Telegram» в приложении ещё раз.")
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Да, это я", callback_data=f"applogin:{code}:yes"),
                InlineKeyboardButton(text="Нет", callback_data=f"applogin:{code}:no")]])
            return await msg.answer("📱 <b>Вход в приложение «Куратор +»</b>\n\n"
                                    "Кто-то хочет войти в приложение под вашим аккаунтом. Если это вы — подтвердите.\n"
                                    "<i>Если вы ничего не нажимали в приложении — нажмите «Нет».</i>", reply_markup=kb)
        if arg.startswith("staff_"):
            g = db.group_by_staff_code(arg[6:])
            if not g:
                return await msg.answer("Ссылка недействительна. Попросите старосту прислать новую.")
            cur = db.member(user.id)
            if cur and cur["group_id"] != g["id"]:
                return await msg.answer("Вы уже состоите в другой группе. Выйти можно в приложении → Ещё.")
            if cur:
                return await msg.answer(f"Вы уже в группе <b>{esc(g['name'])}</b> — роль: {ROLES[cur['role']]}.",
                                        reply_markup=app_kb())
            db.add_member(user.id, g["id"], "curator", user.full_name, user.username)
            for h in db.staff(g["id"], "roles"):
                await services.safe_send(msg.bot, h["tg_id"], f"👤 {esc(user.full_name)} вступил(а) в «{esc(g['name'])}» как куратор. "
                                                       "Роль и права можно изменить в приложении → Ещё → Участники.")
            return await msg.answer(f"✅ Вы в группе <b>{esc(g['name'])}</b> как <b>куратор</b>.\n\n"
                                    "Вам доступны журнал, статистика, отчёты и объявления. "
                                    "Староста может изменить ваши права.", reply_markup=app_kb())
        if arg.startswith("join_"):
            g = db.group_by_code(arg[5:])
            if not g:
                return await msg.answer("Ссылка-приглашение недействительна. Попросите старосту прислать новую.")
            cur = db.member(user.id)
            if cur and cur["group_id"] != g["id"]:
                return await msg.answer("Вы уже состоите в другой группе. Выйти можно в приложении → Ещё.")
            if not cur:
                db.add_member(user.id, g["id"], "student", user.full_name, user.username)
            if (db.member(user.id) or {}).get("role") != "student":
                return await msg.answer(f"✅ Вы в группе <b>{esc(g['name'])}</b> — {ROLES[db.member(user.id)['role']].lower()}.",
                                        reply_markup=app_kb())
            if not db.student_by_tg(user.id):
                return await ask_name(msg, g["id"], f"👋 Добро пожаловать в группу <b>{esc(g['name'])}</b>!\n\n")
            return await msg.answer(f"✅ Вы уже в группе <b>{esc(g['name'])}</b>.", reply_markup=app_kb())

        m = db.member(user.id)
        if m:
            g = db.group(m["group_id"])
            if m["role"] == "student" and not db.student_by_tg(user.id):
                return await ask_name(msg, g["id"])
            return await msg.answer(f"С возвращением! Группа: <b>{esc(g['name'])}</b>\n\n/help — все команды",
                                    reply_markup=app_kb())
        await msg.answer(
            "👋 Привет! Я — «Куратор +», помощник старосты и куратора.\n\n"
            "Перед каждой парой я сам спрашиваю студентов «Будешь?», а старосте присылаю аккуратную сводку. "
            "Журнал, прогулы, отчёт для деканата в Excel, объявления и база конспектов — в приложении.\n\n"
            "• <b>Староста или куратор?</b> Откройте приложение и создайте группу.\n"
            "• <b>Студент?</b> Перейдите по ссылке-приглашению от старосты.",
            reply_markup=app_kb("🚀 Открыть приложение"),
        )

    @r.message(Command("help"))
    async def help_cmd(msg: Message):
        await msg.answer(HELP, reply_markup=app_kb())

    @r.callback_query(F.data.startswith("applogin:"))
    async def applogin_cb(cb: CallbackQuery):
        _, code, ans = cb.data.split(":")
        if ans != "yes":
            db.x("DELETE FROM app_logins WHERE code=?", (code,))
            await safe_edit(cb.message, "🚫 Вход отменён.")
            return await cb.answer()
        u = cb.from_user
        if not db.app_login_approve(code, {"id": u.id, "first_name": u.first_name, "last_name": u.last_name,
                                           "username": u.username}, device="android"):
            await safe_edit(cb.message, "Ссылка для входа устарела — попробуйте ещё раз из приложения.")
            return await cb.answer()
        await safe_edit(cb.message, "✅ Вход подтверждён — вернитесь в приложение.\n\n"
                                    "<i>Выйти на всех устройствах: /logout_all</i>")
        await cb.answer("Готово")

    @r.message(Command("logout_all"))
    async def logout_all(msg: Message):
        n = db.app_logout_all(msg.from_user.id)
        await msg.answer(f"🔒 Вышел на всех устройствах: {n}." if n else "Вы не входили в приложение ни на одном устройстве.")

    @r.message(Command("app"))
    async def app_cmd(msg: Message):
        from api import apk_path
        apk = apk_path()
        if not webapp_url.startswith("https://"):
            return await msg.answer("Приложение доступно, когда бот работает на сервере с https-адресом.")
        lines = ["📱 <b>Куратор + на телефоне</b>", ""]
        if apk.exists():
            lines += [f"Android: скачайте и установите приложение — {webapp_url}/app.apk",
                      "<i>Телефон может спросить разрешение «Устанавливать из этого источника» — разрешите.</i>", ""]
        lines += [f"Браузер (любой телефон или компьютер): {webapp_url}",
                  "Вход — кнопкой «Войти через Telegram», подтверждение придёт сюда."]
        await msg.answer("\n".join(lines), disable_web_page_preview=True)

    @r.callback_query(F.data == "claimnew")
    async def claim_new(cb: CallbackQuery):
        m = db.member(cb.from_user.id)
        p = get_pending(cb.from_user.id, "register")
        if not m or not p or not p.get("name"):
            return await cb.answer("Напишите ФИО ещё раз", show_alert=True)
        res = db.add_self_student(m["group_id"], p["name"], cb.from_user.id, force_new=True)
        clear_pending(cb.from_user.id)
        await safe_edit(cb.message, f"👍 Записал вас как <b>{esc(res['name'])}</b>.")
        await cb.answer()

    @r.callback_query(F.data.startswith("claim:"))
    async def claim(cb: CallbackQuery):
        m = db.member(cb.from_user.id)
        if not m:
            return await cb.answer("Вы не в группе", show_alert=True)
        sid = int(cb.data.split(":")[1])
        if not db.claim_student(m["group_id"], sid, cb.from_user.id):
            return await cb.answer("Этот студент уже привязан к другому аккаунту", show_alert=True)
        clear_pending(cb.from_user.id)
        st = db.student(m["group_id"], sid)
        has_grades = db.q1("SELECT 1 AS x FROM grade_rows WHERE student_id=? LIMIT 1", (sid,))
        await cb.message.edit_text(f"👍 Готово, вы — <b>{esc(st['full_name'])}</b>."
                                   + (" Оценки из ведомости доступны: /grades" if has_grades else "") + "\n\n"
                                   "Теперь перед каждой парой я буду спрашивать, придёте ли вы. Отвечайте одной кнопкой 😉")
        await cb.answer()

    async def safe_edit(message, text, **kw):
        try:
            await message.edit_text(text, **kw)
        except TelegramBadRequest:
            pass

    @r.callback_query(F.data.startswith("poll:"))
    async def poll_cb(cb: CallbackQuery):
        _, lid, d, k = cb.data.split(":")
        m = db.member(cb.from_user.id)
        if not m:
            return await cb.answer("Вы не в группе", show_alert=True)
        res = do_poll_answer(db, m, int(lid), d, k)
        if isinstance(res, str):
            return await cb.answer(res, show_alert=True)
        g = db.group(m["group_id"])
        base = polls.poll_text(g, res).split("\n\nБудешь")[0]
        if k == "A":
            await safe_edit(cb.message, base + "\n\n❌ Не сможете прийти. Причина уважительная?",
                                       reply_markup=polls.reason_kb(int(lid), d))
        else:
            await safe_edit(cb.message, base + f"\n\n{polls.ANSWER_DONE[k]}\n<i>Передумали? Можно изменить до "
                                              f"{polls.close_time(g, res)}.</i>",
                                       reply_markup=polls.poll_kb(int(lid), d, k))
        await cb.answer("Записал 👍")

    @r.callback_query(F.data.startswith("why:"))
    async def why_cb(cb: CallbackQuery):
        _, lid, d, k = cb.data.split(":")
        m = db.member(cb.from_user.id)
        if not m:
            return await cb.answer()
        g = db.group(m["group_id"])
        lesson = db.lesson(g["id"], int(lid))
        if not lesson:
            return await cb.answer("Пара не найдена", show_alert=True)
        base = polls.poll_text(g, lesson).split("\n\nБудешь")[0]
        if k == "back":
            await safe_edit(cb.message, polls.poll_text(g, lesson), reply_markup=polls.poll_kb(int(lid), d, "A"))
            return await cb.answer()
        res = do_poll_answer(db, m, int(lid), d, k, allow_e=True)
        if isinstance(res, str):
            return await cb.answer(res, show_alert=True)
        if k == "E":
            set_pending(cb.from_user.id, "reason", lesson_id=int(lid), date=d)
            await safe_edit(cb.message, base + "\n\n📄 Уважительная причина.\n"
                                              "Напишите коротко причину или пришлите <b>фото справки</b> — староста увидит.",
                                       reply_markup=polls.poll_kb(int(lid), d, None))
        else:
            await safe_edit(cb.message, base + f"\n\n{polls.ANSWER_DONE['A']}",
                                       reply_markup=polls.poll_kb(int(lid), d, "A"))
        await cb.answer()

    def group_of(msg: Message):
        m = db.member(msg.from_user.id)
        return (m, db.group(m["group_id"])) if m else (None, None)

    async def send_day(msg: Message, offset: int):
        m, g = group_of(msg)
        if not m:
            return await msg.answer("Сначала вступите в группу по ссылке старосты.")
        d = today_in(g["tz"]) + timedelta(days=offset)
        periods = db.periods(g["id"])
        items = polls.todays_lessons(db, g, d, active=False)
        wn = week_number(g, d)
        head = f"📅 <b>{WEEKDAYS[d.weekday()]}, {d:%d.%m}</b>" + (f" · {wn}-я неделя ({'нечёт' if wn % 2 else 'чёт'})" if wn else "")
        from logic import day_period
        p = day_period(periods, d)
        body = "\n".join(f"{i}. {fmt_lesson(l)}" for i, l in enumerate(items, 1))
        if not body:
            body = f"🌴 {PERIOD_NAMES[p['kind']]}{(': ' + esc(p['title'])) if p.get('title') else ''}" if p else "Пар нет — отдыхаем 🎉"
        await msg.answer(f"{head}\n\n{body}")

    @r.message(Command("today"))
    async def today_cmd(msg: Message):
        await send_day(msg, 0)

    @r.message(Command("tomorrow"))
    async def tomorrow_cmd(msg: Message):
        await send_day(msg, 1)

    def week_text(g: dict, offset: int) -> tuple[str, InlineKeyboardMarkup]:
        today = today_in(g["tz"])
        monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        lessons, periods = db.lessons(g["id"]), db.periods(g["id"])
        parts = []
        for i in range(7):
            d = monday + timedelta(days=i)
            items = polls.todays_lessons(db, g, d, active=False)
            if items:
                parts.append(f"<b>{WEEKDAYS[i]} {d:%d.%m}</b>{' 👈' if d == today else ''}\n" + "\n".join(fmt_lesson(l) for l in items))
        wn = week_number(g, monday)
        when = {0: "эта неделя", 1: "следующая неделя", -1: "прошлая неделя"}.get(offset, f"{monday:%d.%m}")
        title = f"🗓 <b>Расписание · {when}</b>" + (f"\n{wn}-я неделя — <b>{'нечётная' if wn % 2 else 'чётная'}</b>" if wn else
                                                       "\n<i>Укажите начало семестра, чтобы различать чётные и нечётные недели</i>")
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️", callback_data=f"week:{offset - 1}"),
            InlineKeyboardButton(text="Эта" if offset else "• Эта •", callback_data="week:0"),
            InlineKeyboardButton(text="Следующая" if offset != 1 else "• Следующая •", callback_data="week:1"),
            InlineKeyboardButton(text="▶️", callback_data=f"week:{offset + 1}")]])
        return title + "\n\n" + ("\n\n".join(parts) or "На этой неделе пар нет."), kb

    @r.message(Command("week"))
    async def week_cmd(msg: Message):
        m, g = group_of(msg)
        if not m:
            return await msg.answer("Сначала вступите в группу по ссылке старосты.")
        text, kb = week_text(g, 0)
        await msg.answer(text, reply_markup=kb)

    @r.callback_query(F.data.startswith("week:"))
    async def week_cb(cb: CallbackQuery):
        m = db.member(cb.from_user.id)
        if not m:
            return await cb.answer()
        off = max(-30, min(30, int(cb.data.split(":")[1])))
        text, kb = week_text(db.group(m["group_id"]), off)
        await safe_edit(cb.message, text, reply_markup=kb)
        await cb.answer()

    @r.message(Command("grades"))
    async def grades_cmd(msg: Message):
        import grades as G
        m, g = group_of(msg)
        if not m:
            return await msg.answer("Вы не состоите в группе.")
        months = db.grade_months(g["id"])
        if not months:
            return await msg.answer("Ведомость успеваемости ещё не загружена." +
                                    ("\nПришлите сюда Excel-файл ведомости — я разберу его." if can(m, "grades") else ""))
        view = G.month_view(db, g["id"], months[0]["month"])
        if can(m, "journal", "grades"):
            s = view["summary"]
            low = sorted([r for r in view["rows"] if r["fails"]], key=lambda r: -r["fails"])[:8]
            lines = [f"📒 <b>Успеваемость · {view['title']}</b>",
                     f"Средний балл: <b>{s['avg'] or '—'}</b> · качество знаний {s['quality'] or '—'}% · успеваемость {s['progress'] or '—'}%",
                     f"Пропущено часов: {s['missed_total']} (без уваж. {s['missed_bad']})"]
            if low:
                lines += ["", "⚠️ Есть двойки или неаттестации:"] + [f"• {esc(r['full_name'])} — {r['fails']}" for r in low]
            return await msg.answer("\n".join(lines), reply_markup=app_kb("Открыть ведомость", "#grades"))
        st = db.student_by_tg(msg.from_user.id)
        row = next((r for r in view["rows"] if st and r["student_id"] == st["id"]), None)
        if not row:
            return await msg.answer(f"В ведомости за {view['title'].lower()} вас не нашлось. Обратитесь к старосте.")
        names = {"0": "н/а"}
        body = "\n".join(f"{('🟢' if g_ == '5' else '🔵' if g_ == '4' else '🟡' if g_ == '3' else '🔴')} {esc(s['name'])} — <b>{names.get(g_, g_)}</b>"
                         for s, g_ in zip(view["subjects"], row["grades"]) if g_)
        await msg.answer(f"📒 <b>Ваши оценки · {view['title']}</b>\n\n{body}\n\n"
                         f"Средний балл: <b>{row['avg'] or '—'}</b>"
                         + (f"\nПропущено часов: {row['missed_total']}" + (f" (без уваж. {row['missed_bad']})" if row['missed_bad'] else "") if row['missed_total'] is not None else ""),
                         reply_markup=app_kb("Подробнее", "#grades"))

    async def handle_code(msg: Message, code: str):
        m = db.member(msg.from_user.id)
        if not m:
            return await msg.answer("Вы не состоите в группе.")
        res = do_checkin(db, m, code)
        await msg.answer("❌ " + res if isinstance(res, str) else f"✅ Вы отмечены на паре «{esc(res['subject'])}»")

    @r.message(Command("here"))
    async def here(msg: Message, command: CommandObject):
        if not command.args:
            return await msg.answer("Напишите код, например: /here 1234")
        await handle_code(msg, command.args.strip())

    @r.message(Command("homework", "hw"))
    async def homework_cmd(msg: Message):
        m, g = group_of(msg)
        if not m:
            return await msg.answer("Вы не состоите в группе.")
        import features
        v = features.homework_view(db, m, today_in(g["tz"]))
        items = [x for x in v["items"] if x["bucket"] != "past" or not x["done"]]
        if not items:
            return await msg.answer("📚 Заданий пока нет — можно выдохнуть 🙂", reply_markup=app_kb("📚 Открыть «Задания»", "#homework"))
        titles = {"past": "⚠️ Срок прошёл", "today": "🔥 Сегодня", "week": "🗓 На этой неделе", "later": "Позже"}
        lines = ["📚 <b>Домашние задания</b>"]
        for b in ("past", "today", "week", "later"):
            part = [x for x in items if x["bucket"] == b]
            if part:
                lines.append(f"\n<b>{titles[b]}</b>")
                lines += [f"{'✅' if x['done'] else '•'} <b>{esc(x['subject'])}</b>: {esc(x['title'])} — до {x['due_date'][8:]}.{x['due_date'][5:7]}"
                          for x in part]
        if v["is_student"]:
            lines.append("\n<i>Выполнили — отметьте в приложении, раздел «Задания».</i>")
        await msg.answer("\n".join(lines), reply_markup=app_kb("📚 Открыть «Задания»", "#homework"))

    @r.message(Command("stats"))
    async def stats_cmd(msg: Message):
        m, g = group_of(msg)
        if not m:
            return await msg.answer("Вы не состоите в группе.")
        d2 = today_in(g["tz"])
        recs = db.attendance_range(g["id"], (d2 - timedelta(days=30)).isoformat(), d2.isoformat())
        if can(m, "journal"):
            stats = [s for s in build_stats(db.students(g["id"]), recs) if s["percent"] is not None]
            if not stats:
                return await msg.answer("За последние 30 дней отметок нет.")
            low = [s for s in stats if s["percent"] < 75]
            avg = round(sum(s["percent"] for s in stats) / len(stats), 1)
            lines = [f"📊 <b>Посещаемость за 30 дней</b>\nСредняя по группе: <b>{avg}%</b>\n"]
            lines += (["⚠️ Ниже 75%:"] + [f"• {esc(s['full_name'])} — {s['percent']}% (пропусков: {s['missed']})" for s in low]
                      if low else ["Все студенты выше 75% 👏"])
            return await msg.answer("\n".join(lines), reply_markup=app_kb("Подробнее в приложении"))
        st = db.student_by_tg(msg.from_user.id)
        if not st:
            return await ask_name(msg, g["id"])
        mine = [x for x in recs if x["student_id"] == st["id"]]
        s = build_stats([st], mine)[0]
        if not s["total"]:
            return await msg.answer("За последние 30 дней отметок пока нет.")
        last = "\n".join(f"{x['date'][8:]}.{x['date'][5:7]} {esc(x['subject'])} — {STATUS_NAMES[x['status']]}"
                         for x in mine[-8:][::-1])
        await msg.answer(f"📊 <b>Ваша посещаемость за 30 дней: {s['percent'] if s['percent'] is not None else '—'}%</b>\n"
                         f"Был: {s['P']} · Опоздал: {s['L']} · Пропустил: {s['missed']} · Уважит.: {s['E']}\n\n"
                         f"<b>Последние отметки:</b>\n{last}")

    @r.message(Command("export"))
    async def export_cmd(msg: Message, command: CommandObject, bot: Bot):
        m, g = group_of(msg)
        if not can(m, "export"):
            return await msg.answer("У вас нет права выгружать отчёты.")
        days = int(command.args) if command.args and command.args.strip().isdigit() else 30
        d2 = today_in(g["tz"])
        await services.send_report(bot, db, g["id"], msg.chat.id, d2 - timedelta(days=max(1, min(days, 400))), d2)

    @r.message(Command("import"))
    async def import_cmd(msg: Message):
        m, g = group_of(msg)
        if not can(m, "schedule"):
            return await msg.answer("У вас нет права редактировать расписание.")
        from excel import schedule_template
        from aiogram.types import BufferedInputFile
        set_pending(msg.from_user.id, "import")
        await msg.answer_document(BufferedInputFile(schedule_template(db.lessons(g["id"], include_oneoff=False)),
                                                    filename="raspisanie.xlsx"),
                                  caption="Заполните шаблон и пришлите файл в ответ. Текущее регулярное расписание будет заменено.")

    @r.message(Command("announce"))
    async def announce_cmd(msg: Message, command: CommandObject, bot: Bot):
        m = db.member(msg.from_user.id)
        if not can(m, "announce"):
            return await msg.answer("У вас нет права публиковать объявления.")
        if not command.args:
            return await msg.answer("Напишите текст после команды: /announce Завтра пары в 305 ауд.")
        n = await services.announce(bot, db, m["group_id"], m, command.args.strip()[:3500])
        await msg.answer(f"📢 Объявление доставлено: {n} чел.")

    @r.message(Command("invite"))
    async def invite_cmd(msg: Message):
        m, g = group_of(msg)
        if not can(m, "invite"):
            return await msg.answer("У вас нет права приглашать студентов.")
        await msg.answer(f"👋 Ребята, подключил группу «{esc(g['name'])}» к боту «Куратор +». "
                         f"Перейдите по ссылке и впишите ФИО — дальше бот сам будет спрашивать перед парами:\n"
                         f"https://t.me/{bot_username}?start=join_{g['invite_code']}\n\n"
                         f"<i>Перешлите это сообщение в беседу группы.</i>")

    @r.message(Command("remind"))
    async def remind_cmd(msg: Message, command: CommandObject):
        m = db.member(msg.from_user.id)
        if not m:
            return await msg.answer("Вы не состоите в группе.")
        arg = (command.args or "").strip().lower()
        if arg not in ("on", "off"):
            return await msg.answer(f"Напоминания сейчас {'включены' if m['reminders'] else 'выключены'}. /remind on или /remind off")
        db.set_reminders(m["tg_id"], arg == "on")
        await msg.answer("🔔 Напоминания включены" if arg == "on" else "🔕 Напоминания выключены")

    @r.callback_query(F.data.startswith("kb:"))
    async def kb_cb(cb: CallbackQuery):
        p = get_pending(cb.from_user.id, "kbfile")
        m = db.member(cb.from_user.id)
        if not p or not m:
            return await cb.answer("Пришлите файл ещё раз", show_alert=True)
        idx = cb.data.split(":")[1]
        if idx == "no":
            clear_pending(cb.from_user.id)
            await cb.message.edit_text("Ок, не сохраняю.")
            return await cb.answer()
        subjects = db.subjects(m["group_id"]) or ["Общее"]
        subject = subjects[int(idx)] if idx.isdigit() and int(idx) < len(subjects) else "Общее"
        path = await services.download_to(cb.bot, p["file_id"], db.files_dir)
        db.add_file(m["group_id"], subject, p["title"], p["file_id"], p["file_type"], p.get("size"),
                    m["tg_id"], m["full_name"] or cb.from_user.full_name, path=path)
        clear_pending(cb.from_user.id)
        await cb.message.edit_text(f"📚 Сохранено в «{esc(subject)}»: {esc(p['title'])}", reply_markup=app_kb("Открыть базу знаний", "#files"))
        await cb.answer("Сохранено")

    @r.message(F.document | F.photo)
    async def got_file(msg: Message, bot: Bot):
        m = db.member(msg.from_user.id)
        if not m:
            return await msg.answer("Сначала вступите в группу по ссылке старосты.")
        if msg.document:
            file_id, ftype, size = msg.document.file_id, "document", msg.document.file_size
            title = (msg.caption or msg.document.file_name or "Файл").strip()
        else:
            ph = msg.photo[-1]
            file_id, ftype, size = ph.file_id, "photo", ph.file_size
            title = (msg.caption or "Фото").strip()

        p = get_pending(msg.from_user.id, "reason")
        if p:
            st = db.student_by_tg(msg.from_user.id)
            if st:
                path = await services.download_to(bot, file_id, db.files_dir)
                db.set_reason(p["lesson_id"], p["date"], st["id"], msg.caption, file_id, file_path=path)
            clear_pending(msg.from_user.id)
            return await msg.answer("📄 Справка прикреплена — староста её увидит. Выздоравливайте!")

        p = get_pending(msg.from_user.id, "import")
        if p and msg.document and (msg.document.file_name or "").lower().endswith((".xlsx", ".xlsm")) \
                and can(m, "schedule"):
            buf = io.BytesIO()
            await bot.download(msg.document, destination=buf)
            try:
                lessons, errors = parse_schedule(buf.getvalue())
            except Exception:
                return await msg.answer("Не получилось прочитать файл. Проверьте, что это .xlsx по шаблону (/import).")
            if not lessons:
                return await msg.answer("В файле не нашлось ни одной пары 🤔\n" + "\n".join(errors[:10]))
            gid = m["group_id"]
            for old in db.lessons(gid, include_oneoff=False):
                db.delete_lesson(gid, old["id"])
            for l in lessons:
                db.save_lesson(gid, l)
            clear_pending(msg.from_user.id)
            text = f"✅ Загружено пар: <b>{len(lessons)}</b>"
            if errors:
                text += "\n\nПропущены строки:\n" + "\n".join(esc(e) for e in errors[:10])
            return await msg.answer(text, reply_markup=app_kb("Посмотреть расписание", "#schedule"))

        is_xlsx = msg.document and (msg.document.file_name or "").lower().endswith((".xlsx", ".xlsm"))
        if is_xlsx and can(m, "grades") and (get_pending(msg.from_user.id, "grades") or not get_pending(msg.from_user.id, "upload")):
            import grades as G
            buf = io.BytesIO()
            await bot.download(msg.document, destination=buf)
            try:
                sheets = G.parse_workbook(buf.getvalue())
            except Exception:
                sheets = []
            if sheets:
                clear_pending(msg.from_user.id)
                lines = []
                for sh in sheets:
                    if not sh["month"]:
                        lines.append(f"⚠️ Лист «{esc(sh['sheet'])}»: не нашёл месяц в шапке («за Сентябрь …»)")
                        continue
                    res = G.import_parsed(db, m["group_id"], sh, m["tg_id"])
                    lines.append(f"✅ <b>{res['title']}</b>: {res['students']} студентов, {res['subjects']} предметов"
                                 + (f"\n   новые в списке группы: {', '.join(esc(x) for x in res['created'][:10])}"
                                    + ("…" if len(res["created"]) > 10 else "") if res["created"] else "")
                                 + (f"\n   связал с уже записавшимися: {len(res['merged'])}" if res.get("merged") else ""))
                return await msg.answer("📒 Ведомость загружена\n\n" + "\n".join(lines) +
                                        "\n\nКаждый студент теперь видит свои оценки в приложении и по команде /grades.",
                                        reply_markup=app_kb("Открыть ведомость", "#grades"))
            if get_pending(msg.from_user.id, "grades"):
                return await msg.answer("Не похоже на ведомость 🤔 Нужен столбец «Фамилия, имя и отчество», "
                                        "под ним — строка с дисциплинами, и в шапке месяц («за Сентябрь …»).")

        p = get_pending(msg.from_user.id, "upload")
        if p:
            path = await services.download_to(bot, file_id, db.files_dir)
            db.add_file(m["group_id"], p["subject"], title, file_id, ftype, size, m["tg_id"],
                        m["full_name"] or msg.from_user.full_name, path=path)
            set_pending(msg.from_user.id, "upload", subject=p["subject"])
            return await msg.answer(f"📚 Сохранено в «{esc(p['subject'])}»: {esc(title)}\nМожно прислать ещё.")

        set_pending(msg.from_user.id, "kbfile", file_id=file_id, file_type=ftype, size=size, title=title)
        subjects = db.subjects(m["group_id"]) or ["Общее"]
        rows = [[InlineKeyboardButton(text=s[:40], callback_data=f"kb:{i}")] for i, s in enumerate(subjects[:30])]
        rows.append([InlineKeyboardButton(text="Не сохранять", callback_data="kb:no")])
        await msg.answer("📚 Сохранить в базу знаний группы? Выберите предмет:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    @r.message(F.text & ~F.text.startswith("/"))
    async def text_msg(msg: Message):
        m = db.member(msg.from_user.id)
        text = msg.text.strip()
        if m and (m["full_name"] != msg.from_user.full_name or m["username"] != msg.from_user.username):
            db.x("UPDATE members SET full_name=?, username=? WHERE tg_id=?",
                 (msg.from_user.full_name, msg.from_user.username, msg.from_user.id))

        if m and get_pending(msg.from_user.id, "register"):
            name = " ".join(text.split())
            if len(name.split()) < 2 or len(name) > 80 or any(ch.isdigit() for ch in name):
                return await msg.answer("Напишите фамилию и имя через пробел, например: <i>Иванов Иван</i>")
            res = db.add_self_student(m["group_id"], name, msg.from_user.id)
            if "choose" in res:
                rows = [[InlineKeyboardButton(text="Это я: " + c["full_name"] + (f" ({c['record_no']})" if c.get("record_no") else ""),
                                              callback_data=f"claim:{c['id']}")] for c in res["choose"][:10]]
                rows.append([InlineKeyboardButton(text="Меня нет в списке", callback_data="claimnew")])
                set_pending(msg.from_user.id, "register", name=name)
                return await msg.answer("В списке группы несколько похожих записей — выберите себя:",
                                        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            clear_pending(msg.from_user.id)
            found = ""
            if res["matched"]:
                found = f"\n\n📒 Нашёл вас в списке группы (<i>{esc(res['was'])}</i>) — оценки из ведомости теперь доступны: /grades"
            return await msg.answer(f"👍 Приятно познакомиться, <b>{esc(res['name'])}</b>!{found}\n\n"
                                    "Перед каждой парой я буду спрашивать, придёте ли вы — отвечайте одной кнопкой. "
                                    "Кто промолчит, тому засчитается пропуск 😉", reply_markup=app_kb())

        p = get_pending(msg.from_user.id, "reason")
        if m and p:
            st = db.student_by_tg(msg.from_user.id)
            if st:
                db.set_reason(p["lesson_id"], p["date"], st["id"], text[:300], None)
            clear_pending(msg.from_user.id)
            return await msg.answer("📄 Причину записал, староста увидит. Если есть справка — можно прислать фото.")

        if text.isdigit() and len(text) == 4:
            return await handle_code(msg, text)

        await msg.answer("Не понял 🤔 /help — список команд", reply_markup=app_kb())

    @r.message()
    async def fallback(msg: Message):
        await msg.answer("Не знаю такой команды 🤔 /help — список команд", reply_markup=app_kb())

    return r
