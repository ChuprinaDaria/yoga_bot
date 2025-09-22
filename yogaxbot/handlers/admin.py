import logging
from aiogram import F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from . import router
from .common import AdminStates, is_admin
from yogaxbot.db import SessionLocal, User, WorkoutCatalog, TextBlock

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
        [InlineKeyboardButton(text='📣 Розсилка', callback_data='admin_broadcast')],
        [InlineKeyboardButton(text='✏️ Редагувати повідомлення', callback_data='admin_texts')]
    ])
    await message.answer('Адмін-панель', reply_markup=kb)
    await state.clear()

@router.callback_query(F.data == 'admin_panel')
async def admin_panel_cb(callback: CallbackQuery, state):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🏋️ Тренування', callback_data='admin_workouts')],
        [InlineKeyboardButton(text='📣 Розсилка', callback_data='admin_broadcast')],
        [InlineKeyboardButton(text='✏️ Редагувати повідомлення', callback_data='admin_texts')]
    ])
    await callback.message.answer('Адмін-панель', reply_markup=kb)
    await state.clear()
    await callback.answer()
@router.callback_query(F.data == 'admin_texts')
async def admin_texts_menu(callback: CallbackQuery, state):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='👋 Welcome (текст)', callback_data='edit_text_WELCOME')],
        [InlineKeyboardButton(text='🖼️ Welcome (фото)', callback_data='admin_edit_welcome_photo')],
        [InlineKeyboardButton(text='⏳ Кінець курсу', callback_data='edit_text_COURSE_FINISHED')],
        [InlineKeyboardButton(text='🙂 Фідбек: Так', callback_data='edit_text_FEEDBACK_POSITIVE')],
        [InlineKeyboardButton(text='🙁 Фідбек: Ні', callback_data='edit_text_FEEDBACK_NEGATIVE')],
        [InlineKeyboardButton(text='🏁 Фінальне повідомлення', callback_data='edit_text_FINAL_COURSE_END')],
        [InlineKeyboardButton(text='⏰ Нагадування з днями', callback_data='edit_text_REMINDER_WITH_DAYS')],
        [InlineKeyboardButton(text='ℹ️ Інтро курсу', callback_data='edit_text_OPEN_COURSE_INTRO')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_panel')]
    ])
    await callback.message.answer('Оберіть, що редагувати:', reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith('edit_text_'))
async def admin_edit_any_text(callback: CallbackQuery, state):
    key = callback.data.replace('edit_text_', '')
    await state.update_data(edit_text_key=key)
    await state.set_state(AdminStates.await_text_block_content)
    await callback.message.answer(f'Надішліть новий текст для {key} (HTML дозволено):')
    await callback.answer()

@router.message(AdminStates.await_text_block_content)
async def admin_save_any_text(message: Message, state):
    data = await state.get_data()
    key = data.get('edit_text_key')
    if not key:
        await state.clear()
        return
    session = SessionLocal()
    try:
        session.merge(TextBlock(key=key, content=message.html_text or ''))
        session.commit()
        await message.answer(f'Текст {key} оновлено.')
    finally:
        session.close()
    await state.clear()
@router.callback_query(F.data == 'admin_edit_welcome_photo')
async def admin_edit_welcome_photo_cb(callback: CallbackQuery, state):
    await state.set_state(AdminStates.await_welcome_photo)
    await callback.message.answer('Надішліть фото для привітання або URL-лінк на зображення:')
    await callback.answer()

@router.message(AdminStates.await_welcome_photo)
async def admin_edit_welcome_photo_msg(message: Message, state):
    session = SessionLocal()
    try:
        if message.photo:
            file_id = message.photo[-1].file_id
            content = file_id
        else:
            content = (message.text or '').strip()
        block = session.query(TextBlock).get('WELCOME_PHOTO')
        if block:
            block.content = content
        else:
            session.add(TextBlock(key='WELCOME_PHOTO', content=content))
        session.commit()
        await message.answer('Фото для привітання оновлено.')
    finally:
        session.close()
    await state.clear()

@router.callback_query(F.data == 'admin_workouts')
async def admin_workouts_cb(callback: CallbackQuery, state):
    session = SessionLocal()
    workouts = session.query(WorkoutCatalog).all()
    kb = [[
        InlineKeyboardButton(text=f'{w.code}', callback_data=f'none_{w.id}'), # Placeholder
        InlineKeyboardButton(text='🖼️ Фото', callback_data=f'admin_set_workout_photo_{w.id}'),
        InlineKeyboardButton(text='🗑️ Видалити', callback_data=f'admin_delete_workout_{w.id}')
    ] for w in workouts]
    kb.append([InlineKeyboardButton(text='➕ Додати тренування', callback_data='admin_add_workout')])
    kb.append([InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_panel')])
    await callback.message.answer('Тренування:', reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    session.close()
    await state.clear()
    await callback.answer()

@router.callback_query(F.data.startswith('admin_confirm_delete_workout_'))
async def admin_confirm_delete_workout_cb(callback: CallbackQuery, state):
    parts = callback.data.split('_')
    action = parts[4]
    wid = int(parts[5])

    if action == 'yes':
        session = SessionLocal()
        try:
            w = session.query(WorkoutCatalog).get(wid)
            if w:
                code = w.code
                session.delete(w)
                session.commit()
                await callback.message.answer(f'Тренування {code} видалено.')
            else:
                await callback.message.answer('Тренування вже видалено.')
        finally:
            session.close()
    else: # 'no'
        await callback.message.answer('Видалення скасовано.')

    await admin_workouts_cb(callback, state)
    await callback.answer()

@router.callback_query(F.data.startswith('admin_delete_workout_'))
async def admin_delete_workout_cb(callback: CallbackQuery, state):
    wid = int(callback.data.replace('admin_delete_workout_', ''))
    session = SessionLocal()
    try:
        w = session.query(WorkoutCatalog).get(wid)
        if w:
            kb_confirm = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text='Так, видалити', callback_data=f'admin_confirm_delete_workout_yes_{w.id}'),
                    InlineKeyboardButton(text='Ні, скасувати', callback_data=f'admin_confirm_delete_workout_no_{w.id}')
                ]
            ])
            await callback.message.answer(f'Ви впевнені, що хочете видалити тренування {w.code}?', reply_markup=kb_confirm)
    finally:
        session.close()
    await callback.answer()

@router.callback_query(F.data.startswith('admin_set_workout_photo_'))
async def admin_set_workout_photo_cb(callback: CallbackQuery, state):
    wid = int(callback.data.replace('admin_set_workout_photo_', ''))
    await state.update_data(target_workout_id=wid)
    await state.set_state(AdminStates.await_set_workout_photo)
    await callback.message.answer('Надішліть фото для цього тренування')
    await callback.answer()
