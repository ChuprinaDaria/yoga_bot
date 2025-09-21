import logging
from aiogram import F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from . import router
from .common import AdminStates, is_admin
from yogaxbot.db import SessionLocal, User, WorkoutCatalog

logger = logging.getLogger(__name__)

@router.message(Command('admin'))
async def cmd_admin(message: Message, state):
    logger.info("/admin by user_id=%s", message.from_user.id)
    user_id = message.from_user.id
    if not is_admin(user_id):
        # bootstrap: якщо нікого немає — надати права поточному
        session = SessionLocal()
        try:
            has_admin = session.query(User).filter(User.status == 'admin').first() is not None
            if not has_admin:
                user = session.query(User).get(user_id)
                if not user:
                    user = User(user_id=user_id, status='admin')
                    session.add(user)
                else:
                    user.status = 'admin'
                session.commit()
                logger.info("Bootstrap admin granted to user_id=%s", user_id)
            else:
                await message.answer('Недостатньо прав.')
                return
        finally:
            session.close()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🏋️ Тренування', callback_data='admin_workouts')],
        [InlineKeyboardButton(text='📣 Розсилка', callback_data='admin_broadcast')]
        
    ])
    await message.answer('Адмін-панель', reply_markup=kb)
    await state.clear()

@router.callback_query(F.data == 'admin_panel')
async def admin_panel_cb(callback: CallbackQuery, state):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🏋️ Тренування', callback_data='admin_workouts')],
        [InlineKeyboardButton(text='📣 Розсилка', callback_data='admin_broadcast')]
        
    ])
    await callback.message.answer('Адмін-панель', reply_markup=kb)
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == 'admin_workouts')
async def admin_workouts_cb(callback: CallbackQuery, state):
    session = SessionLocal()
    workouts = session.query(WorkoutCatalog).all()
    kb = [[
        InlineKeyboardButton(text=f'{"✅" if w.is_active else "❌"} {w.code}', callback_data=f'admin_toggle_workout_{w.id}'),
        InlineKeyboardButton(text='🖼️ Фото', callback_data=f'admin_set_workout_photo_{w.id}')
    ] for w in workouts]
    kb.append([InlineKeyboardButton(text='➕ Додати тренування', callback_data='admin_add_workout')])
    kb.append([InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_panel')])
    await callback.message.answer('Тренування:', reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    session.close()
    await state.clear()
    await callback.answer()

@router.callback_query(F.data.startswith('admin_toggle_workout_'))
async def admin_toggle_workout_cb(callback: CallbackQuery, state):
    wid = int(callback.data.replace('admin_toggle_workout_', ''))
    session = SessionLocal()
    try:
        w = session.query(WorkoutCatalog).get(wid)
        if not w:
            await callback.message.answer('Тренування не знайдено.')
        else:
            if w.is_active:
                # Якщо активне — вимкнути (показати ❌). Повторне натискання видалить
                w.is_active = False
                session.commit()
                await callback.message.answer(f'Тренування {w.code} вимкнено. Повторне натискання (на ❌) — видалить його.')
            else:
                code = w.code
                session.delete(w)
                session.commit()
                await callback.message.answer(f'Тренування {code} видалено.')
    finally:
        session.close()
    await admin_workouts_cb(callback, state)
    await callback.answer()

@router.callback_query(F.data.startswith('admin_set_workout_photo_'))
async def admin_set_workout_photo_cb(callback: CallbackQuery, state):
    wid = int(callback.data.replace('admin_set_workout_photo_', ''))
    await state.update_data(target_workout_id=wid)
    await state.set_state(AdminStates.await_set_workout_photo)
    await callback.message.answer('Надішліть фото для цього тренування')
    await callback.answer()
