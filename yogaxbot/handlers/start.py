import logging
import os
import asyncio
from aiogram import Bot
from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from yogaxbot.db import SessionLocal, User, WorkoutCatalog, WorkoutMessage, T, TextBlock
from . import router
from .common import get_main_reply_keyboard, menu_text

logger = logging.getLogger(__name__)

async def send_welcome(user_id, chat_id, bot: Bot):
    # 0) Локальний файл у корені проєкту (за замовчуванням: photo_YYYY-MM-DD_..jpg або шлях з .env)
    default_name = os.getenv('WELCOME_PHOTO_PATH', 'photo_2025-09-21_09-36-24.jpg')
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    local_path = os.path.join(project_root, default_name)

    # Статична кнопка для старту курсу
    btn_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='ПОЧАТИ БЕЗКОШТОВНИЙ КУРС', callback_data='start_first_workout')]
    ])

    if os.path.exists(local_path):
        try:
            await bot.send_photo(chat_id=chat_id, photo=FSInputFile(local_path), caption=await T('WELCOME'), reply_markup=btn_kb, protect_content=True)
            return
        except Exception as e:
            logger.warning("Failed to send local welcome photo at %s: %s", local_path, e)

    # 1) .env URL
    photo_url = os.getenv('WELCOME_PHOTO_URL')
    if photo_url:
        try:
            await bot.send_photo(chat_id=chat_id, photo=photo_url, caption=await T('WELCOME'), reply_markup=btn_kb, protect_content=True)
            return
        except Exception as e:
            logger.warning("Failed to send welcome photo by URL %s: %s", photo_url, e)

    # 2) Текстовий блок з URL
    session = SessionLocal()
    try:
        block = session.query(TextBlock).filter_by(key='WELCOME_PHOTO').first()
        url = block.content if block else None
    finally:
        session.close()
    if url:
        try:
            await bot.send_photo(chat_id=chat_id, photo=url, caption=await T('WELCOME'), reply_markup=btn_kb, protect_content=True)
            return
        except Exception as e:
            logger.warning("Failed to send welcome photo by TextBlock URL %s: %s", url, e)

    # Фолбек: тільки текст
    await bot.send_message(chat_id=chat_id, text=await T('WELCOME'), reply_markup=btn_kb, protect_content=True)

async def send_six_workouts(user_id, chat_id, bot: Bot):
    session = SessionLocal()
    workouts = session.query(WorkoutCatalog).all() # Прибираємо фільтр is_active=True
    if not workouts:
        session.close()
        return
    for w in workouts[:6]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text='Перейти до тренування', url=w.url)
        ]]) if w.url else None
        msg = None
        if w.photo_file_id:
            try:
                msg = await bot.send_photo(chat_id, w.photo_file_id, caption=w.caption, reply_markup=kb, protect_content=True)
            except Exception as e:
                logger.warning("Failed to send workout photo code=%s: %s; fallback to text", getattr(w, 'code', '?'), e)
        if msg is None:
            msg = await bot.send_message(chat_id, w.caption, reply_markup=kb, protect_content=True)
        session.add(WorkoutMessage(user_id=user_id, chat_id=chat_id, message_id=msg.message_id))
    session.commit()
    session.close()

async def run_start_open_course(user_id: int, chat_id: int, bot: Bot, force: bool = False):
    session = SessionLocal()
    try:
        logger.info("run_start_open_course invoked for user_id=%s chat_id=%s", user_id, chat_id)
        user = session.query(User).get(user_id)
        if not user:
            user = User(user_id=user_id, status='new')
            session.add(user)
            session.commit()
        # Якщо не примусово, перевіряємо очікування відкладеного старту
        if not force:
            now_local = datetime.now()
            if not getattr(user, 'start_pending_at', None):
                logger.info("Auto-start skipped for user_id=%s: no pending flag", user_id)
                return
            if now_local < user.start_pending_at:
                logger.info("Auto-start skipped for user_id=%s: not yet time (start_pending_at=%s)", user_id, user.start_pending_at)
                return
        if user.status != 'trial_active':
            now = datetime.utcnow()
            user.status = 'trial_active'
            user.trial_started_at = now
            user.trial_expires_at = now + timedelta(days=15)
            user.last_reminder_at = now
            user.start_pending_at = None
            session.commit()
            await bot.send_message(chat_id, await T('OPEN_COURSE_INTRO'), protect_content=True)
            await asyncio.sleep(10)
            await send_six_workouts(user_id, chat_id, bot)
        else:
            # Якщо вже активний тріал, але тренування ще не відправлялись — відправити 6 тренувань
            has_any = session.query(WorkoutMessage).filter_by(user_id=user_id).first() is not None
            if not has_any:
                user.start_pending_at = None
                session.commit()
                await bot.send_message(chat_id, await T('OPEN_COURSE_INTRO'), protect_content=True)
                await asyncio.sleep(10)
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
    try:
        await bot.send_message(message.chat.id, '\u2063', reply_markup=get_main_reply_keyboard())
    except TelegramBadRequest:
        await bot.send_message(message.chat.id, '.', reply_markup=get_main_reply_keyboard())
   
    if scheduler:
        run_at = datetime.now() + timedelta(minutes=1)
        logger.info("Scheduling run_start_open_course at %s for user_id=%s", run_at.isoformat(), user_id)
        # Позначити очікування автозапуску
        session2 = SessionLocal()
        try:
            u = session2.query(User).get(user_id)
            if u:
                u.start_pending_at = run_at
                session2.commit()
        finally:
            session2.close()
        scheduler.add_job(run_start_open_course, 'date', run_date=run_at, args=[user_id, message.chat.id, bot])

@router.message(F.text == '🧘‍♀️ Безкоштовний курс')
async def handle_free_course(message: Message, bot: Bot):
    user_id = message.from_user.id
    await bot.send_message(message.chat.id, await T('OPEN_COURSE_INTRO'), protect_content=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🚀 Почати зараз', callback_data='start_first_workout')]])
    await message.answer(await T('START_NOW_MSG'), reply_markup=kb)



@router.message(F.text == '💬 Чат школи йоги')
async def handle_chat_link(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Перейти до чату', url='https://t.me/+xA1DOM00cc4zYmRi')]])
    await message.answer('Приєднуйтесь до нашого чату:', reply_markup=kb)



@router.message(Command('contact'))
@router.message(F.text.in_({'Написати тренеру', '✉️Написати тренеру'}))
async def handle_write_coach(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Написати тренеру', url='https://t.me/seryogaji')]])
    await message.answer('Напишіть тренеру, щоб підібрати персональну програму:', reply_markup=kb)

@router.message(F.text == 'Купити абонемент')
async def handle_buy_subscription(message: Message):
    # Поки що ставимо "заглушку" посилання
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Оформити абонемент', url='https://example.com/subscription')]])
    await message.answer('Оберіть тариф та оформіть абонемент:', reply_markup=kb)
@router.callback_query(F.data == 'start_first_workout')
async def cb_start_first_workout(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    session = SessionLocal()
    try:
        has_any = session.query(WorkoutMessage).filter_by(user_id=user_id).first() is not None
        # Скасувати відкладений автозапуск — користувач натиснув "Почати зараз"
        u = session.query(User).get(user_id)
        if u and u.start_pending_at is not None:
            u.start_pending_at = None
            session.commit()
    finally:
        session.close()

    if has_any:
        logger.info("Resending six workouts to user_id=%s chat_id=%s via button", user_id, chat_id)
        await send_six_workouts(user_id, chat_id, bot)
    else:
        logger.info("Starting course and sending six workouts to user_id=%s chat_id=%s via button", user_id, chat_id)
        # Спочатку надсилаємо інтро, потім тренування
        await bot.send_message(chat_id, await T('OPEN_COURSE_INTRO'), protect_content=True)
        await asyncio.sleep(10)
        await run_start_open_course(user_id, chat_id, bot, force=True)
    await callback.answer()

