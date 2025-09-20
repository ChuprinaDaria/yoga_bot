import logging
from aiogram import F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from . import router
from .common import AdminStates
from db import SessionLocal, User, BroadcastLog
from datetime import datetime

logger = logging.getLogger(__name__)

@router.callback_query(F.data == 'admin_broadcast')
async def admin_broadcast_cb(callback: CallbackQuery, state):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📝 Текст', callback_data='admin_broadcast_text')],
        [InlineKeyboardButton(text='🖼️ Фото + підпис', callback_data='admin_broadcast_photo')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_panel')]
    ])
    await callback.message.answer('Розсилка:', reply_markup=kb)
    await state.clear()
    await callback.answer()

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
