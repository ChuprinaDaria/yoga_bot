import logging
from aiogram import F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from . import router
from .common import AdminStates
from yogaxbot.db import SessionLocal, User, BroadcastLog
from datetime import datetime
from sqlalchemy import func

logger = logging.getLogger(__name__)

@router.callback_query(F.data == 'admin_broadcast')
async def admin_broadcast_cb(callback: CallbackQuery, state):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📝 Текст', callback_data='admin_broadcast_text')],
        [InlineKeyboardButton(text='🖼️ Фото + підпис', callback_data='admin_broadcast_photo')],
        [InlineKeyboardButton(text='🎯 За статусом користувачів', callback_data='admin_broadcast_by_status')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_panel')]
    ])
    await callback.message.answer('Розсилка:', reply_markup=kb)
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == 'admin_broadcast_by_status')
async def admin_broadcast_status_menu(callback: CallbackQuery, state):
    session = SessionLocal()
    try:
        stats = {}
        result = session.query(User.status, func.count(User.user_id)).group_by(User.status).all()
        for status, count in result:
            stats[status] = count

        total = session.query(User).count()

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f'👥 Всім ({total})', callback_data='broadcast_status_all')],
            [InlineKeyboardButton(text=f'🆕 Новим ({stats.get("new", 0)})', callback_data='broadcast_status_new')],
            [InlineKeyboardButton(text=f'🏃 Активний тріал ({stats.get("trial_active", 0)})', callback_data='broadcast_status_trial_active')],
            [InlineKeyboardButton(text=f'⏰ Тріал закінчився ({stats.get("trial_expired", 0)})', callback_data='broadcast_status_trial_expired')],
            [InlineKeyboardButton(text=f'✅ Готові купувати ({stats.get("open", 0)})', callback_data='broadcast_status_open')],
            [InlineKeyboardButton(text=f'💎 Активні клієнти ({stats.get("active", 0)})', callback_data='broadcast_status_active')],
            [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_broadcast')]
        ])

        await callback.message.answer('Оберіть цільову аудиторію:', reply_markup=kb)
    finally:
        session.close()
    await callback.answer()

@router.callback_query(F.data.startswith('broadcast_status_'))
async def admin_broadcast_status_selected(callback: CallbackQuery, state):
    status = callback.data.replace('broadcast_status_', '')
    await state.update_data(target_status=status)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📝 Текст', callback_data='admin_status_broadcast_text')],
        [InlineKeyboardButton(text='🖼️ Фото + підпис', callback_data='admin_status_broadcast_photo')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_broadcast_by_status')]
    ])

    status_names = {
        'all': 'всім користувачам',
        'new': 'новим користувачам', 
        'trial_active': 'користувачам з активним тріалом',
        'trial_expired': 'користувачам з закінченим тріалом',
        'open': 'готовим до покупки',
        'active': 'активним клієнтам'
    }
    await callback.message.answer(
        f'Розсилка {status_names.get(status, status)}.\nОберіть тип повідомлення:', 
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data == 'admin_status_broadcast_text')
async def admin_status_broadcast_text_cb(callback: CallbackQuery, state):
    await callback.message.answer('Введіть текст для розсилки:')
    await state.set_state(AdminStates.await_status_broadcast_text)
    await callback.answer()

@router.message(AdminStates.await_status_broadcast_text)
async def admin_status_broadcast_text_msg(message: Message, state, bot: Bot):
    data = await state.get_data()
    target_status = data.get('target_status', 'all')

    session = SessionLocal()
    try:
        if target_status == 'all':
            users = session.query(User).all()
        else:
            users = session.query(User).filter(User.status == target_status).all()

        total, success, failed = 0, 0, 0
        for u in users:
            try:
                await bot.send_message(u.user_id, message.text, protect_content=True)
                success += 1
            except Exception as e:
                failed += 1
                logger.warning("status_broadcast_text failed to user_id=%s err=%s", u.user_id, e)
            total += 1

        session.add(BroadcastLog(
            created_at=datetime.utcnow(), 
            kind=f'text_status_{target_status}', 
            payload_preview=(message.text or '')[:100], 
            total=total, 
            success=success, 
            failed=failed
        ))
        session.commit()

        status_names = {
            'all': 'всім користувачам',
            'new': 'новим користувачам', 
            'trial_active': 'користувачам з активним тріалом',
            'trial_expired': 'користувачам з закінченим тріалом',
            'open': 'готовим до покупки',
            'active': 'активним клієнтам'
        }

        await message.answer(
            f'Розсилку {status_names.get(target_status, target_status)} завершено.\n'
            f'Успішно: {success}, помилок: {failed}'
        )
    finally:
        session.close()

    await state.clear()

@router.callback_query(F.data == 'admin_status_broadcast_photo')
async def admin_status_broadcast_photo_cb(callback: CallbackQuery, state):
    await callback.message.answer('Надішліть фото з підписом для розсилки:')
    await state.set_state(AdminStates.await_status_broadcast_photo)
    await callback.answer()

@router.message(AdminStates.await_status_broadcast_photo)
async def admin_status_broadcast_photo_msg(message: Message, state, bot: Bot):
    if not message.photo or not message.caption:
        await message.answer('Надішліть фото з підписом!')
        return

    data = await state.get_data()
    target_status = data.get('target_status', 'all')

    session = SessionLocal()
    try:
        if target_status == 'all':
            users = session.query(User).all()
        else:
            users = session.query(User).filter(User.status == target_status).all()

        total, success, failed = 0, 0, 0
        for u in users:
            try:
                await bot.send_photo(
                    u.user_id, 
                    message.photo[-1].file_id, 
                    caption=message.caption, 
                    protect_content=True
                )
                success += 1
            except Exception as e:
                failed += 1
                logger.warning("status_broadcast_photo failed to user_id=%s err=%s", u.user_id, e)
            total += 1

        session.add(BroadcastLog(
            created_at=datetime.utcnow(), 
            kind=f'photo_status_{target_status}', 
            payload_preview=(message.caption or '')[:100], 
            total=total, 
            success=success, 
            failed=failed
        ))
        session.commit()

        status_names = {
            'all': 'всім користувачам',
            'new': 'новим користувачам', 
            'trial_active': 'користувачам з активним тріалом',
            'trial_expired': 'користувачам з закінченим тріалом',
            'open': 'готовим до покупки',
            'active': 'активним клієнтам'
        }

        await message.answer(
            f'Розсилку {status_names.get(target_status, target_status)} завершено.\n'
            f'Успішно: {success}, помилок: {failed}'
        )
    finally:
        session.close()
    await state.clear()

@router.callback_query(F.data == 'admin_broadcast_text')
async def admin_broadcast_text_cb(callback: CallbackQuery, state):
    await callback.message.answer('Введіть текст для розсилки:')
    await state.set_state(AdminStates.await_broadcast_text)
    await callback.answer()

@router.message(AdminStates.await_broadcast_text)
async def admin_broadcast_text_msg(message: Message, state, bot: Bot):
    session = SessionLocal()
    users = session.query(User).all()
    total, success, failed = 0, 0, 0
    for u in users:
        try:
            await bot.send_message(u.user_id, message.text, protect_content=True)
            success += 1
        except Exception as e:
            failed += 1
            logger.warning("broadcast_text failed to user_id=%s err=%s", u.user_id, e)
        total += 1
    session.add(BroadcastLog(created_at=datetime.utcnow(), kind='text', payload_preview=(message.text or '')[:100], total=total, success=success, failed=failed))
    session.commit()
    session.close()
    await message.answer(f'Розсилку завершено. Успішно: {success}, помилок: {failed}')
    await state.clear()

@router.callback_query(F.data == 'admin_broadcast_photo')
async def admin_broadcast_photo_cb(callback: CallbackQuery, state):
    await callback.message.answer('Надішліть фото з підписом для розсилки:')
    await state.set_state(AdminStates.await_broadcast_photo)
    await callback.answer()

@router.message(AdminStates.await_broadcast_photo)
async def admin_broadcast_photo_msg(message: Message, state, bot: Bot):
    if not message.photo or not message.caption:
        await message.answer('Надішліть фото з підписом!')
        return
    session = SessionLocal()
    users = session.query(User).all()
    total, success, failed = 0, 0, 0
    for u in users:
        try:
            await bot.send_photo(u.user_id, message.photo[-1].file_id, caption=message.caption, protect_content=True)
            success += 1
        except Exception as e:
            failed += 1
            logger.warning("broadcast_photo failed to user_id=%s err=%s", u.user_id, e)
        total += 1
    session.add(BroadcastLog(created_at=datetime.utcnow(), kind='photo', payload_preview=(message.caption or '')[:100], total=total, success=success, failed=failed))
    session.commit()
    session.close()
    await message.answer(f'Розсилку завершено. Успішно: {success}, помилок: {failed}')
    await state.clear()
