import logging
from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from . import router
from yogaxbot.db import SessionLocal, User, log_status_change, T
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


@router.callback_query(F.data == 'course_feedback_yes')
async def course_feedback_positive(callback: CallbackQuery, bot):
    user_id = callback.from_user.id
    session = SessionLocal()
    try:
        user = session.query(User).get(user_id)
        if user:
            old_status = user.status
            user.status = 'open'
            user.course_feedback_given = True
            log_status_change(user, old_status, 'open', 'positive_course_feedback')
            session.commit()

            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text='Отримати знижку на перший абонемент',
                    url='https://t.me/m/JHM2HLOFZDky'
                )
            ]])

            await callback.message.edit_text(await T('FEEDBACK_POSITIVE'), reply_markup=kb)
    finally:
        session.close()
    await callback.answer()


@router.callback_query(F.data == 'course_feedback_no')
async def course_feedback_negative(callback: CallbackQuery, bot):
    user_id = callback.from_user.id
    session = SessionLocal()
    try:
        user = session.query(User).get(user_id)
        if user:
            user.course_feedback_given = True
            session.commit()

            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text='Спробувати ще 1 день', callback_data='try_one_more_day')
            ]])

            await callback.message.edit_text(await T('FEEDBACK_NEGATIVE'), reply_markup=kb)
    finally:
        session.close()
    await callback.answer()


@router.callback_query(F.data == 'try_one_more_day')
async def try_one_more_day(callback: CallbackQuery, bot):
    user_id = callback.from_user.id
    session = SessionLocal()
    try:
        user = session.query(User).get(user_id)
        if user and not user.course_extension_used:
            old_status = user.status
            user.course_extension_used = True
            user.trial_expires_at = datetime.utcnow() + timedelta(days=1)
            user.status = 'trial_active'
            log_status_change(user, old_status, 'trial_active', 'extension_used')
            session.commit()

            await callback.message.edit_text("Ваш курс продовжено на 1 день! 🎉")
    finally:
        session.close()
    await callback.answer()


