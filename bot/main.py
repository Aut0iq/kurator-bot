"""Точка входа: запускает бота (long polling), веб-сервер Mini App и напоминания."""
import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

import monitor
from api import build_app
from config import load_config
from db import DB
from handlers import setup_router
from tasks import scheduler

COMMANDS = [
    ("today", "Пары сегодня"), ("tomorrow", "Пары завтра"), ("week", "Расписание на неделю"),
    ("here", "Отметиться по коду"), ("stats", "Посещаемость"), ("homework", "Домашние задания"), ("grades", "Оценки за месяц"), ("announce", "Объявление группе"),
    ("export", "Отчёт в Excel"), ("import", "Загрузить расписание из Excel"), ("invite", "Ссылка-приглашение"), ("remind", "Напоминания вкл/выкл"), ("app", "Приложение для Android"),
    ("privacy", "Документы и персональные данные"), ("forget", "Удалить мои данные"), ("help", "Помощь"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    monitor.install_error_tap()
    cfg = load_config()
    db = DB(cfg.db_path)
    from perms import SUPER_IDS
    if db.apply_super_curators():
        logging.info("Главные кураторы обновлены: %s", ", ".join(map(str, SUPER_IDS)))
    for g in db.all_groups():            # склеиваем «антонюк алексей» и «АНТОНЮК А.С.» из ведомости
        for pair in db.auto_merge(g["id"]):
            logging.info("Объединены записи студента: %s", pair)
    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()

    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in COMMANDS])
    from aiogram.types import BotCommandScopeChat
    for uid in SUPER_IDS:                 # главному куратору — ещё и /server
        try:
            await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in COMMANDS]
                                      + [BotCommand(command="server", description="Мониторинг сервера"),
                                         BotCommand(command="lock", description="Закрыть доступ всем"),
                                         BotCommand(command="unlock", description="Открыть доступ")],
                                      scope=BotCommandScopeChat(chat_id=uid))
        except Exception:  # noqa: BLE001  (куратор ещё не писал боту)
            pass
    if cfg.webapp_url.startswith("https://"):
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text="Открыть", web_app=WebAppInfo(url=cfg.webapp_url + "/")))
    else:
        logging.warning("WEBAPP_URL не задан или не https:// — кнопка Mini App не появится. "
                        "Бот работает только командами.")

    dp = Dispatcher()
    dp.include_router(setup_router(db, cfg.webapp_url, me.username))

    app = build_app(db, bot, cfg.bot_token, cfg.default_tz, me.username)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, cfg.host, cfg.port).start()
    logging.info("Mini App: http://%s:%s  ·  бот @%s запущен", cfg.host, cfg.port, me.username)

    sched = asyncio.create_task(scheduler(bot, db, cfg.webapp_url))
    watch = asyncio.create_task(monitor.watch(db, bot, cfg.db_path))
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        sched.cancel()
        watch.cancel()
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except SystemExit as e:
        print("\n❌ ОШИБКА:", e)
    except Exception:
        logging.exception("\n❌ Бот остановился с ошибкой")
