import logging
from db import SessionLocal, User, WorkoutMessage, T
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

logger = logging.getLogger(__name__)

async def trial_maintenance(bot: Bot):
    session = SessionLocal()
    now = datetime.utcnow()
    users = session.query(User).filter(User.status == 'trial_active').all()
    for user in users:
        updated = False
        if user.last_reminder_at and (now - user.last_reminder_at).days >= 3:
            days_left = (user.trial_expires_at - now).days if user.trial_expires_at else 0
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Чат школи йоги', url='https://t.me/yogaxchat')]])
            await bot.send_message(chat_id=user.user_id, text=(await T('REMINDER_TPL', days_left=days_left)), reply_markup=kb, protect_content=True)
            user.last_reminder_at = now
            updated = True
        if user.trial_expires_at and now >= user.trial_expires_at:
            user.status = 'trial_expired'
            updated = True
        if updated:
            session.commit()
    session.close()

async def purge_workouts(bot: Bot):
    session = SessionLocal()
    now = datetime.utcnow()
    users = session.query(User).filter(User.trial_expires_at != None, User.trial_expires_at <= now).all()
    for user in users:
        workouts = session.query(WorkoutMessage).filter_by(user_id=user.user_id).all()
        for wm in workouts:
            try:
                await bot.delete_message(chat_id=wm.chat_id, message_id=wm.message_id)
            except Exception:
                pass
            session.delete(wm)
        session.commit()
    session.close()
