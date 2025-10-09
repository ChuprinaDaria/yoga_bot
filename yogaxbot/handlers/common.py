import os
import logging
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.state import State, StatesGroup
from yogaxbot.db import SessionLocal, User
from datetime import datetime

logger = logging.getLogger(__name__)

def get_main_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            
            
            [KeyboardButton(text='✉️Написати тренеру')]
            
        ],
        resize_keyboard=True,
        is_persistent=True
    )

def menu_text(user_id: int) -> str:
    session = SessionLocal()
    try:
        user = session.query(User).get(user_id)
        status = user.status if user else 'new'
        days_left = ''
        if user and user.trial_expires_at:
            delta = (user.trial_expires_at - datetime.utcnow()).days
            if delta >= 0:
                days_left = f' (Залишилось днів: {delta})'
        return f'Ваш статус: <b>{status}</b>{days_left}'
    finally:
        session.close()

class AdminStates(StatesGroup):
    settext = State()
    await_workout = State()
    await_broadcast_text = State()
    await_broadcast_photo = State()
    await_workout_photo = State()
    await_workout_caption = State()
    await_workout_code = State()
    await_workout_url = State()
    # Нові стани для розсилки по статусах
    await_status_broadcast_text = State()
    await_status_broadcast_photo = State()
    # Встановлення фото для існуючого тренування
    await_set_workout_photo = State()
    # Редагування привітання/фото/кнопки
    await_welcome_text = State()
    await_welcome_photo = State()
    await_text_block_content = State()
    # Вибір дії після додавання тренування
    await_workout_action = State()

# Admin helpers
_DEF_ADMIN_IDS = None

def _load_admin_ids():
    global _DEF_ADMIN_IDS
    if _DEF_ADMIN_IDS is not None:
        return _DEF_ADMIN_IDS
    ids = set()
    raw_many = os.getenv('ADMIN_USER_IDS')
    raw_one = os.getenv('ADMIN_USER_ID')
    if raw_many:
        for part in raw_many.split(','):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
    if raw_one and raw_one.strip().isdigit():
        ids.add(int(raw_one.strip()))
    _DEF_ADMIN_IDS = ids
    return _DEF_ADMIN_IDS

def is_admin(user_id: int) -> bool:
    admin_ids = _load_admin_ids()
    if user_id in admin_ids:
        return True
    session = SessionLocal()
    try:
        user = session.query(User).get(user_id)
        return bool(user and getattr(user, 'status', None) == 'admin')
    finally:
        session.close()
