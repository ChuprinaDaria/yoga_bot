import logging
from aiogram import Bot
from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from db import SessionLocal, User, WorkoutCatalog, WorkoutMessage, T, DISCOUNT_DEEP_LINK
from . import router
from .common import get_main_reply_keyboard, menu_text

logger = logging.getLogger(__name__)

async def send_welcome(user_id, chat_id, bot: Bot):
    session = SessionLocal()
    block = session.query(__import__('db').TextBlock).filter_by(key='WELCOME_PHOTO').first()
    photo = block.content if block else None
    session.close()
    if photo:
        await bot.send_photo(chat_id=chat_id, photo=photo, caption=await T('WELCOME'), protect_content=True)
    else:
        await bot.send_message(chat_id=chat_id, text=await T('WELCOME'), protect_content=True)

async def send_six_workouts(user_id, chat_id, bot: Bot):
    session = SessionLocal()
    workouts = session.query(WorkoutCatalog).filter_by(is_active=True).all()
    if not workouts:
        session.close()
        return
    for w in workouts[:6]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Перейти до тренування', url=w.url)]]) if w.url else None
        if w.photo_file_id:
            msg = await bot.send_photo(chat_id, w.photo_file_id, caption=w.caption, reply_markup=kb, protect_content=True)
        else:
            msg = await bot.send_message(chat_id, w.caption, reply_markup=kb, protect_content=True)
        session.add(WorkoutMessage(user_id=user_id, chat_id=chat_id, message_id=msg.message_id))
    session.commit()
    session.close()

async def run_start_open_course(user_id: int, chat_id: int, bot: Bot):
    session = SessionLocal()
    try:
        user = session.query(User).get(user_id)
        if not user:
            user = User(user_id=user_id, status='new')
            session.add(user)
            session.commit()
        if user.status != 'trial_active':
            now = datetime.utcnow()
            user.status = 'trial_active'
            user.trial_started_at = now
            user.trial_expires_at = now + timedelta(days=15)
            user.last_reminder_at = now
            session.commit()
            await bot.send_message(chat_id, await T('OPEN_COURSE_INTRO'), protect_content=True)
            await send_six_workouts(user_id, chat_id, bot)
    finally:
        session.close()

@router.message(Command('start'))
async def cmd_start(message: Message, bot: Bot, **data):
    scheduler: AsyncIOScheduler = data.get('scheduler')
    user_id = message.from_user.id
    # ensure user exists
    session = SessionLocal()
    user = session.query(User).get(user_id)
    if not user:
        user = User(user_id=user_id, status='new')
        session.add(user)
        session.commit()
    session.close()
    await send_welcome(user_id, message.chat.id, bot)
    await message.answer('Головне меню:', reply_markup=get_main_reply_keyboard())
    if scheduler:
        scheduler.add_job(run_start_open_course, 'date', run_date=datetime.utcnow()+timedelta(minutes=1), args=[user_id, message.chat.id, bot])

@router.message(F.text == '🧘‍♀️ Безкоштовний курс')
async def handle_free_course(message: Message, bot: Bot):
    user_id = message.from_user.id
    await bot.send_message(message.chat.id, await T('OPEN_COURSE_INTRO'), protect_content=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🚀 Почати зараз', callback_data='start_first_workout')]])
    await message.answer(await T('START_NOW_MSG'), reply_markup=kb)

@router.message(F.text == '💳 Купити абонемент')
async def handle_buy_subscription(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Написати тренеру', url=DISCOUNT_DEEP_LINK)]])
    await message.answer('Інформація про абонементи. Напишіть тренеру, щоб підібрати програму:', reply_markup=kb)

@router.message(F.text == '💬 Чат школи йоги')
async def handle_chat_link(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Перейти до чату', url='https://t.me/+xA1DOM00cc4zYmRi')]])
    await message.answer('Приєднуйтесь до нашого чату:', reply_markup=kb)

@router.message(F.text == 'ℹ️ Мій статус')
async def handle_my_status(message: Message):
    await message.answer(menu_text(message.from_user.id))

@router.message(F.text == 'Написати тренеру')
async def handle_write_coach(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Написати тренеру', url='https://t.me/eryogaji')]])
    await message.answer('Напишіть тренеру, щоб підібрати персональну програму:', reply_markup=kb)

@router.callback_query(F.data == 'start_first_workout')
async def cb_start_first_workout(callback: CallbackQuery, bot: Bot):
    session = SessionLocal()
    try:
        w = session.query(WorkoutCatalog).filter_by(is_active=True).order_by(WorkoutCatalog.id.asc()).first()
        if not w:
            await callback.message.answer('Тимчасово немає активних тренувань.', protect_content=True)
            await callback.answer()
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Перейти до тренування', url=w.url)]]) if w.url else None
        if w.photo_file_id:
            msg = await bot.send_photo(callback.message.chat.id, w.photo_file_id, caption=w.caption, reply_markup=kb, protect_content=True)
        else:
            msg = await bot.send_message(callback.message.chat.id, w.caption, reply_markup=kb, protect_content=True)
        session.add(WorkoutMessage(user_id=callback.from_user.id, chat_id=callback.message.chat.id, message_id=msg.message_id))
        session.commit()
    finally:
        session.close()
    await callback.answer()
