import os
import sys
import argparse
import logging
import asyncio
from datetime import datetime, timedelta

from dotenv import load_dotenv

from yogaxbot.db import SessionLocal, User
from yogaxbot.handlers.tasks import trial_maintenance, purge_workouts, cleanup_old_messages

try:
    # aiogram is required only for maintenance tasks
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from aiogram.client.default import DefaultBotProperties
except Exception:
    Bot = None  # type: ignore


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s - %(message)s'
)
logger = logging.getLogger("manage")


def _require_bot_token() -> str:
    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.error('BOT_TOKEN не знайдено в оточенні. Експортуйте його або додайте в .env')
        sys.exit(2)
    return token


def _get_bot() -> "Bot":
    token = _require_bot_token()
    if Bot is None:
        logger.error('aiogram недоступний. Переконайтесь, що залежності встановлено.')
        sys.exit(2)
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def cmd_find_15days_users(args: argparse.Namespace) -> None:
    """
    Пошук користувачів, які користуються 15+ днів: trial_started_at <= now - 15 днів
    Виводить кількість та перші N (за потреби всі) користувачів із днями використання.
    """
    now = datetime.utcnow()
    threshold = now - timedelta(days=15)
    session = SessionLocal()
    try:
        q = session.query(User).filter(User.trial_started_at != None, User.trial_started_at <= threshold)  # noqa: E711
        users = q.all()
        logger.info("Знайдено користувачів із тріалом 15+ днів: %s", len(users))
        if not users:
            return
        limit = args.limit if isinstance(getattr(args, 'limit', None), int) else 50
        for u in users[:limit]:
            started = u.trial_started_at or threshold
            days = (now - started).days
            logger.info("user_id=%s status=%s days=%s expires_at=%s", u.user_id, u.status, days, getattr(u, 'trial_expires_at', None))
        if len(users) > limit:
            logger.info("... та ще %s користувачів", len(users) - limit)
    finally:
        session.close()


async def _run_maintenance_async(run_cleanup: bool) -> None:
    bot = _get_bot()
    # 1) Оновлення статусів/нагадувань
    logger.info("Запуск trial_maintenance()")
    try:
        await trial_maintenance(bot)
    except Exception as e:
        logger.warning("trial_maintenance failed: %s", e)
    # 2) Видалення тренувальних повідомлень у тих, у кого тріал сплив
    logger.info("Запуск purge_workouts()")
    try:
        await purge_workouts(bot)
    except Exception as e:
        logger.warning("purge_workouts failed: %s", e)
    # 3) Додаткове очищення фінального повідомлення після продовження на 1 день
    if run_cleanup:
        logger.info("Запуск cleanup_old_messages()")
        try:
            await cleanup_old_messages(bot)
        except Exception as e:
            logger.warning("cleanup_old_messages failed: %s", e)
    # Закриємо клієнтську сесію бота акуратно
    try:
        await bot.session.close()
    except Exception:
        pass
    logger.info("Завершено одноразове обслуговування")


def cmd_run_maintenance(args: argparse.Namespace) -> None:
    load_dotenv()
    asyncio.run(_run_maintenance_async(run_cleanup=not args.skip_cleanup))


def cmd_print_stats(args: argparse.Namespace) -> None:
    session = SessionLocal()
    try:
        from sqlalchemy import func
        rows = session.query(User.status, func.count(User.user_id)).group_by(User.status).all()
        total = session.query(User).count()
        logger.info("=== Поточна статистика користувачів ===")
        logger.info("Всього: %s", total)
        for status, count in sorted(rows, key=lambda r: str(r[0])):
            logger.info("%s: %s", status, count)
    finally:
        session.close()


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description='YogaXBot Manage CLI')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_find = sub.add_parser('find-15days', help='Знайти користувачів, які користуються 15+ днів')
    p_find.add_argument('--limit', type=int, default=50, help='Максимум записів для виводу (за замовчуванням 50)')
    p_find.set_defaults(func=cmd_find_15days_users)

    p_maint = sub.add_parser('run-maintenance', help='Одноразово виконати maintenance задачі')
    p_maint.add_argument('--skip-cleanup', action='store_true', help='Пропустити cleanup_old_messages')
    p_maint.set_defaults(func=cmd_run_maintenance)

    p_stats = sub.add_parser('print-stats', help='Вивести статистику користувачів за статусами')
    p_stats.set_defaults(func=cmd_print_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()


