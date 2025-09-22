import logging
from aiogram import F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from . import router
from .common import AdminStates
from yogaxbot.db import SessionLocal, WorkoutCatalog, User
from datetime import datetime
from sqlalchemy import func

logger = logging.getLogger(__name__)

@router.callback_query(F.data == 'admin_add_workout')
async def admin_add_workout_cb(callback: CallbackQuery, state):
    await state.clear()
    await callback.message.answer('Крок 1/4: надішліть фото тренування')
    await state.set_state(AdminStates.await_workout_photo)
    await callback.answer()

@router.message(AdminStates.await_workout_photo)
async def admin_add_workout_step_photo(message: Message, state):
    if not message.photo:
        await message.answer('Потрібне фото. Спробуйте ще раз.')
        return
    file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=file_id)
    await message.answer('Крок 2/4: надішліть опис (текст) тренування')
    await state.set_state(AdminStates.await_workout_caption)

@router.message(AdminStates.await_workout_caption)
async def admin_add_workout_step_caption(message: Message, state):
    if not message.text:
        await message.answer('Потрібен текстовий опис. Спробуйте ще раз.')
        return
    await state.update_data(caption=message.text)
    await message.answer('Крок 3/4: введіть код/номер тренування (наприклад 360)')
    await state.set_state(AdminStates.await_workout_code)

@router.message(AdminStates.await_workout_code)
async def admin_add_workout_step_code(message: Message, state):
    code_raw = (message.text or '').strip()
    if not code_raw:
        await message.answer('Код не може бути порожнім. Введіть ще раз:')
        return
    # дозволимо як чистий номер, так і будь-який рядок, збережемо як є
    await state.update_data(workout_code=code_raw)
    await message.answer('Крок 4/4: надішліть посилання на відео (починається з http)')
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
    data_code = data.get('workout_code')
    code = str(data_code) if data_code else f"w{int(datetime.utcnow().timestamp())}"
    session = SessionLocal()
    try:
        existing = session.query(WorkoutCatalog).filter_by(code=code).first()
        if existing is not None:
            await message.answer('Такий код вже існує. Введіть інший код:')
            await state.set_state(AdminStates.await_workout_code)
            return
        w = WorkoutCatalog(code=code, caption=caption, url=url, photo_file_id=photo_file_id, is_active=True)
        session.add(w)
        session.commit()
        
        # Запитати, що робити далі
        await state.update_data(new_workout_id=w.id)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Просто зберегти', callback_data='workout_action_save')],
            [InlineKeyboardButton(text='Зберегти і відправити', callback_data='workout_action_send')]
        ])
        await message.answer(f'Тренування збережено! Код: {code}. Що робити далі?', reply_markup=kb)
        await state.set_state(AdminStates.await_workout_action)

    finally:
        session.close()

@router.callback_query(AdminStates.await_workout_action)
async def workout_action_callback(callback: CallbackQuery, state, bot: Bot):
    action = callback.data
    data = await state.get_data()
    wid = data.get('new_workout_id')

    if not wid:
        await callback.message.answer("Помилка: не знайдено ID тренування.")
        await state.clear()
        await callback.answer()
        return

    if action == 'workout_action_save':
        await callback.message.edit_text("Тренування збережено.")
        await state.clear()
        await callback.answer()
        return

    # Логіка для 'workout_action_send'
    session = SessionLocal()
    try:
        stats = {}
        result = session.query(User.status, func.count(User.user_id)).group_by(User.status).all()
        for status, count in result:
            stats[status] = count
        total = session.query(User).count()

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f'👥 Відправити всім ({total})', callback_data=f'workout_send_all_{wid}')],
            [InlineKeyboardButton(text=f'🆕 Новим ({stats.get("new", 0)})', callback_data=f'workout_send_status_new_{wid}')],
            [InlineKeyboardButton(text=f'🏃 Активний тріал ({stats.get("trial_active", 0)})', callback_data=f'workout_send_status_trial_active_{wid}')],
            [InlineKeyboardButton(text=f'⏰ Тріал закінчився ({stats.get("trial_expired", 0)})', callback_data=f'workout_send_status_trial_expired_{wid}')],
            [InlineKeyboardButton(text=f'✅ Готові купувати ({stats.get("open", 0)})', callback_data=f'workout_send_status_open_{wid}')],
            [InlineKeyboardButton(text=f'💎 Активні клієнти ({stats.get("active", 0)})', callback_data=f'workout_send_status_active_{wid}')]
        ])
        await callback.message.edit_text('Кому відправити бонусне тренування?', reply_markup=kb)
    finally:
        session.close()
    
    # Стан не очищуємо, бо workout_send_callback очікує на ID
    await callback.answer()

@router.callback_query(F.data.startswith('workout_send_'))
async def workout_send_callback(callback: CallbackQuery, state, bot: Bot):
    parts = callback.data.split('_')
    # patterns: workout_send_all_{id} or workout_send_status_{status}_{id}
    if len(parts) < 4:
        await callback.answer()
        return
    target = parts[2]
    if target == 'all':
        try:
            wid = int(parts[-1])
        except Exception:
            await callback.answer('Помилка параметрів')
            return
        status_filter = 'all'
    elif target == 'status' and len(parts) >= 5:
        # статус може містити підкреслення (наприклад trial_active)
        status_filter = '_'.join(parts[3:-1])
        try:
            wid = int(parts[-1])
        except Exception:
            await callback.answer('Помилка параметрів')
            return
    else:
        await callback.answer()
        return

    session = SessionLocal()
    try:
        w = session.query(WorkoutCatalog).get(wid)
        if not w:
            await callback.message.answer('Тренування не знайдено.')
            await callback.answer()
            return
        # Підібрати аудиторію
        if status_filter == 'all':
            users = session.query(User).all()
        else:
            users = session.query(User).filter(User.status == status_filter).all()
    finally:
        session.close()

    # Текст і кнопка як у вимозі
    text = (
        'Привіт! Ви отримали бонусне безкоштовне тренування!\n'
        'Для придбання повного курсу — напишіть тренеру'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Написати', url='https://t.me/seryogaji')]])

    # Надсилання: фото (якщо є) + підпис із посиланням на відео
    sent_ok, sent_fail = 0, 0
    for u in users:
        try:
            if w.photo_file_id:
                await bot.send_photo(
                    u.user_id,
                    w.photo_file_id,
                    caption=f"{text}\n\n{w.caption}\n{w.url}",
                    reply_markup=kb,
                    protect_content=True
                )
            else:
                await bot.send_message(
                    u.user_id,
                    f"{text}\n\n{w.caption}\n{w.url}",
                    reply_markup=kb,
                    protect_content=True
                )
            sent_ok += 1
        except Exception:
            sent_fail += 1
            continue
    await callback.message.answer(f'Розсилку завершено. Успішно: {sent_ok}, помилок: {sent_fail}')
    await state.clear() # Очищуємо стан тут, після завершення розсилки
    await callback.answer()

@router.message(AdminStates.await_set_workout_photo)
async def admin_set_workout_photo(message: Message, state):
    if not message.photo:
        await message.answer('Потрібне фото. Спробуйте ще раз.')
        return
    data = await state.get_data()
    wid = data.get('target_workout_id')
    if not wid:
        await message.answer('Помилка: не вибране тренування.')
        await state.clear()
        return
    session = SessionLocal()
    try:
        w = session.query(WorkoutCatalog).get(wid)
        if not w:
            await message.answer('Тренування не знайдено.')
        else:
            w.photo_file_id = message.photo[-1].file_id
            session.commit()
            await message.answer('Фото оновлено!')
    finally:
        session.close()
    await state.clear()