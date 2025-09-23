import logging
from yogaxbot.db import SessionLocal, User, WorkoutMessage, T, log_status_change
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from .common import is_admin

logger = logging.getLogger(__name__)

async def trial_maintenance(bot: Bot):
    session = SessionLocal()
    now = datetime.utcnow()
    users = session.query(User).filter(User.status == 'trial_active').all()

    for user in users:
        updated = False

        # Нагадування кожні 3 дні
        if user.last_reminder_at and (now - user.last_reminder_at).days >= 3:
            days_left = (user.trial_expires_at - now).days if user.trial_expires_at else 0
            if days_left > 0:
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Написати у чат школи йоги', url='https://t.me/+xA1DOM00cc4zYmRi')]])
                await bot.send_message(
                    chat_id=user.user_id,
                    text=await T('REMINDER_WITH_DAYS', days_left=days_left),
                    reply_markup=kb,
                    protect_content=True
                )
                user.last_reminder_at = now
                updated = True

        # Закінчення курсу
        if user.trial_expires_at and now >= user.trial_expires_at and not user.course_feedback_given:
            old_status = user.status
            user.status = 'trial_expired'
            log_status_change(user, old_status, 'trial_expired', 'course_expired')

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='Так вдалося 🙂', callback_data='course_feedback_yes')],
                [InlineKeyboardButton(text='Ні, руки не дійшли 🙁', callback_data='course_feedback_no')]
            ])

            msg = await bot.send_message(
                chat_id=user.user_id,
                text=await T('COURSE_FINISHED'),
                reply_markup=kb,
                protect_content=True
            )
            user.feedback_message_id = msg.message_id
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


# Додати нову функцію для видалення старих повідомлень
async def cleanup_old_messages(bot: Bot):
    session = SessionLocal()
    now = datetime.utcnow()

    users = session.query(User).filter(
        User.course_extension_used == True,
        User.feedback_message_id != None
    ).all()

    for user in users:
        if user.trial_expires_at and now >= user.trial_expires_at + timedelta(hours=24):
            try:
                if user.feedback_message_id:
                    await bot.delete_message(user.user_id, user.feedback_message_id)

                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Написати тренеру', url='https://t.me/seryogaji')]])

                await bot.send_message(
                    user.user_id,
                    await T('FINAL_COURSE_END'),
                    reply_markup=kb,
                    protect_content=True
                )

                user.feedback_message_id = None
                session.commit()
            except Exception as e:
                logger.error(f"Failed to cleanup for user {user.user_id}: {e}")

    session.close()

async def send_payment_reminders(bot: Bot):
    session = SessionLocal()
    now = datetime.utcnow()
    try:
        admins = session.query(User).filter(User.status == 'admin').all()
        for admin in admins:
            if admin.trial_expires_at and admin.trial_expires_at > now:
                days_left = (admin.trial_expires_at - now).days
                
                text = (
                    "Пане Сергіє - оплатить залишок за замовленням, будь ласка.\n"
                    f"У вас залишилось {days_left} днів на оплату."
                )
                
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text='ОПЛАТИТИ ЗАРАЗ',
                        url='https://checkout.revolut.com/pay/4805ea02-11d9-416a-b817-a56ebdc5d3f3'
                    )]
                ])
                
                try:
                    await bot.send_message(admin.user_id, text, reply_markup=kb)
                    logger.info(f"Sent payment reminder to admin {admin.user_id}")
                except Exception as e:
                    logger.error(f"Failed to send payment reminder to admin {admin.user_id}: {e}")
    finally:
        session.close()
