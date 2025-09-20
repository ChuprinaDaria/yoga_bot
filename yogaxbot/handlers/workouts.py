import logging
from aiogram import F
from aiogram.types import Message, CallbackQuery
from . import router
from .common import AdminStates
from db import SessionLocal, WorkoutCatalog
from datetime import datetime

logger = logging.getLogger(__name__)

@router.callback_query(F.data == 'admin_add_workout')
async def admin_add_workout_cb(callback: CallbackQuery, state):
    await state.clear()
    await callback.message.answer('Крок 1/3: надішліть фото тренування')
    await state.set_state(AdminStates.await_workout_photo)
    await callback.answer()

@router.message(AdminStates.await_workout_photo)
async def admin_add_workout_step_photo(message: Message, state):
    if not message.photo:
        await message.answer('Потрібне фото. Спробуйте ще раз.')
        return
    file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=file_id)
    await message.answer('Крок 2/3: надішліть опис (текст) тренування')
    await state.set_state(AdminStates.await_workout_caption)

@router.message(AdminStates.await_workout_caption)
async def admin_add_workout_step_caption(message: Message, state):
    if not message.text:
        await message.answer('Потрібен текстовий опис. Спробуйте ще раз.')
        return
    await state.update_data(caption=message.text)
    await message.answer('Крок 3/3: надішліть посилання на відео (починається з http)')
    await state.set_state(AdminStates.await_workout_url)

@router.message(AdminStates.await_workout_url)
async def admin_add_workout_step_url(message: Message, state):
    url = (message.text or '').strip()
    if not url.startswith('http'):
        await message.answer('Невірний формат посилання. Має починатися з http або https. Надішліть ще раз:')
        return
    data = await state.get_data()
    photo_file_id = data.get('photo_file_id')
    caption = data.get('caption', '')
    code = f"w{int(datetime.utcnow().timestamp())}"
    session = SessionLocal()
    try:
        existing = session.query(WorkoutCatalog).filter_by(code=code).first()
        while existing is not None:
            code = f"w{int(datetime.utcnow().timestamp())}"
            existing = session.query(WorkoutCatalog).filter_by(code=code).first()
        w = WorkoutCatalog(code=code, caption=caption, url=url, photo_file_id=photo_file_id, is_active=True)
        session.add(w)
        session.commit()
        await message.answer(f'Тренування збережено! Код: {code}')
    finally:
        session.close()
    await state.clear()
